"""配售结果公告提取器 — 从 HKEX 配发公告文本提取关键数据"""
from __future__ import annotations

import re
from typing import Optional

from ipo_analyzer.backtest.ipo_models import AllotmentExtractionResult

logger = __import__("logging").getLogger(__name__)

_OFFER_PRICE_RE = [
    re.compile(r"(?:發售價|发售价).*?([\d.]+)", re.IGNORECASE),
    re.compile(r"(?:final\s*)?offer\s*price.*?([\d.]+)", re.IGNORECASE),
    re.compile(r"([\d.]+)\s*港元", re.IGNORECASE),
]

_SUBSCRIPTION_MULTIPLE_RE = [
    re.compile(r"超購.*?([\d.]+)\s*倍", re.IGNORECASE),
    re.compile(r"超购.*?([\d.]+)\s*倍", re.IGNORECASE),
    re.compile(r"(?:over.?subscri|excess.*?appli).*?([\d.]+)", re.IGNORECASE),
    re.compile(r"subscription\s*(?:level|multiple).*?([\d.]+)", re.IGNORECASE),
]

_ONE_LOT_RATE_RE = [
    re.compile(r"一手中籤率.*?([\d.]+)\s*%", re.IGNORECASE),
    re.compile(r"一手中签率.*?([\d.]+)\s*%", re.IGNORECASE),
    re.compile(r"one[\s-]*lot\s*(?:success\s*)?rate.*?([\d.]+)\s*%", re.IGNORECASE),
]

_CLAWBACK_RE = [
    re.compile(r"回撥.*?([\d.]+)\s*%", re.IGNORECASE),
    re.compile(r"回拨.*?([\d.]+)\s*%", re.IGNORECASE),
    re.compile(r"clawback.*?([\d.]+)\s*%", re.IGNORECASE),
]


def _extract_first_float(text: str, patterns: list[re.Pattern]) -> Optional[float]:
    for pat in patterns:
        m = pat.search(text)
        if m:
            try:
                return float(m.group(1))
            except (ValueError, IndexError):
                continue
    return None


def extract_allotment_result(text: str) -> AllotmentExtractionResult:
    """从配售结果公告文本提取关键字段。

    无法可靠提取的字段返回 None。
    """
    if not text or len(text) < 50:
        return AllotmentExtractionResult()

    snippets: list[str] = []
    final_price = _extract_first_float(text, _OFFER_PRICE_RE)
    sub_multiple = _extract_first_float(text, _SUBSCRIPTION_MULTIPLE_RE)
    one_lot_rate = _extract_first_float(text, _ONE_LOT_RATE_RE)
    clawback = _extract_first_float(text, _CLAWBACK_RE)

    if final_price is not None:
        snippets.append(f"final_offer_price={final_price}")
    if sub_multiple is not None:
        snippets.append(f"subscription_multiple={sub_multiple}")
    if one_lot_rate is not None:
        one_lot_rate = one_lot_rate / 100.0 if one_lot_rate > 1 else one_lot_rate
        snippets.append(f"one_lot_rate={one_lot_rate}")
    if clawback is not None:
        clawback = clawback / 100.0 if clawback > 1 else clawback
        snippets.append(f"clawback_ratio={clawback}")

    return AllotmentExtractionResult(
        final_offer_price=final_price,
        public_subscription_multiple=sub_multiple,
        one_lot_success_rate=one_lot_rate,
        clawback_ratio=clawback,
        raw_text_snippets=snippets,
    )
