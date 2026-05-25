"""流通盘干涸度分析.

综合分析 Mechanism B、流通盘大小、基石锁定、公开发售比例等因素，
评估新股上市首日流通筹码稀缺度和潜在逼空/抢筹风险。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FloatDrynessResult:
    dryness_label: str = "适中"
    dryness_score: int = 50
    dryness_detail: str = ""
    float_millions: float | None = None
    public_offer_lots: float | None = None
    cornerstone_lockup_pct: float | None = None
    mechanism_b: bool = False
    mechanism_b_detail: str = ""
    squeeze_risk_label: str = "低"
    squeeze_risk_score: int = 0
    squeeze_risk_detail: str = ""
    float_signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dryness_label": self.dryness_label,
            "dryness_score": self.dryness_score,
            "dryness_detail": self.dryness_detail,
            "float_millions": self.float_millions,
            "public_offer_lots": self.public_offer_lots,
            "cornerstone_lockup_pct": self.cornerstone_lockup_pct,
            "mechanism_b": self.mechanism_b,
            "mechanism_b_detail": self.mechanism_b_detail,
            "squeeze_risk_label": self.squeeze_risk_label,
            "squeeze_risk_score": self.squeeze_risk_score,
            "squeeze_risk_detail": self.squeeze_risk_detail,
            "float_signals": self.float_signals,
        }


def _detect_mechanism_b(prospectus_info: dict, text: str = "") -> tuple[bool, str]:
    """检测是否使用 Mechanism B（18A 生物科技公司可下调公开发售至 5%）。"""
    lower_text = (text or "").lower()

    # 直接检测 Mechanism B 关键词
    b_keywords = [
        "mechanism b",
        "public offer shares may be reduced to 5%",
        "public offering to be reduced",
        "public offer is 5%",
        "public offer ratio of 5%",
        "公开发售可降至",
        "公开发售占5%",
        "公开发售5%",
    ]
    for kw in b_keywords:
        if kw in lower_text:
            return True, f"招股书明确提及 {kw}"

    # 间接检测：18A + 极低的公开发售比例（<= 5%）
    sector = prospectus_info.get("sector", "").lower()
    public_ratio = prospectus_info.get("public_offer_ratio_pct")
    if sector == "healthcare" and public_ratio is not None:
        if 4.0 <= public_ratio <= 6.0:
            return True, f"18A 生物科技公司 + 公开发售比例 {public_ratio:.1f}%（典型 Mechanism B 特征）"

    return False, ""


def _calculate_float_millions(prospectus_info: dict) -> float | None:
    """计算流通盘市值（亿港元）= 总市值 * 流通比例。"""
    # 支持多种字段名：market_cap_hkd (百万港元) / market_cap_hkd_million (百万港元)
    market_cap_hkd = prospectus_info.get("market_cap_hkd") or prospectus_info.get("market_cap_hkd_million")
    if market_cap_hkd is None:
        return None

    cornerstone_pct = prospectus_info.get("cornerstone_pct") or prospectus_info.get("cornerstone_offer_ratio_pct") or 0
    public_ratio = prospectus_info.get("public_offer_ratio_pct") or 0
    # 流通比例 = 公开发售 + (1 - 基石 - 公开发售) * 50%（假设非基石非公开发售部分约50%流通）
    free_float_ratio = public_ratio / 100 + (1 - cornerstone_pct / 100 - public_ratio / 100) * 0.5

    return round(market_cap_hkd * free_float_ratio / 10000, 2)


def _label_from_dryness(score: int) -> str:
    if score >= 80:
        return "极干"
    if score >= 60:
        return "干"
    if score >= 40:
        return "适中"
    if score >= 20:
        return "充裕"
    return "极充裕"


def _label_from_squeeze(score: int) -> str:
    if score >= 80:
        return "极高"
    if score >= 60:
        return "高"
    if score >= 40:
        return "中"
    if score >= 20:
        return "低"
    return "极低"


class FloatDrynessAnalyzer:
    """流通盘干涸度分析器。"""

    def analyze(self, prospectus_info: dict, text: str = "", ipo_data: dict = None) -> dict[str, Any]:
        # 防御性处理
        if isinstance(text, dict):
            text = ""
        if ipo_data is None:
            ipo_data = {}

        dryness_score = 50
        squeeze_score = 0
        signals: list[str] = []

        # 1. Mechanism B 检测
        mech_b, mech_b_detail = _detect_mechanism_b(prospectus_info, text)
        if mech_b:
            dryness_score += 20
            squeeze_score += 15
            signals.append(f" 使用 Mechanism B：{mech_b_detail}")

        # 2. 流通盘市值分析
        float_millions = _calculate_float_millions(prospectus_info)
        if float_millions is not None:
            if float_millions < 1:
                dryness_score += 25
                squeeze_score += 20
                signals.append(f"💀 流通盘极小：仅 {float_millions:.1f} 亿港元")
            elif float_millions < 3:
                dryness_score += 15
                squeeze_score += 10
                signals.append(f"⚠️ 流通盘小：{float_millions:.1f} 亿港元")
            elif float_millions < 5:
                dryness_score += 5
                signals.append(f"流通盘适中：{float_millions:.1f} 亿港元")

        # 3. 基石锁定比例
        cornerstone_pct = ipo_data.get("cornerstone_pct") or prospectus_info.get("cornerstone_pct")
        if cornerstone_pct is not None:
            if cornerstone_pct >= 50:
                dryness_score += 15
                squeeze_score += 10
                signals.append(f"🔒 基石锁定高：{cornerstone_pct:.1f}%")
            elif cornerstone_pct >= 30:
                dryness_score += 5
                signals.append(f"基石锁定适中：{cornerstone_pct:.1f}%")

        # 4. 公开发售手数
        public_lots = ipo_data.get("public_offer_lots") or prospectus_info.get("public_offer_lots")
        if public_lots is not None:
            if public_lots < 500:
                dryness_score += 15
                squeeze_score += 15
                signals.append(f" 公开发售仅 {int(public_lots)} 手，散户没货！")
            elif public_lots < 1000:
                dryness_score += 8
                squeeze_score += 5
                signals.append(f"公开发售 {int(public_lots)} 手，流通偏紧")

        # 5. 总市值
        market_cap = ipo_data.get("market_cap_hkd") or prospectus_info.get("market_cap_hkd")
        if market_cap is not None:
            if market_cap < 2000:
                dryness_score += 5
                signals.append(f"总市值 {market_cap:.0f} 百万港元，小盘特征")

        # Clamp scores
        dryness_score = max(0, min(100, dryness_score))
        squeeze_score = max(0, min(100, squeeze_score))

        # Build detail
        detail_parts = []
        if float_millions is not None:
            detail_parts.append(f"流通盘约 {float_millions:.1f} 亿港元")
        if cornerstone_pct is not None:
            detail_parts.append(f"基石锁定 {cornerstone_pct:.1f}%")
        if public_lots is not None:
            detail_parts.append(f"公开发售 {int(public_lots)} 手")
        if mech_b:
            detail_parts.append("Mechanism B")

        result = FloatDrynessResult(
            dryness_label=_label_from_dryness(dryness_score),
            dryness_score=dryness_score,
            dryness_detail="；".join(detail_parts) if detail_parts else "数据不足",
            float_millions=float_millions,
            public_offer_lots=public_lots,
            cornerstone_lockup_pct=cornerstone_pct,
            mechanism_b=mech_b,
            mechanism_b_detail=mech_b_detail,
            squeeze_risk_label=_label_from_squeeze(squeeze_score),
            squeeze_risk_score=squeeze_score,
            squeeze_risk_detail=self._build_squeeze_detail(squeeze_score, signals),
            float_signals=signals,
        )

        return result.to_dict()

    @staticmethod
    def _build_squeeze_detail(score: int, signals: list[str]) -> str:
        if score >= 80:
            return "⚡ 极干流通盘 + 高基石锁定 + 低公开发售 = 上市首日极易引发抢筹逼空"
        if score >= 60:
            return "️ 流通筹码稀缺，机构抢筹可能推高首日涨幅"
        if score >= 40:
            return "流通筹码适中，需关注市场情绪"
        return "流通筹码充裕，逼空风险较低"
