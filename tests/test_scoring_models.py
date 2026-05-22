import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ipo_analyzer.scoring.models import (
    ScoringInput,
    DimensionScores,
    Adjustments,
    ScoreTrace,
    WeightProfile,
)


def test_scoring_input_defaults():
    inp = ScoringInput(stock_code="09999", company_name="测试")
    assert inp.heat_score == 0.0
    assert inp.is_biotech is False
    assert inp.cornerstone_investors == []


def test_adjustments_total():
    adj = Adjustments(peer_adj=3.0, val_penalty=-2.0, pricing_gap_adj=1.0, risk_penalty=5.0, cornerstone_penalty=2.0)
    assert adj.total == 3.0 + (-2.0) + 1.0 - 5.0 - 2.0


def test_score_trace_record():
    trace = ScoreTrace()
    trace.record("step1", {"a": 1}, {"b": 2})
    assert len(trace.steps) == 1
    assert trace.steps[0].step_name == "step1"


def test_weight_profile():
    wp = WeightProfile(name="live_heat", weights={"trade": 0.25, "fundamental": 0.35})
    assert wp.weights["trade"] == 0.25
