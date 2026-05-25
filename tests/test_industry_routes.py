#!/usr/bin/env python3
"""行业场景测试 — 验证不同行业路由下估值标签是否正确触发。

运行:
    python3 -m pytest tests/test_industry_routes.py -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ipo_analyzer.analyzers import ValuationAnalyzer
from ipo_analyzer.scoring import ScoringSystem, SignalComponentAnalyzer, ProspectusQualityAnalyzer
from ipo_analyzer.peer_comps import PeerComparableAnalyzer


def _build_base_ipo():
    return {
        'company_name': 'TestCo',
        'hk_code': '1234',
        'margin_total': None,
        'public_offer': 1.0,
        'over_sub_ratio': None,
        'over_sub_ratio_source': 'missing',
    }


def _run_full_scoring(ipo, prospectus_info):
    """运行完整的评分 pipeline，返回 scoring result。

    注意：mock LiveMarketHeatAnalyzer 避免测试中进行 yfinance 网络请求。
    """
    from unittest.mock import patch
    text = prospectus_info.get('_extracted_text', '')

    pi = prospectus_info
    pi['peer_comparison'] = PeerComparableAnalyzer().analyze(pi, text, ipo)
    pi['valuation'] = ValuationAnalyzer().analyze(pi, text, ipo)

    with patch('ipo_analyzer.signal_analyzer.LiveMarketHeatAnalyzer.analyze', return_value={}):
        signal = SignalComponentAnalyzer().analyze(ipo, pi, text)
    quality = ProspectusQualityAnalyzer().analyze(pi)
    pi['stock_quality'] = quality

    scorer = ScoringSystem()
    scoring = scorer.calculate(ipo, pi, signal_components=signal.get('components'))
    return scoring, signal, quality


def test_tech_saas_unprofitable_high_growth():
    """SaaS/科技：高 PS、未盈利、高增速、高毛利。"""
    ipo = _build_base_ipo()
    prospectus_info = {
        'revenue': 800,
        'revenue_y1': 300,
        'net_profit': -200,
        'gross_margin': 75,
        'profitable': False,
        'market_cap_hkd_million': 12000,
        'offer_price': 25.0,
        'pro_forma_NTA_per_share_HKD': 3.0,
        'sector': 'hardtech',
        'financial_currency': 'RMB',
        'extracted_company_name': 'TestCloud-SaaS',
        '_extracted_text': 'cloud saas platform ai subscription revenue recurring ARR NRR',
        'public_offer_ratio_pct': 8.0,
        'issuance_ratio_pct': 12.0,
        'cornerstone_offer_ratio_pct': 40.0,
        'rd_expense': 150,
        'rnd_pipeline': {
            'technology_moat_score': 7,
            'pipeline_quality_label': '强',
            'product_count_pipeline': 3,
        },
        'cornerstone_analysis': {
            'score': 60,
            'label': 'A级',
            'grade_band': 'A',
            'has_cornerstone_section': True,
        },
        'peer_comparison': {
            'subsector': 'ai_saas_platform',
            'scarcity_score': 6,
            'peer_score': 8,
            'valuation_position': '样本不足，仅作定性参考',
            'quantitative_peer_count': 1,
        },
        'valuation': {
            'ps_ratio': 15.0,
            'pe_ratio': None,
            'cash_runway_years': 3.5,
            'valuation_framework_type': 'tech_saas',
            'valuation_label': 'PS辅助估值',
            'valuation_profitability_type': 'loss_making',
            'revenue_too_small_for_ps': False,
        },
        'financial_extract_confidence': 'consolidated_statement',
        'financial_data_quality_flags': [],
    }

    scoring, signal, quality = _run_full_scoring(ipo, prospectus_info)

    # 未盈利科技公司不应得到"缺失"估值标签
    val_label = prospectus_info['valuation']['valuation_label']
    assert val_label != '缺失', f"SaaS 未盈利公司估值不应为'缺失': {val_label}"

    # 高增速应体现在基本面分中
    assert scoring['fundamental_score'] >= 30, f"高增速 SaaS 基本面应≥30，实际 {scoring['fundamental_score']}"

    # 主题分应有加分（hardtech + AI/SaaS 关键词）
    assert scoring['theme_score'] >= 20, f"SaaS AI 主题分应≥20，实际 {scoring['theme_score']}"

    # 估值面不应为 0（有 PS 和稀缺性评分）
    assert scoring['valuation_score'] >= 20, f"有 PS 的 SaaS 估值面应≥20，实际 {scoring['valuation_score']}"

    print(f"✅ test_tech_saas_unprofitable_high_growth passed (score={scoring['score']}, "
          f"fundamental={scoring['fundamental_score']}, theme={scoring['theme_score']}, "
          f"valuation={scoring['valuation_score']})")


def test_consumer_mfg_profitable_pe_driven():
    """消费制造：盈利、PE 主导、周转指标、中等增速。"""
    ipo = _build_base_ipo()
    prospectus_info = {
        'revenue': 5000,
        'revenue_y1': 4200,
        'net_profit': 500,
        'gross_margin': 35,
        'profitable': True,
        'market_cap_hkd_million': 8000,
        'offer_price': 8.0,
        'pro_forma_NTA_per_share_HKD': 4.0,
        'sector': 'consumer',
        'financial_currency': 'RMB',
        'extracted_company_name': 'TestConsumer',
        '_extracted_text': 'consumer products manufacturing retail distribution brand',
        'public_offer_ratio_pct': 10.0,
        'issuance_ratio_pct': 15.0,
        'cornerstone_offer_ratio_pct': 35.0,
        'rnd_pipeline': {
            'technology_moat_score': 3,
            'pipeline_quality_label': '弱',
            'product_count_pipeline': 0,
        },
        'cornerstone_analysis': {
            'score': 50,
            'label': 'B级',
            'grade_band': 'B',
            'has_cornerstone_section': True,
        },
        'peer_comparison': {
            'subsector': 'consumer_brands',
            'scarcity_score': 3,
            'peer_score': 6,
            'valuation_position': '合理',
            'quantitative_peer_count': 3,
        },
        'valuation': {
            'ps_ratio': 1.6,
            'pe_ratio': 16.0,
            'cash_runway_years': None,
            'valuation_framework_type': 'pe_driven',
            'valuation_label': '合理',
            'valuation_profitability_type': 'profitable',
        },
        'financial_extract_confidence': 'consolidated_statement',
        'financial_data_quality_flags': [],
    }

    scoring, signal, quality = _run_full_scoring(ipo, prospectus_info)

    # 盈利公司应有合理的 PE 估值标签
    val_label = prospectus_info['valuation']['valuation_label']
    assert val_label in ('合理', '低估', '偏贵但可解释'), f"盈利消费公司估值标签异常: {val_label}"

    # 基本面分应较高（盈利 + 正增长 + 合理毛利）
    assert scoring['fundamental_score'] >= 50, f"盈利消费公司基本面应≥50，实际 {scoring['fundamental_score']}"

    # 主题分不应过高（consumer 赛道，非主线）
    assert scoring['theme_score'] <= 60, f"消费公司主题分不应过高，实际 {scoring['theme_score']}"

    print(f"✅ test_consumer_mfg_profitable_pe_driven passed (score={scoring['score']}, "
          f"fundamental={scoring['fundamental_score']}, theme={scoring['theme_score']}, "
          f"valuation={scoring['valuation_score']})")


def test_biotech_loss_making_pipeline_valuation():
    """Biotech：亏损、管线估值、18A 框架。"""
    ipo = _build_base_ipo()
    prospectus_info = {
        'revenue': 50,
        'revenue_y1': 10,
        'net_profit': -400,
        'gross_margin': 90,
        'profitable': False,
        'market_cap_hkd_million': 5000,
        'offer_price': 15.0,
        'pro_forma_NTA_per_share_HKD': 1.5,
        'sector': 'healthcare',
        'financial_currency': 'RMB',
        'extracted_company_name': 'TestBio-B',
        '_extracted_text': '18A biotech clinical stage Phase II oncology immuno-oncology pipeline',
        'public_offer_ratio_pct': 6.0,
        'issuance_ratio_pct': 10.0,
        'cornerstone_offer_ratio_pct': 50.0,
        'rd_expense': 120,
        'rnd_pipeline': {
            'technology_moat_score': 8,
            'pipeline_quality_label': '强',
            'product_count_pipeline': 4,
            'latest_clinical_stage': 'Phase II',
        },
        'cornerstone_analysis': {
            'score': 75,
            'label': 'A级',
            'grade_band': '强A',
            'has_cornerstone_section': True,
        },
        'peer_comparison': {
            'subsector': 'io_oncology',
            'scarcity_score': 7,
            'peer_score': 9,
            'valuation_position': '样本不足，仅作定性参考',
            'quantitative_peer_count': 1,
        },
        'valuation': {
            'ps_ratio': 100.0,
            'pe_ratio': None,
            'market_cap_to_rd_ratio': 42.0,
            'cash_runway_years': 3.0,
            'valuation_framework_type': '18A_biotech',
            'valuation_label': 'PS失真，仅作参考',
            'valuation_profitability_type': 'loss_making',
            'revenue_too_small_for_ps': True,
        },
        'financial_extract_confidence': 'consolidated_statement',
        'financial_data_quality_flags': [],
    }

    scoring, signal, quality = _run_full_scoring(ipo, prospectus_info)

    # Biotech 亏损公司估值不应为"缺失"
    val_label = prospectus_info['valuation']['valuation_label']
    assert val_label != '缺失', f"Biotech 估值不应为'缺失': {val_label}"

    # 优质管线 + 强基石应有较好的基本面分
    assert scoring['fundamental_score'] >= 35, f"优质管线 biotech 基本面应≥35，实际 {scoring['fundamental_score']}"

    # 主题分应有加分（healthcare + oncology + 稀缺）
    assert scoring['theme_score'] >= 30, f"IO oncology biotech 主题分应≥30，实际 {scoring['theme_score']}"

    print(f"✅ test_biotech_loss_making_pipeline_valuation passed (score={scoring['score']}, "
          f"fundamental={scoring['fundamental_score']}, theme={scoring['theme_score']}, "
          f"valuation={scoring['valuation_score']})")


def test_validators_catch_sanity_errors():
    """校验器应能捕捉明显异常的数值。"""
    from ipo_analyzer.validators import ProspectusValidator

    validator = ProspectusValidator()

    # 收入过大（疑似 billion 被当作 million）
    result = validator.validate({'revenue': 2_000_000})
    assert not result['valid']
    assert any('收入' in e and '单位错误' in e for e in result['errors'])

    # 毛利率超过 100%
    result = validator.validate({'gross_margin': 150})
    assert not result['valid']
    assert any('毛利率' in e for e in result['errors'])

    # 发行价异常高
    result = validator.validate({'offer_price': 50_000})
    assert not result['valid']  # error 级别

    # 正常值应通过
    result = validator.validate({
        'revenue': 500,
        'net_profit': 50,
        'market_cap_hkd_million': 5000,
        'offer_price': 10.0,
        'gross_margin': 40,
        'financial_currency': 'RMB',
    })
    assert result['valid']
    assert len(result['errors']) == 0

    print("✅ test_validators_catch_sanity_errors passed")


def test_validators_date_consistency():
    """校验器应能发现日期不一致。"""
    from ipo_analyzer.validators import ProspectusValidator

    validator = ProspectusValidator()

    # 开始日期晚于结束日期
    result = validator.validate({
        'apply_start_date': '2026-06-01',
        'apply_end_date': '2026-05-01',
    })
    assert not result['valid']
    assert any('开始日期晚于结束' in e for e in result['errors'])

    # 正常日期应通过
    result = validator.validate({
        'apply_start_date': '2026-05-01',
        'apply_end_date': '2026-05-05',
        'listing_date': '2026-05-12',
    })
    assert result['valid']

    print("✅ test_validators_date_consistency passed")


def test_validators_cross_field_pe():
    """校验器应能发现跨字段不一致（如 PE 极端值）。"""
    from ipo_analyzer.validators import ProspectusValidator

    validator = ProspectusValidator()

    # PE 极高（净利润单位错误）
    result = validator.validate({
        'market_cap_hkd_million': 5000,
        'net_profit': 5,  # 500万利润 vs 50亿市值 = PE 1000
    })
    assert any('PE' in w for w in result['warnings'])

    print("✅ test_validators_cross_field_pe passed")
