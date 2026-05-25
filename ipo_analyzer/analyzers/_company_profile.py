"""公司简介提取分析器 — 从招股书PDF文本中提取公司介绍摘要和结构化标签。

港股招股书标准结构中，"业务"章节（BUSINESS / 我们的业务）通常位于前半部分，
包含公司主营业务、市场地位、核心产品等关键信息。
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

import httpx

from ..models import CompanyProfileResult
from ..utils import _is_num

logger = logging.getLogger(__name__)

_BUSINESS_SECTION_RE = re.compile(
    r'(?:^|\n)\s*(?:BUSINESS|Our\s+Business|Business\s+Overview|业务|業務|我们的业务|我們的業務'
    r'|OVERVIEW|公司概览|公司概覽|集团概览|集團概覽|我们是谁|我們是誰|Who\s+We\s+Are)'
    r'[\s\x00-\x1f]*\n',
    re.IGNORECASE,
)

_BUSINESS_PRIORITY_RE = re.compile(
    r'(我们是谁|我們是誰|Who\s+We\s+Are|Business\s+Overview|Our\s+Business)',
    re.IGNORECASE,
)

_SUMMARY_STOP_RE = re.compile(
    r'(?:^|\n)\s*(?:RISK|风险|風險|FINANCIAL\s+(?:INFORMATION|STATEMENTS|CONDITION|DATA)'
    r'|FINANCIAL[^.a-z]*$|财务(?:资料|报表|状况|数据)|財務(?:資料|報表|狀況|數據)'
    r'|LEGAL|法律|REGULATORY|监管|監管|DIRECTORS|董事|INDEPENDENT\s+AUDITOR)',
    re.IGNORECASE,
)

_CONTROL_CHAR_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')

_MULTI_SPACE_RE = re.compile(r' {2,}')

_MARKET_POSITION_RE = re.compile(
    r'(?:leading|leader|first|largest|top|biggest|No\.\s*1|ranked\s+(?:first|No\.?\s*1|top)'
    r'|领先|第一|最大|首位|龙头|top\s*\d|排名(?:第一|首位|第一))',
    re.IGNORECASE,
)

_FOUNDED_RE = re.compile(
    r'(?:founded|established|incorporated|formed|set\s+up)\s+(?:in\s+)?'
    r'(?:the\s+year\s+of\s+)?(\d{4})'
    r'|成立于(\d{4})年?'
    r'|(\d{4})年成立'
    r'|incorporated\s+(?:in|on)\s+(?:\w+\s+)?(\d{4})',
    re.IGNORECASE,
)

_HEADQUARTERS_RE = re.compile(
    r'(?:headquarter(?:ed|s)?|head\s+office|principal\s+office|based\s+in)\s+(?:is\s+)?(?:located\s+)?(?:in\s+)?'
    r'([\w\s]+?(?:China|Hong Kong|Shanghai|Beijing|Shenzhen|Hangzhou|Suzhou|Guangzhou|Nanjing|Chengdu|Wuhan))'
    r'|总部[位于在]([\w]+)',
    re.IGNORECASE,
)

_MAX_SUMMARY_CHARS = 2000

_MAX_LLM_INPUT_CHARS = 3000

_LLM_SYSTEM_PROMPT = """你是港股IPO分析师，只负责把招股书业务描述压缩成结构化公司简介。
必须只输出三行，不要标题、前言、解释、Markdown、编号或空行。"""

_LLM_SUMMARY_PROMPT = """请用中文提炼以下公司业务描述，严格输出三行：

做什么：[一句话描述公司核心产品/服务品类]
卖给谁：[目标客户行业/类型，说明B2B还是B2C]
怎么赚钱：[商业模式关键词，如SaaS订阅、项目制、直销、分销、耗材销售等]

如果原文没有证据，请写“未披露”，不要编造。

