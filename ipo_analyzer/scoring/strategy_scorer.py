"""计算 long_term_score 和 strict_ipo_score."""

from __future__ import annotations

from .models import ScoringInput, DimensionScores, StrategyScores


class StrategyScorer:
    def calculate(self, inp: ScoringInput, raw_score: float, dims: DimensionScores) -> StrategyScores:
        # Determine fundamental_score: prefer quality_dimensions.profitability_score if available,
        # otherwise fall back to dims.fundamental
        fundamental_score = inp.quality_dimensions.profitability_score or 0.0
        if fundamental_score == 0.0:
            fundamental_score = dims.fundamental

        # Determine valuation_score: prefer quality_dimensions.valuation_score if available,
        # otherwise fall back to dims.valuation
        valuation_score = inp.quality_dimensions.valuation_score or 0.0
        if valuation_score == 0.0:
            valuation_score = dims.valuation

        moat_score = inp.quality_dimensions.moat_score or 0.0
        financial_health_score = inp.quality_dimensions.financial_health_score or 0.0
        growth_score = inp.quality_dimensions.growth_score or 0.0
        stock_connect_path_score = inp.stock_connect_path_score or 0.0
        mainline_beta_score = inp.mainline_beta_score or 0.0

        long_term_score = (
            fundamental_score * 0.35
            + valuation_score * 0.25
            + moat_score * 0.15
            + financial_health_score * 0.10
            + growth_score * 0.05
            + stock_connect_path_score * 0.05
            + mainline_beta_score * 0.05
        )
        long_term_score = max(0.0, min(long_term_score, 100.0))

        long_term_components = {
            "fundamental_score": fundamental_score,
            "valuation_score": valuation_score,
            "moat_score": moat_score,
            "financial_health_score": financial_health_score,
            "growth_score": growth_score,
            "stock_connect_path_score": stock_connect_path_score,
            "mainline_beta_score": mainline_beta_score,
        }

        strict_ipo_score = (
            inp.heat_score * 0.40
            + long_term_score * 0.40
            + inp.valuation_framework_score * 0.20
        )
        strict_ipo_score = max(0.0, min(strict_ipo_score, 100.0))

        return StrategyScores(
            long_term_score=long_term_score,
            strict_ipo_score=strict_ipo_score,
            long_term_components=long_term_components,
        )
