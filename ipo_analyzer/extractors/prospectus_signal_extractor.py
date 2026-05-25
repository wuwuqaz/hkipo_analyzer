"""招股书信号提取器 — 从招股书文本提取绿鞋、保荐人、基石投资者等信号"""
from __future__ import annotations

import re
from typing import Optional

from ipo_analyzer.backtest.ipo_models import ProspectusSignalResult

logger = __import__("logging").getLogger(__name__)

_GREENSHOE_YES_RE = [
    re.compile(r"超额配股|超額配股|over.allotment|greenshoe", re.IGNORECASE),
    re.compile(r"稳价操作|穩價操作|price\s*stabiliz", re.IGNORECASE),
]
_GREENSHOE_NO_RE = [
    re.compile(r"无.*超额配股|沒有.*超額配股|no.*over.allotment", re.IGNORECASE),
    re.compile(r"不.*设.*超额配股|不.*設.*超額配股", re.IGNORECASE),
]

_SPONSOR_RE = [
    re.compile(r"保薦人[:：]\s*([^\n,，;；]{2,40})"),
    re.compile(r"保荐人[:：]\s*([^\n,，;；]{2,40})"),
    re.compile(r"sponsor[s]?[:：]\s*([^\n,，;；]{2,40})", re.IGNORECASE),
    re.compile(r"([^\s]{2,20}(?:证券|證券|資本|资本|partners|capital))担任保薦", re.IGNORECASE),
    re.compile(r"([^\s]{2,20}(?:证券|證券|資本|资本|partners|capital))担任保荐", re.IGNORECASE),
]

_CORNERSTONE_RE = [
    re.compile(r"基石投資者[:：]?\s*([^\n]{10,200})"),
    re.compile(r"基石投资者[:：]?\s*([^\n]{10,200})"),
    re.compile(r"cornerstone\s*investor[s]?[:：]?\s*([^\n]{10,200})", re.IGNORECASE),
]

_CORNERSTONE_AMOUNT_RE = [
    re.compile(r"([\d.]+)\s*(?:百万|百萬|million).*?基石", re.IGNORECASE),
    re.compile(r"基石.*?([\d.]+)\s*(?:百万|百萬|million)", re.IGNORECASE),
    re.compile(r"认购.*?([\d.]+)\s*(?:百万|百萬|million)", re.IGNORECASE),
]

_RELATED_KEYWORDS = [
    "关联方", "關聯方", "关连", "關連", "related party", "connected",
    "控股股东", "控股股東", "controlling shareholder", "executive director",
    "执行董事", "執行董事", "subsidiary", "附属公司", "附屬公司",
    "same group", "同一集团", "同一集團",
]

_INDEPENDENT_KEYWORDS = [
    "独立第三方", "獨立第三方", "independent third party",
    "in place cornerstone", "placee", "independent of",
]


def _detect_greenshoe(text: str) -> Optional[bool]:
    for pat in _GREENSHOE_NO_RE:
        if pat.search(text):
            return False
    for pat in _GREENSHOE_YES_RE:
        if pat.search(text):
            return True
    return None


def _extract_sponsors(text: str) -> list[str]:
    sponsors = []
    for pat in _SPONSOR_RE:
        for m in pat.finditer(text):
            name = m.group(1).strip().rstrip("，,;；。.")
            if 2 <= len(name) <= 40 and name not in sponsors:
                sponsors.append(name)
    return sponsors[:5]


def _extract_cornerstones(text: str) -> list[str]:
    investors = []
    for pat in _CORNERSTONE_RE:
        for m in pat.finditer(text):
            block = m.group(1)
            parts = re.split(r"[,，;；、\n]", block)
            for p in parts:
                name = p.strip().rstrip("。.")
                if 2 <= len(name) <= 60:
                    if not any(kw in name.lower() for kw in ["table", "表格", "以下"]):
                        investors.append(name)
    return list(dict.fromkeys(investors))[:20]


def _extract_cornerstone_amount(text: str) -> Optional[float]:
    for pat in _CORNERSTONE_AMOUNT_RE:
        m = pat.search(text)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                continue
    return None


def _assess_independence(text: str, cornerstones: list[str]) -> Optional[str]:
    if not cornerstones:
        return None

    has_related = any(
        kw.lower() in text.lower() for kw in _RELATED_KEYWORDS
    )
    has_independent = any(
        kw.lower() in text.lower() for kw in _INDEPENDENT_KEYWORDS
    )

    if has_related and has_independent:
        return "mixed"
    if has_related:
        return "related"
    if has_independent:
        return "independent"
    return "unknown"


def _detect_related_support(text: str) -> bool:
    support_keywords = [
        r"知名.*?投资者", r"知名.*?機構", r"famous.*?investor",
        r"明星.*?基金", r"star.*?fund",
    ]
    for kw in support_keywords:
        if re.search(kw, text, re.IGNORECASE):
            return True
    return False


def extract_prospectus_signals(text: str) -> ProspectusSignalResult:
    """从招股书文本提取信号。

    基石独立性只用明确规则判断，无法判断则 None。
    """
    if not text or len(text) < 5:
        return ProspectusSignalResult()

    has_greenshoe = _detect_greenshoe(text)
    sponsors = _extract_sponsors(text)
    cornerstones = _extract_cornerstones(text)
    amount = _extract_cornerstone_amount(text)
    independence = _assess_independence(text, cornerstones)
    has_related = _detect_related_support(text)

    snippets = []
    if has_greenshoe is not None:
        snippets.append(f"greenshoe={has_greenshoe}")
    if sponsors:
        snippets.append(f"sponsors={sponsors}")
    if cornerstones:
        snippets.append(f"cornerstones_count={len(cornerstones)}")

    return ProspectusSignalResult(
        has_greenshoe=has_greenshoe,
        sponsors=sponsors,
        cornerstone_investors=cornerstones,
        cornerstone_amount_hkd_million=amount,
        cornerstone_independence=independence,
        has_related_support=has_related,
        raw_text_snippets=snippets,
    )
