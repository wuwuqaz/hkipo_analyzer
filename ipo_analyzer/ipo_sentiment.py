"""市场IPO情绪模块 — 基于历史上市数据统计近期IPO表现，作为市场水温指标。"""

import os
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_CACHE = {}
_CACHE_TTL = timedelta(hours=12)


def get_ipo_sentiment(history_dir=None):
    """从 ipo_history.json 计算近期IPO市场情绪。

    Returns:
        dict: sentiment_label, sentiment_bonus, avg_return_1m/3m, break_rate_1m/3m, ipo_count
    """
    from ipo_analyzer.settings import SETTINGS
    st = SETTINGS.sentiment_macro

    result = {
        'sentiment_label': '数据不足',
        'sentiment_bonus': 0,
        'avg_return_1m': None,
        'avg_return_3m': None,
        'break_rate_1m': None,
        'break_rate_3m': None,
        'ipo_count_1m': 0,
        'ipo_count_3m': 0,
        'confidence': 'insufficient_data',
    }

    if not history_dir:
        history_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'data'
        )

    history_file = os.path.join(history_dir, 'ipo_history.json')

    cache_key = 'ipo_sentiment'
    now = datetime.now()
    if cache_key in _CACHE:
        cached_result, cached_time = _CACHE[cache_key]
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(history_file))
            if cached_time >= mtime and (now - cached_time) < _CACHE_TTL:
                return cached_result
        except OSError:
            if (now - cached_time) < _CACHE_TTL:
                return cached_result

    try:
        if not os.path.exists(history_file):
            _CACHE[cache_key] = (result, now)
            return result

        with open(history_file, 'r', encoding='utf-8') as f:
            history_data = json.load(f)

        records = _extract_listed_records(history_data)
        if not records:
            _CACHE[cache_key] = (result, now)
            return result

        result = _calculate_sentiment(records, now, st)
        _CACHE[cache_key] = (result, now)
        return result

    except Exception as e:
        logger.warning("IPO情绪计算失败: %s", e)
        _CACHE[cache_key] = (result, now)
        return result


def _extract_listed_records(history_data):
    records = []
    if isinstance(history_data, list):
        entries = history_data
    elif isinstance(history_data, dict):
        entries = history_data.get('records', history_data.get('data', []))
        if not entries:
            entries = [v for v in history_data.values() if isinstance(v, dict)]
    else:
        return records

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        post_listing = entry.get('post_listing', {}) or {}
        list_date = post_listing.get('listing_date') or entry.get('list_date') or entry.get('listing_date')
        first_day_return = post_listing.get('first_day_return') or entry.get('first_day_return')
        is_break = post_listing.get('is_break')
        if is_break is None and first_day_return is not None:
            is_break = first_day_return < 0
        if list_date and isinstance(first_day_return, (int, float)):
            records.append({
                'list_date': _parse_date(list_date),
                'first_day_return': float(first_day_return),
                'is_break': bool(is_break) if is_break is not None else False,
            })
    return records


def _parse_date(date_str):
    if isinstance(date_str, datetime):
        return date_str
    if not isinstance(date_str, str):
        return None
    for fmt in ('%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f', '%Y%m%d'):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def _calculate_sentiment(records, now, st):
    result = {
        'sentiment_label': '数据不足',
        'sentiment_bonus': 0,
        'avg_return_1m': None,
        'avg_return_3m': None,
        'break_rate_1m': None,
        'break_rate_3m': None,
        'ipo_count_1m': 0,
        'ipo_count_3m': 0,
        'confidence': 'insufficient_data',
    }

    cutoff_1m = now - timedelta(days=30)
    cutoff_3m = now - timedelta(days=90)

    records_1m = [r for r in records if r['list_date'] and r['list_date'] >= cutoff_1m]
    records_3m = [r for r in records if r['list_date'] and r['list_date'] >= cutoff_3m]

    if len(records_1m) >= st.min_samples_1m:
        avg_ret = sum(r['first_day_return'] for r in records_1m) / len(records_1m)
        break_count = sum(1 for r in records_1m if r['is_break'])
        result['avg_return_1m'] = round(avg_ret, 2)
        result['break_rate_1m'] = round(break_count / len(records_1m), 2)
        result['ipo_count_1m'] = len(records_1m)
        result['confidence'] = 'history'

        if avg_ret >= st.sentiment_hot_threshold:
            result['sentiment_label'] = '火热'
            result['sentiment_bonus'] = st.sentiment_hot_bonus
        elif avg_ret >= st.sentiment_warm_threshold:
            result['sentiment_label'] = '偏热'
            result['sentiment_bonus'] = st.sentiment_warm_bonus
        elif avg_ret >= st.sentiment_neutral_threshold:
            result['sentiment_label'] = '温和'
            result['sentiment_bonus'] = st.sentiment_neutral_bonus
        elif avg_ret >= -5.0:
            result['sentiment_label'] = '偏冷'
            result['sentiment_bonus'] = st.sentiment_cool_bonus
        else:
            result['sentiment_label'] = '冷清'
            result['sentiment_bonus'] = st.sentiment_cold_bonus

    if len(records_3m) >= st.min_samples_1m:
        avg_ret_3m = sum(r['first_day_return'] for r in records_3m) / len(records_3m)
        break_count_3m = sum(1 for r in records_3m if r['is_break'])
        result['avg_return_3m'] = round(avg_ret_3m, 2)
        result['break_rate_3m'] = round(break_count_3m / len(records_3m), 2)
        result['ipo_count_3m'] = len(records_3m)

    return result
