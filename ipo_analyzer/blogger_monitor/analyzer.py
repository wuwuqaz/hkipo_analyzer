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
        prompt = self._build_prompt(article, stock_code, company_name)
        raw = self._call_llm(prompt)
        if raw is None:
            return None

        data = self._parse_json(raw)
        if data is None:
            data = self._repair_json(raw)
        if data is None:
            logger.warning("LLM 响应 JSON 解析失败: %s", raw[:200])
            return None

        return self._validate_with_pydantic(data)

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

    def _call_llm(self, prompt: str) -> Optional[str]:
        if not self.config.llm_api_key:
            logger.warning("LLM_API_KEY 未配置，跳过 LLM 分析")
            return None

        url = f"{self.config.llm_base_url.rstrip('/')}/chat/completions"
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
