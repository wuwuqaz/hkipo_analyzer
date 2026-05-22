"""评分管道主类 — 串联所有评分组件."""

from __future__ import annotations

from .models import (
    ScoringInput,
    ScoringResult,
    ScoreTrace,
    DimensionScores,
    Adjustments,
    StrategyScores,
    RecommendationResult,
)
from .dimension_scorer import DimensionScorer
from .adjustment_engine import AdjustmentEngine
from .weight_detector import WeightProfileDetector
from .strategy_scorer import StrategyScorer
from .recommender import Recommender


def _apply_caps(score: float, strat: StrategyScores, inp: ScoringInput) -> float:
    """Cap final score between 0 and 100."""
    return max(0.0, min(score, 100.0))


class ScoringPipeline:
    """评分管道 — 串联所有评分组件."""

    def __init__(
        self,
        dimension_scorer: DimensionScorer | None = None,
        adjustment_engine: AdjustmentEngine | None = None,
        weight_detector: WeightProfileDetector | None = None,
        strategy_scorer: StrategyScorer | None = None,
        recommender: Recommender | None = None,
    ) -> None:
        self.dimension_scorer = dimension_scorer or DimensionScorer()
        self.adjustment_engine = adjustment_engine or AdjustmentEngine()
        self.weight_detector = weight_detector or WeightProfileDetector()
        self.strategy_scorer = strategy_scorer or StrategyScorer()
        self.recommender = recommender or Recommender()

    def run(self, inp: ScoringInput) -> ScoringResult:
        trace = ScoreTrace()

        # Step 1: dimension scorer
        dims = self.dimension_scorer.calculate(inp)
        trace.record(
            step_name="dimension_scorer",
            input_data={"heat_score": inp.heat_score, "stock_quality_score": inp.stock_quality_score},
            output_data={
                "trade": dims.trade,
                "fundamental": dims.fundamental,
                "valuation": dims.valuation,
                "theme": dims.theme,
                "data_quality": dims.data_quality,
            },
        )

        # Step 2: adjustment engine
        adj = self.adjustment_engine.calculate(inp, dims)
        trace.record(
            step_name="adjustment_engine",
            input_data={"peer_adj_label": inp.peer_adj_label, "valuation_label": inp.valuation_label},
            output_data={
                "peer_adj": adj.peer_adj,
                "val_penalty": adj.val_penalty,
                "pricing_gap_adj": adj.pricing_gap_adj,
                "risk_penalty": adj.risk_penalty,
                "cornerstone_penalty": adj.cornerstone_penalty,
                "total": adj.total,
            },
        )

        # Step 3: weight detector + raw score
        profile = self.weight_detector.detect(inp)
        weights = profile.weights
        raw_score = (
            dims.trade * weights.get("trade", 0.0)
            + dims.fundamental * weights.get("fundamental", 0.0)
            + dims.valuation * weights.get("valuation", 0.0)
            + dims.theme * weights.get("theme", 0.0)
            + dims.data_quality * weights.get("data_quality", 0.0)
        )
        trace.record(
            step_name="weight_profile",
            input_data={"heat_score": inp.heat_score, "real_money_signal": inp.real_money_signal},
            output_data={"profile": profile.name, "weights": weights, "raw_score": raw_score},
        )

        # Step 4: apply adjustments
        score = raw_score + adj.total
        trace.record(
            step_name="apply_adjustments",
            input_data={"raw_score": raw_score, "adjustment_total": adj.total},
            output_data={"score": score},
        )

        # Step 5: strategy scorer
        strat = self.strategy_scorer.calculate(inp, score, dims)
        trace.record(
            step_name="strategy_scorer",
            input_data={"score": score},
            output_data={
                "long_term_score": strat.long_term_score,
                "strict_ipo_score": strat.strict_ipo_score,
                "long_term_components": strat.long_term_components,
            },
        )

        # Step 6: cap final score
        final_score = _apply_caps(score, strat, inp)
        trace.record(
            step_name="cap_final_score",
            input_data={"score": score},
            output_data={"final_score": final_score},
        )

        # Step 7: recommender
        rec = self.recommender.recommend(final_score, strat, adj, dims)
        trace.record(
            step_name="recommender",
            input_data={"final_score": final_score},
            output_data={
                "recommendation": rec.recommendation,
                "reasons": rec.reasons,
                "dimension_grades": rec.dimension_grades,
            },
        )

        return ScoringResult(
            score=score,
            final_score=final_score,
            trade_score=dims.trade,
            fundamental_score=dims.fundamental,
            valuation_score=dims.valuation,
            theme_score=dims.theme,
            data_quality_score=dims.data_quality,
            long_term_score=strat.long_term_score,
            strict_ipo_score=strat.strict_ipo_score,
            ipo_trade_score=dims.trade,
            recommendation=rec.recommendation,
            reasons=rec.reasons,
            dimension_grades=rec.dimension_grades,
            score_trace=trace,
            weight_profile=profile.name,
            debug_info={
                "raw_score": raw_score,
                "adjustments": {
                    "peer_adj": adj.peer_adj,
                    "val_penalty": adj.val_penalty,
                    "pricing_gap_adj": adj.pricing_gap_adj,
                    "risk_penalty": adj.risk_penalty,
                    "cornerstone_penalty": adj.cornerstone_penalty,
                    "total": adj.total,
                },
                "long_term_components": strat.long_term_components,
            },
        )
