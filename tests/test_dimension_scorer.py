"""Tests for DimensionScorer."""

from __future__ import annotations

import pytest

from ipo_analyzer.scoring.dimension_scorer import DimensionScorer
from ipo_analyzer.scoring.models import ScoringInput, QualityDimensions, DimensionScores


@pytest.fixture
def scorer() -> DimensionScorer:
    return DimensionScorer()


def _make_input(**overrides) -> ScoringInput:
    defaults = {
        "stock_code": "01234",
        "company_name": "TestCo",
        "heat_score": 10.0,
        "scale_score": 8.0,
        "cornerstone_score": 7.0,
        "real_money_signal": 6.0,
        "float_structure_score": 5.0,
        "sponsor_score": 4.0,
        "greenshoe_score": 3.0,
        "clawback_score": 2.0,
        "stock_quality_score": 72.0,
        "quality_dimensions": QualityDimensions(
            growth_score=70.0,
            profitability_score=60.0,
            valuation_score=50.0,
            risk_score=40.0,
            cashflow_score=30.0,
            moat_score=20.0,
            financial_health_score=80.0,
            management_score=75.0,
            balance_sheet_score=65.0,
            profit_sustainability_score=55.0,
        ),
        "valuation_framework_score": 65.0,
        "mainline_beta_score": 50.0,
        "stock_connect_path_score": 60.0,
        "scarcity_score": 40.0,
        "sentiment_bonus": 10.0,
        "macro_bonus": 20.0,
        "data_quality_score": 88.0,
    }
    defaults.update(overrides)
    return ScoringInput(**defaults)


def test_basic_scoring(scorer: DimensionScorer) -> None:
    inp = _make_input()
    result = scorer.calculate(inp)

    assert isinstance(result, DimensionScores)

    # trade = (10+8+7+6+5+4+3+2)/130*100 = 45/130*100 ≈ 34.615
    expected_trade = (45.0 / 130.0) * 100.0
    assert result.trade == pytest.approx(expected_trade, rel=1e-4)

    assert result.fundamental == 72.0
    assert result.valuation == 65.0

    # theme = 50*0.30 + 60*0.30 + 40*0.20 + 10*0.10 + 20*0.10 = 15+18+8+1+2 = 44
    expected_theme = 50.0 * 0.30 + 60.0 * 0.30 + 40.0 * 0.20 + 10.0 * 0.10 + 20.0 * 0.10
    assert result.theme == pytest.approx(expected_theme, rel=1e-4)

    assert result.data_quality == 88.0

    # trade_components
    assert result.trade_components["heat_score"] == 10.0
    assert result.trade_components["scale_score"] == 8.0
    assert result.trade_components["cornerstone_score"] == 7.0
    assert result.trade_components["real_money_signal"] == 6.0
    assert result.trade_components["float_structure_score"] == 5.0
    assert result.trade_components["sponsor_score"] == 4.0
    assert result.trade_components["greenshoe_score"] == 3.0
    assert result.trade_components["clawback_score"] == 2.0

    # fundamental_components
    assert result.fundamental_components["stock_quality_score"] == 72.0
    assert result.fundamental_components["growth_score"] == 70.0
    assert result.fundamental_components["profitability_score"] == 60.0
    assert result.fundamental_components["valuation_score"] == 50.0
    assert result.fundamental_components["risk_score"] == 40.0
    assert result.fundamental_components["cashflow_score"] == 30.0
    assert result.fundamental_components["moat_score"] == 20.0
    assert result.fundamental_components["financial_health_score"] == 80.0
    assert result.fundamental_components["management_score"] == 75.0
    assert result.fundamental_components["balance_sheet_score"] == 65.0
    assert result.fundamental_components["profit_sustainability_score"] == 55.0


def test_trade_cap_at_100(scorer: DimensionScorer) -> None:
    inp = _make_input(
        heat_score=50.0,
        scale_score=50.0,
        cornerstone_score=50.0,
        real_money_signal=50.0,
        float_structure_score=50.0,
        sponsor_score=50.0,
        greenshoe_score=50.0,
        clawback_score=50.0,
    )
    result = scorer.calculate(inp)
    # sum = 400, /130*100 = 307.69, capped at 100
    assert result.trade == 100.0


def test_zero_input(scorer: DimensionScorer) -> None:
    inp = ScoringInput(stock_code="00000", company_name="ZeroCo")
    result = scorer.calculate(inp)

    assert result.trade == 0.0
    assert result.fundamental == 0.0
    assert result.valuation == 0.0
    assert result.theme == 0.0
    assert result.data_quality == 0.0

    assert result.trade_components == {
        "heat_score": 0.0,
        "scale_score": 0.0,
        "cornerstone_score": 0.0,
        "real_money_signal": 0.0,
        "float_structure_score": 0.0,
        "sponsor_score": 0.0,
        "greenshoe_score": 0.0,
        "clawback_score": 0.0,
    }

    assert result.fundamental_components == {
        "stock_quality_score": 0.0,
        "growth_score": 0.0,
        "profitability_score": 0.0,
        "valuation_score": 0.0,
        "risk_score": 0.0,
        "cashflow_score": 0.0,
        "moat_score": 0.0,
        "financial_health_score": 0.0,
        "management_score": 0.0,
        "balance_sheet_score": 0.0,
        "profit_sustainability_score": 0.0,
    }


def test_none_scores_treated_as_zero(scorer: DimensionScorer) -> None:
    inp = _make_input(sponsor_score=None, greenshoe_score=None, clawback_score=None)
    result = scorer.calculate(inp)
    expected_trade = (10.0 + 8.0 + 7.0 + 6.0 + 5.0) / 130.0 * 100.0
    assert result.trade == pytest.approx(expected_trade, rel=1e-4)
    assert result.trade_components["sponsor_score"] == 0.0
    assert result.trade_components["greenshoe_score"] == 0.0
    assert result.trade_components["clawback_score"] == 0.0


def test_fundamental_capping(scorer: DimensionScorer) -> None:
    inp = _make_input(stock_quality_score=150.0)
    result = scorer.calculate(inp)
    assert result.fundamental == 100.0

    inp2 = _make_input(stock_quality_score=-20.0)
    result2 = scorer.calculate(inp2)
    assert result2.fundamental == 0.0


def test_valuation_capping(scorer: DimensionScorer) -> None:
    inp = _make_input(valuation_framework_score=110.0)
    result = scorer.calculate(inp)
    assert result.valuation == 100.0

    inp2 = _make_input(valuation_framework_score=-5.0)
    result2 = scorer.calculate(inp2)
    assert result2.valuation == 0.0


def test_theme_capping(scorer: DimensionScorer) -> None:
    inp = _make_input(
        mainline_beta_score=200.0,
        stock_connect_path_score=200.0,
        scarcity_score=200.0,
        sentiment_bonus=200.0,
        macro_bonus=200.0,
    )
    result = scorer.calculate(inp)
    assert result.theme == 100.0

    inp2 = _make_input(
        mainline_beta_score=-50.0,
        stock_connect_path_score=-50.0,
        scarcity_score=-50.0,
        sentiment_bonus=-50.0,
        macro_bonus=-50.0,
    )
    result2 = scorer.calculate(inp2)
    assert result2.theme == 0.0


def test_data_quality_capping(scorer: DimensionScorer) -> None:
    inp = _make_input(data_quality_score=120.0)
    result = scorer.calculate(inp)
    assert result.data_quality == 100.0

    inp2 = _make_input(data_quality_score=-10.0)
    result2 = scorer.calculate(inp2)
    assert result2.data_quality == 0.0
