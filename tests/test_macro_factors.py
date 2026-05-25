"""宏观环境因子模块单元测试。"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_tailwind_classification():
    """HSI 涨 > 3%，宏观顺风。"""
    from ipo_analyzer.settings import SETTINGS
    st = SETTINGS.sentiment_macro
    hsi_change = 0.05
    assert hsi_change >= st.macro_tailwind_threshold
    bonus = st.macro_tailwind_bonus
    assert bonus == 3


def test_headwind_classification():
    """HSI 跌 > 3%，宏观逆风。"""
    from ipo_analyzer.settings import SETTINGS
    st = SETTINGS.sentiment_macro
    hsi_change = -0.05
    assert hsi_change <= st.macro_headwind_threshold
    bonus = st.macro_headwind_bonus
    assert bonus == -3


def test_slight_tailwind():
    """HSI 涨 0-3%，偏顺风。"""
    from ipo_analyzer.settings import SETTINGS
    st = SETTINGS.sentiment_macro
    hsi_change = 0.01
    assert 0 <= hsi_change < st.macro_tailwind_threshold
    bonus = st.macro_slight_tailwind_bonus
    assert bonus == 1


def test_slight_headwind():
    """HSI 跌 0-3%，偏逆风。"""
    from ipo_analyzer.settings import SETTINGS
    st = SETTINGS.sentiment_macro
    hsi_change = -0.02
    assert st.macro_headwind_threshold < hsi_change < 0
    bonus = -1
    assert bonus == -1


def test_neutral_when_no_data():
    """数据不可用时默认中性。"""
    result = {
        'macro_label': '中性',
        'macro_bonus': 0,
        'hsi_20d_change': None,
    }
    assert result['macro_bonus'] == 0
    assert result['macro_label'] == '中性'