以下是招股书业务章节摘要：
{business_text}"""

_LLM_LABELS = ("做什么", "卖给谁", "怎么赚钱")


class CompanyProfileAnalyzer:
    """公司简介提取分析器"""

    @staticmethod
    def analyze(prospectus_info: dict) -> CompanyProfileResult:
        """从招股书文本中提取公司简介。"""
        result = CompanyProfileResult()

        text = prospectus_info.get('_extracted_text', '') or ''
        if not text:
            result.confidence = "missing"
            return result

        business_raw_text = CompanyProfileAnalyzer._get_business_raw_text(text)

        llm_summary = CompanyProfileAnalyzer._summarize_with_llm(business_raw_text)
        if llm_summary:
            result.company_summary = llm_summary
            result.confidence = "high"
        else:
            summary = CompanyProfileAnalyzer._extract_business_summary(text)
            result.company_summary = summary

        result.industry = CompanyProfileAnalyzer._get_industry(prospectus_info)
        result.main_business = CompanyProfileAnalyzer._get_main_business(prospectus_info)
        result.market_position = CompanyProfileAnalyzer._get_market_position(result.company_summary, prospectus_info)
        result.key_products = CompanyProfileAnalyzer._get_key_products(prospectus_info)
        result.geographic_focus = CompanyProfileAnalyzer._get_geographic_focus(prospectus_info)

        founded = CompanyProfileAnalyzer._extract_founded_year(text)
        if founded:
            result.founded_year = founded

        hq = CompanyProfileAnalyzer._extract_headquarters(text)
        if hq:
            result.headquarters = hq

        tags = CompanyProfileAnalyzer._extract_business_tags(prospectus_info)
        result.business_model = tags.get('business_model', '')
        result.customer_type = tags.get('customer_type', '')
        result.customer_industries = tags.get('customer_industries', '')
        result.revenue_scale = tags.get('revenue_scale', '')

        if not llm_summary:
            summary_for_confidence = result.company_summary
            data_points = sum([
                bool(summary_for_confidence),
                bool(result.industry),
                bool(result.main_business),
                bool(result.market_position),
                bool(result.key_products),
                bool(result.geographic_focus),
                result.founded_year is not None,
                bool(result.headquarters),
            ])
            if data_points >= 6:
                result.confidence = "high"
            elif data_points >= 4:
                result.confidence = "medium"
            elif data_points >= 2:
                result.confidence = "low"
            else:
                result.confidence = "missing"

        return result

    @staticmethod
    def _get_business_raw_text(text: str) -> str:
        """提取业务章节原始文本（最多3000字符），用于LLM输入。"""
        start = CompanyProfileAnalyzer._find_business_section_start(text)
        if start is None:
            return CompanyProfileAnalyzer._clean_text(text[:_MAX_LLM_INPUT_CHARS])

        remaining = text[start:start + _MAX_LLM_INPUT_CHARS + 2000]

        stop_match = _SUMMARY_STOP_RE.search(remaining)
        if stop_match:
            remaining = remaining[:stop_match.start()]

        cleaned = CompanyProfileAnalyzer._clean_text(remaining)
        if len(cleaned) > _MAX_LLM_INPUT_CHARS:
            cleaned = cleaned[:_MAX_LLM_INPUT_CHARS]

        return cleaned

    @staticmethod
    def _find_business_section_start(text: str) -> Optional[int]:
        """定位业务正文起点，避开目录中的章节标题。"""
        for match in _BUSINESS_PRIORITY_RE.finditer(text):
            after = text[match.end():match.end() + 1200]
            if not CompanyProfileAnalyzer._looks_like_toc_fragment(after):
                return match.end()

        for match in _BUSINESS_SECTION_RE.finditer(text):
            after = text[match.end():match.end() + 1200]
            if not CompanyProfileAnalyzer._looks_like_toc_fragment(after):
                return match.end()

        return None

    @staticmethod
    def _looks_like_toc_fragment(fragment: str) -> bool:
        """判断标题后是否仍在目录/页码区域。"""
        head = fragment[:800]
        dot_count = head.count(".")
        if dot_count >= 20:
            return True
        if re.search(r'\.{3,}\s*\d{1,4}', head):
            return True
        if "目  錄" in head or "目錄" in head or "CONTENTS" in head.upper():
            return True
        return False

    @staticmethod
    def _clean_text(text: str) -> str:
        """清洗PDF提取文本中的控制字符和多余空格。"""
        text = _CONTROL_CHAR_RE.sub(' ', text)
        text = _MULTI_SPACE_RE.sub(' ', text)
        return text.strip()

    @staticmethod
    def _extract_business_summary(text: str) -> str:
        """从招股书文本中提取'业务'章节的前几段作为公司摘要。"""
        match = _BUSINESS_SECTION_RE.search(text)
        if not match:
            first_500 = CompanyProfileAnalyzer._clean_text(text[:2000])
            if len(first_500) > 100:
                sentences = re.split(r'[.。!！?？]\s*', first_500)
                summary = '. '.join(sentences[:3])
                if len(summary) > _MAX_SUMMARY_CHARS:
                    summary = summary[:_MAX_SUMMARY_CHARS] + '...'
                return summary
            return ""

        start = match.end()
        remaining = text[start:start + 5000]

        stop_match = _SUMMARY_STOP_RE.search(remaining)
        if stop_match:
            remaining = remaining[:stop_match.start()]

        # PDF extraction splits text into short lines; merge back into flowing text
        cleaned = CompanyProfileAnalyzer._clean_text(remaining)
        # Replace line breaks with spaces to merge PDF-split lines into continuous text
        merged = re.sub(r'\n+', ' ', cleaned)
        # Collapse resulting multi-spaces
        merged = _MULTI_SPACE_RE.sub(' ', merged).strip()

        if not merged or len(merged) < 20:
            return ""

        if len(merged) <= _MAX_SUMMARY_CHARS:
            return merged

        # Truncate at a sentence boundary near _MAX_SUMMARY_CHARS
        truncated = merged[:_MAX_SUMMARY_CHARS]
        last_period = max(truncated.rfind('。'), truncated.rfind('. '), truncated.rfind('；'))
        if last_period > _MAX_SUMMARY_CHARS // 2:
            return truncated[:last_period + 1]
        return truncated.rstrip() + '...'

    @staticmethod
    def _summarize_with_llm(business_text: str) -> Optional[str]:
        """调用LLM生成三段式公司业务总结。"""
        api_key = os.environ.get('LLM_API_KEY', '')
        if not api_key:
            return None

        base_url = os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
        model = os.environ.get('LLM_MODEL', 'gpt-4o-mini')

        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": _LLM_SYSTEM_PROMPT},
                {"role": "user", "content": _LLM_SUMMARY_PROMPT.format(business_text=business_text)},
            ],
            "temperature": 0.1,
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, headers=headers, json=body)
                resp.raise_for_status()
        except (httpx.HTTPStatusError, httpx.RequestError):
            logger.debug("LLM summarization API call failed")
            return None

        try:
            content = resp.json()["choices"][0]["message"]["content"]
            return CompanyProfileAnalyzer._normalize_llm_summary(content)
        except (KeyError, IndexError, TypeError, ValueError):
            logger.debug("LLM summarization response parse failed")
            return None

    @staticmethod
    def _normalize_llm_summary(content: str) -> Optional[str]:
        """把不同模型的回复统一成三行标签格式，过滤前言和解释。"""
        if not content:
            return None

        text = CompanyProfileAnalyzer._clean_text(str(content).replace("\r\n", "\n").replace("\r", "\n"))
        if not text:
            return None

        segments = {}
        label_pattern = re.compile(r'(做什么|卖给谁|怎么赚钱)\s*[：:]\s*')
        matches = list(label_pattern.finditer(text))
        if matches:
            for idx, match in enumerate(matches):
                label = match.group(1)
                start = match.end()
                end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
                value = text[start:end].strip()
                value = re.sub(r'^[\s\-*•\d.、）)]+', '', value).strip()
                value = re.sub(r'\n+', ' ', value).strip()
                if value:
                    segments[label] = value
        else:
            lines = [
                re.sub(r'^[\s\-*•\d.、）)]+', '', line).strip()
                for line in text.split("\n")
            ]
            lines = [
                line for line in lines
                if line and not re.match(r'^以下.*(?:三段|格式|提炼|描述)', line)
            ]
            if len(lines) < 3:
                paragraphs = [
                    p.strip()
                    for p in re.split(r'\n\s*\n|(?<=[。.!?？])\s+(?=公司|其|主要|通过)', text)
                    if p.strip()
                ]
                lines = [
                    p for p in paragraphs
                    if not re.match(r'^以下.*(?:三段|格式|提炼|描述)', p)
                ]
            if len(lines) >= 3:
                for label, value in zip(_LLM_LABELS, lines[:3]):
                    segments[label] = value

        # 至少需要 2/3 标签，允许 LLM 遗漏一个维度
        present = [label for label in _LLM_LABELS if segments.get(label)]
        if len(present) < 2:
            return None

        normalized_lines = []
        for label in _LLM_LABELS:
            value = segments.get(label)
            if not value:
                normalized_lines.append(f"{label}：未披露")
                continue
            value = re.sub(r'\s+', ' ', value).strip()
            value = re.sub(r'[。.;；\s]+$', '', value)
            normalized_lines.append(f"{label}：{value}")

        return "\n".join(normalized_lines)

    @staticmethod
    def _get_industry(prospectus_info: dict) -> str:
        sector = prospectus_info.get('sector', '')
        if sector and sector != 'unknown':
            sector_map = {
                'biotech': '生物科技',
                'healthcare': '医疗健康',
                'technology': '科技',
                'hardtech': '硬科技',
                'consumer': '消费',
                'retail': '零售',
                'financial': '金融',
                'industrial': '工业制造',
                'real_estate': '房地产',
                'energy': '能源',
            }
            return sector_map.get(sector, sector)
        return ""

    @staticmethod
    def _get_main_business(prospectus_info: dict) -> str:
        business = prospectus_info.get('business_breakdown', {}) or {}
        label = business.get('business_model_label', '')
        if label:
            return label
        segments = business.get('segments', [])
        if segments and isinstance(segments, list):
            names = [s.get('name', '') for s in segments[:3] if isinstance(s, dict) and s.get('name')]
            return '、'.join(names)
        return ""

    @staticmethod
    def _get_market_position(summary: str, prospectus_info: dict) -> str:
        peer = prospectus_info.get('peer_comparison', {}) or {}
        scarcity = peer.get('scarcity_score', 0)
        if _is_num(scarcity) and scarcity >= 7:
            return "赛道稀缺龙头"
        if _is_num(scarcity) and scarcity >= 4:
            return "细分赛道领先"

        if summary and _MARKET_POSITION_RE.search(summary):
            positions = _MARKET_POSITION_RE.findall(summary)
            if positions:
                return "市场领先者"

        dominant = peer.get('dominant_share_pct')
        if _is_num(dominant) and dominant >= 20:
            return f"市场份额领先({dominant:.0f}%)"

        return ""

    @staticmethod
    def _get_key_products(prospectus_info: dict) -> list[str]:
        products = []
        rnd = prospectus_info.get('rnd_pipeline', {}) or {}
        pipelines = rnd.get('pipeline_products', [])
        if pipelines and isinstance(pipelines, list):
            for p in pipelines[:3]:
                if isinstance(p, dict):
                    name = p.get('name', '') or p.get('product_name', '')
                    if name:
                        products.append(name)
                elif isinstance(p, str):
                    products.append(p)

        if not products:
            business = prospectus_info.get('business_breakdown', {}) or {}
            segments = business.get('segments', [])
            if segments and isinstance(segments, list):
                for s in segments[:3]:
                    if isinstance(s, dict):
                        name = s.get('name', '')
                        if name:
                            products.append(name)

        return products[:5]

    @staticmethod
    def _get_geographic_focus(prospectus_info: dict) -> str:
        geo = prospectus_info.get('geographic', {}) or {}
        if isinstance(geo, dict):
            label = geo.get('expansion_label', '')
            if label:
                return label
            regions = geo.get('regions', [])
            if regions and isinstance(regions, list):
                names = []
                for r in regions[:3]:
                    if isinstance(r, dict):
                        names.append(r.get('name', ''))
                    elif isinstance(r, str):
                        names.append(r)
                return '、'.join(n for n in names if n)
        return ""

    @staticmethod
    def _extract_founded_year(text: str) -> int | None:
        search_text = text[:30000]
        match = _FOUNDED_RE.search(search_text)
        if match:
            for group in match.groups():
                if group and group.isdigit():
                    year = int(group)
                    if 1980 <= year <= 2026:
                        return year
        return None

    @staticmethod
    def _extract_headquarters(text: str) -> str:
        search_text = text[:30000]
        match = _HEADQUARTERS_RE.search(search_text)
        if match:
            for group in match.groups():
                if group:
                    cleaned = group.strip()
                    cleaned = re.sub(r'^(?:in|at|on)\s+', '', cleaned, flags=re.IGNORECASE)
                    return cleaned
        return ""

    @staticmethod
    def _extract_business_tags(prospectus_info: dict) -> dict:
        """从现有分析结果中提取业务标签。"""
        tags = {
            'business_model': '',
            'customer_type': '',
            'customer_industries': '',
            'revenue_scale': '',
        }

        business_breakdown = prospectus_info.get('business_breakdown', {}) or {}
        tags['business_model'] = business_breakdown.get('business_model_label', '')

        customer_supplier = prospectus_info.get('customer_supplier', {}) or {}
        customer_type_label = customer_supplier.get('customer_type_label', '')
        if customer_type_label:
            tags['customer_type'] = customer_type_label
        else:
            if customer_supplier.get('largest_customer_revenue_pct') is not None:
                tags['customer_type'] = 'B2B-企业客户'
            consumer_ratio = customer_supplier.get('consumer_ratio')
            if consumer_ratio is not None and consumer_ratio > 0.5:
                tags['customer_type'] = 'B2C-消费者'

        customer_industries = customer_supplier.get('customer_industries', [])
        if not customer_industries:
            customer_industries = customer_supplier.get('industry_distribution', [])
        if customer_industries and isinstance(customer_industries, list):
            names = []
            for item in customer_industries[:3]:
                if isinstance(item, dict):
                    name = item.get('name', '') or item.get('industry', '')
                    if name:
                        names.append(name)
                elif isinstance(item, str):
                    names.append(item)
            if names:
                tags['customer_industries'] = '、'.join(names)

        revenue = prospectus_info.get('revenue')
        if revenue is not None:
            revenue_year = prospectus_info.get('revenue_year')
            value_yi = revenue / 100
            if revenue_year is not None:
                tags['revenue_scale'] = f"{revenue_year}年营收 {value_yi:.1f}亿 RMB"
            else:
                tags['revenue_scale'] = f"营收 {value_yi:.1f}亿 RMB"

        return tags
