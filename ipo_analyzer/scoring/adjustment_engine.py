"""集中计算所有调整项."""

from __future__ import annotations

from .models import ScoringInput, DimensionScores, Adjustments


class AdjustmentEngine:
    def calculate(self, inp: ScoringInput, dims: DimensionScores) -> Adjustments:
        return Adjustments()
