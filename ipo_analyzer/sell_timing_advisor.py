"""Sell timing advisor for Hong Kong IPOs.

Provides data-driven recommendations on when to sell after listing,
based on sector, market heat, and grey market performance.

Based on research from Dongwu Securities and historical HK IPO data:
- Consumer staples: peak at ~14 days (+68% first day, +105% peak)
- Healthcare/biotech: peak at ~14 days (+34% first day, +59% peak)
- Tech: peak at ~7 days
- Traditional: sell on first day
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class SellTimingRecommendation:
    recommended_hold_days: int
    sell_timing_label: str
    confidence: str
    reasoning: str
    detail: str

    def __getitem__(self, key: str):
        return getattr(self, key)
    
    def get(self, key: str, default=None):
        return getattr(self, key, default)


class SellTimingAdvisor:
    """首日卖出时机建议。
    
    基于东吴证券研究和历史港股IPO数据：
    - 必选消费：首日回报68%，14日最高回报105%
    - 医药生物：首日回报34%，14日最高回报59%
    - 科技：7日左右达到阶段性高点
    - 传统行业：首日卖出最优
    
    综合考虑暗盘涨跌幅、超购倍数、基石质量等因子。
    """
    
    SECTOR_HOLD_DAYS = {
        "healthcare": 14,
        "biotech": 14,
        "consumer": 14,
        "tech": 7,
        "internet": 7,
        "semiconductor": 10,
        "new_energy": 7,
        "traditional": 1,
        "real_estate": 1,
        "manufacturing": 3,
        "financial": 3,
        "industrial": 3,
    }
    
    def analyze(
        self,
        sector: Optional[str] = None,
        subsector: Optional[str] = None,
        grey_market_change_pct: Optional[float] = None,
        over_sub_ratio: Optional[float] = None,
        cornerstone_quality: Optional[str] = None,
    ) -> SellTimingRecommendation:
        """分析卖出时机建议。
        
        Args:
            sector: 行业分类
            subsector: 子行业
            grey_market_change_pct: 暗盘涨跌幅
            over_sub_ratio: 超购倍数
            cornerstone_quality: 基石质量
        
        Returns:
            卖出时机建议
        """
        if sector is None and grey_market_change_pct is None and over_sub_ratio is None:
            return SellTimingRecommendation(
                recommended_hold_days=1,
                sell_timing_label="默认建议",
                confidence="低",
                reasoning="数据不足，采用保守默认策略",
                detail="建议首日卖出以锁定收益（数据不足时的默认策略）",
            )
        
        base_days = self._get_base_days(sector, subsector)
        heat_adj = self._heat_adjustment(over_sub_ratio, grey_market_change_pct)
        quality_adj = self._quality_adjustment(cornerstone_quality)
        
        final_days = max(1, min(30, base_days + heat_adj + quality_adj))
        label = self._build_label(final_days)
        confidence = self._calc_confidence(sector, grey_market_change_pct, over_sub_ratio)
        reasoning = self._build_reasoning(sector, base_days, heat_adj, quality_adj, grey_market_change_pct)
        detail = self._build_detail(final_days, label, confidence, grey_market_change_pct)
        
        return SellTimingRecommendation(
            recommended_hold_days=final_days,
            sell_timing_label=label,
            confidence=confidence,
            reasoning=reasoning,
            detail=detail,
        )
    
    def _get_base_days(self, sector: Optional[str], subsector: Optional[str]) -> int:
        """获取行业基础持有天数。"""
        if subsector:
            subsector_lower = subsector.lower()
            if any(kw in subsector_lower for kw in ("biotech", "innovative_drug", "oncology", "gene")):
                return 14
        
        if sector:
            sector_lower = sector.lower()
            for key, days in self.SECTOR_HOLD_DAYS.items():
                if key in sector_lower:
                    return days
        
        return 3
    
    def _heat_adjustment(self, over_sub_ratio: Optional[float], grey_market_change_pct: Optional[float]) -> int:
        """基于市场热度调整持有天数。"""
        adj = 0
        if grey_market_change_pct is not None:
            if grey_market_change_pct > 10:
                adj += 5
            elif grey_market_change_pct > 5:
                adj += 3
            elif grey_market_change_pct > 0:
                adj += 1
            elif grey_market_change_pct < -5:
                adj -= 2
            elif grey_market_change_pct < -10:
                adj -= 3
        
        if over_sub_ratio is not None:
            if over_sub_ratio > 500:
                adj += 3
            elif over_sub_ratio > 100:
                adj += 2
            elif over_sub_ratio > 50:
                adj += 1
        
        return adj
    
    def _quality_adjustment(self, cornerstone_quality: Optional[str]) -> int:
        """基于基石质量调整持有天数。"""
        if cornerstone_quality is None:
            return 0
        quality_upper = cornerstone_quality.upper()
        if quality_upper in ("S", "A"):
            return 3
        if quality_upper == "B":
            return 1
        if quality_upper == "C":
            return -1
        return 0
    
    def _build_label(self, days: int) -> str:
        """构建卖出时机标签。"""
        if days == 1:
            return "首日卖出"
        if days <= 3:
            return "尽早卖出（3日内）"
        if days <= 7:
            return "持有至7日"
        if days <= 14:
            return "持有至14日"
        return "持有至30日"
    
    def _calc_confidence(
        self,
        sector: Optional[str],
        grey_market_change_pct: Optional[float],
        over_sub_ratio: Optional[float],
    ) -> str:
        """计算建议置信度。"""
        score = 0
        if sector:
            score += 1
        if grey_market_change_pct is not None:
            score += 1
        if over_sub_ratio is not None:
            score += 1
        
        if score >= 3:
            return "高"
        if score >= 2:
            return "中高"
        if score >= 1:
            return "中"
        return "低"
    
    def _build_reasoning(
        self,
        sector: Optional[str],
        base_days: int,
        heat_adj: int,
        quality_adj: int,
        grey_market_change_pct: Optional[float],
    ) -> str:
        """构建推理说明。"""
        parts = []
        if sector:
            parts.append(f"行业基础持有{base_days}天")
        if heat_adj != 0:
            sign = "+" if heat_adj > 0 else ""
            parts.append(f"热度调整{sign}{heat_adj}天")
        if quality_adj != 0:
            sign = "+" if quality_adj > 0 else ""
            parts.append(f"基石调整{sign}{quality_adj}天")
        if grey_market_change_pct is not None and abs(grey_market_change_pct) > 5:
            direction = "涨" if grey_market_change_pct > 0 else "跌"
            parts.append(f"暗盘{direction}{abs(grey_market_change_pct):.1f}%")
        return "，".join(parts) if parts else "数据不足，采用保守策略"
    
    def _build_detail(
        self,
        days: int,
        label: str,
        confidence: str,
        grey_market_change_pct: Optional[float],
    ) -> str:
        """构建详细说明。"""
        detail = f"建议{label}（置信度{confidence}）"
        if grey_market_change_pct is not None:
            detail += f"，暗盘涨跌幅{grey_market_change_pct:+.1f}%"
        if days >= 14:
            detail += "。研究显示该行业在14日左右可能达到阶段性高点"
        elif days >= 7:
            detail += "。建议关注7-14日区间的卖出机会"
        elif days >= 3:
            detail += "。建议尽早锁定收益"
        else:
            detail += "。热度不足，建议首日卖出"
        return detail
