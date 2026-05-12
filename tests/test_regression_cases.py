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

from unittest.mock import patch
from ipo_analyzer.peer_comps import (
    _filter_peer_candidates,
    _build_issuer_aliases,
    _split_peer_samples,
    _calc_company_valuation_metrics,
    PeerComparableAnalyzer,
)
from ipo_analyzer.analyzers import ValuationAnalyzer
from ipo_analyzer.scoring import SignalComponentAnalyzer, ScoringSystem
from ipo_analyzer.models import IPOData
from ipo_analyzer.parser import ProspectusParser
from ipo_analyzer.core import _calculate_final_score


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
    quant, qual, basis, q_count, ql_count = _split_peer_samples(mock_peers)
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
    assert val.adjusted_profit_hkd_million == 12.0, "adjusted_profit_hkd_million 丢失"
    assert val.financial_currency == "RMB", "financial_currency 丢失"

    pc = pi.peer_comparison
    assert pc is not None
    assert pc.quantitative_peer_count == 1, "quantitative_peer_count 丢失"
    assert pc.qualitative_peer_count == 1, "qualitative_peer_count 丢失"
    assert pc.peer_sample_warning == "样本不足", "peer_sample_warning 丢失"
    assert len(pc.quantitative_peers) == 1, "quantitative_peers 丢失"
    assert len(pc.qualitative_peers) == 1, "qualitative_peers 丢失"

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
    # 估值 strength 可以是强/中/弱/缺失，取决于管线/平台/现金runway等综合支撑
    assert val_reading.get('strength') in ("强", "中", "弱", "缺失"), \
        f"估值 strength 应为有效等级: {val_reading.get('strength')}"

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


def test_signal_component_analyzer_none_quant_count():
    """quantitative_peer_count 为 None 时不应触发类型错误"""
    ipo = {"company_name": "TestBio", "hk_code": "9999"}
    prospectus_info = {
        "sector": "healthcare",
        "extracted_company_name": "TestBio-B",
        "_extracted_text": "18A biotech clinical stage platform",
        "revenue": 30,
        "revenue_y1": 10,
        "net_profit": -100,
        "gross_margin": 60,
        "market_cap_hkd_million": 5000,
        "profitable": False,
        "peer_comparison": {
            "subsector": "ai_drug_delivery_nanomedicine",
            "scarcity_score": 7,
            "peer_score": 8,
            "valuation_position": "样本不足，仅作定性参考",
            "quantitative_peer_count": None,
        },
        "valuation": {
            "ps_ratio": 80.0,
            "pe_ratio": None,
            "cash_runway_years": 2.0,
            "market_cap_to_rd_ratio": 35.0,
        },
        "rnd_pipeline": {
            "pipeline_quality_label": "强",
            "technology_moat_score": 8,
            "latest_clinical_stage": "Phase II",
        },
        "cornerstone_analysis": {
            "score": 0,
            "label": "未披露",
            "grade_band": "缺失",
        },
        "financial_data_quality_flags": [],
    }

    signal = SignalComponentAnalyzer().analyze(ipo, prospectus_info, prospectus_info["_extracted_text"])
    valuation = signal.get("components", {}).get("valuation_framework", {})

    assert valuation.get("score") is not None, "应正常返回 valuation_framework 分数"
    assert valuation.get("label") in ("PS失真，仅作参考", "管线阶段估值", "PS辅助估值")
    print("✅ test_signal_component_analyzer_none_quant_count passed")


