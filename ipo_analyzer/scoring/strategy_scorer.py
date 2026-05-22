"""计算 long_term_score 和 strict_ipo_score."""

from __future__ import annotations

from .models import ScoringInput, DimensionScores, StrategyScores


class StrategyScorer:
    def calculate(self, inp: ScoringInput, raw_score: float, dims: DimensionScores) -> StrategyScores:
        return StrategyScores()
