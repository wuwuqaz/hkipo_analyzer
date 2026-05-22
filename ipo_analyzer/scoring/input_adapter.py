"""将分析器输出的扁平 dict 映射为强类型 ScoringInput."""

from __future__ import annotations

from typing import Any

from .models import ScoringInput, CornerstoneInvestorInput, QualityDimensions
from ._utils import is_biotech


class AnalyzerOutputAdapter:
    """统一适配器: prospectus_info dict -> ScoringInput."""

    def adapt(self, stock_code: str, company_name: str, prospectus_info: dict[str, Any]) -> ScoringInput:
        signal = prospectus_info.get("signal_components", {})
        valuation = prospectus_info.get("valuation", {})
        quality = prospectus_info.get("quality_analysis", {})
        risk = prospectus_info.get("risk_analysis", {})
        cornerstone = prospectus_info.get("cornerstone_analysis", {})

        # Map cornerstone investors
        raw_investors = cornerstone.get("cornerstone_investors", []) if isinstance(cornerstone, dict) else []
        investors: list[CornerstoneInvestorInput] = []
        for inv in raw_investors:
            if not isinstance(inv, dict):
                continue
            investors.append(
                CornerstoneInvestorInput(
                    name=inv.get("name", ""),
                    offer_shares=inv.get("offer_shares"),
                    offer_shares_pct=inv.get("offer_shares_pct"),
                    lockup_months=inv.get("lockup_months"),
                    type_hint=inv.get("type"),
                )
            )

        # Map quality dimensions
        qd = QualityDimensions(
            growth_score=quality.get("growth_score", 0.0) if isinstance(quality, dict) else 0.0,
            profitability_score=quality.get("profitability_score", 0.0) if isinstance(quality, dict) else 0.0,
            valuation_score=quality.get("valuation_score", 0.0) if isinstance(quality, dict) else 0.0,
            risk_score=quality.get("risk_score", 0.0) if isinstance(quality, dict) else 0.0,
            cashflow_score=quality.get("cashflow_score", 0.0) if isinstance(quality, dict) else 0.0,
            moat_score=quality.get("moat_score", 0.0) if isinstance(quality, dict) else 0.0,
            financial_health_score=quality.get("financial_health_score", 0.0) if isinstance(quality, dict) else 0.0,
            management_score=quality.get("management_score", 0.0) if isinstance(quality, dict) else 0.0,
            balance_sheet_score=quality.get("balance_sheet_score", 0.0) if isinstance(quality, dict) else 0.0,
            profit_sustainability_score=quality.get("profit_sustainability_score", 0.0) if isinstance(quality, dict) else 0.0,
        )

        # Risk categories
        raw_risks = risk.get("risks", {}) if isinstance(risk, dict) else {}
        risk_categories: dict[str, list[str]] = raw_risks if isinstance(raw_risks, dict) else {}

        return ScoringInput(
            stock_code=stock_code,
            company_name=company_name,
            is_biotech=is_biotech(prospectus_info),
            heat_score=signal.get("heat_score", 0.0),
            scale_score=signal.get("scale_score", 0.0),
            cornerstone_score=signal.get("cornerstone_score", 0.0),
            real_money_signal=signal.get("real_money", 0.0),
            float_structure_score=signal.get("float_structure", 0.0),
            sponsor_score=signal.get("sponsor_score"),
            greenshoe_score=signal.get("greenshoe_score"),
            clawback_score=signal.get("clawback_score"),
            stock_quality_score=prospectus_info.get("stock_quality_score", 0.0),
            quality_dimensions=qd,
            valuation_framework_score=valuation.get("valuation_framework_score", 0.0) if isinstance(valuation, dict) else 0.0,
            peer_adj_label=valuation.get("peer_adj_label") if isinstance(valuation, dict) else None,
            pricing_gap_adj=prospectus_info.get("pricing_gap_adj", 0.0),
            valuation_label=valuation.get("valuation_label") if isinstance(valuation, dict) else None,
            mainline_beta_score=signal.get("mainline_beta", 0.0),
            stock_connect_path_score=signal.get("stock_connect_path", 0.0),
            scarcity_score=signal.get("scarcity", 0.0),
            sentiment_bonus=prospectus_info.get("sentiment_bonus", 0.0),
            macro_bonus=prospectus_info.get("macro_bonus", 0.0),
            data_quality_score=signal.get("data_quality", 0.0),
            risk_penalty=risk.get("total_penalty", 0.0) if isinstance(risk, dict) else 0.0,
            risk_categories=risk_categories,
            cornerstone_pct=prospectus_info.get("cornerstone_pct"),
            cornerstone_investors=investors,
            cornerstone_red_flags=prospectus_info.get("cornerstone_red_flags", []),
            raw_prospectus_info=prospectus_info,
        )
