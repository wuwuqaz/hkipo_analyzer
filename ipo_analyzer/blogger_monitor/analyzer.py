from __future__ import annotations

import json
import logging
import re
from typing import Optional

import httpx

from .config import BloggerMonitorConfig, load_config
from .models import BloggerOpinionModel, SearchResultModel

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """你是一个港股IPO打新分析专家。请分析以下关于 {company_name}（股票代码：{stock_code}）的文章，提取作者对这只新股的观点。

文章标题：{title}
文章来源：{source}
文章内容：
{content}

请输出 JSON 格式的分析结果，包含以下字段：
{{
  "stock_code": "{stock_code}",
  "company_name": "{company_name}",
  "source": "来源",
  "author": "作者",
  "author_type": "blogger/analyst/media/retail",
  "title": "标题",
  "published_at": "发布日期",
  "stance": "positive/neutral/negative",
  "stance_score": 0-100,
  "apply_suggestion": "积极申购/适量申购/谨慎/不建议",
  "suggested_capital_ratio": "建议资金比例",
  "main_reasons": ["理由1", "理由2"],
  "risk_points": ["风险1", "风险2"],
  "valuation_comment": "估值评价",
  "summary": "一句话总结",
  "confidence_score": 0-100,
  "evidence_quotes": ["原文引用1"],
  "is_actionable": true/false
}}

注意：
- stance_score: 看好>70, 中性30-70, 看空<30
- author_type: blogger(个人博主), analyst(分析师), media(媒体), retail(散户)
- is_actionable: 文章是否包含可操作的申购建议
- 如果文章与该IPO无关，stance 设为 neutral，confidence_score 设为 0"""


