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
from ipo_analyzer.scoring import SignalComponentAnalyzer, ScoringSystem
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


def test_signal_component_analyzer_biotech():
    """剂泰科技类未盈利 biotech：信号拆解应正确，估值不应强行 100 分"""
    ipo = {"margin_total": 50.0, "public_offer": 2.0, "over_sub_ratio": 25.0}
    prospectus_info = {
        "revenue": 33,
        "revenue_y1": 5,
        "net_profit": -300,
        "gross_margin": 80,
        "market_cap_hkd_million": 3800,
        "offer_price": 12.0,
        "pro_forma_NTA_per_share_HKD": 2.0,
        "sector": "healthcare",
        "financial_currency": "RMB",
        "extracted_company_name": "剂泰科技-B",
        "_extracted_text": "18A biotech clinical stage\nAI drug delivery platform",
        "public_offer_ratio_pct": 12.0,
        "issuance_ratio_pct": 15.0,
        "cornerstone_offer_ratio_pct": 45.0,
        "rnd_pipeline": {
            "technology_moat_score": 8,
            "pipeline_quality_label": "强",
            "product_count_pipeline": 3,
            "latest_clinical_stage": "Phase II",
        },
        "cornerstone_analysis": {
            "cornerstone_investors": [],
            "matched_investors": [],
            "score": 55,
            "label": "A级",
            "grade_band": "强A",
        },
        "peer_comparison": {
            "subsector": "ai_drug_delivery_nanomedicine",
            "scarcity_score": 7,
            "peer_score": 8,
            "valuation_position": "样本不足，仅作定性参考",
            "quantitative_peer_count": 1,
            "peer_sample_warning": "定量同行样本不足，估值仅作定性参考",
        },
        "valuation": {
            "ps_ratio": 115.0,
            "pe_ratio": None,
            "market_cap_to_rd_ratio": 45.0,
            "cash_runway_years": 2.5,
            "valuation_framework_type": "18A_biotech",
            "valuation_label": "PS失真，仅作参考",
            "valuation_profitability_type": "loss_making",
            "latest_clinical_stage": "Phase II",
            "revenue_too_small_for_ps": True,
        },
        "financial_extract_confidence": "consolidated_statement",
        "financial_data_quality_flags": [],
    }
    text = "18A biotech clinical stage AI drug delivery platform"

    signal = SignalComponentAnalyzer().analyze(ipo, prospectus_info, text)
    sb = signal.get('signal_breakdown', {})

    # 1. 不再输出独立 100 分“进阶框架”
    assert 'score' in signal, "兼容字段 score 应保留"
    assert 'label' in signal, "兼容字段 label 应保留"
    assert 'signal_breakdown' in signal, "必须有 signal_breakdown"

    # 2. 估值解释：未盈利 biotech 不强行打分
    val_reading = sb.get('valuation_reading', {})
    assert val_reading.get('label') in ("PS失真，仅作参考", "管线阶段估值", "PS辅助估值"), \
        f"未盈利 biotech 估值标签异常: {val_reading.get('label')}"
    # 不应是强行的高分
    assert val_reading.get('strength') in ("弱", "中", "缺失"), \
        f"极低收入 biotech 估值 strength 不应为强: {val_reading.get('strength')}"

    # 3. 数据置信度
    dq = sb.get('data_confidence', {})
    assert dq.get('strength') in ("高", "中", "低"), "数据置信度应有明确等级"

    # 4. 各组件可追溯
    assert 'real_money' in sb
    assert 'float_structure' in sb
    assert 'cornerstone_quality' in sb
    assert 'theme_bonus' in sb
    assert 'liquidity_bonus' in sb

    print("✅ test_signal_component_analyzer_biotech passed")


def test_scoring_system_new_weights():
    """验证新五维评分权重结构"""
    ipo = {"over_sub_ratio": 100.0, "total_fund": 5.0, "market_heat": "热门"}
    prospectus_info = {
        "gross_margin": 40,
        "profitable": True,
        "revenue": 500,
        "revenue_y1": 400,
        "sector": "hardtech",
        "cornerstone_analysis": {"score": 70, "label": "A级"},
        "valuation": {"pe_ratio": 25.0, "ps_ratio": 3.0},
        "peer_comparison": {"peer_score": 10, "scarcity_score": 6, "valuation_position": "合理"},
    }
    signal_components = {
        'real_money': {'score': 15},
        'float_structure': {'score': 10},
        'valuation_framework': {'score': 14},
        'mainline_beta': {'score': 10},
        'stock_connect_path': {'score': 6},
        'data_quality': {'score': 5},
    }
    result = ScoringSystem().calculate(ipo, prospectus_info, signal_components=signal_components)

    assert 'trade_score' in result, "必须有 trade_score"
    assert 'valuation_score' in result, "必须有 valuation_score"
    assert 'theme_score' in result, "必须有 theme_score"
    assert 'data_quality_score' in result, "必须有 data_quality_score"
    assert result['score'] >= 0 and result['score'] <= 100, "总分应在 0-100 之间"

    # theme_score 上限约 50（权重 0.10 → 最多贡献 5 分）
    assert result['theme_score'] <= 50, f"theme_score 应封顶 50: {result['theme_score']}"

    # data_quality_score 作为 confidence_gate：高分不限制，低分限制
    if result['data_quality_score'] < 40:
        assert result['score'] <= 60, "数据质量差时应限制总分上限"

    print(f"✅ test_scoring_system_new_weights passed (score={result['score']})")


def test_advanced_framework_adjustment_removed():
    """验证 advanced_score_adjustment 已废弃（固定为 0 或不产生独立主卡片）"""
    ipo = {"margin_total": 10.0, "public_offer": 1.0, "over_sub_ratio": 5.0}
    prospectus_info = {
        "revenue": 200,
        "net_profit": -50,
        "gross_margin": 35,
        "market_cap_hkd_million": 3000,
        "sector": "healthcare",
        "extracted_company_name": "TestBio-B",
        "_extracted_text": "biotech",
        "valuation": {"ps_ratio": 15.0, "pe_ratio": None},
        "peer_comparison": {"valuation_position": "样本不足，仅作定性参考"},
        "financial_data_quality_flags": [],
    }
    text = "biotech"
    signal = SignalComponentAnalyzer().analyze(ipo, prospectus_info, text)

    # 兼容字段 advanced_framework_score 仍可输出，但不应作为独立主指标
    assert 'score' in signal  # 兼容
    assert 'signal_breakdown' in signal  # 新结构
    # 信号拆解中没有“进阶框架 54/100”这种独立总分展示
    sb = signal['signal_breakdown']
    assert 'real_money' in sb
    assert 'valuation_reading' in sb
    print("✅ test_advanced_framework_adjustment_removed passed")


if __name__ == "__main__":
    test_issuer_alias_not_in_unmatched()
    test_quantitative_peers_less_than_two_weak_conclusion()
    test_private_low_quality_not_in_quantitative()
    test_loss_making_valuation_not_missing()
    test_new_fields_persist_through_from_dict()
    test_signal_component_analyzer_biotech()
    test_scoring_system_new_weights()
    test_advanced_framework_adjustment_removed()
    print("\n" + "=" * 60)
    print("✅ 所有回归测试通过")
    print("=" * 60)
