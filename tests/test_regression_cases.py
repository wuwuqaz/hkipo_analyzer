#!/usr/bin/env python3
"""回归测试 — 0.4.0-alpha 稳定性修复验证

运行:
    python3 -m pytest tests/test_regression_cases.py -v
    # 或
    python3 tests/test_regression_cases.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import copy
from ipo_analyzer.peer_comps import (
    _filter_peer_candidates,
    _build_issuer_aliases,
    _split_peer_samples,
    PeerComparableAnalyzer,
)
from ipo_analyzer.analyzers import ValuationAnalyzer
from ipo_analyzer.models import IPOData, ValuationResult, PeerComparisonResult, ProspectusInfo


def test_issuer_alias_not_in_unmatched():
    """发行人别名重叠的 candidate 不应进入 unmatched_peer_candidates"""
    ipo = {"company_name": "LdsRobotics Limited", "shortname": "LdsRobotics"}
    pi = {"extracted_company_name": "LdsRobotics Limited", "company_name_aliases": ["LdsRobotics"]}
    issuer_aliases = _build_issuer_aliases(pi, ipo)

    candidates = [
        {"name": "LdsRobotics Technology", "confidence": "high", "reason": "test", "source": "test"},
        {"name": "True Peer Company", "confidence": "high", "reason": "test", "source": "test"},
    ]
    filtered = _filter_peer_candidates(candidates, [], issuer_aliases)
    assert "LdsRobotics Technology" not in filtered, "发行人别名重叠的 candidate 应被排除"
    assert "True Peer Company" in filtered, "真实同行应保留"
    print("✅ test_issuer_alias_not_in_unmatched passed")


def test_quantitative_peers_less_than_two_weak_conclusion():
    """quantitative peers 少于 2 家时不输出强相对估值结论"""
    ipo = {
        "company_name": "TestCo",
        "hk_code": "1234",
        "prospectus_info": {
            "revenue": 500,
            "revenue_y1": 400,
            "net_profit": 50,
            "gross_margin": 35,
            "market_cap_hkd_million": 10000,
            "offer_price": 10.0,
            "pro_forma_NTA_per_share_HKD": 2.0,
            "sector": "hardtech",
            "business_breakdown": {"segments": [], "growth_source": "test"},
            "rnd_pipeline": {"technology_moat_score": 5, "pipeline_quality_label": "中"},
            "cornerstone_analysis": {"cornerstone_investors": [], "matched_investors": [], "score": 30},
        }
    }
    pi = ipo["prospectus_info"]
    text = "We compete with listed robotics companies."

    analyzer = PeerComparableAnalyzer()
    result = analyzer.analyze(pi, text, ipo)

    q_count = result.get("quantitative_peer_count", 0)
    if q_count < 2:
        vp = result.get("valuation_position", "")
        assert vp == "样本不足，仅作定性参考", f"期望'样本不足，仅作定性参考', 实际: {vp}"
        assert result.get("peer_score", 0) <= 5, f"peer_score 应受限: {result.get('peer_score')}"
        assert result.get("peer_sample_warning") is not None, "应有 peer_sample_warning"
    print(f"✅ test_quantitative_peers_less_than_two_weak_conclusion passed (q_count={q_count})")


def test_private_low_quality_not_in_quantitative():
    """private / low quality / needs_refresh 不进入 quantitative peers"""
    mock_peers = [
        {"name": "Listed A", "type": "listed", "ps": 5.0, "pe": 20.0, "data_quality": "high", "needs_refresh": False},
        {"name": "Private B", "type": "private", "ps": 3.0, "pe": 15.0, "data_quality": "high", "needs_refresh": False},
        {"name": "Listed C LowQ", "type": "listed", "ps": 4.0, "pe": 18.0, "data_quality": "low", "needs_refresh": False},
        {"name": "Listed D Stale", "type": "listed", "ps": 6.0, "pe": 22.0, "data_quality": "high", "needs_refresh": True},
        {"name": "Listed E NoMetrics", "type": "listed", "ps": None, "pe": None, "market_cap_hkd_million": None, "data_quality": "moderate", "needs_refresh": False},
    ]
    quant, qual = _split_peer_samples(mock_peers)
    quant_names = {p["name"] for p in quant}
    qual_names = {p["name"] for p in qual}

    assert "Listed A" in quant_names, "高质量 listed 应进入 quantitative"
    assert "Private B" in qual_names, "private 不应进入 quantitative"
    assert "Listed C LowQ" in qual_names, "low quality 不应进入 quantitative"
    assert "Listed D Stale" in qual_names, "needs_refresh 不应进入 quantitative"
    assert "Listed E NoMetrics" in qual_names, "无 metrics 不应进入 quantitative"
    print("✅ test_private_low_quality_not_in_quantitative passed")


def test_loss_making_valuation_not_missing():
    """未盈利公司估值标签不应为'缺失'"""
    prospectus_info = {
        "revenue": 200,
        "revenue_y1": 100,
        "net_profit": -50,
        "gross_margin": 40,
        "market_cap_hkd_million": 3000,
        "offer_price": 10.0,
        "pro_forma_NTA_per_share_HKD": 2.0,
        "sector": "healthcare",
        "financial_currency": "RMB",
        "rd_expense": 80,
        "_extracted_text": "18A biotech clinical stage",
        "business_breakdown": {"segments": [], "growth_source": "test"},
        "rnd_pipeline": {"technology_moat_score": 6, "pipeline_quality_label": "中"},
        "cornerstone_analysis": {"cornerstone_investors": [], "matched_investors": [], "score": 30},
        "peer_comparison": {"valuation_position": "样本不足，仅作定性参考"},
    }
    ipo = {"company_name": "TestBio", "hk_code": "9999"}
    val = ValuationAnalyzer().analyze(prospectus_info, ipo)
    label = val.get("valuation_label", "")
    assert label != "缺失", f"亏损公司估值不应为'缺失': {label}"
    assert label in ("PS辅助估值", "PS失真，仅作参考", "管线阶段估值", "数据不足，需人工核对"), \
        f"unexpected label: {label}"
    assert val.get("net_profit_hkd_million") is not None, "net_profit_hkd_million 应存在"
    print(f"✅ test_loss_making_valuation_not_missing passed (label={label})")


def test_new_fields_persist_through_from_dict():
    """新增字段经过 IPOData.from_dict 后不丢失"""
    # 构造一个包含所有新增字段的 dict
    raw = {
        "company_name": "TestCo",
        "hk_code": "1234",
        "prospectus_info": {
            "revenue": 100,
            "net_profit": 10,
            "sector": "hardtech",
            "valuation": {
                "pe_ratio": 15.0,
                "ps_ratio": 3.0,
                "net_profit_hkd_million": 10.8,
                "adjusted_profit_hkd_million": 12.0,
                "financial_currency": "RMB",
                "revenue_too_small_for_ps": False,
            },
            "peer_comparison": {
                "subsector": "robotics_visual_perception",
                "quantitative_peers": [{"name": "Peer A", "type": "listed"}],
                "qualitative_peers": [{"name": "Peer B", "type": "private"}],
                "quantitative_peer_count": 1,
                "qualitative_peer_count": 1,
                "peer_sample_warning": "样本不足",
            },
        },
    }
    obj = IPOData.from_dict(raw)
    assert obj is not None
    pi = obj.prospectus_info
    assert pi is not None
    val = pi.valuation
    assert val is not None
    assert val.net_profit_hkd_million == 10.8, f"net_profit_hkd_million 丢失: {val.net_profit_hkd_million}"
    assert val.adjusted_profit_hkd_million == 12.0, f"adjusted_profit_hkd_million 丢失"
    assert val.financial_currency == "RMB", f"financial_currency 丢失"

    pc = pi.peer_comparison
    assert pc is not None
    assert pc.quantitative_peer_count == 1, f"quantitative_peer_count 丢失"
    assert pc.qualitative_peer_count == 1, f"qualitative_peer_count 丢失"
    assert pc.peer_sample_warning == "样本不足", f"peer_sample_warning 丢失"
    assert len(pc.quantitative_peers) == 1, f"quantitative_peers 丢失"
    assert len(pc.qualitative_peers) == 1, f"qualitative_peers 丢失"

    # 反向 to_dict 也应保留
    d = obj.to_dict()
    assert d["prospectus_info"]["valuation"]["net_profit_hkd_million"] == 10.8
    assert d["prospectus_info"]["peer_comparison"]["quantitative_peer_count"] == 1
    print("✅ test_new_fields_persist_through_from_dict passed")


if __name__ == "__main__":
    test_issuer_alias_not_in_unmatched()
    test_quantitative_peers_less_than_two_weak_conclusion()
    test_private_low_quality_not_in_quantitative()
    test_loss_making_valuation_not_missing()
    test_new_fields_persist_through_from_dict()
    print("\n" + "=" * 60)
    print("✅ 所有回归测试通过")
    print("=" * 60)
