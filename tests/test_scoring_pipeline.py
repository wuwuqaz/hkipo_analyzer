"""Tests for ScoringPipeline."""

from __future__ import annotations

import pytest

from ipo_analyzer.scoring.pipeline import ScoringPipeline
from ipo_analyzer.scoring.models import ScoringInput, QualityDimensions


@pytest.fixture
def pipeline() -> ScoringPipeline:
    return ScoringPipeline()


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
        "peer_adj_label": "fair",
        "pricing_gap_adj": 0.0,
        "valuation_label": "合理",
        "mainline_beta_score": 50.0,
        "stock_connect_path_score": 60.0,
        "scarcity_score": 40.0,
        "sentiment_bonus": 10.0,
        "macro_bonus": 20.0,
        "data_quality_score": 88.0,
        "risk_penalty": 5.0,
        "risk_categories": {},
        "cornerstone_red_flags": [],
    }
    defaults.update(overrides)
    return ScoringInput(**defaults)


def test_pipeline_live_heat_profile(pipeline: ScoringPipeline) -> None:
    inp = _make_input()
    result = pipeline.run(inp)

    assert result.weight_profile == "live_heat"
    assert 0 <= result.final_score <= 100
    assert result.score_trace is not None
    assert len(result.score_trace.steps) == 7

    # Check dimension scores are populated
    assert result.trade_score >= 0
    assert result.fundamental_score >= 0
    assert result.valuation_score >= 0
    assert result.theme_score >= 0
    assert result.data_quality_score >= 0

    # Strategy scores
    assert 0 <= result.long_term_score <= 100
    assert 0 <= result.strict_ipo_score <= 100

    # Recommendation
    assert result.recommendation in ("强烈推荐", "推荐", "中性", "谨慎", "回避")
    assert isinstance(result.reasons, list)
    assert isinstance(result.dimension_grades, dict)
    assert set(result.dimension_grades.keys()) == {"trade", "fundamental", "valuation", "theme", "data_quality"}


def test_pipeline_prospectus_only_profile(pipeline: ScoringPipeline) -> None:
    inp = _make_input(heat_score=0.0, real_money_signal=0.0)
    result = pipeline.run(inp)

    assert result.weight_profile == "prospectus_only"
    assert 0 <= result.final_score <= 100
    assert len(result.score_trace.steps) == 7


def test_score_trace_has_seven_steps(pipeline: ScoringPipeline) -> None:
    inp = _make_input()
    result = pipeline.run(inp)

    step_names = [step.step_name for step in result.score_trace.steps]
    expected = [
        "dimension_scorer",
        "adjustment_engine",
        "weight_profile",
        "apply_adjustments",
        "strategy_scorer",
        "cap_final_score",
        "recommender",
    ]
    assert step_names == expected


def test_recommendation_and_grades(pipeline: ScoringPipeline) -> None:
    # High score input to get "强烈推荐"
    inp = _make_input(
        heat_score=80.0,
        scale_score=80.0,
        cornerstone_score=80.0,
        real_money_signal=80.0,
        float_structure_score=80.0,
        stock_quality_score=90.0,
        valuation_framework_score=90.0,
        mainline_beta_score=80.0,
        stock_connect_path_score=80.0,
        scarcity_score=80.0,
        sentiment_bonus=80.0,
        macro_bonus=80.0,
        data_quality_score=95.0,
        risk_penalty=0.0,
        peer_adj_label="excellent",
        quality_dimensions=QualityDimensions(
            growth_score=80.0,
            profitability_score=90.0,
            valuation_score=85.0,
            risk_score=40.0,
            cashflow_score=80.0,
            moat_score=80.0,
            financial_health_score=90.0,
            management_score=85.0,
            balance_sheet_score=85.0,
            profit_sustainability_score=80.0,
        ),
    )
    result = pipeline.run(inp)

    assert result.recommendation == "强烈推荐"
    assert "交易热度强劲" in result.reasons
    assert "基本面优质" in result.reasons
    assert "估值相对同行有优势" in result.reasons
    assert "长期投资价值较高" in result.reasons

    # All grades should be high
    for grade in result.dimension_grades.values():
        assert grade in ("A+", "A", "A-")


def test_low_score_recommendation(pipeline: ScoringPipeline) -> None:
    inp = _make_input(
        heat_score=0.0,
        scale_score=0.0,
        cornerstone_score=0.0,
        real_money_signal=0.0,
        float_structure_score=0.0,
        stock_quality_score=10.0,
        valuation_framework_score=10.0,
        mainline_beta_score=0.0,
        stock_connect_path_score=0.0,
        scarcity_score=0.0,
        sentiment_bonus=0.0,
        macro_bonus=0.0,
        data_quality_score=10.0,
        risk_penalty=15.0,
        peer_adj_label="overvalued",
    )
    result = pipeline.run(inp)

    assert result.recommendation in ("谨慎", "回避")
    assert "交易热度不足" in result.reasons
    assert "基本面较弱" in result.reasons
    assert "估值相对同行偏高" in result.reasons
    assert "风险因子较多，需注意" in result.reasons


def test_pipeline_zero_input(pipeline: ScoringPipeline) -> None:
    inp = ScoringInput(stock_code="00000", company_name="ZeroCo")
    result = pipeline.run(inp)

    assert result.weight_profile == "prospectus_only"
    assert result.final_score == 0.0
    assert result.recommendation == "回避"
    assert len(result.score_trace.steps) == 7
