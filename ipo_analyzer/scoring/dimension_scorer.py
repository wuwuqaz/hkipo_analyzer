"""计算五维原始分 — 不含任何调整项."""

from __future__ import annotations

from .models import ScoringInput, DimensionScores


class DimensionScorer:
    def calculate(self, inp: ScoringInput) -> DimensionScores:
        # Trade: sum of components, normalize by 130 then * 100, cap at 100
        trade_sum = (
            inp.heat_score
            + inp.scale_score
            + inp.cornerstone_score
            + inp.real_money_signal
            + inp.float_structure_score
            + (inp.sponsor_score or 0.0)
            + (inp.greenshoe_score or 0.0)
            + (inp.clawback_score or 0.0)
        )
        trade = min((trade_sum / 130.0) * 100.0, 100.0)

        # Fundamental: directly stock_quality_score, cap 0-100
        fundamental = max(0.0, min(inp.stock_quality_score, 100.0))

        # Valuation: directly valuation_framework_score, cap 0-100
        valuation = max(0.0, min(inp.valuation_framework_score, 100.0))

        # Theme: weighted sum, cap 0-100
        theme = (
            inp.mainline_beta_score * 0.30
            + inp.stock_connect_path_score * 0.30
            + inp.scarcity_score * 0.20
            + inp.sentiment_bonus * 0.10
            + inp.macro_bonus * 0.10
        )
        theme = max(0.0, min(theme, 100.0))

        # Data quality: directly data_quality_score, cap 0-100
        data_quality = max(0.0, min(inp.data_quality_score, 100.0))

        trade_components = {
            "heat_score": inp.heat_score,
            "scale_score": inp.scale_score,
            "cornerstone_score": inp.cornerstone_score,
            "real_money_signal": inp.real_money_signal,
            "float_structure_score": inp.float_structure_score,
            "sponsor_score": inp.sponsor_score or 0.0,
            "greenshoe_score": inp.greenshoe_score or 0.0,
            "clawback_score": inp.clawback_score or 0.0,
        }

        fundamental_components = {
            "stock_quality_score": inp.stock_quality_score,
            "growth_score": inp.quality_dimensions.growth_score,
            "profitability_score": inp.quality_dimensions.profitability_score,
            "valuation_score": inp.quality_dimensions.valuation_score,
            "risk_score": inp.quality_dimensions.risk_score,
            "cashflow_score": inp.quality_dimensions.cashflow_score,
            "moat_score": inp.quality_dimensions.moat_score,
            "financial_health_score": inp.quality_dimensions.financial_health_score,
            "management_score": inp.quality_dimensions.management_score,
            "balance_sheet_score": inp.quality_dimensions.balance_sheet_score,
            "profit_sustainability_score": inp.quality_dimensions.profit_sustainability_score,
        }

        return DimensionScores(
            trade=trade,
            fundamental=fundamental,
            valuation=valuation,
            theme=theme,
            data_quality=data_quality,
            trade_components=trade_components,
            fundamental_components=fundamental_components,
        )
