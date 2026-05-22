"""基于分数生成推荐、原因和等级评定."""

from __future__ import annotations

from .models import (
    ScoringInput,
    DimensionScores,
    Adjustments,
    StrategyScores,
    RecommendationResult,
)


class Recommender:
    def recommend(self, final_score: float, strategy_scores: StrategyScores,
                  adjustments: Adjustments, dimensions: DimensionScores) -> RecommendationResult:
        return RecommendationResult()
