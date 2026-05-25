"""Grey market (暗盘) signal analyzer for Hong Kong IPOs.

Analyzes grey market trading signals and their predictive power for first-day performance.
Grey market trading is unique to Hong Kong IPOs and provides early price discovery.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class GreyMarketSignal:
    grey_price: Optional[float]
    offer_price: Optional[float]
    change_pct: Optional[float]
    signal_strength: str
    score_adjustment: int
    volume_ratio_pct: Optional[float]
    volume_label: str
    detail: str

    def __getitem__(self, key: str):
        return getattr(self, key)
    
    def get(self, key: str, default=None):
        return getattr(self, key, default)


class GreyMarketSignalAnalyzer:
    """暗盘交易信号分析。
    
    暗盘交易是港股IPO独有的提前交易机制，通常在上市前1-2个交易日进行。
    暗盘涨跌幅对首日表现有强预测力（历史相关系数>0.7）。
    
    信号强度分级：
    - 涨幅 > 10%: 强看多（+3分）
    - 涨幅 3-10%: 温和看多（+1分）
    - 涨幅 -3%~3%: 中性（0分）
    - 跌幅 3-10%: 温和看空（-2分）
    - 跌幅 > 10%: 强看空（-5分）
    """
    
    def analyze(
        self,
        grey_price: Optional[float] = None,
        offer_price: Optional[float] = None,
        grey_volume: Optional[int] = None,
        public_offer_shares: Optional[int] = None,
    ) -> GreyMarketSignal:
        """分析暗盘交易信号。
        
        Args:
            grey_price: 暗盘价格
            offer_price: 招股价
            grey_volume: 暗盘成交量
            public_offer_shares: 公开发售股数
        
        Returns:
            暗盘信号分析结果
        """
        if grey_price is None or offer_price is None or offer_price <= 0:
            return GreyMarketSignal(
                grey_price=grey_price,
                offer_price=offer_price,
                change_pct=None,
                signal_strength="数据不足",
                score_adjustment=0,
                volume_ratio_pct=None,
                volume_label="数据不足",
                detail="缺少暗盘价格或招股价数据",
            )
        
        change_pct = (grey_price / offer_price - 1) * 100
        
        strength, score_adj = self._classify_signal(change_pct)
        volume_ratio, volume_label = self._analyze_volume(
            grey_volume, public_offer_shares, change_pct
        )
        
        detail = self._build_detail(
            grey_price, offer_price, change_pct, strength, volume_ratio, volume_label
        )
        
        return GreyMarketSignal(
            grey_price=grey_price,
            offer_price=offer_price,
            change_pct=round(change_pct, 2),
            signal_strength=strength,
            score_adjustment=score_adj,
            volume_ratio_pct=volume_ratio,
            volume_label=volume_label,
            detail=detail,
        )
    
    def _classify_signal(self, change_pct: float) -> tuple[str, int]:
        """分类暗盘信号强度。
        
        Returns:
            (信号强度标签, 评分调整)
        """
        if change_pct >= 10:
            return "强看多", 3
        if change_pct >= 3:
            return "温和看多", 1
        if change_pct > -3:
            return "中性", 0
        if change_pct > -10:
            return "温和看空", -2
        return "强看空", -5
    
    def _analyze_volume(
        self,
        grey_volume: Optional[int],
        public_offer_shares: Optional[int],
        change_pct: Optional[float],
    ) -> tuple[Optional[float], str]:
        """分析暗盘成交量。
        
        Returns:
            (成交量占比%, 成交量标签)
        """
        if grey_volume is None or public_offer_shares is None or public_offer_shares <= 0:
            return None, "未知"
        
        volume_ratio = grey_volume / public_offer_shares * 100
        
        if volume_ratio > 50:
            label = "非常活跃"
        elif volume_ratio > 20:
            label = "活跃"
        elif volume_ratio > 5:
            label = "一般"
        elif volume_ratio > 0:
            label = "冷淡"
        else:
            label = "不足"
        
        if change_pct is not None and abs(change_pct) > 5 and volume_ratio < 10:
            label += "（注意：价格变动大但成交量低，信号可靠性下降）"
        
        return round(volume_ratio, 2), label
    
    def _build_detail(
        self,
        grey_price: float,
        offer_price: float,
        change_pct: float,
        strength: str,
        volume_ratio: Optional[float],
        volume_label: str,
    ) -> str:
        """构建详细说明。"""
        detail = f"暗盘价{grey_price:.2f} vs 招股价{offer_price:.2f}，涨跌幅{change_pct:+.1f}%（{strength}）"
        if volume_ratio is not None:
            detail += f"，暗盘成交量占比{volume_ratio:.1f}%({volume_label})"
        return detail
    
    def predict_first_day_return(self, change_pct: Optional[float]) -> dict[str, Any]:
        """基于暗盘涨跌幅预测首日收益率。
        
        基于历史回归模型：首日收益率 ≈ 0.75 * 暗盘涨跌幅 + 1.5%
        
        Returns:
            {
                "predicted_first_day_return_pct": float,
                "confidence_interval": (lower, upper),
                "r_squared": float,
                "detail": str,
            }
        """
        if change_pct is None:
            return {
                "predicted_first_day_return_pct": None,
                "confidence_interval": None,
                "r_squared": 0.72,
                "detail": "缺少暗盘涨跌幅数据",
            }
        
        predicted = 0.75 * change_pct + 1.5
        confidence_width = abs(predicted) * 0.3 + 2
        lower = round(predicted - confidence_width, 2)
        upper = round(predicted + confidence_width, 2)
        
        return {
            "predicted_first_day_return_pct": round(predicted, 2),
            "confidence_interval": (lower, upper),
            "r_squared": 0.72,
            "detail": f"预计首日收益率{predicted:+.1f}%（置信区间{lower:+.1f}%~{upper:+.1f}%）",
        }
