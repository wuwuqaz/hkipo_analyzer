"""盈利质量综合分析器单元测试。"""

from ipo_analyzer.analyzers._earnings_quality import EarningsQualityAnalyzer


def test_default_returns_when_no_data():
    """测试数据缺失时返回默认值。"""
    result = EarningsQualityAnalyzer().analyze({}, '')
    assert result['earnings_quality_score'] == 50
    assert result['label'] == '一般'  # 50 分对应"一般"
    assert result['confidence'] == 'computed'


def test_high_receivables_growth_penalty():
    """测试应收增速远高于收入增速时扣分。"""
    prospectus_info = {
        'revenue': 100.0,
        'revenue_y1': 80.0,  # 收入增长 25%
        'net_profit': 20.0,
    }
    cashflow = {
        'receivables_amount': 60.0,
        'receivables_amount_prev': 40.0,  # 应收增长 50%
        'operating_cash_flow': 15.0,
    }
    prospectus_info['cashflow'] = cashflow

    result = EarningsQualityAnalyzer().analyze(prospectus_info, '')
    assert result['receivables_quality']['score'] < 50
    assert any('应收增速' in r for r in result['receivables_quality']['reasons'])


def test_strong_cashflow_quality_bonus():
    """测试经营现金流质量强时加分。"""
    prospectus_info = {
        'revenue': 100.0,
        'revenue_y1': 80.0,
        'net_profit': 20.0,
    }
    cashflow = {
        'operating_cash_flow': 25.0,  # OCF > 净利润
        'ocf_to_net_profit': 1.25,
        'ocf_to_revenue': 0.25,
    }
    prospectus_info['cashflow'] = cashflow

    result = EarningsQualityAnalyzer().analyze(prospectus_info, '')
    assert result['cashflow_quality']['score'] > 50
    assert any('利润含金量' in r for r in result['cashflow_quality']['reasons'])


def test_high_non_recurring_ratio_penalty():
    """测试非经常性损益占比高时扣分。"""
    prospectus_info = {
        'net_profit': 50.0,
    }
    profit_sustainability = {
        'non_recurring_ratio': 0.40,  # 40% 非经常性损益
        'non_gaap_net_profit': 30.0,
        'government_subsidy': 5.0,
    }
    prospectus_info['profit_sustainability'] = profit_sustainability

    result = EarningsQualityAnalyzer().analyze(prospectus_info, '')
    assert result['non_recurring_quality']['score'] < 50
    assert any('非经常性损益' in r for r in result['non_recurring_quality']['reasons'])


def test_opposite_direction_penalty():
    """测试扣非净利润与净利润反向时严重扣分。"""
    prospectus_info = {
        'net_profit': 20.0,  # 净利润为正
    }
    profit_sustainability = {
        'non_recurring_ratio': 1.5,
        'non_gaap_net_profit': -10.0,  # 扣非为负
    }
    prospectus_info['profit_sustainability'] = profit_sustainability

    result = EarningsQualityAnalyzer().analyze(prospectus_info, '')
    assert result['non_recurring_quality']['score'] < 30
    assert any('实际经营亏损' in r for r in result['non_recurring_quality']['reasons'])


def test_high_inventory_penalty():
    """测试存货/收入偏高时扣分。"""
    prospectus_info = {
        'revenue': 100.0,
        'revenue_y1': 90.0,
    }
    cashflow = {
        'inventory_amount': 80.0,  # 存货/收入 = 80%
        'inventory_amount_prev': 50.0,  # 存货增长 60%
        'inventory_turnover_days_latest': 180,
    }
    prospectus_info['cashflow'] = cashflow

    result = EarningsQualityAnalyzer().analyze(prospectus_info, '')
    assert result['inventory_quality']['score'] < 50
    assert any('存货' in r for r in result['inventory_quality']['reasons'])


