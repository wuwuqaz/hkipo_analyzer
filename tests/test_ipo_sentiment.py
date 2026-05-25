"""市场IPO情绪模块单元测试。"""

import json
import tempfile
from datetime import datetime, timedelta
from ipo_analyzer.ipo_sentiment import _calculate_sentiment, _extract_listed_records


def _make_history_file(records):
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
    json.dump(records, tmp)
    tmp.close()
    return tmp.name


def _make_record(list_date, first_day_return, is_break=False):
    return {
        'post_listing': {
            'listing_date': list_date,
            'first_day_return': first_day_return,
            'is_break': is_break,
        }
    }


def test_hot_sentiment():
    """近1月平均收益 > 10%，情绪火热。"""
    now = datetime.now()
    records = [
        _make_record((now - timedelta(days=5)).strftime('%Y-%m-%d'), 15.0),
        _make_record((now - timedelta(days=10)).strftime('%Y-%m-%d'), 12.0),
        _make_record((now - timedelta(days=15)).strftime('%Y-%m-%d'), 8.0),
    ]
    from ipo_analyzer.settings import SETTINGS
    st = SETTINGS.sentiment_macro
    extracted = _extract_listed_records(records)
    result = _calculate_sentiment(extracted, now, st)
    assert result['sentiment_label'] == '火热'
    assert result['sentiment_bonus'] == 5
    assert result['confidence'] == 'history'


def test_warm_sentiment():
    """近1月平均收益 5-10%，情绪偏热。"""
    now = datetime.now()
    records = [
        _make_record((now - timedelta(days=5)).strftime('%Y-%m-%d'), 8.0),
        _make_record((now - timedelta(days=10)).strftime('%Y-%m-%d'), 6.0),
        _make_record((now - timedelta(days=15)).strftime('%Y-%m-%d'), 4.0),
    ]
    from ipo_analyzer.settings import SETTINGS
    st = SETTINGS.sentiment_macro
    extracted = _extract_listed_records(records)
    result = _calculate_sentiment(extracted, now, st)
    assert result['sentiment_bonus'] == 3
    assert result['sentiment_label'] == '偏热'


def test_cold_sentiment():
    """近1月平均 < -5%，情绪冷清。"""
    now = datetime.now()
    records = [
        _make_record((now - timedelta(days=5)).strftime('%Y-%m-%d'), -8.0),
        _make_record((now - timedelta(days=10)).strftime('%Y-%m-%d'), -6.0),
        _make_record((now - timedelta(days=15)).strftime('%Y-%m-%d'), -4.0),
    ]
    from ipo_analyzer.settings import SETTINGS
    st = SETTINGS.sentiment_macro
    extracted = _extract_listed_records(records)
    result = _calculate_sentiment(extracted, now, st)
    assert result['sentiment_bonus'] == -5
    assert result['sentiment_label'] == '冷清'


def test_insufficient_data():
    """样本不足时返回数据不足。"""
    now = datetime.now()
    records = [
        _make_record((now - timedelta(days=5)).strftime('%Y-%m-%d'), 20.0),
        _make_record((now - timedelta(days=10)).strftime('%Y-%m-%d'), 10.0),
    ]
    from ipo_analyzer.settings import SETTINGS
    st = SETTINGS.sentiment_macro
    extracted = _extract_listed_records(records)
    result = _calculate_sentiment(extracted, now, st)
    assert result['confidence'] == 'insufficient_data'
    assert result['sentiment_bonus'] == 0


def test_break_rate_calculation():
    """测试破发率计算。"""
    now = datetime.now()
    records = [
        _make_record((now - timedelta(days=5)).strftime('%Y-%m-%d'), -5.0, True),
        _make_record((now - timedelta(days=10)).strftime('%Y-%m-%d'), 15.0, False),
        _make_record((now - timedelta(days=15)).strftime('%Y-%m-%d'), -2.0, True),
        _make_record((now - timedelta(days=20)).strftime('%Y-%m-%d'), 4.0, False),
    ]
    from ipo_analyzer.settings import SETTINGS
    st = SETTINGS.sentiment_macro
    extracted = _extract_listed_records(records)
    result = _calculate_sentiment(extracted, now, st)
    assert result['ipo_count_1m'] == 4
    assert result['break_rate_1m'] == 0.50
