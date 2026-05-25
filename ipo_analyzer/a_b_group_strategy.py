"""A/B group strategy analyzer for Hong Kong IPO subscription.

Analyzes optimal subscription strategy based on capital amount and
market heat (oversubscription ratio).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .allotment_predictor import AllotmentPredictor


class ABGroupStrategyAnalyzer:
    """甲乙组策略分析。
    
    港股打新采用独特的甲乙组划分：
    - 甲组：申购金额 < 500万港元（红鞋机制保护）
    - 乙组：申购金额 > 500万港元（按资金比例分配）
    """
    
    GROUP_B_THRESHOLD = 5_000_000  # 500万港元
    
    def analyze(
        self,
        over_sub_ratio: Optional[float],
        public_offer_shares: Optional[int] = None,
        lot_size: Optional[int] = None,
    ) -> dict[str, Any]:
        predictor = AllotmentPredictor()
        
        data_sufficient = over_sub_ratio is not None and over_sub_ratio > 0
        
        if not data_sufficient:
            return {
                "data_sufficient": False,
                "group_a_analysis": {
                    "threshold": "申购金额 < 500万港元",
                    "predicted_one_lot_rate": "数据不足",
                    "advantage": "红鞋机制保护，一手党优势",
                    "recommended_amount": "甲头（一手党）",
                },
                "group_b_analysis": {
                    "threshold": "申购金额 > 500万港元",
                    "predicted_allotment_rate": "数据不足",
                    "advantage": "按资金比例分配，中签率更高",
                    "recommended_amount": "数据不足",
                },
                "optimal_strategy": {
                    "small_capital": {
                        "strategy": "甲头（一手党）",
                        "reasoning": "红鞋机制保护，一手中签率最高",
                    },
                    "medium_capital": {
                        "strategy": "甲头（一手党）",
                        "reasoning": "超购倍数未知，保守策略",
                    },
                    "large_capital": {
                        "strategy": "甲头（一手党）",
                        "reasoning": "超购倍数未知，保守策略",
                    },
                },
                "detail": "缺少超购倍数数据，策略分析仅供参考",
            }
        
        allotment = predictor.predict_one_lot_allotment(over_sub_ratio)
        group_allotment = predictor.predict_group_allotment(over_sub_ratio)
        steady_capital = predictor.predict_steady_one_lot_capital(over_sub_ratio)
        
        group_a_analysis = self._analyze_group_a(over_sub_ratio, allotment, group_allotment)
        group_b_analysis = self._analyze_group_b(over_sub_ratio, allotment, group_allotment)
        optimal = self._recommend_strategy(over_sub_ratio, allotment, steady_capital)
        
        return {
            "data_sufficient": True,
            "over_sub_ratio": over_sub_ratio,
            "group_a_analysis": group_a_analysis,
            "group_b_analysis": group_b_analysis,
            "optimal_strategy": optimal,
            "detail": f"基于超购{over_sub_ratio:.0f}倍分析",
        }
    
    def _analyze_group_a(
        self,
        over_sub_ratio: float,
        allotment: Any,
        group_allotment: dict[str, Any],
    ) -> dict[str, Any]:
        rate_str = f"{allotment.one_lot_rate_min:.0f}%-{allotment.one_lot_rate_max:.0f}%"
        
        if over_sub_ratio < 15:
            recommended = "甲头（一手党）"
            reasoning = "超购倍数不高，一手党中签率很高"
        elif over_sub_ratio < 100:
            recommended = "甲尾（接近500万）"
            reasoning = "超购适中，甲尾可提高分配概率"
        else:
            recommended = "甲头（一手党）"
            reasoning = "极热行情下，红鞋机制优先保障一手"
        
        return {
            "threshold": "申购金额 < 500万港元",
            "predicted_one_lot_rate": rate_str,
            "advantage": "红鞋机制保护，一手党优势",
            "recommended_amount": recommended,
            "reasoning": reasoning,
        }
    
    def _analyze_group_b(
        self,
        over_sub_ratio: float,
        allotment: Any,
        group_allotment: dict[str, Any],
    ) -> dict[str, Any]:
        rate_str = f"{group_allotment['group_b_one_lot_rate_min']:.0f}%-{group_allotment['group_b_one_lot_rate_max']:.0f}%"
        
        if over_sub_ratio < 50:
            recommended = "不推荐乙组"
            reasoning = "超购倍数不高，甲组已足够"
        elif over_sub_ratio < 500:
            recommended = "乙头（刚超500万）"
            reasoning = "乙组中签率更高，资金效率最优"
        else:
            recommended = "乙头或顶头槌"
            reasoning = "极热行情下，顶头槌也不保证中签"
        
        return {
            "threshold": "申购金额 > 500万港元",
            "predicted_allotment_rate": rate_str,
            "advantage": "按资金比例分配，中签率更高",
            "recommended_amount": recommended,
            "reasoning": reasoning,
        }
    
    def _recommend_strategy(
        self,
        over_sub_ratio: float,
        allotment: Any,
        steady_capital: dict[str, Any],
    ) -> dict[str, dict[str, str]]:
        if over_sub_ratio < 15:
            small = "甲头（一手党）"
            small_reason = "冷门股，一手党即可高概率中签"
            medium = "甲头（一手党）"
            medium_reason = "超购不高，无需大额申购"
            large = "甲头（一手党）"
            large_reason = "冷门股，资金量不是关键"
        elif over_sub_ratio < 50:
            small = "甲头（一手党）"
            small_reason = "红鞋保护，一手党仍有不错概率"
            medium = "甲尾（接近500万）"
            medium_reason = "提高分配概率，接近500万门槛"
            large = "乙头（刚超500万）"
            large_reason = "乙组按资金分配，中签率更高"
        elif over_sub_ratio < 500:
            small = "甲头（一手党）"
            small_reason = "热门股，红鞋机制优先保障一手"
            medium = "甲尾（接近500万）"
            medium_reason = "最大化甲组分配"
            large = "乙头（刚超500万）"
            large_reason = f"预计稳中一手需{steady_capital.get('steady_capital_hkd', 0)/10000:.0f}万"
        else:
            small = "甲头（一手党）"
            small_reason = "极热股，一手党中签率极低，但成本低"
            medium = "甲尾（接近500万）"
            medium_reason = "极热行情，顶多甲尾"
            large = "乙头或顶头槌"
            large_reason = f"预计稳中一手需{steady_capital.get('steady_capital_hkd', 0)/10000:.0f}万，顶头槌也不保证"
        
        return {
            "small_capital": {
                "strategy": small,
                "reasoning": small_reason,
            },
            "medium_capital": {
                "strategy": medium,
                "reasoning": medium_reason,
            },
            "large_capital": {
                "strategy": large,
                "reasoning": large_reason,
            },
        }
