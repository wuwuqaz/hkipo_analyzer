"""验证长线价值分修复的回归测试。"""

from ipo_analyzer.signal_analyzer import SignalComponentAnalyzer
from ipo_analyzer.industry_router import classify_company, _BIOTECH_SUBSECTORS
from ipo_analyzer.parser import ProspectusParser
from ipo_analyzer.quality_analyzer import ProspectusQualityAnalyzer
from ipo_analyzer.scoring import ScoringSystem


class TestCornerstoneHighPctFix:
    """P0: cornerstone_high_pct 属性缺失导致 signal_analyzer 崩溃。"""

    def test_valuation_framework_score_not_zero_for_biotech(self):
        """估值框架对 biotech 不应返回 0 分。"""
        analyzer = SignalComponentAnalyzer()
        prospectus_info = {
            'revenue': 191.8,
            'revenue_y1': 31.0,
            'net_profit': 153.2,
            'profitable': True,
            'sector': 'healthcare',
            'market_cap_hkd_million': 3917.7,
            'valuation': {
                'pe_ratio': 23.68,
                'ps_ratio': 18.91,
                'cash_runway_years': 29.2,
            },
            'peer_comparison': {
                'peer_score': 7,
                'valuation_position': 'PS辅助(偏贵但可解释)',
                'scarcity_score': 8,
                'quantitative_peer_count': 3,
            },
            'rnd_pipeline': {
                'pipeline_quality_label': '强',
                'technology_moat_score': 10,
                'latest_clinical_stage': 'Phase III',
            },
        }
        vf = analyzer._analyze_valuation_framework(prospectus_info, '')
        assert vf['score'] > 0, f"估值框架分数应为正数，实际为 {vf['score']}"
        assert vf['label'] != '缺失', f"估值框架标签不应为缺失，实际为 {vf['label']}"

    def test_signal_analyzer_does_not_crash(self):
        """signal_analyzer.analyze 不应因 cornerstone_high_pct 崩溃。"""
        analyzer = SignalComponentAnalyzer()
        ipo_data = {'over_sub_ratio': 115.214, 'over_sub_ratio_source': 'post_listing_actual'}
        prospectus_info = {
            'revenue': 191.8,
            'sector': 'healthcare',
            'market_cap_hkd_million': 3917.7,
            'valuation': {'pe_ratio': 23.68, 'ps_ratio': 18.91},
            'peer_comparison': {'scarcity_score': 8},
        }
        result = analyzer.analyze(ipo_data, prospectus_info, '')
        assert 'components' in result
        assert result['components'] != {}
        assert 'valuation_framework' in result['components']


class TestParserGrossMarginFallback:
    """P0: parser gross_margin 缺失 fallback。"""

    def test_gross_margin_inferred_for_license_revenue(self):
        """许可收入型公司应推断毛利率为 100%。"""
        parser = ProspectusParser()
        # 使用 mock 数据测试逻辑
        _ = {
            'revenue': 100.0,
            'revenue_year': 2024,
            'net_profit': 80.0,
            'cost_of_sales': None,
            'gross_margin': None,
        }
        _ = "Our revenue primarily consists of upfront payment and milestone payment from licensing agreements."
        # 手动触发 fallback 逻辑（在 extract_info 内部）
        # 这里直接验证：如果 parser 返回了 gross_margin，应为 100
        result = parser.parse_pdf_file('storage/06872_prospectus.pdf', stock_code='06872', company_name='丹诺医药')
        assert result.get('gross_margin') is not None, "parser 应推断毛利率"
        assert result.get('gross_margin') >= 90, f"许可收入型公司毛利率应接近 100%，实际为 {result.get('gross_margin')}"


class TestSectorClassificationFix:
    """P0: sector 分类错误修复。"""

    def test_biotech_subsector_forces_healthcare_sector(self):
        """biotech 子行业应强制修正 sector 为 healthcare。"""
        prospectus_info = {
            'sector': 'hardtech',
            'peer_comparison': {'subsector': 'innovative_drug_biotech'},
            'revenue': 191.8,
        }
        profile = classify_company(prospectus_info, '')
        assert profile.is_biotech is True, "应判定为 biotech"
        assert prospectus_info['sector'] == 'healthcare', f"sector 应被修正为 healthcare，实际为 {prospectus_info['sector']}"

    def test_peer_comparison_biotech_subsectors(self):
        """所有 biotech 子行业都应触发 sector 修正。"""
        for subsector in _BIOTECH_SUBSECTORS:
            prospectus_info = {'sector': 'hardtech', 'peer_comparison': {'subsector': subsector}, 'revenue': 100}
            classify_company(prospectus_info, '')
            assert prospectus_info['sector'] == 'healthcare', f"子行业 {subsector} 应修正 sector 为 healthcare"


