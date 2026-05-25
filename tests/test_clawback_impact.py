"""回拨机制单元测试。"""

from ipo_analyzer.clawback_impact import analyze_clawback_impact


def test_no_trigger():
    """超购<15倍不触发回拨。"""
    info = {'over_sub_ratio': 10, 'public_offer_ratio_pct': 10.0}
    result = analyze_clawback_impact(info)
    assert result['clawback_triggered'] is False
    assert result['impact_score'] == 0


def test_moderate_clawback():
    """超购15-50倍触发回拨，公开比例增加。"""
    info = {'over_sub_ratio': 20, 'public_offer_ratio_pct': 10.0}
    result = analyze_clawback_impact(info)
    assert result['clawback_triggered'] is True
    assert result['clawback_ratio'] == 30.0
    assert result['impact_score'] == -2  # gap=20, 回拨显著


def test_significant_clawback():
    """超购倍数较高触发显著回拨。"""
    info = {'over_sub_ratio': 30, 'public_offer_ratio_pct': 10.0}
    result = analyze_clawback_impact(info)
    assert result['impact_score'] == -2
    assert result['clawback_ratio'] == 30.0


def test_extreme_clawback():
    """超购>100倍触发最大回拨。"""
    info = {'over_sub_ratio': 200, 'public_offer_ratio_pct': 10.0}
    result = analyze_clawback_impact(info)
    assert result['impact_score'] == -4
    assert result['clawback_ratio'] == 50.0


def test_actual_clawback_override():
    """实际clawback_max_pct覆盖计算值。"""
    info = {
        'over_sub_ratio': 30,
        'public_offer_ratio_pct': 10.0,
        'public_offer_clawback_max_pct': 45.0,
    }
    result = analyze_clawback_impact(info)
    assert result['clawback_ratio'] == 45.0


def test_no_data():
    """无超购数据时不触发。"""
    info = {'public_offer_ratio_pct': 10.0}
    result = analyze_clawback_impact(info)
    assert result['impact_score'] == 0
    assert result['confidence'] == 'insufficient_data'
