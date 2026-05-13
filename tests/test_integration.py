"""集成测试 — 验证全流程和数据完整性。"""

import sys
import os


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestIntegrationPipeline:
    """验证核心分析流程的端到端行为。"""

    def test_full_scoring_pipeline_with_fixtures(self, base_ipo_data, base_prospectus_info):
        """使用 fixtures 验证从评分计算到输出结构完整性。"""
        from ipo_analyzer.scoring import ScoringSystem, ProspectusQualityAnalyzer, SignalComponentAnalyzer
        from ipo_analyzer.analyzers import ValuationAnalyzer, RiskFactorAnalyzer
        from ipo_analyzer.core import _calculate_risk_penalty

        pi = dict(base_prospectus_info)
        ipo = dict(base_ipo_data)

        # 运行估值和风险分析器
        pi['valuation'] = ValuationAnalyzer().analyze(pi, text='')
        pi['risk_factors'] = RiskFactorAnalyzer().analyze(pi, text='')

        # 验证估值分析器结果结构
        assert 'valuation_label' in pi['valuation']
        assert 'pe_ratio' in pi['valuation']
        assert '_error' not in pi['valuation'], f"Valuation analyzer error: {pi['valuation'].get('_error')}"

        # 验证风险分析器结果结构
        assert 'total_penalty' in pi['risk_factors']
        assert 'confidence' in pi['risk_factors']

        # 运行股票质量分析
        quality = ProspectusQualityAnalyzer().analyze(pi)
        pi['stock_quality'] = quality
        assert 'score' in quality

        # 运行信号分析
        signal = SignalComponentAnalyzer().analyze(ipo, pi, text='')
        assert 'components' in signal

        # 运行评分
        scoring = ScoringSystem().calculate(ipo, pi, signal_components=signal.get('components'))
        assert 0 <= scoring['score'] <= 100
        assert 'ipo_trade_score' in scoring
        assert 'long_term_score' in scoring
        assert 'subscription_recommendation' in scoring

        # 风险惩罚
        risk_penalty = _calculate_risk_penalty(pi)
        assert 'total_penalty' in risk_penalty
        assert 'breakdown' in risk_penalty

    def test_analyzer_error_tracking(self, base_prospectus_info):
        """验证分析器的 _error 追踪字段在异常时被正确设置。"""
        from ipo_analyzer.analyzers import GeographicExpansionAnalyzer

        bad_info = {'sector': 'hardtech'}
        result = GeographicExpansionAnalyzer().analyze(bad_info, text=None)

        assert isinstance(result, dict)
        assert 'overseas_growth_label' in result
        assert '_error' in result, "Analyzer should record error when text is None"

    def test_reanalysis_pipeline_output_structure(self, base_ipo_data, base_prospectus_info, tmp_output_dir):
        """验证重新分析管道返回统一结构。"""
        from ipo_analyzer.core import _run_scoring_pipeline

        pi = dict(base_prospectus_info)
        pi['_extracted_text'] = 'Sample prospectus text for testing the pipeline flow.'
        ipo = dict(base_ipo_data)

        result = _run_scoring_pipeline(ipo, pi, pi.get('_extracted_text', ''))
        assert isinstance(result, dict)
        assert 'score' in result
        assert 'hk_code' in result

    def test_fee_rate_from_settings(self):
        """验证入场费率已集中到 SETTINGS。"""
        from ipo_analyzer.settings import SETTINGS
        rate = SETTINGS.fx.entry_fee_rate
        assert rate > 0.01
        assert rate < 0.02

    def test_cornerstone_yaml_loading(self):
        """验证基石投资者档案从 YAML 正常加载。"""
        from ipo_analyzer.cornerstone import CornerstoneAnalyzer
        profiles = CornerstoneAnalyzer.INVESTOR_PROFILES
        assert len(profiles) >= 50
        assert any(p['tier'] == 'S' for p in profiles)
        assert any(p['tier'] == 'A' for p in profiles)