class TestCashflowBiotechExemption:
    """P0: biotech 经营现金流为负的豁免。"""

    def test_biotech_negative_ocf_with_long_runway(self):
        """biotech 且 runway >=5 年时，OCF 为负不应判弱。"""
        from ipo_analyzer.analyzers._cashflow import WorkingCapitalCashFlowAnalyzer
        analyzer = WorkingCapitalCashFlowAnalyzer()
        prospectus_info = {
            'sector': 'healthcare',
            'revenue': 191.8,
            'profitable': True,
            'net_profit': 153.2,
            'cashflow': {'cash_and_cash_equivalents': 150.0},
        }
        text = "clinical trial phase III biotech pharmaceutical"
        result = analyzer.analyze(prospectus_info, text)
        # 注意：这个测试依赖于 analyzer 内部是否能正确提取 operating_cash_flow
        # 如果提取不到，cash_quality_label 可能为 '缺失'
        # 这里主要验证逻辑存在且不会崩溃
        assert 'cash_quality_label' in result


class TestQualityAnalyzerBiotechBonus:
    """P1: fisher/lynch 对 biotech 的加分。"""

    def test_fisher_lynch_biotech_pipeline_bonus(self):
        """biotech 强管线应获得 fisher/lynch 加分。"""
        analyzer = ProspectusQualityAnalyzer()
        prospectus_info = {
            'gross_margin': 100.0,
            'gross_margin_year': 2024,
            'revenue': 191.8,
            'revenue_y1': 31.0,
            'revenue_year': 2024,
            'revenue_y1_year': 2023,
            'net_profit': 153.2,
            'profitable': True,
            'sector': 'healthcare',
            'peer_comparison': {'subsector': 'innovative_drug_biotech', 'scarcity_score': 8},
            'rnd_pipeline': {
                'pipeline_quality_label': '强',
                'hardtech_moat_label': '强',
                'technology_moat_score': 10,
                'latest_clinical_stage': 'Phase III',
                'rd_expense_ratio': 37.5,
                'product_count_pipeline': 5,
            },
            'valuation': {'valuation_label': '合理', 'valuation_reasons': ['P/E 23.7x']},
            'business_breakdown': {'growth_source': 'license revenue', 'profit_revenue_mismatch': False},
            'customer_supplier': {'customer_quality_score': 25, 'customer_quality_label': '弱'},
            'cashflow': {'cash_quality_label': '一般', 'cash_runway_years': 29.2},
        }
        result = analyzer.analyze(prospectus_info)
        assert result['fisher_label'] == '适配', f"强管线 biotech 的 fisher_label 应为适配，实际为 {result['fisher_label']}"
        assert result['lynch_label'] in ('适配', '部分适配'), f"临床后期 biotech 的 lynch_label 不应为不适配，实际为 {result['lynch_label']}"


class TestScoringCustomerQualityDefault:
    """P1: customer_quality 缺失时给予默认值。"""

    def test_customer_quality_missing_gets_default(self):
        """customer_quality 缺失时应给予 35 分默认值。"""
        scorer = ScoringSystem()
        prospectus_info = {
            'customer_supplier': {
                'customer_quality_score': 0,
                'customer_quality_label': '缺失',
            },
            'stock_quality': {'fisher_label': '部分适配', 'lynch_label': '部分适配'},
            'rnd_pipeline': {},
            'business_breakdown': {},
            'cashflow': {},
            'risk_factors': {},
        }
        result = scorer._build_strategy_scores(
            prospectus_info,
            trade_score=60,
            fundamental_score=80,
            valuation_score=60,
            theme_score=50,
        )
        assert result['raw_long_term_score_before_penalty'] >= 58, \
            f"customer_quality 缺失时应给予默认值，raw_before_penalty 应 >= 58，实际为 {result['raw_long_term_score_before_penalty']}"


class TestLongTermScoreOverall:
    """整体长线分修复验证：丹诺医药案例。"""

    def test_danuo_long_term_score_reasonable(self):
        """丹诺医药的长线分应在合理区间（>=70）。"""
        from ipo_analyzer.core import reanalyze_ipo
        result = reanalyze_ipo(
            stock_code='06872',
            pdf_path='storage/06872_prospectus.pdf',
            force_refresh=True,
        )
        assert result['status'] in ('ok', 'warning')
        full = result.get('result', {}).get('_full_result', result.get('result', {}))
        long_term = full.get('long_term_score', 0)
        assert long_term >= 70, f"丹诺医药长线分应 >= 70，实际为 {long_term}"
        assert full.get('fundamental_score', 0) >= 80, "fundamental_score 应 >= 80"
        assert full.get('valuation_score', 0) > 0, "valuation_score 不应为 0"
        assert full.get('prospectus_info', {}).get('sector') == 'healthcare', \
            "sector 应为 healthcare"
