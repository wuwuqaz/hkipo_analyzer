#!/usr/bin/env python3
"""评分偏差修复回归测试 — 2026-05-09

运行:
    python3 -m pytest tests/test_scoring_fixes.py -v
    # 或
    python3 tests/test_scoring_fixes.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ipo_analyzer.peer_comps import _split_peer_samples
# ScoringSystem lives in ipo_analyzer/scoring.py (module), not the scoring/ package.
# Import via importlib to avoid package/shadowing ambiguity.
import importlib.util
_scoring_spec = importlib.util.spec_from_file_location(
    "ipo_analyzer.scoring_legacy",
    os.path.join(os.path.dirname(__file__), "..", "ipo_analyzer", "scoring.py"),
)
_scoring_mod = importlib.util.module_from_spec(_scoring_spec)
_scoring_spec.loader.exec_module(_scoring_mod)
ScoringSystem = _scoring_mod.ScoringSystem
from ipo_analyzer.industry_router import classify_company
from ipo_analyzer.analyzers import ValuationAnalyzer


def test_peer_fallback_when_only_one_hk_peer():
    """1 个 HK peer + 3 个 non-HK listed peers 时，quantitative_peer_count 应 >= 2"""
    mock_peers = [
        {"name": "HK Peer", "type": "listed", "ticker": "1234.HK", "ps": 5.0, "pe": 20.0, "data_quality": "high", "needs_refresh": False},
        {"name": "US Peer A", "type": "listed", "ticker": "AAPL", "ps": 4.0, "pe": 18.0, "data_quality": "high", "needs_refresh": False},
        {"name": "US Peer B", "type": "listed", "ticker": "MSFT", "ps": 6.0, "pe": 22.0, "data_quality": "high", "needs_refresh": False},
        {"name": "CN Peer", "type": "listed", "ticker": "600519.SH", "ps": 3.0, "pe": 15.0, "data_quality": "high", "needs_refresh": False},
    ]
    quant, qual, basis, q_count, ql_count = _split_peer_samples(mock_peers)
    assert q_count >= 2, f"期望 quantitative_peer_count >= 2，实际 {q_count}"
    assert basis == "composite_listed_peers", f"期望 fallback 到 composite_listed_peers，实际 {basis}"
    # 不应触发强样本不足
    assert len(quant) >= 2
    print(f"✅ test_peer_fallback_when_only_one_hk_peer passed (q_count={q_count}, basis={basis})")


def test_biotech_b_suffix_forces_special_valuation():
    """-B 后缀应强制识别为 biotech 并使用特殊估值框架"""
    prospectus_info = {
        "extracted_company_name": "TestBio-B",
        "company_name_aliases": ["TestBio"],
        "sector": "unknown",
        "revenue": 50,
        "net_profit": -200,
        "market_cap_hkd_million": 5000,
        "financial_currency": "RMB",
        "_extracted_text": "biotech pipeline",
    }
    profile = classify_company(prospectus_info, "biotech pipeline")
    assert profile.is_biotech is True, "-B 后缀应强制 is_biotech=True"
    assert profile.sector == "healthcare", "-B 后缀应强制 sector=healthcare"

    val = ValuationAnalyzer().analyze(prospectus_info, "biotech pipeline")
    assert val.get("valuation_framework_type") == "18A_biotech", \
        f"应使用 18A_biotech 框架，实际 {val.get('valuation_framework_type')}"
    print("✅ test_biotech_b_suffix_forces_special_valuation passed")


def test_w_suffix_not_biotech_keyword():
    """-W 后缀不应作为 biotech 依据"""
    prospectus_info = {
        "extracted_company_name": "TestTech-W",
        "sector": "hardtech",
        "revenue": 500,
        "net_profit": 100,
        "_extracted_text": "technology platform",
    }
    profile = classify_company(prospectus_info, "technology platform")
    assert profile.is_biotech is False, "-W 后缀不应触发 biotech"
    assert profile.sector == "hardtech", "-W 不应改变 sector"
    print("✅ test_w_suffix_not_biotech_keyword passed")


def test_low_revenue_biotech_ps_not_hard_penalty():
    """low_revenue_biotech 且 revenue_too_small_for_ps=True 时，PS 只提示，不硬扣"""
    ipo = {"over_sub_ratio": 20.0, "total_fund": 2.0, "market_heat": "温和"}
    prospectus_info = {
        "gross_margin": 80,
        "profitable": False,
        "revenue": 30,
        "revenue_y1": 10,
        "sector": "healthcare",
        "extracted_company_name": "TestBio-B",
        "cornerstone_analysis": {"score": 70, "label": "A级", "has_cornerstone_section": True},
        "valuation": {
            "ps_ratio": 150.0,
            "pe_ratio": None,
            "valuation_label": "PS失真，仅作参考",
            "relative_valuation_label": "明显偏贵",
            "revenue_too_small_for_ps": True,
            "revenue_quality": "standard",
        },
        "peer_comparison": {
            "peer_score": 8,
            "scarcity_score": 7,
            "valuation_position": "明显偏贵",
            "quantitative_peer_count": 3,
            "relative_ps_premium_pct": 120,
        },
    }
    result = ScoringSystem().calculate(ipo, prospectus_info, signal_components={})
    reasons_text = " ".join(result.get("reasons", []))
    # 不应出现硬扣分描述
    assert "同行估值明显偏贵" not in reasons_text, "低收入biotech不应因PS硬扣peer_adj"
    # 应出现提示
    assert "PS失真" in reasons_text or "低收入biotech PS失真" in reasons_text, "应提示PS失真"
    print("✅ test_low_revenue_biotech_ps_not_hard_penalty passed")


def test_currency_growth_uses_same_fx_basis():
    """收入增长率必须使用同一币种口径（HKD）"""
    prospectus_info = {
        "revenue": 100,  # RMB million
        "revenue_y1": 80,  # RMB million
        "financial_currency": "RMB",
        "market_cap_hkd_million": 5000,
        "net_profit": -50,
        "sector": "healthcare",
        "extracted_company_name": "TestBio-B",
        "_extracted_text": "biotech",
        "peer_comparison": {"valuation_position": "样本不足，仅作定性参考"},
    }
    val = ValuationAnalyzer().analyze(prospectus_info, "biotech")
    revenue_hkd = val.get("revenue_hkd_million")
    revenue_prev_hkd = val.get("revenue_previous_hkd_million")
    assert revenue_hkd is not None, "应输出 revenue_hkd_million"
    assert revenue_prev_hkd is not None, "应输出 revenue_previous_hkd_million"
    # 增长率计算基于 HKD 口径
    (revenue_hkd - revenue_prev_hkd) / revenue_prev_hkd
    reasons = val.get("valuation_reasons", [])
    growth_reason = [r for r in reasons if "收入增速" in r]
    assert growth_reason, f"应包含收入增速说明，实际 reasons={reasons}"
    print(f"✅ test_currency_growth_uses_same_fx_basis passed (growth_reason={growth_reason[0]})")


def test_score_trace_contains_all_adjustments():
    """score_trace 应包含所有调整项"""
    ipo = {"over_sub_ratio": 100.0, "total_fund": 5.0, "market_heat": "热门"}
    prospectus_info = {
        "gross_margin": 40,
        "profitable": True,
        "revenue": 500,
        "revenue_y1": 400,
        "sector": "hardtech",
        "cornerstone_analysis": {"score": 70, "label": "A级", "has_cornerstone_section": True},
        "valuation": {"pe_ratio": 25.0, "ps_ratio": 3.0, "valuation_label": "合理"},
        "peer_comparison": {"peer_score": 10, "scarcity_score": 6, "valuation_position": "合理"},
    }
    result = ScoringSystem().calculate(ipo, prospectus_info, signal_components={})
    score_trace = result.get("score_trace")
    assert score_trace is not None, "必须有 score_trace"
    assert "raw_weighted_score" in score_trace, "score_trace 应包含 raw_weighted_score"
    assert "peer_adj" in score_trace, "score_trace 应包含 peer_adj"
    assert "val_penalty" in score_trace, "score_trace 应包含 val_penalty"
    assert "cap_reason" in score_trace, "score_trace 应包含 cap_reason"
    assert "final_score_before_cap" in score_trace, "score_trace 应包含 final_score_before_cap"
    assert "final_score_after_cap" in score_trace, "score_trace 应包含 final_score_after_cap"
    print("✅ test_score_trace_contains_all_adjustments passed")


def test_no_prospectus_market_only_mode():
    """parse_success=False 时 analysis_mode 应为 market_only"""
    from ipo_analyzer.core import _run_scoring_pipeline
    ipo_data = {
        "company_name": "TestCo",
        "hk_code": "1234",
        "over_sub_ratio": 50.0,
        "over_sub_ratio_source": "actual",
        "market_heat": "热门",
        "total_fund": 5.0,
    }
    prospectus_info = {
        "parse_success": False,
        "parse_error": "PDF解析失败",
        "sector": "unknown",
    }
    result = _run_scoring_pipeline(ipo_data, prospectus_info, "")
    assert result.get("analysis_mode") == "market_only", \
        f"parse_success=False 时应为 market_only，实际 {result.get('analysis_mode')}"
    reasons = result.get("score_reasons", [])
    assert any("仅热度参考" in r for r in reasons), "应提示仅热度参考"
    print("✅ test_no_prospectus_market_only_mode passed")


def test_no_double_count_peer_overvaluation_penalty():
    """valuation_framework 已包含 relative valuation 时，不重复扣同一类 PS/同行偏贵"""
    ipo = {"over_sub_ratio": 20.0, "total_fund": 2.0, "market_heat": "温和"}
    prospectus_info = {
        "gross_margin": 35,
        "profitable": True,
        "revenue": 300,
        "revenue_y1": 250,
        "sector": "hardtech",
        "cornerstone_analysis": {"score": 70, "label": "A级", "has_cornerstone_section": True},
        "valuation": {
            "pe_ratio": 30.0,
            "ps_ratio": 8.0,
            "valuation_label": "偏贵",
            "relative_valuation_label": "合理",  # 相对估值已合理
            "revenue_too_small_for_ps": False,
        },
        "peer_comparison": {
            "peer_score": 10,
            "scarcity_score": 6,
            "valuation_position": "合理",
            "quantitative_peer_count": 3,
            "relative_ps_premium_pct": 10,
        },
    }
    result = ScoringSystem().calculate(ipo, prospectus_info, signal_components={})
    # 相对估值已合理时，不应因绝对估值偏贵而重扣
    assert result.get("val_penalty", 0) >= -1, \
        f"relative_valuation_label=合理时不应重扣 val_penalty，实际 {result.get('val_penalty')}"
    print(f"✅ test_no_double_count_peer_overvaluation_penalty passed (val_penalty={result.get('val_penalty')})")


if __name__ == "__main__":
    test_peer_fallback_when_only_one_hk_peer()
    test_biotech_b_suffix_forces_special_valuation()
    test_w_suffix_not_biotech_keyword()
    test_low_revenue_biotech_ps_not_hard_penalty()
    test_currency_growth_uses_same_fx_basis()
    test_score_trace_contains_all_adjustments()
    test_no_prospectus_market_only_mode()
    test_no_double_count_peer_overvaluation_penalty()
    print("\n" + "=" * 60)
    print("✅ 所有评分偏差修复回归测试通过")
    print("=" * 60)
