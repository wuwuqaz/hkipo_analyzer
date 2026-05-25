"""Pricing gap analyzer — evaluates where the final offer price sits within the price range."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Optional


@dataclass
class PricingGapResult:
    pricing_position: str
    pricing_pct: float
    score_adjustment: int
    detail: str
    
    def __getitem__(self, key: str):
        return getattr(self, key)


class PricingGapAnalyzer:
    """分析最终定价在招股价区间中的位置。
    
    华泰证券打新模型中，定价价差是5个核心指标之一：
    - 上限定价 → 认购火爆，机构认可
    - 下限定价 → 冷门，破发风险高
    """
    
    def analyze(self, prospectus_info: dict[str, Any]) -> PricingGapResult:
        min_price = self._get_num(prospectus_info, "min_price")
        max_price = self._get_num(prospectus_info, "max_price")
        offer_price = self._get_num(prospectus_info, "offer_price")
        
        if min_price is None or max_price is None or offer_price is None:
            return PricingGapResult(
                pricing_position="缺失",
                pricing_pct=0.0,
                score_adjustment=0,
                detail="缺少价格数据",
            )
        
        if max_price <= 0:
            return PricingGapResult(
                pricing_position="缺失",
                pricing_pct=0.0,
                score_adjustment=0,
                detail="最高价无效",
            )
        
        if abs(max_price - min_price) < 0.001:
            return PricingGapResult(
                pricing_position="固定定价",
                pricing_pct=100.0,
                score_adjustment=0,
                detail="固定定价（无价格区间）",
            )
        
        pricing_pct = (offer_price - min_price) / (max_price - min_price)
        
        position, adjustment = self._classify(pricing_pct)
        
        detail = f"定价位于区间{position}位置({pricing_pct*100:.0f}%)"
        
        return PricingGapResult(
            pricing_position=position,
            pricing_pct=round(pricing_pct * 100, 1),
            score_adjustment=adjustment,
            detail=detail,
        )
    
    def _classify(self, pricing_pct: float) -> tuple[str, int]:
        p = round(pricing_pct, 6)  # Handle floating point precision
        if p >= 0.95:
            return "上限定价", 3
        if p >= 0.70:
            return "中上限", 1
        if p >= 0.40:
            return "中间价", 0
        if p >= 0.15:
            return "中下限", -2
        return "下限定价", -5
    
    @staticmethod
    def _get_num(data: dict[str, Any], key: str) -> Optional[float]:
        val = data.get(key)
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None
