"""基于分数生成推荐、原因和等级评定."""

from __future__ import annotations

from ._utils import grade_from_score
from .models import (
    ScoringInput,
    DimensionScores,
    Adjustments,
    StrategyScores,
    RecommendationResult,
)


class Recommender:
    def recommend(
        self,
        final_score: float,
        strategy_scores: StrategyScores,
        adjustments: Adjustments,
        dimensions: DimensionScores,
    ) -> RecommendationResult:
        # Recommendation based on final_score
        if final_score >= 75:
            recommendation = "强烈推荐"
        elif final_score >= 60:
            recommendation = "推荐"
        elif final_score >= 45:
            recommendation = "中性"
        elif final_score >= 30:
            recommendation = "谨慎"
        else:
            recommendation = "回避"

        # Reasons
        reasons: list[str] = []
        if dimensions.trade >= 70:
            reasons.append("交易热度强劲")
        elif dimensions.trade <= 30:
            reasons.append("交易热度不足")

        if dimensions.fundamental >= 70:
            reasons.append("基本面优质")
        elif dimensions.fundamental <= 30:
            reasons.append("基本面较弱")

        if adjustments.peer_adj > 0:
            reasons.append("估值相对同行有优势")
        elif adjustments.peer_adj < 0:
            reasons.append("估值相对同行偏高")

        if adjustments.risk_penalty > 10:
            reasons.append("风险因子较多，需注意")

        if strategy_scores.long_term_score >= 70:
            reasons.append("长期投资价值较高")

        # Dimension grades
        dimension_grades = {
            "trade": grade_from_score(dimensions.trade),
            "fundamental": grade_from_score(dimensions.fundamental),
            "valuation": grade_from_score(dimensions.valuation),
            "theme": grade_from_score(dimensions.theme),
            "data_quality": grade_from_score(dimensions.data_quality),
        }

        return RecommendationResult(
            recommendation=recommendation,
            reasons=reasons,
            dimension_grades=dimension_grades,
        )