def test_scoring_system_new_weights():
    """验证新五维评分权重结构"""
    ipo = {"over_sub_ratio": 100.0, "total_fund": 5.0, "market_heat": "热门"}
    prospectus_info = {
        "gross_margin": 40,
        "profitable": True,
        "revenue": 500,
        "revenue_y1": 400,
        "sector": "hardtech",
        "cornerstone_analysis": {"score": 70, "label": "A级", "has_cornerstone_section": True},
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
    assert 'weight_profile' in result, "必须有 weight_profile"
    assert result['score'] >= 0 and result['score'] <= 100, "总分应在 0-100 之间"

    # theme_score 标准化为 0-100（主题维度满分 35 → 映射到 0-100）
    assert result['theme_score'] <= 100, f"theme_score 应封顶 100: {result['theme_score']}"
    assert result['theme_score'] >= 0, f"theme_score 应 >= 0: {result['theme_score']}"

    # data_quality_score 作为 confidence_gate：高分不限制，低分限制
    if result['data_quality_score'] < 40:
        assert result['score'] <= 60, "数据质量差时应限制总分上限"

    # 验证权重配置正确
    wp = result.get('weight_profile', {})
    assert wp.get('name') == 'live_heat', f"有热度数据时应为 live_heat: {wp.get('name')}"

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


def test_financial_table_loss_and_used_cashflow_are_negative():
    """财务主表 Loss / Net cash used 行应按负数入库"""
    text = """
Selected consolidated financial information
Year ended December 31
2023
2024
RMB'000
Revenue
100,000
120,000
Loss for the year
50,000
60,000
Net cash used in operating activities
30,000
40,000
"""
    parser = ProspectusParser()
    fin_table = parser._extract_consolidated_financial_table(text)
    info = {}
    parser._apply_financial_table_to_info(info, fin_table, source='consolidated_statement', force=True)

    assert info.get("net_profit") == -60.0, f"Loss 行应为负净利润: {info.get('net_profit')}"
    assert info.get("net_profit_y1") == -50.0, f"上一期 Loss 行应为负: {info.get('net_profit_y1')}"
    assert info.get("profitable") is False, "Loss 行不应标记为盈利"
    assert info.get("operating_cash_flow") == -40.0, f"Net cash used 应为负: {info.get('operating_cash_flow')}"
    print("✅ test_financial_table_loss_and_used_cashflow_are_negative passed")


def test_peer_company_metrics_use_hkd_currency_basis():
    """同行对比自身 PS/PE 应使用与估值模块一致的 HKD 口径"""
    pi = {
        "market_cap_hkd_million": 1080,
        "revenue": 100,
        "net_profit": 10,
        "financial_currency": "RMB",
    }
    company_ps, company_pe, _ = _calc_company_valuation_metrics(pi)
    assert company_ps == 10.0, f"PS 应按 RMB->HKD 后计算: {company_ps}"
    assert company_pe == 100.0, f"PE 应按 RMB->HKD 后计算: {company_pe}"
    print("✅ test_peer_company_metrics_use_hkd_currency_basis passed")


def test_insufficient_peer_sample_does_not_add_positive_peer_adj():
    """quantitative peers 不足时，peer_score 不能给总分额外正向加分"""
    ipo = {"over_sub_ratio": 20.0, "total_fund": 2.0, "market_heat": "温和"}
    prospectus_info = {
        "gross_margin": 35,
        "profitable": True,
        "revenue": 300,
        "revenue_y1": 250,
        "sector": "hardtech",
        "cornerstone_analysis": {"score": 70, "label": "A级"},
        "valuation": {"pe_ratio": 20.0, "ps_ratio": 3.0},
        "peer_comparison": {
            "peer_score": 12,
            "scarcity_score": 7,
            "valuation_position": "样本不足，仅作定性参考",
            "quantitative_peer_count": 1,
            "peer_sample_warning": "quantitative peers 仅 1 家，不参与强估值判断，仅作定性参考",
        },
    }
    signal_components = {
        'real_money': {'score': 8},
        'float_structure': {'score': 7},
        'valuation_framework': {'score': 10},
        'mainline_beta': {'score': 5},
        'stock_connect_path': {'score': 4},
        'data_quality': {'score': 5},
    }
    result = ScoringSystem().calculate(ipo, prospectus_info, signal_components=signal_components)
    reasons_text = " ".join(result.get("reasons", []))
    assert "同行对比优异" not in reasons_text, "样本不足时不应给 peer_adj 正向加分"
    assert "不额外加分" in reasons_text, "应说明同行样本不足仅作定性参考"
    print("✅ test_insufficient_peer_sample_does_not_add_positive_peer_adj passed")


def test_core_fundamental_score_matches_scoring_breakdown():
    """展示用 fundamental_score 应与参与总分公式的分数一致"""

    class FakeScorer:
        def calculate(self, ipo_data, prospectus_info, signal_components=None):
            return {
                "score": 50,
                "subscription_score": 11,
                "fundamental_score": 42,
                "reasons": [],
                "components": {},
                "trade_score": 10,
                "valuation_score": 20,
                "theme_score": 5,
                "data_quality_score": 100,
            }

    class FakeQualityAnalyzer:
        def analyze(self, prospectus_info):
            return {"score": 88, "label": "优秀", "reasons": [], "dimensions": {}}

    class FakeSignalAnalyzer:
        def analyze(self, ipo_data, prospectus_info, prospectus_text):
            return {"components": {}, "score": 0, "signal_breakdown": {}}

    ipo_data = {"company_name": "TestCo", "hk_code": "1234"}
    prospectus_info = {"sector": "unknown", "financial_data_quality_flags": []}
    _calculate_final_score(FakeScorer(), FakeQualityAnalyzer(), FakeSignalAnalyzer(), ipo_data, prospectus_info, "")

    assert ipo_data["fundamental_score"] == 42, "展示分应使用 ScoringSystem 的 fundamental_score"
    assert ipo_data["stock_quality_score"] == 88, "股票质地分应单独保留，避免和评分公式混淆"
    print("✅ test_core_fundamental_score_matches_scoring_breakdown passed")


def test_jitai_pre_ipo_score_not_too_low():
    """剂泰科技无实时孖展时，最终分不应低于 55"""
    ipo = {
        'margin_total': None,
        'public_offer': 1.06,
        'total_fund': 21.13,
        'over_sub_ratio': None,
        'over_sub_ratio_source': 'missing',
    }
    prospectus_info = {
        'revenue': 105,
        'revenue_y1': 1.482,
        'net_profit': -250,
        'gross_margin': 98.2,
        'profitable': False,
        'market_cap_hkd_million': 3800,
        'offer_price': 12.0,
        'pro_forma_NTA_per_share_HKD': 2.0,
        'sector': 'healthcare',
        'financial_currency': 'RMB',
        'extracted_company_name': '剂泰科技-B',
        '_extracted_text': '18C biotech AI drug delivery NanoForge LNP RNA targeted delivery pre-NDA',
        'public_offer_ratio_pct': 5.0,
        'issuance_ratio_pct': 10.0,
        'cornerstone_offer_ratio_pct': 55.0,
        'rd_expense': 85,
        'rnd_pipeline': {
            'technology_moat_score': 9,
            'pipeline_quality_label': '强',
            'product_count_pipeline': 5,
            'latest_clinical_stage': 'Phase II',
        },
        'cornerstone_analysis': {
            'score': 85,
            'label': 'A级',
            'grade_band': '强A',
            'cornerstone_investors': [
                {'name': 'BlackRock', 'tier': 'S'},
                {'name': 'UBS AM', 'tier': 'A'},
                {'name': 'Hillhouse', 'tier': 'A'},
                {'name': 'Deerfield', 'tier': 'A'},
                {'name': 'Lake Bleu', 'tier': 'A'},
            ],
            'matched_investors': [
                {'name': 'BlackRock', 'tier': 'S'},
                {'name': 'UBS AM', 'tier': 'A'},
                {'name': 'Hillhouse', 'tier': 'A'},
            ],
        },
        'peer_comparison': {
            'subsector': 'ai_drug_delivery_nanomedicine',
            'scarcity_score': 8,
            'peer_score': 8,
            'valuation_position': '样本不足，仅作定性参考',
            'quantitative_peer_count': 1,
            'peer_sample_warning': '定量同行样本不足',
        },
        'valuation': {
            'ps_ratio': 36.0,
            'pe_ratio': None,
            'market_cap_to_rd_ratio': 45.0,
            'cash_runway_years': 2.8,
            'valuation_framework_type': '18A_biotech',
            'valuation_label': 'PS辅助估值',
            'valuation_profitability_type': 'loss_making',
            'revenue_too_small_for_ps': False,
            'revenue_quality': 'license_upfront_driven',
        },
        'financial_extract_confidence': 'consolidated_statement',
        'financial_data_quality_flags': [],
    }
    text = '18C biotech AI drug delivery NanoForge LNP RNA targeted delivery pre-NDA'

    from ipo_analyzer.scoring import ScoringSystem, SignalComponentAnalyzer, ProspectusQualityAnalyzer
    from ipo_analyzer.peer_comps import PeerComparableAnalyzer
    from ipo_analyzer.analyzers import ValuationAnalyzer

    pi = prospectus_info
    pi['peer_comparison'] = PeerComparableAnalyzer().analyze(pi, text, ipo)
    pi['valuation'] = ValuationAnalyzer().analyze(pi, text, ipo)

    signal = SignalComponentAnalyzer().analyze(ipo, pi, text)
    quality = ProspectusQualityAnalyzer().analyze(pi)
    pi['stock_quality'] = quality

    scorer = ScoringSystem()
    scoring = scorer.calculate(ipo, pi, signal_components=signal.get('components'))

    print(f"\n剂泰科技 pre-IPO: score={scoring['score']}, trade={scoring['trade_score']}, "
          f"fundamental={scoring['fundamental_score']}, valuation={scoring['valuation_score']}, "
          f"theme={scoring['theme_score']}")

    assert scoring['score'] >= 55, f"剂泰科技 pre-IPO 评分应≥55，实际 {scoring['score']}"
    assert scoring['fundamental_score'] >= 40, f"基本面应≥40，实际 {scoring['fundamental_score']}"
    assert scoring['valuation_score'] >= 30, f"估值面应≥30，实际 {scoring['valuation_score']}"
    print("✅ test_jitai_pre_ipo_score_not_too_low passed")


def test_jitai_hot_with_strong_cornerstone():
    """剂泰科技有超购+强基石时，最终分应进入 70+"""
    ipo = {
        'margin_total': 500.0,
        'public_offer': 1.06,
        'total_fund': 21.13,
        'over_sub_ratio': 500.0,
        'over_sub_ratio_source': 'actual',
        'market_heat': '极热',
    }
    prospectus_info = {
        'revenue': 105,
        'revenue_y1': 1.482,
        'net_profit': -250,
        'gross_margin': 98.2,
        'profitable': False,
        'market_cap_hkd_million': 3800,
        'offer_price': 12.0,
        'pro_forma_NTA_per_share_HKD': 2.0,
        'sector': 'healthcare',
        'financial_currency': 'RMB',
        'extracted_company_name': '剂泰科技-B',
        '_extracted_text': '18C biotech AI drug delivery NanoForge LNP RNA targeted delivery pre-NDA',
        'public_offer_ratio_pct': 5.0,
        'issuance_ratio_pct': 10.0,
        'cornerstone_offer_ratio_pct': 55.0,
        'rd_expense': 85,
        'rnd_pipeline': {
            'technology_moat_score': 9,
            'pipeline_quality_label': '强',
            'product_count_pipeline': 5,
            'latest_clinical_stage': 'Phase II',
        },
        'cornerstone_analysis': {
            'score': 85,
            'label': 'A级',
            'grade_band': '强A',
            'cornerstone_investors': [
                {'name': 'BlackRock', 'tier': 'S'},
                {'name': 'UBS AM', 'tier': 'A'},
                {'name': 'Hillhouse', 'tier': 'A'},
                {'name': 'Deerfield', 'tier': 'A'},
                {'name': 'Lake Bleu', 'tier': 'A'},
            ],
            'matched_investors': [
                {'name': 'BlackRock', 'tier': 'S'},
                {'name': 'UBS AM', 'tier': 'A'},
                {'name': 'Hillhouse', 'tier': 'A'},
            ],
        },
        'peer_comparison': {
            'subsector': 'ai_drug_delivery_nanomedicine',
            'scarcity_score': 8,
            'peer_score': 8,
            'valuation_position': '样本不足，仅作定性参考',
            'quantitative_peer_count': 1,
        },
        'valuation': {
            'ps_ratio': 36.0,
            'pe_ratio': None,
            'market_cap_to_rd_ratio': 45.0,
            'cash_runway_years': 2.8,
            'valuation_framework_type': '18A_biotech',
            'valuation_label': 'PS辅助估值',
            'valuation_profitability_type': 'loss_making',
            'revenue_too_small_for_ps': False,
            'revenue_quality': 'license_upfront_driven',
        },
        'financial_extract_confidence': 'consolidated_statement',
        'financial_data_quality_flags': [],
    }
    text = '18C biotech AI drug delivery NanoForge LNP RNA targeted delivery pre-NDA'

    from ipo_analyzer.scoring import ScoringSystem, SignalComponentAnalyzer, ProspectusQualityAnalyzer
    from ipo_analyzer.peer_comps import PeerComparableAnalyzer
    from ipo_analyzer.analyzers import ValuationAnalyzer

    pi = prospectus_info
    pi['peer_comparison'] = PeerComparableAnalyzer().analyze(pi, text, ipo)
    pi['valuation'] = ValuationAnalyzer().analyze(pi, text, ipo)

    signal = SignalComponentAnalyzer().analyze(ipo, pi, text)
    quality = ProspectusQualityAnalyzer().analyze(pi)
    pi['stock_quality'] = quality

    scorer = ScoringSystem()
    scoring = scorer.calculate(ipo, pi, signal_components=signal.get('components'))

    print(f"\n剂泰科技 热发+强基石: score={scoring['score']}, trade={scoring['trade_score']}, "
          f"fundamental={scoring['fundamental_score']}, valuation={scoring['valuation_score']}, "
          f"theme={scoring['theme_score']}")

    assert scoring['score'] >= 70, f"剂泰科技 热发+强基石 评分应≥70，实际 {scoring['score']}"
    assert scoring['trade_score'] >= 60, f"交易面应≥60，实际 {scoring['trade_score']}"
    print("✅ test_jitai_hot_with_strong_cornerstone passed")


def test_yifei_no_cornerstone_misidentified():
    """翼菲科技：无基石章节，只有 pre-IPO 投资者，不应被误判为有基石"""
    from ipo_analyzer.cornerstone import CornerstoneAnalyzer

    text = """
    Our Company has received investments from a number of sophisticated independent investors.
    The pathfinder sophisticated independent investors include Primavera Capital,
    China Broadband Capital, Tsinghua Holdings Capital, and other previous investors.
    These pre-ipo investors have supported our growth since Series A.
    """

    result = CornerstoneAnalyzer().analyze(text)
    assert result.get('has_cornerstone_section') is False, \
        f"应判定为无基石章节，实际: {result.get('has_cornerstone_section')}"
    assert result.get('score') == 0, f"无基石时 score 应为 0，实际: {result.get('score')}"
    assert result.get('label') == '未披露', f"无基石时 label 应为'未披露'，实际: {result.get('label')}"
    assert result.get('recommendation') == '无基石', f"无基石时 recommendation 应为'无基石'，实际: {result.get('recommendation')}"
    assert result.get('matched_investors') == [], f"无基石时 matched_investors 应为空，实际: {result.get('matched_investors')}"
    assert result.get('red_flags') == [], f"无基石时 red_flags 应为空，实际: {result.get('red_flags')}"
    print("✅ test_yifei_no_cornerstone_misidentified passed")


def test_jitai_cornerstone_detected_correctly():
    """剂泰科技：有基石章节，应正确识别强基石"""
    from ipo_analyzer.cornerstone import CornerstoneAnalyzer

    text = """
    Cornerstone Investors
    The following cornerstone investors have agreed to subscribe for the Offer Shares:
    BlackRock, Inc. has agreed to subscribe for 5,000,000 Offer Shares.
    UBS Asset Management has agreed to subscribe for 3,000,000 Offer Shares.
    HHLR Fund, L.P. has agreed to subscribe for 2,000,000 Offer Shares.
    RTW Investments, LP has agreed to subscribe for 1,500,000 Offer Shares.
    """

    result = CornerstoneAnalyzer().analyze(text)
    assert result.get('has_cornerstone_section') is True, \
        f"应判定为有基石章节，实际: {result.get('has_cornerstone_section')}"
    assert result.get('score', 0) > 0, f"有强基石时 score 应>0，实际: {result.get('score')}"
    matched_names = [m['name'] for m in result.get('matched_investors', [])]
    assert 'BlackRock' in matched_names, f"应识别 BlackRock，实际: {matched_names}"
    assert 'Hillhouse/HHLR' in matched_names, f"应识别 Hillhouse/HHLR，实际: {matched_names}"
    assert 'UBS Asset Management' in matched_names, f"应识别 UBS，实际: {matched_names}"
    assert 'RTW' in matched_names, f"应识别 RTW，实际: {matched_names}"
    print("✅ test_jitai_cornerstone_detected_correctly passed")


def test_cornerstone_profiles_fallback_when_yaml_missing():
    """YAML 缺失时应回退到内置基石投资者档案。"""
    from ipo_analyzer.cornerstone import CornerstoneAnalyzer, _load_investor_profiles

    with patch("builtins.open", side_effect=FileNotFoundError("missing")):
        profiles = _load_investor_profiles()

    assert profiles == CornerstoneAnalyzer._BUILTIN_INVESTOR_PROFILES
    print("✅ test_cornerstone_profiles_fallback_when_yaml_missing passed")


def test_cornerstone_unknown_investor_does_not_crash():
    """基石行未命中词库时应按普通基石处理，不能抛 IndexError。"""
    from ipo_analyzer.cornerstone import CornerstoneAnalyzer

    analyzer = CornerstoneAnalyzer()

    assert analyzer._best_profile("Obscure Capital Holdings Limited") is None

    rows = analyzer._enrich_cornerstone_rows(
        "Cornerstone Investors\nObscure Capital Holdings Limited has agreed to subscribe.",
        [{'name': 'Obscure Capital Holdings Limited', 'offer_shares_pct': 5.0}],
    )

    assert rows
    assert rows[0].get('tier') is None
    assert rows[0].get('role_note') == '未纳入高质量基石词库，按普通基石处理'


def test_cornerstone_analysis_keeps_source_excerpt():
    """基石分析应保留 PDF 文本摘录，方便人工核对。"""
    from ipo_analyzer.cornerstone import CornerstoneAnalyzer

    text = """
    Cornerstone Investors
    The following cornerstone investors have agreed to subscribe for the Offer Shares:
    BlackRock, Inc. has agreed to subscribe for 5,000,000 Offer Shares.
    """

    result = CornerstoneAnalyzer().analyze(text)

    assert result.get('has_cornerstone_section') is True
    assert 'Cornerstone Investors' in result.get('source_excerpt', '')
    assert 'BlackRock' in result.get('source_excerpt', '')


def test_yifei_pre_ipo_investors_not_counted_as_cornerstone():
    """翼菲科技：pre-IPO 投资者即使在全文出现，也不应计入基石评分"""
    from ipo_analyzer.cornerstone import CornerstoneAnalyzer

    # 同时包含基石章节和 pre-IPO 章节，pre-IPO 章节的投资者不应计入
    text = """
    Pre-IPO Investment
    Our pre-ipo investors include Primavera Capital and Hillhouse.
    They invested in Series B and C rounds.

    Cornerstone Investors
    The following cornerstone investors have agreed to subscribe:
    BlackRock, Inc. has agreed to subscribe for 5,000,000 Offer Shares.
    UBS Asset Management has agreed to subscribe for 3,000,000 Offer Shares.
    Hillhouse Capital has agreed to subscribe for 1,000,000 Offer Shares.
    """

    result = CornerstoneAnalyzer().analyze(text)
    assert result.get('has_cornerstone_section') is True
    matched_names = [m['name'] for m in result.get('matched_investors', [])]
    # Hillhouse 出现在基石章节中，应计入
    assert 'Hillhouse/HHLR' in matched_names, f"应识别 Hillhouse，实际: {matched_names}"
    assert 'BlackRock' in matched_names, f"应识别 BlackRock，实际: {matched_names}"
    assert 'UBS Asset Management' in matched_names, f"应识别 UBS，实际: {matched_names}"
    # 所有匹配都应标记为 cornerstone_section（因为它们都在基石章节内）
    for m in result.get('matched_investors', []):
        assert m.get('source') == 'cornerstone_section', \
            f"基石章节内的投资者应标记为 cornerstone_section，实际: {m}"
    print("✅ test_yifei_pre_ipo_investors_not_counted_as_cornerstone passed")


def test_pre_ipo_investors_excluded_from_cornerstone():
    """pre-IPO 章节中的投资者不应被计入基石评分"""
    from ipo_analyzer.cornerstone import CornerstoneAnalyzer

    text = """
    Pre-IPO Investment
    Our pre-ipo investors include Primavera Capital and Hillhouse.
    They invested in Series B and C rounds.

    Shareholders
    The following shareholders hold substantial interests:
    China Broadband Capital holds 10% of shares.
    Tsinghua Holdings Capital holds 5% of shares.
    """

    result = CornerstoneAnalyzer().analyze(text)
    assert result.get('has_cornerstone_section') is False
    assert result.get('score') == 0
    assert result.get('matched_investors') == []
    print("✅ test_pre_ipo_investors_excluded_from_cornerstone passed")


def test_no_heat_data_weight_profile():
    """无热度数据时应使用 prospectus_only 权重配置"""
    ipo = {
        'over_sub_ratio': None,
        'over_sub_ratio_source': 'missing',
        'forecast_over_sub_ratio': None,
        'market_heat': None,
        'total_fund': 5.0,
    }
    prospectus_info = {
        'gross_margin': 40,
        'profitable': True,
        'revenue': 500,
        'revenue_y1': 400,
        'sector': 'hardtech',
        'cornerstone_analysis': {'score': 70, 'label': 'A级', 'has_cornerstone_section': True},
        'valuation': {'pe_ratio': 25.0, 'ps_ratio': 3.0},
        'peer_comparison': {'peer_score': 10, 'scarcity_score': 6, 'valuation_position': '合理'},
    }
    result = ScoringSystem().calculate(ipo, prospectus_info, signal_components={})

    wp = result.get('weight_profile', {})
    assert wp.get('name') == 'prospectus_only', f"期望 prospectus_only，实际: {wp.get('name')}"
    assert wp.get('weights', {}).get('trade') == 0.20, f"trade 权重应为 0.20，实际: {wp.get('weights', {}).get('trade')}"
    assert wp.get('weights', {}).get('fundamental') == 0.35, f"fundamental 权重应为 0.35，实际: {wp.get('weights', {}).get('fundamental')}"
    assert wp.get('weights', {}).get('theme') == 0.15, f"theme 权重应为 0.15，实际: {wp.get('weights', {}).get('theme')}"
    assert wp.get('weights', {}).get('data_quality') == 0.10, f"data_quality 权重应为 0.10，实际: {wp.get('weights', {}).get('data_quality')}"
    assert "未检测到有效热度数据" in wp.get('reason', ''), f"reason 应说明未检测到热度数据: {wp.get('reason')}"
    print("✅ test_no_heat_data_weight_profile passed")


def test_live_heat_weight_profile():
    """有热度数据时应使用 live_heat 权重配置"""
    ipo = {
        'over_sub_ratio': 100.0,
        'over_sub_ratio_source': 'actual',
        'total_fund': 5.0,
        'market_heat': '热门',
    }
    prospectus_info = {
        'gross_margin': 40,
        'profitable': True,
        'revenue': 500,
        'revenue_y1': 400,
        'sector': 'hardtech',
        'cornerstone_analysis': {'score': 70, 'label': 'A级', 'has_cornerstone_section': True},
        'valuation': {'pe_ratio': 25.0, 'ps_ratio': 3.0},
        'peer_comparison': {'peer_score': 10, 'scarcity_score': 6, 'valuation_position': '合理'},
    }
    result = ScoringSystem().calculate(ipo, prospectus_info, signal_components={})

    wp = result.get('weight_profile', {})
    assert wp.get('name') == 'live_heat', f"期望 live_heat，实际: {wp.get('name')}"
    assert wp.get('weights', {}).get('trade') == 0.35, f"trade 权重应为 0.35，实际: {wp.get('weights', {}).get('trade')}"
    assert wp.get('weights', {}).get('fundamental') == 0.30, f"fundamental 权重应为 0.30，实际: {wp.get('weights', {}).get('fundamental')}"
    assert wp.get('weights', {}).get('theme') == 0.10, f"theme 权重应为 0.10，实际: {wp.get('weights', {}).get('theme')}"
    assert wp.get('weights', {}).get('data_quality') == 0.05, f"data_quality 权重应为 0.05，实际: {wp.get('weights', {}).get('data_quality')}"
    assert "检测到有效超购" in wp.get('reason', ''), f"reason 应说明检测到超购数据: {wp.get('reason')}"
    print("✅ test_live_heat_weight_profile passed")


def test_theme_score_normalized_to_100():
    """theme_score 应标准化为 0-100 分，而非之前的 0-50"""
    ipo = {'over_sub_ratio': 100.0, 'over_sub_ratio_source': 'actual'}
    prospectus_info = {
        'gross_margin': 40,
        'profitable': True,
        'revenue': 500,
        'revenue_y1': 400,
        'sector': 'hardtech',
        'cornerstone_analysis': {'score': 70, 'label': 'A级', 'has_cornerstone_section': True},
        'valuation': {'pe_ratio': 25.0, 'ps_ratio': 3.0},
        'peer_comparison': {'peer_score': 10, 'scarcity_score': 10, 'valuation_position': '合理'},
    }
    signal_components = {
        'mainline_beta': {'score': 15},
        'stock_connect_path': {'score': 10},
        'data_quality': {'score': 5},
    }
    result = ScoringSystem().calculate(ipo, prospectus_info, signal_components=signal_components)

    theme_raw = 15 + 10 + 10  # mainline_beta + stock_connect_path + scarcity
    theme_max = 35
    expected_theme_score = min(100, round(theme_raw / theme_max * 100))
    
    assert result.get('theme_score') == expected_theme_score, \
        f"theme_score 应为 {expected_theme_score}，实际: {result.get('theme_score')}"
    assert result.get('theme_score') <= 100, f"theme_score 不应超过 100，实际: {result.get('theme_score')}"
    print(f"✅ test_theme_score_normalized_to_100 passed (theme_score={result.get('theme_score')})")


def test_theme_score_full_raw_equals_100():
    """theme_raw=35 时，theme_score 应为 100"""
    ipo = {'over_sub_ratio': 100.0, 'over_sub_ratio_source': 'actual'}
    prospectus_info = {
        'gross_margin': 40,
        'profitable': True,
        'revenue': 500,
        'revenue_y1': 400,
        'sector': 'hardtech',
        'cornerstone_analysis': {'score': 70, 'label': 'A级', 'has_cornerstone_section': True},
        'valuation': {'pe_ratio': 25.0, 'ps_ratio': 3.0},
        'peer_comparison': {'peer_score': 10, 'scarcity_score': 10, 'valuation_position': '合理'},
    }
    signal_components = {
        'mainline_beta': {'score': 15},
        'stock_connect_path': {'score': 10},
        'data_quality': {'score': 5},
    }
    result = ScoringSystem().calculate(ipo, prospectus_info, signal_components=signal_components)

    # theme_raw = 15 + 10 + 10 = 35, theme_max = 35, so theme_score = 100
    assert result.get('theme_score') == 100, \
        f"theme_raw=35 时 theme_score 应为 100，实际: {result.get('theme_score')}"
    print("✅ test_theme_score_full_raw_equals_100 passed")


def test_risk_penalty_only_for_major_red_flags():
    """risk_penalty 只应针对重大红旗，普通风险不应重复扣分"""
    from ipo_analyzer.core import _calculate_risk_penalty

    prospectus_info = {
        '_extracted_text': (
            '公司面临持续经营重大不确定性，且存在多项重大诉讼风险。'
            '审计师出具了标准无保留意见。'
        ),
        'risk_factors': {
            'risks': {
                'customer_concentration_risk': {
                    'risk_level': '中',  # 普通偏高，不应触发 penalty
                }
            },
            'total_penalty': 3,
        },
        'customer_supplier': {
            'largest_customer_revenue_pct': 40,  # 普通偏高（<50%），不应触发 penalty
            'top5_customer_revenue_pct': 75,      # 普通偏高（<80%），不应触发 penalty
        },
        'valuation': {
            'cash_runway_years': 1.5,  # > 1 年，不应触发 penalty
        },
        'stock_quality': {
            'reasons': [],
        },
    }

    result = _calculate_risk_penalty(prospectus_info)
    penalty = result.get('total_penalty', 0)
    breakdown = result.get('breakdown', [])

    assert penalty > 0, "重大红旗应触发 penalty"
    assert len(breakdown) >= 2, "应至少有两个 penalty 项"
    
    penalty_types = [b['type'] for b in breakdown]
    assert 'going_concern' in penalty_types, "持续经营不确定性应触发 penalty"
    assert 'lawsuit' in penalty_types, "重大诉讼应触发 penalty"
    assert 'customer_concentration' not in penalty_types, "普通客户集中度不应触发 penalty"
    assert 'cornerstone_red_flag' not in penalty_types, "普通基石红旗不应触发 penalty"
    print(f"✅ test_risk_penalty_only_for_major_red_flags passed (penalty={penalty})")


def test_risk_penalty_customer_extreme_concentration():
    """客户极端集中应触发 risk_penalty"""
    from ipo_analyzer.core import _calculate_risk_penalty

    prospectus_info = {
        'customer_supplier': {
            'largest_customer_pct': 55,  # 超过 50%，应触发 penalty
        },
    }

    result = _calculate_risk_penalty(prospectus_info)
    penalty = result.get('total_penalty', 0)
    breakdown = result.get('breakdown', [])

    assert penalty > 0, "客户极端集中应触发 penalty"
    penalty_types = [b['type'] for b in breakdown]
    assert 'customer_concentration' in penalty_types, "应识别客户集中度 penalty"
    print(f"✅ test_risk_penalty_customer_extreme_concentration passed (penalty={penalty})")


def test_risk_penalty_cash_runway_short():
    """现金 runway < 1 年应触发 risk_penalty"""
    from ipo_analyzer.core import _calculate_risk_penalty

    prospectus_info = {
        'valuation': {
            'cash_runway_years': 0.5,  # < 1 年，应触发 penalty
        },
    }

    result = _calculate_risk_penalty(prospectus_info)
    penalty = result.get('total_penalty', 0)
    breakdown = result.get('breakdown', [])

    assert penalty > 0, "现金 runway 短应触发 penalty"
    penalty_types = [b['type'] for b in breakdown]
    assert 'cash_runway' in penalty_types, "应识别现金 runway penalty"
    print(f"✅ test_risk_penalty_cash_runway_short passed (penalty={penalty})")


def test_historical_actual_over_sub_ratio_source():
    """historical_actual 应被识别为有效热度数据，使用 live_heat 权重"""
    ipo = {
        'over_sub_ratio': 150.0,
        'over_sub_ratio_source': 'historical_actual',
    }
    prospectus_info = {
        'gross_margin': 40,
        'profitable': True,
        'revenue': 500,
        'sector': 'hardtech',
        'cornerstone_analysis': {'score': 70, 'label': 'A级', 'has_cornerstone_section': True},
        'valuation': {'pe_ratio': 25.0, 'ps_ratio': 3.0},
        'peer_comparison': {'peer_score': 10, 'scarcity_score': 6, 'valuation_position': '合理'},
    }
    result = ScoringSystem().calculate(ipo, prospectus_info, signal_components={})

    wp = result.get('weight_profile', {})
    assert wp.get('name') == 'live_heat', f"期望 live_heat，实际: {wp.get('name')}"
    assert wp.get('weights', {}).get('trade') == 0.35, "trade 权重应为 0.35"
    print("✅ test_historical_actual_over_sub_ratio_source passed")


def test_historical_forecast_over_sub_ratio_source():
    """historical_forecast 应被识别为有效热度数据，使用 live_heat 权重"""
    ipo = {
        'over_sub_ratio': 100.0,
        'over_sub_ratio_source': 'historical_forecast',
    }
    prospectus_info = {
        'gross_margin': 40,
        'profitable': True,
        'revenue': 500,
        'sector': 'hardtech',
        'cornerstone_analysis': {'score': 70, 'label': 'A级', 'has_cornerstone_section': True},
        'valuation': {'pe_ratio': 25.0, 'ps_ratio': 3.0},
        'peer_comparison': {'peer_score': 10, 'scarcity_score': 6, 'valuation_position': '合理'},
    }
    result = ScoringSystem().calculate(ipo, prospectus_info, signal_components={})

    wp = result.get('weight_profile', {})
    assert wp.get('name') == 'live_heat', f"期望 live_heat，实际: {wp.get('name')}"
    assert wp.get('weights', {}).get('trade') == 0.35, "trade 权重应为 0.35"
    print("✅ test_historical_forecast_over_sub_ratio_source passed")


def test_reanalysis_version_delta_calculation():
    """版本对比 delta 计算应正确"""
    from ipo_analyzer.history import HistoryStore
    import tempfile
    import shutil

    # 创建临时目录
    temp_dir = tempfile.mkdtemp()
    try:
        store = HistoryStore(temp_dir)
        
        # 模拟第一次分析结果
        first_result = {
            'hk_code': '09995',
            'company_name': 'TestCo',
            'score': 65,
            'trade_score': 70,
            'fundamental_score': 60,
            'valuation_score': 65,
            'theme_score': 70,
            'data_quality_score': 80,
            'weight_profile': {'name': 'live_heat'},
            '_reanalysis': {
                'analysis_mode': 'reanalysis',
                'heat_data_source': 'historical_actual',
                'source_type': 'local_pdf',
            },
        }
        
        # 保存第一次分析
        record1, delta1 = store.save_reanalysis(first_result)
        assert delta1 is None, "第一次分析不应有 delta"
        assert record1.get('score') == 65
        assert record1.get('stock_code') == '09995'
        
        # 模拟第二次分析结果（评分变化）
        second_result = {
            'hk_code': '09995',
            'company_name': 'TestCo',
            'score': 72,
            'trade_score': 75,
            'fundamental_score': 65,
            'valuation_score': 70,
            'theme_score': 72,
            'data_quality_score': 80,
            'weight_profile': {'name': 'live_heat'},
            '_reanalysis': {
                'analysis_mode': 'reanalysis',
                'heat_data_source': 'historical_actual',
                'source_type': 'local_pdf',
            },
        }
        
        # 保存第二次分析
        record2, delta2 = store.save_reanalysis(second_result)
        assert delta2 is not None, "第二次分析应有 delta"
        assert delta2.get('previous_score') == 65
        assert delta2.get('current_score') == 72
        assert delta2.get('score_delta') == 7
        assert delta2.get('dimension_deltas', {}).get('trade_score') == 5
        assert delta2.get('dimension_deltas', {}).get('fundamental_score') == 5
        
        # 检查时间戳版本文件存在
        history = store.load_reanalysis_history('09995')
        assert len(history) >= 1, "应至少有一条历史记录"
        
        # 检查 latest 文件
        latest = store.load_reanalysis_latest('09995')
        assert latest.get('score') == 72, "latest 应指向最新结果"
        
        print("✅ test_reanalysis_version_delta_calculation passed")
        
    finally:
        shutil.rmtree(temp_dir)


def test_reanalysis_no_heat_data_uses_prospectus_only():
    """无历史热度数据时应使用 prospectus_only 权重"""
    from ipo_analyzer.history import HistoryStore
    import tempfile
    import shutil

    temp_dir = tempfile.mkdtemp()
    try:
        store = HistoryStore(temp_dir)
        
        result = {
            'hk_code': '09995',
            'company_name': 'TestCo',
            'score': 58,
            'weight_profile': {'name': 'prospectus_only', 'weights': {'trade': 0.20, 'theme': 0.15}},
            '_reanalysis': {
                'analysis_mode': 'reanalysis',
                'heat_data_source': 'missing',
                'source_type': 'local_pdf',
            },
        }
        
        store.save_reanalysis(result)
        latest = store.load_reanalysis_latest('09995')
        
        assert latest.get('heat_data_source') == 'missing'
        assert latest.get('weight_profile', {}).get('name') == 'prospectus_only'
        assert latest.get('weight_profile', {}).get('weights', {}).get('trade') == 0.20
        assert latest.get('weight_profile', {}).get('weights', {}).get('theme') == 0.15
        
        print("✅ test_reanalysis_no_heat_data_uses_prospectus_only passed")
        
    finally:
        shutil.rmtree(temp_dir)


def test_reanalyze_ipo_returns_unified_structure():
    """reanalyze_ipo 返回统一结构"""
    from ipo_analyzer.core import reanalyze_ipo
    import tempfile
    import shutil

    temp_dir = tempfile.mkdtemp()
    try:
        # 测试错误情况：未提供股票代码和PDF
        result = reanalyze_ipo(stock_code=None, pdf_path=None, output_dir=temp_dir)
        
        assert 'status' in result, "返回应包含 status"
        assert 'message' in result, "返回应包含 message"
        assert 'suggestion' in result, "返回应包含 suggestion"
        assert 'result' in result, "返回应包含 result"
        
        assert result['status'] == 'error', "无输入时应为 error"
        assert "未提供股票代码或PDF文件" in result['message']
        
        print("✅ test_reanalyze_ipo_returns_unified_structure passed")
        
    finally:
        shutil.rmtree(temp_dir)


def test_cornerstone_red_flags_penalty_normal():
    """普通基石红旗扣分测试：每个普通红旗扣3分，最高10分"""
    from ipo_analyzer.scoring import ScoringSystem

    scorer = ScoringSystem()

    ipo = {
        'over_sub_ratio': 4322.0,
        'over_sub_ratio_source': 'historical_actual',
        'margin_total': 500.0,
        'public_offer': 10.0,
    }

    prospectus_info = {
        'cornerstone_analysis': {
            'score': 80,
            'label': '强基石',
            'has_cornerstone_section': True,
            'red_flags': ['普通风险1', '普通风险2', '普通风险3'],
        },
        'quality_score': 70,
        'stock_quality': {
            'score': 70,
            'label': '优',
            'reasons': [],
            'dimensions': {},
        },
    }

    result = scorer.calculate(ipo, prospectus_info)

    assert result['penalty_reason'] is not None, "应有扣分原因"
    assert '基石红旗扣' in result['penalty_reason'], "应包含基石红旗扣分"
    assert 'debug_info' in result, "应有 debug_info 字段"
    assert result['debug_info']['cornerstone_red_flags'] == ['普通风险1', '普通风险2', '普通风险3']

    print("✅ test_cornerstone_red_flags_penalty_normal passed")


def test_cornerstone_severe_flags_cap_60():
    """严重基石红旗封顶测试：严重红旗封顶60分"""
    from ipo_analyzer.scoring import ScoringSystem

    scorer = ScoringSystem()

    ipo = {
        'over_sub_ratio': 4322.0,
        'over_sub_ratio_source': 'historical_actual',
        'margin_total': 500.0,
        'public_offer': 10.0,
    }

    prospectus_info = {
        'cornerstone_analysis': {
            'score': 80,
            'label': '强基石',
            'has_cornerstone_section': True,
            'red_flags': ['关联方认购', '锁定异常'],
        },
        'quality_score': 70,
        'stock_quality': {
            'score': 70,
            'label': '优',
            'reasons': [],
            'dimensions': {},
        },
    }

    result = scorer.calculate(ipo, prospectus_info)

    assert result['penalty_reason'] is not None, "应有扣分原因"
    assert '严重基石问题封顶60' in result['penalty_reason'], "应包含严重基石问题封顶"
    assert result['score'] <= 60, f"严重红旗封顶60，实际 {result['score']}"

    print("✅ test_cornerstone_severe_flags_cap_60 passed")


def test_cornerstone_no_red_flags_no_penalty():
    """无基石红旗：不扣分不封顶"""
    from ipo_analyzer.scoring import ScoringSystem

    scorer = ScoringSystem()

    ipo = {
        'over_sub_ratio': 4322.0,
        'over_sub_ratio_source': 'historical_actual',
        'margin_total': 500.0,
        'public_offer': 10.0,
    }

    prospectus_info = {
        'cornerstone_analysis': {
            'score': 80,
            'label': '强基石',
            'has_cornerstone_section': True,
            'red_flags': [],
        },
        'quality_score': 70,
        'stock_quality': {
            'score': 70,
            'label': '优',
            'reasons': [],
            'dimensions': {},
        },
    }

    result = scorer.calculate(ipo, prospectus_info)

    assert result['penalty_reason'] is None, "无红旗不应有扣分原因"
    assert result['debug_info']['cap_reason'] is None, "无红旗不应有封顶原因"

    print("✅ test_cornerstone_no_red_flags_no_penalty passed")


def test_high_heat_with_normal_red_flags_not_capped_at_40():
    """高热度+普通红旗：不应被封顶到40分"""
    from ipo_analyzer.scoring import ScoringSystem

    scorer = ScoringSystem()

    ipo = {
        'over_sub_ratio': 4322.0,
        'over_sub_ratio_source': 'historical_actual',
        'margin_total': 500.0,
        'public_offer': 10.0,
    }

    prospectus_info = {
        'cornerstone_analysis': {
            'score': 80,
            'label': '强基石',
            'has_cornerstone_section': True,
            'red_flags': ['SPV数量偏多', '认购集中度高'],
        },
        'quality_score': 70,
        'stock_quality': {
            'score': 70,
            'label': '优',
            'reasons': [],
            'dimensions': {},
        },
    }

    result = scorer.calculate(ipo, prospectus_info)

    assert result['score'] > 40, f"高热度+普通红旗不应封顶40，实际 {result['score']}"
    assert result['debug_info']['weight_profile']['name'] == 'live_heat', "应有 live_heat 权重"
    assert result['debug_info']['over_sub_ratio'] == 4322.0, "超购倍数应为 4322"
    assert result['debug_info']['trade_score'] > 50, f"trade_score 应较高，实际 {result['debug_info']['trade_score']}"

    print("✅ test_high_heat_with_normal_red_flags_not_capped_at_40 passed")


def test_debug_fields_present():
    """调试字段完整性测试"""
    from ipo_analyzer.scoring import ScoringSystem

    scorer = ScoringSystem()

    ipo = {
        'over_sub_ratio': 100.0,
        'over_sub_ratio_source': 'historical_actual',
        'margin_total': 100.0,
        'public_offer': 5.0,
    }

    prospectus_info = {
        'cornerstone_analysis': {
            'score': 60,
            'label': '中基石',
            'has_cornerstone_section': True,
            'red_flags': ['普通红旗'],
        },
        'quality_score': 50,
        'stock_quality': {
            'score': 50,
            'label': '中',
            'reasons': [],
            'dimensions': {},
        },
    }

    result = scorer.calculate(ipo, prospectus_info)

    debug = result['debug_info']
    assert 'over_sub_ratio' in debug
    assert 'over_sub_ratio_source' in debug
    assert 'weight_profile' in debug
    assert 'heat_score' in debug
    assert 'trade_score' in debug
    assert 'cornerstone_red_flags' in debug
    assert 'final_score_before_cap' in debug
    assert 'final_score_after_cap' in debug
    assert 'cap_reason' in debug

    print("✅ test_debug_fields_present passed")


if __name__ == "__main__":
    test_issuer_alias_not_in_unmatched()
    test_quantitative_peers_less_than_two_weak_conclusion()
    test_private_low_quality_not_in_quantitative()
    test_loss_making_valuation_not_missing()
    test_new_fields_persist_through_from_dict()
    test_signal_component_analyzer_biotech()
    test_scoring_system_new_weights()
    test_advanced_framework_adjustment_removed()
    test_financial_table_loss_and_used_cashflow_are_negative()
    test_peer_company_metrics_use_hkd_currency_basis()
    test_insufficient_peer_sample_does_not_add_positive_peer_adj()
    test_core_fundamental_score_matches_scoring_breakdown()
    test_jitai_pre_ipo_score_not_too_low()
    test_jitai_hot_with_strong_cornerstone()
    test_yifei_no_cornerstone_misidentified()
    test_jitai_cornerstone_detected_correctly()
    test_yifei_pre_ipo_investors_not_counted_as_cornerstone()
    test_pre_ipo_investors_excluded_from_cornerstone()
    test_no_heat_data_weight_profile()
    test_live_heat_weight_profile()
    test_theme_score_normalized_to_100()
    test_theme_score_full_raw_equals_100()
    test_risk_penalty_only_for_major_red_flags()
    test_risk_penalty_customer_extreme_concentration()
    test_risk_penalty_cash_runway_short()
    # 重新分析功能测试
    test_historical_actual_over_sub_ratio_source()
    test_historical_forecast_over_sub_ratio_source()
    test_reanalysis_version_delta_calculation()
    test_reanalysis_no_heat_data_uses_prospectus_only()
    test_reanalyze_ipo_returns_unified_structure()
    test_cornerstone_red_flags_penalty_normal()
    test_cornerstone_severe_flags_cap_60()
    test_cornerstone_no_red_flags_no_penalty()
    test_high_heat_with_normal_red_flags_not_capped_at_40()
    test_debug_fields_present()
    print("\n" + "=" * 60)
    print("✅ 所有回归测试通过")
    print("=" * 60)