class BloggerAnalyzer:
    def __init__(self, config: Optional[BloggerMonitorConfig] = None):
        self.config = config or load_config()

    def analyze(
        self,
        article: SearchResultModel,
        stock_code: str,
        company_name: str,
    ) -> Optional[BloggerOpinionModel]:
        # 优先走 LLM 路径
        prompt = self._build_prompt(article, stock_code, company_name)
        raw = self._call_llm(prompt)
        if raw is not None:
            data = self._parse_json(raw)
            if data is None:
                data = self._repair_json(raw)
            if data is not None:
                result = self._validate_with_pydantic(data)
                if result is not None:
                    return result
            logger.warning("LLM 响应 JSON 解析失败: %s", raw[:200] if raw else "")

        # 回退：关键词情感分析
        return self._keyword_sentiment(article, stock_code, company_name)

    def _build_prompt(
        self,
        article: SearchResultModel,
        stock_code: str,
        company_name: str,
    ) -> str:
        return _PROMPT_TEMPLATE.format(
            company_name=company_name,
            stock_code=stock_code,
            title=article.title,
            source=article.source_domain,
            content=article.content or article.snippet,
        )

    # --- 关键词情感分析（无需 LLM，作为 API key 缺失时的回退）---
    _POSITIVE_KEYWORDS = [
        "看好", "推荐", "建议申购", "积极申购", "建议认购", "值得参与",
        "值得打新", "可申购", "建议参与", "重点关注", "强烈推荐",
        "估值合理", "定价合理", "性价比较高", "值得关注",
    ]
    _NEGATIVE_KEYWORDS = [
        "看空", "不建议", "谨慎参与", "放弃申购", "不参与",
        "风险较大", "风险过高", "定价偏高", "估值偏高",
        "不建议申购", "不建议参与", "观望", "避开",
    ]

    def _keyword_sentiment(self, article: SearchResultModel, stock_code: str, company_name: str) -> Optional[BloggerOpinionModel]:
        content = f"{article.title} {article.snippet or ''} {article.content or ''}"
        if len(content) < 30:
            return None

        pos_hits = [kw for kw in self._POSITIVE_KEYWORDS if kw in content]
        neg_hits = [kw for kw in self._NEGATIVE_KEYWORDS if kw in content]

        pos_score = len(pos_hits)
        neg_score = len(neg_hits)

        if pos_score == 0 and neg_score == 0:
            return self._neutral_fallback(article, stock_code, company_name)

        if pos_score > neg_score:
            stance = "positive"
            stance_score = min(90, 55 + pos_score * 10)
        elif neg_score > pos_score:
            stance = "negative"
            stance_score = max(10, 45 - neg_score * 10)
        else:
            stance = "neutral"
            stance_score = 50

        reasons = pos_hits[:3] if pos_hits else []
        risks = neg_hits[:3] if neg_hits else []

        return BloggerOpinionModel(
            stock_code=stock_code,
            company_name=company_name,
            source=article.source_domain,
            author="",
            author_type="blogger",
            title=article.title,
            published_at=article.published_at,
            stance=stance,
            stance_score=stance_score,
            apply_suggestion="",
            suggested_capital_ratio="",
            main_reasons=reasons,
            risk_points=risks,
            valuation_comment="",
            summary=f"关键词匹配: 正面{pos_score}个, 负面{neg_score}个",
            confidence_score=30,
            evidence_quotes=[],
            is_actionable=bool(pos_score or neg_score),
        )

    def _neutral_fallback(self, article: SearchResultModel, stock_code: str, company_name: str) -> Optional[BloggerOpinionModel]:
        content = f"{article.title} {article.snippet or ''} {article.content or ''}"
        headline = f"{article.title} {article.snippet or ''}"
        if len(content) < 30:
            return None

        has_company = company_name in headline or company_name in content
        has_stock_code = stock_code in headline or stock_code in content
        ipo_hits = [kw for kw in ("IPO", "打新", "招股", "港股", "申购", "新股", "暗盘", "中签") if kw in headline or kw in content]
        if not (has_company or has_stock_code) or not ipo_hits:
            return None

        return BloggerOpinionModel(
            stock_code=stock_code,
            company_name=company_name,
            source=article.source_domain,
            author="",
            author_type="blogger",
            title=article.title,
            published_at=article.published_at,
            stance="neutral",
            stance_score=50,
            apply_suggestion="观望",
            suggested_capital_ratio="",
            main_reasons=ipo_hits[:3],
            risk_points=[],
            valuation_comment="",
            summary="文章与IPO相关，但缺少明确看多看空措辞，按中性观点处理",
            confidence_score=20,
            evidence_quotes=[],
            is_actionable=False,
        )

    # --- LLM 分析 ---

    def _call_llm(self, prompt: str) -> Optional[str]:
        if not self.config.llm_api_key:
            logger.debug("LLM_API_KEY 未配置，使用关键词回退")
            return None

        url = f"{self.config.llm_base_url.rstrip('/')}/chat/completions"
        if not url.startswith("https://"):
            logger.warning("LLM_BASE_URL 不是 HTTPS (%s)，API Key 可能以明文传输", self.config.llm_base_url)
        headers = {
            "Authorization": f"Bearer {self.config.llm_api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.config.llm_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(url, headers=headers, json=body)
                resp.raise_for_status()
        except httpx.HTTPStatusError:
            logger.exception("LLM API 返回错误状态码")
            return None
        except httpx.RequestError:
            logger.exception("LLM API 请求失败")
            return None

        try:
            return resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            logger.exception("LLM API 响应格式异常")
            return None

    def _parse_json(self, text: str) -> Optional[dict]:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        md_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if md_match:
            try:
                return json.loads(md_match.group(1))
            except json.JSONDecodeError:
                pass

        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            try:
                return json.loads(text[first_brace : last_brace + 1])
            except json.JSONDecodeError:
                pass

        return None

    def _repair_json(self, text: str) -> Optional[dict]:
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace == -1 or last_brace <= first_brace:
            return None

        segment = text[first_brace : last_brace + 1]
        segment = re.sub(r",\s*([}\]])", r"\1", segment)
        segment = segment.replace("'", '"')
        segment = re.sub(r"(\w+)\s*:", r'"\1":', segment)
        segment = segment.replace("True", "true").replace("False", "false")
        segment = segment.replace("None", "null")

        try:
            return json.loads(segment)
        except json.JSONDecodeError:
            return None

    def _validate_with_pydantic(self, data: dict) -> Optional[BloggerOpinionModel]:
        try:
            return BloggerOpinionModel(**data)
        except Exception:
            logger.exception("BloggerOpinionModel 校验失败: %s", data)
            return None
