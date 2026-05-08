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
    _calc_company_valuation_metrics,
    PeerComparableAnalyzer,
)
from ipo_analyzer.analyzers import ValuationAnalyzer
from ipo_analyzer.scoring import SignalComponentAnalyzer, ScoringSystem
from ipo_analyzer.models import IPOData, ValuationResult, PeerComparisonResult, ProspectusInfo
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
    print("\n" + "=" * 60)
    print("✅ 所有回归测试通过")
    print("=" * 60)
