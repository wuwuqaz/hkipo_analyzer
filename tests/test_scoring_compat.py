import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ScoringSystem lives in ipo_analyzer/scoring.py (module), not the scoring/ package.
# Import via importlib to avoid package/shadowing ambiguity.
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "ipo_analyzer.scoring_legacy",
    os.path.join(os.path.dirname(__file__), "..", "ipo_analyzer", "scoring.py"),
)
_scoring_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_scoring_mod)
ScoringSystem = _scoring_mod.ScoringSystem


def test_compat_layer_returns_expected_keys():
    system = ScoringSystem()
    ipo = {"hk_code": "09999", "company_name": "测试", "margin_total": 100.0}
    prospectus_info = {
        "sector": "hardtech",
        "revenue": 500.0,
        "stock_quality_score": 70.0,
        "signal_components": {"heat_score": 30.0, "data_quality": 80.0},
        "valuation": {"valuation_framework_score": 60.0},
        "risk_analysis": {"total_penalty": 5.0, "risks": {}},
    }
    result = system.calculate(ipo, prospectus_info)

    # Old fields must exist
    assert "score" in result
    assert "ipo_trade_score" in result
    assert "subscription_recommendation" in result
    assert "reasons" in result

    # New fields should be added by compat layer
    assert "score_trace_structured" in result
    assert "weight_profile" in result
    assert result["weight_profile"] in ("live_heat", "prospectus_only", "optimized")
