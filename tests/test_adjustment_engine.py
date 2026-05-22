"""Tests for AdjustmentEngine."""

from __future__ import annotations

import pytest

from ipo_analyzer.scoring.adjustment_engine import AdjustmentEngine
from ipo_analyzer.scoring.models import ScoringInput, DimensionScores


@pytest.fixture
def engine() -> AdjustmentEngine:
    return AdjustmentEngine()


def _make_input(**overrides) -> ScoringInput:
    defaults = {
        "stock_code": "01234",
        "company_name": "TestCo",
        "peer_adj_label": "fair",
        "valuation_label": "合理",
        "pricing_gap_adj": 0.0,
        "risk_penalty": 5.0,
        "risk_categories": {},
        "cornerstone_red_flags": [],
    }
    defaults.update(overrides)
    return ScoringInput(**defaults)


def test_peer_adj_excellent(engine: AdjustmentEngine) -> None:
    inp = _make_input(peer_adj_label="excellent")
    dims = DimensionScores()
    result = engine.calculate(inp, dims)
    assert result.peer_adj == 6.0


def test_peer_adj_fair(engine: AdjustmentEngine) -> None:
    inp = _make_input(peer_adj_label="fair")
    dims = DimensionScores()
    result = engine.calculate(inp, dims)
    assert result.peer_adj == 0.0


def test_peer_adj_overvalued(engine: AdjustmentEngine) -> None:
    inp = _make_input(peer_adj_label="overvalued")
    dims = DimensionScores()
    result = engine.calculate(inp, dims)
    assert result.peer_adj == -6.0


def test_peer_adj_clearly_overvalued(engine: AdjustmentEngine) -> None:
    inp = _make_input(peer_adj_label="clearly_overvalued")
    dims = DimensionScores()
    result = engine.calculate(inp, dims)
    assert result.peer_adj == -6.0


def test_peer_adj_unknown(engine: AdjustmentEngine) -> None:
    inp = _make_input(peer_adj_label="something_else")
    dims = DimensionScores()
    result = engine.calculate(inp, dims)
    assert result.peer_adj == 0.0


def test_val_penalty_labels(engine: AdjustmentEngine) -> None:
    cases = [
        ("很贵", -5.0),
        ("偏贵", -3.0),
        ("合理", 0.0),
        ("便宜", 2.0),
        ("unknown", 0.0),
    ]
    for label, expected in cases:
        inp = _make_input(valuation_label=label)
        dims = DimensionScores()
        result = engine.calculate(inp, dims)
        assert result.val_penalty == expected, f"Failed for label {label}"


def test_pricing_gap_adj_pass_through(engine: AdjustmentEngine) -> None:
    inp = _make_input(pricing_gap_adj=2.5)
    dims = DimensionScores()
    result = engine.calculate(inp, dims)
    assert result.pricing_gap_adj == 2.5


def test_risk_penalty_no_severe_categories(engine: AdjustmentEngine) -> None:
    inp = _make_input(risk_penalty=5.0, risk_categories={"market": ["volatile"]})
    dims = DimensionScores()
    result = engine.calculate(inp, dims)
    assert result.risk_penalty == 5.0


def test_risk_penalty_with_severe_categories(engine: AdjustmentEngine) -> None:
    inp = _make_input(
        risk_penalty=5.0,
        risk_categories={
            "legal": ["lawsuit"],
            "regulatory": ["fine"],
            "accounting": ["restatement"],
        },
    )
    dims = DimensionScores()
    result = engine.calculate(inp, dims)
    # 5.0 + 2.0*3 = 11.0
    assert result.risk_penalty == 11.0


def test_risk_penalty_cap_at_20(engine: AdjustmentEngine) -> None:
    inp = _make_input(
        risk_penalty=18.0,
        risk_categories={
            "legal": ["lawsuit"],
            "regulatory": ["fine"],
        },
    )
    dims = DimensionScores()
    result = engine.calculate(inp, dims)
    # 18.0 + 4.0 = 22.0, capped at 20.0
    assert result.risk_penalty == 20.0


def test_risk_penalty_empty_severe_category(engine: AdjustmentEngine) -> None:
    inp = _make_input(
        risk_penalty=5.0,
        risk_categories={
            "legal": [],
            "regulatory": ["fine"],
        },
    )
    dims = DimensionScores()
    result = engine.calculate(inp, dims)
    # 5.0 + 2.0 = 7.0
    assert result.risk_penalty == 7.0


def test_cornerstone_penalty(engine: AdjustmentEngine) -> None:
    inp = _make_input(cornerstone_red_flags=["flag1", "flag2", "flag3"])
    dims = DimensionScores()
    result = engine.calculate(inp, dims)
    # 3 * 3.0 = 9.0
    assert result.cornerstone_penalty == 9.0


def test_cornerstone_penalty_cap_at_15(engine: AdjustmentEngine) -> None:
    inp = _make_input(cornerstone_red_flags=["f"] * 10)
    dims = DimensionScores()
    result = engine.calculate(inp, dims)
    # 10 * 3.0 = 30.0, capped at 15.0
    assert result.cornerstone_penalty == 15.0


def test_total_adjustment(engine: AdjustmentEngine) -> None:
    inp = _make_input(
        peer_adj_label="excellent",
        valuation_label="便宜",
        pricing_gap_adj=1.0,
        risk_penalty=4.0,
        risk_categories={"legal": ["suit"]},
        cornerstone_red_flags=["flag1"],
    )
    dims = DimensionScores()
    result = engine.calculate(inp, dims)

    assert result.peer_adj == 6.0
    assert result.val_penalty == 2.0
    assert result.pricing_gap_adj == 1.0
    assert result.risk_penalty == 6.0  # 4.0 + 2.0
    assert result.cornerstone_penalty == 3.0  # 1 * 3.0

    # total = peer_adj + val_penalty + pricing_gap_adj - risk_penalty - cornerstone_penalty
    expected_total = 6.0 + 2.0 + 1.0 - 6.0 - 3.0
    assert result.total == expected_total