def test_composite_score_calculation():
    """测试综合评分计算。"""
    prospectus_info = {
        'revenue': 100.0,
        'revenue_y1': 80.0,
        'net_profit': 20.0,
        'cashflow': {
            'operating_cash_flow': 22.0,
            'ocf_to_net_profit': 1.1,
            'receivables_amount': 30.0,
            'receivables_amount_prev': 25.0,
            'inventory_amount': 20.0,
            'inventory_amount_prev': 18.0,
        },
        'profit_sustainability': {
            'non_recurring_ratio': 0.10,
            'non_gaap_net_profit': 18.0,
        },
    }

    result = EarningsQualityAnalyzer().analyze(prospectus_info, '')
    # 综合评分应该在 0-100 之间
    assert 0 <= result['earnings_quality_score'] <= 100
    # 由于各项指标都不错，评分应该高于默认值
    assert result['earnings_quality_score'] >= 50


def test_label_calculation():
    """测试标签计算。"""
    # 测试不同评分对应的标签
    analyzer = EarningsQualityAnalyzer()

    assert analyzer._calculate_label(80) == '强'
    assert analyzer._calculate_label(65) == '良好'
    assert analyzer._calculate_label(50) == '一般'
    assert analyzer._calculate_label(35) == '偏弱'
    assert analyzer._calculate_label(20) == '弱'


def test_biotech_cashflow_exempt():
    """测试Biotech经营现金流为负时的豁免。"""
    prospectus_info = {
        'revenue': 10.0,
        'revenue_y1': 8.0,
        'net_profit': -30.0,
        'sector': 'healthcare',
        'listing_suffix': 'B',
    }
    cashflow = {
        'operating_cash_flow': -25.0,  # OCF 为负
        'cash_runway_years': 6.0,  # 但现金 runway 充足
    }
    prospectus_info['cashflow'] = cashflow

    result = EarningsQualityAnalyzer().analyze(prospectus_info, '')
    # Biotech 现金 runway 充足时，不应该因为 OCF 为负而严重扣分
    assert result['cashflow_quality']['score'] >= 40


def test_risk_and_positive_signals():
    """测试风险信号和正面信号收集。"""
    prospectus_info = {
        'revenue': 100.0,
        'revenue_y1': 80.0,
        'net_profit': 20.0,
        'cashflow': {
            'operating_cash_flow': 25.0,
            'ocf_to_net_profit': 1.25,
            'receivables_amount': 15.0,
            'receivables_amount_prev': 12.0,
            'inventory_amount': 10.0,
            'inventory_amount_prev': 8.0,
        },
        'profit_sustainability': {
            'non_recurring_ratio': 0.05,
            'non_gaap_net_profit': 19.0,
        },
    }

    result = EarningsQualityAnalyzer().analyze(prospectus_info, '')
    # 应该有正面信号
    assert len(result['positive_signals']) > 0 or result['earnings_quality_score'] >= 60


def test_accrual_quality_calculation():
    """测试应计质量计算。"""
    prospectus_info = {
        'net_profit': 20.0,
    }
    cashflow = {
        'operating_cash_flow': 18.0,  # 应计利润 = 2
    }
    prospectus_info['cashflow'] = cashflow

    result = EarningsQualityAnalyzer().analyze(prospectus_info, '')
    # 应计利润/净利润 = 2/20 = 10%，应该评分较高
    assert result['accrual_quality']['score'] >= 50


def test_weak_cashflow_penalty():
    """测试经营现金流弱时扣分。"""
    prospectus_info = {
        'net_profit': 20.0,
    }
    cashflow = {
        'operating_cash_flow': 5.0,  # OCF/净利润 = 0.25
        'ocf_to_net_profit': 0.25,
    }
    prospectus_info['cashflow'] = cashflow

    result = EarningsQualityAnalyzer().analyze(prospectus_info, '')
    assert result['cashflow_quality']['score'] < 50
    assert any('利润含金量' in r for r in result['cashflow_quality']['reasons'])
