"""检测权重配置文件 (live_heat / prospectus_only / optimized)."""

from __future__ import annotations

import os
from typing import Optional

from .models import ScoringInput, WeightProfile


class WeightProfileDetector:
    """基于输入数据可用性选择权重配置."""

    def __init__(self, optimized_weights_path: str = "data/optimized_weights.yaml"):
        self._optimized_path = optimized_weights_path
        self._optimized: Optional[WeightProfile] = None
        self._load_optimized()

    def _load_optimized(self) -> None:
        if not os.path.exists(self._optimized_path):
            return
        try:
            import yaml
            with open(self._optimized_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if data and "weights" in data:
                self._optimized = WeightProfile(name="optimized", weights=data["weights"])
        except Exception:
            pass

    def detect(self, inp: ScoringInput) -> WeightProfile:
        has_heat = inp.heat_score > 0 or inp.real_money_signal > 0
        if self._optimized:
            return self._optimized
        if has_heat:
            return WeightProfile(
                name="live_heat",
                weights={"trade": 0.25, "fundamental": 0.35, "data_quality": 0.05, "valuation": 0.25, "theme": 0.10},
            )
        return WeightProfile(
            name="prospectus_only",
            weights={"trade": 0.15, "fundamental": 0.40, "data_quality": 0.05, "valuation": 0.25, "theme": 0.15},
        )
