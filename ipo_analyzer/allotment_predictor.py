"""Allotment rate predictor for Hong Kong IPOs.

Predicts one-lot allotment rate based on oversubscription ratio,
using historical data from HKEX allotment announcements.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class AllotmentRange:
    over_sub_min: float
    over_sub_max: Optional[float]
    one_lot_rate_min: float
    one_lot_rate_max: float
    sample_count: int
    description: str


@dataclass
class AllotmentPrediction:
    one_lot_rate_min: Optional[float]
    one_lot_rate_max: Optional[float]
    heat_label: str
    detail: str

    def __getitem__(self, key: str):
        return getattr(self, key)


class AllotmentPredictor:
    """基于历史数据预测港股IPO中签率。
    
    数据来源：
    - HKEX配发公告实际数据
    - 雪球/TradeSmart统计
    - 2024-2026年港股IPO样本
    """
    
    _ranges: list[AllotmentRange] = []
    _steady_capital: dict[str, int] = {}
    _group_b_multiplier: float = 1.5
    
    def __init__(self, data_path: Optional[str] = None):
        if not self._ranges:
            self._load_data(data_path)
    
    def _load_data(self, data_path: Optional[str] = None):
        """加载中签率历史数据。"""
        import yaml
        
        if data_path is None:
            data_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "data",
                "allotment_history.yaml",
            )
        
        try:
            with open(data_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except FileNotFoundError:
            logger.warning("中签率历史数据文件未找到: %s, 使用默认数据", data_path)
            self._use_default_data()
            return
        
        ranges = data.get("allotment_ranges", {})
        for key, cfg in ranges.items():
            self._ranges.append(AllotmentRange(
                over_sub_min=cfg["over_sub_min"],
                over_sub_max=cfg["over_sub_max"],
                one_lot_rate_min=cfg["one_lot_rate_min"],
                one_lot_rate_max=cfg["one_lot_rate_max"],
                sample_count=cfg["sample_count"],
                description=cfg["description"],
            ))
        
        steady = data.get("steady_one_lot_capital", {})
        for key, val in steady.items():
            self._steady_capital[key] = int(val)
        
        group_cfg = data.get("group_ratio", {})
        self._group_b_multiplier = group_cfg.get("group_b_multiplier", 1.5)
    
    def _use_default_data(self):
        """使用内置默认数据。"""
        self._ranges = [
            AllotmentRange(0, 5, 80, 100, 45, "冷门"),
            AllotmentRange(5, 15, 50, 80, 62, "温和"),
            AllotmentRange(15, 50, 20, 50, 88, "一般"),
            AllotmentRange(50, 100, 6, 20, 54, "热门"),
            AllotmentRange(100, 500, 2, 10, 76, "极热"),
            AllotmentRange(500, 1000, 0.5, 3, 32, "疯狂"),
            AllotmentRange(1000, None, 0.03, 1, 18, "极端"),
        ]
        self._steady_capital = {
            "very_cold": 20000,
            "cold": 100000,
            "normal": 300000,
            "hot": 1500000,
            "very_hot": 3000000,
            "crazy": 5000000,
            "extreme": 10000000,
        }
    
    def predict_one_lot_allotment(self, over_sub_ratio: Optional[float]) -> AllotmentPrediction:
        """预测一手中签率。
        
        Args:
            over_sub_ratio: 超购倍数（公开发售超购）
        
        Returns:
            中签率预测结果
        """
        if over_sub_ratio is None or over_sub_ratio <= 0:
            return AllotmentPrediction(
                one_lot_rate_min=None,
                one_lot_rate_max=None,
                heat_label="数据不足",
                detail="缺少超购倍数数据",
            )
        
        for r in self._ranges:
            if r.over_sub_max is None:
                if over_sub_ratio >= r.over_sub_min:
                    return AllotmentPrediction(
                        one_lot_rate_min=r.one_lot_rate_min,
                        one_lot_rate_max=r.one_lot_rate_max,
                        heat_label=r.description,
                        detail=f"超购{over_sub_ratio:.0f}倍，预计一手中签率{r.one_lot_rate_min:.0f}%-{r.one_lot_rate_max:.0f}%",
                    )
            elif r.over_sub_min <= over_sub_ratio < r.over_sub_max:
                return AllotmentPrediction(
                    one_lot_rate_min=r.one_lot_rate_min,
                    one_lot_rate_max=r.one_lot_rate_max,
                    heat_label=r.description,
                    detail=f"超购{over_sub_ratio:.0f}倍，预计一手中签率{r.one_lot_rate_min:.0f}%-{r.one_lot_rate_max:.0f}%",
                )
        
        return AllotmentPrediction(
            one_lot_rate_min=None,
            one_lot_rate_max=None,
            heat_label="数据不足",
            detail=f"超购{over_sub_ratio:.0f}倍超出历史数据范围",
        )
    
    def predict_group_allotment(self, over_sub_ratio: Optional[float]) -> dict[str, Any]:
        """预测甲组/乙组中签率差异。
        
        Returns:
            {
                "group_a_one_lot_rate_min": ...,
                "group_a_one_lot_rate_max": ...,
                "group_b_one_lot_rate_min": ...,
                "group_b_one_lot_rate_max": ...,
                "group_b_multiplier": ...,
            }
        """
        base = self.predict_one_lot_allotment(over_sub_ratio)
        
        if base.one_lot_rate_min is None:
            return {
                "group_a_one_lot_rate_min": None,
                "group_a_one_lot_rate_max": None,
                "group_b_one_lot_rate_min": None,
                "group_b_one_lot_rate_max": None,
                "group_b_multiplier": self._group_b_multiplier,
                "detail": "缺少超购倍数数据",
            }
        
        group_a_min = base.one_lot_rate_min
        group_a_max = base.one_lot_rate_max
        group_b_min = min(100, group_a_min * self._group_b_multiplier)
        group_b_max = min(100, group_a_max * self._group_b_multiplier)
        
        return {
            "group_a_one_lot_rate_min": group_a_min,
            "group_a_one_lot_rate_max": group_a_max,
            "group_b_one_lot_rate_min": round(group_b_min, 1),
            "group_b_one_lot_rate_max": round(group_b_max, 1),
            "group_b_multiplier": self._group_b_multiplier,
            "detail": f"乙组中签率约为甲组的{self._group_b_multiplier}倍",
        }
    
    def predict_steady_one_lot_capital(self, over_sub_ratio: Optional[float]) -> dict[str, Any]:
        """计算稳中一手所需资金。
        
        Returns:
            {
                "steady_capital_hkd": 稳中一手所需港元,
                "capital_label": 资金量标签,
                "detail": 详细说明,
            }
        """
        if over_sub_ratio is None or over_sub_ratio <= 0:
            return {
                "steady_capital_hkd": None,
                "capital_label": "数据不足",
                "detail": "缺少超购倍数数据",
            }
        
        capital_hkd = self._estimate_capital(over_sub_ratio)
        
        if capital_hkd < 50000:
            label = "小资金"
        elif capital_hkd < 500000:
            label = "中等资金"
        elif capital_hkd < 5000000:
            label = "大资金"
        else:
            label = "超大资金（需乙组）"
        
        return {
            "steady_capital_hkd": capital_hkd,
            "capital_label": label,
            "detail": f"预计稳中一手需要约{capital_hkd/10000:.0f}万港元",
        }
    
    def _estimate_capital(self, over_sub_ratio: float) -> int:
        """基于超购倍数估算稳中一手所需资金。
        
        简化模型：资金需求与超购倍数呈指数关系。
        """
        if over_sub_ratio < 5:
            return 20000
        if over_sub_ratio < 15:
            return 100000
        if over_sub_ratio < 50:
            return 300000
        if over_sub_ratio < 100:
            return 1500000
        if over_sub_ratio < 500:
            return 3000000
        if over_sub_ratio < 1000:
            return 5000000
        return 10000000
