"""资产负债结构分析器单元测试。"""

from ipo_analyzer.analyzers._balance_sheet import BalanceSheetAnalyzer


def test_extract_asset_liability_ratio():
    """测试提取资产负债率。"""
    text = """
    截至2023年12月31日，本公司资产负债率为55.2%。
    """
    result = BalanceSheetAnalyzer().analyze({}, text)
    assert result['asset_liability_ratio'] is not None
    assert 0.50 <= result['asset_liability_ratio'] <= 0.60


def test_extract_current_ratio():
    """测试提取流动比率。"""
    text = """
    流动比率：2.1
    """
    result = BalanceSheetAnalyzer().analyze({}, text)
    assert result['current_ratio'] is not None
    assert 2.0 <= result['current_ratio'] <= 2.2


def test_good_balance_sheet_score():
    """测试健康资产负债表评分较高。"""
    text = """
    资产负债率为45.0%。
    流动比率为2.5。
    利息保障倍数为8.5。
    """
    result = BalanceSheetAnalyzer().analyze({}, text)
    assert result['balance_sheet_score'] >= 70
    assert result['label'] == '稳健'


def test_risky_balance_sheet_flags():
    """测试高风险资产负债表识别风险标志。"""
    text = """
    资产负债率为75.0%。
    流动比率为1.2。
    利息保障倍数为2.0。
    """
    result = BalanceSheetAnalyzer().analyze({}, text)
    assert len(result['risk_flags']) > 0
    assert result['balance_sheet_score'] < 50


def test_missing_data_returns_default():
    """测试数据缺失时返回默认值。"""
    result = BalanceSheetAnalyzer().analyze({}, '')
    assert result['asset_liability_ratio'] is None
    assert result['balance_sheet_score'] == 50
    assert result['label'] == '缺失'
    assert result['confidence'] == 'missing'
