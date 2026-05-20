"""盈利可持续性分析器单元测试。"""

from ipo_analyzer.analyzers._profit_sustainability import ProfitSustainabilityAnalyzer


def test_extract_government_subsidy():
    """测试提取政府补贴。"""
    text = """
    本公司收到政府补助人民币15.5百万元。
    """
    result = ProfitSustainabilityAnalyzer().analyze({}, text)
    assert result['government_subsidy'] is not None
    assert 10 <= result['government_subsidy'] <= 20


def test_high_non_recurring_ratio_detection():
    """测试高非经常性损益占比识别。"""
    text = """
    非经常性损益为50百万元。
    扣非净利润为30百万元。
    """
    prospectus_info = {'net_profit': 80.0, '_extracted_text': text}
    result = ProfitSustainabilityAnalyzer().analyze(prospectus_info, text)
    assert result['non_recurring_ratio'] is not None
    assert result['non_recurring_ratio'] > 0.3
    assert len(result['quality_flags']) > 0


def test_sustainable_profit_score():
    """测试可持续盈利情况下评分较高。"""
    text = """
    扣非净利润为50百万元。
    """
    prospectus_info = {'net_profit': 52.0, '_extracted_text': text}
    result = ProfitSustainabilityAnalyzer().analyze(prospectus_info, text)
    assert result['sustainability_score'] >= 70
    assert result['label'] in ('可持续', '基本可持续')


def test_biotech_unprofitable_exempt():
    """测试Biotech未盈利情况不扣分。"""
    text = """
    本公司仍在研发阶段，尚未商业化。
    """
    prospectus_info = {
        'net_profit': -50.0,
        'sector': 'healthcare',
        'listing_suffix': 'B',
        '_extracted_text': text,
    }
    result = ProfitSustainabilityAnalyzer().analyze(prospectus_info, text)
    # Biotech未盈利应该不扣分，评分不应过低
    assert result['sustainability_score'] >= 40


def test_profit_quality_flag_opposite_direction():
    """测试扣非与净利润反向时识别风险。"""
    text = """
    扣非净利润为-10百万元。
    """
    prospectus_info = {'net_profit': 20.0, '_extracted_text': text}
    result = ProfitSustainabilityAnalyzer().analyze(prospectus_info, text)
    assert any('扣非' in f for f in result['quality_flags'])
    assert result['sustainability_score'] < 50


def test_missing_data_returns_default():
    """测试数据缺失时返回默认值。"""
    result = ProfitSustainabilityAnalyzer().analyze({}, '')
    assert result['non_recurring_ratio'] is None
    assert result['sustainability_score'] == 50
    assert result['label'] == '缺失'
    assert result['confidence'] == 'missing'
