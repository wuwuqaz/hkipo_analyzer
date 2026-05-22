"""Tests for AnalyzerOutputAdapter."""

from __future__ import annotations

import pytest

from ipo_analyzer.scoring.input_adapter import AnalyzerOutputAdapter
from ipo_analyzer.scoring.models import ScoringInput, CornerstoneInvestorInput, QualityDimensions


@pytest.fixture
def adapter() -> AnalyzerOutputAdapter:
    return AnalyzerOutputAdapter()


def _make_minimal_prospectus_info(**overrides) -> dict:
    base = {
        "signal_components": {
            "heat_score": 10.0,
            "scale_score": 8.0,
            "cornerstone_score": 7.0,
            "real_money": 6.0,
            "float_structure": 5.0,
            "sponsor_score": 4.0,
            "greenshoe_score": 3.0,
            "clawback_score": 2.0,
            "mainline_beta": 1.0,
            "stock_connect_path": 2.0,
            "scarcity": 3.0,
            "data_quality": 90.0,
        },
        "quality_analysis": {
            "growth_score": 70.0,
            "profitability_score": 60.0,
            "valuation_score": 50.0,
            "risk_score": 40.0,
            "cashflow_score": 30.0,
            "moat_score": 20.0,
            "financial_health_score": 80.0,
            "management_score": 75.0,
            "balance_sheet_score": 65.0,
            "profit_sustainability_score": 55.0,
        },
        "valuation": {
            "valuation_framework_score": 65.0,
            "peer_adj_label": "fair",
            "valuation_label": "合理",
        },
        "risk_analysis": {
            "total_penalty": 5.0,
            "risks": {
                "market": ["volatile"],
            },
        },
        "cornerstone_analysis": {
            "cornerstone_investors": [
                {
                    "name": "Investor A",
                    "offer_shares": 1000,
                    "offer_shares_pct": 5.0,
                    "lockup_months": 6,
                    "type": "institution",
                }
            ],
        },
        "stock_quality_score": 72.0,
        "pricing_gap_adj": 1.5,
        "sentiment_bonus": 2.0,
        "macro_bonus": 1.0,
        "cornerstone_pct": 30.0,
        "cornerstone_red_flags": ["flag1"],
    }
    base.update(overrides)
    return base


def test_minimal_adaptation(adapter: AnalyzerOutputAdapter) -> None:
    info = _make_minimal_prospectus_info()
    result = adapter.adapt("01234", "TestCo", info)

    assert isinstance(result, ScoringInput)
    assert result.stock_code == "01234"
    assert result.company_name == "TestCo"
    assert result.heat_score == 10.0
    assert result.scale_score == 8.0
    assert result.cornerstone_score == 7.0
    assert result.real_money_signal == 6.0
    assert result.float_structure_score == 5.0
    assert result.sponsor_score == 4.0
    assert result.greenshoe_score == 3.0
    assert result.clawback_score == 2.0
    assert result.stock_quality_score == 72.0
    assert result.valuation_framework_score == 65.0
    assert result.peer_adj_label == "fair"
    assert result.pricing_gap_adj == 1.5
    assert result.valuation_label == "合理"
    assert result.mainline_beta_score == 1.0
    assert result.stock_connect_path_score == 2.0
    assert result.scarcity_score == 3.0
    assert result.sentiment_bonus == 2.0
    assert result.macro_bonus == 1.0
    assert result.data_quality_score == 90.0
    assert result.risk_penalty == 5.0
    assert result.risk_categories == {"market": ["volatile"]}
    assert result.cornerstone_pct == 30.0
    assert result.cornerstone_red_flags == ["flag1"]
    assert result.raw_prospectus_info == info


def test_biotech_detection(adapter: AnalyzerOutputAdapter) -> None:
    info = _make_minimal_prospectus_info(extracted_company_name="BioCo-B")
    result = adapter.adapt("01234", "BioCo-B", info)
    assert result.is_biotech is True

    info2 = _make_minimal_prospectus_info(extracted_company_name="NormalCo")
    result2 = adapter.adapt("01234", "NormalCo", info2)
    assert result2.is_biotech is False


def test_cornerstone_investors_mapping(adapter: AnalyzerOutputAdapter) -> None:
    info = _make_minimal_prospectus_info()
    result = adapter.adapt("01234", "TestCo", info)

    assert len(result.cornerstone_investors) == 1
    inv = result.cornerstone_investors[0]
    assert isinstance(inv, CornerstoneInvestorInput)
    assert inv.name == "Investor A"
    assert inv.offer_shares == 1000
    assert inv.offer_shares_pct == 5.0
    assert inv.lockup_months == 6
    assert inv.type_hint == "institution"


def test_quality_dimensions_mapping(adapter: AnalyzerOutputAdapter) -> None:
    info = _make_minimal_prospectus_info()
    result = adapter.adapt("01234", "TestCo", info)

    qd = result.quality_dimensions
    assert isinstance(qd, QualityDimensions)
    assert qd.growth_score == 70.0
    assert qd.profitability_score == 60.0
    assert qd.valuation_score == 50.0
    assert qd.risk_score == 40.0
    assert qd.cashflow_score == 30.0
    assert qd.moat_score == 20.0
    assert qd.financial_health_score == 80.0
    assert qd.management_score == 75.0
    assert qd.balance_sheet_score == 65.0
    assert qd.profit_sustainability_score == 55.0


def test_defaults_when_keys_missing(adapter: AnalyzerOutputAdapter) -> None:
    info: dict = {}
    result = adapter.adapt("01234", "TestCo", info)

    assert result.heat_score == 0.0
    assert result.scale_score == 0.0
    assert result.cornerstone_score == 0.0
    assert result.real_money_signal == 0.0
    assert result.float_structure_score == 0.0
    assert result.sponsor_score is None
    assert result.greenshoe_score is None
    assert result.clawback_score is None
    assert result.stock_quality_score == 0.0
    assert result.valuation_framework_score == 0.0
    assert result.peer_adj_label is None
    assert result.pricing_gap_adj == 0.0
    assert result.valuation_label is None
    assert result.mainline_beta_score == 0.0
    assert result.stock_connect_path_score == 0.0
    assert result.scarcity_score == 0.0
    assert result.sentiment_bonus == 0.0
    assert result.macro_bonus == 0.0
    assert result.data_quality_score == 0.0
    assert result.risk_penalty == 0.0
    assert result.risk_categories == {}
    assert result.cornerstone_pct is None
    assert result.cornerstone_investors == []
    assert result.cornerstone_red_flags == []
    assert result.is_biotech is False
