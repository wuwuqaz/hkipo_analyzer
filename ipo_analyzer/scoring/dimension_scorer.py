"""计算五维原始分 — 不含任何调整项."""

from __future__ import annotations

from .models import ScoringInput, DimensionScores


class DimensionScorer:
    def calculate(self, inp: ScoringInput) -> DimensionScores:
        return DimensionScores()
