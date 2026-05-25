"""宏观环境因子模块 — 通过 yfinance 获取 HSI/HIBOR/USD 等宏观指标。"""

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_CACHE = {}
_CACHE_TTL = timedelta(hours=6)


def get_macro_factors():
    """获取宏观环境因子：HSI 20日涨跌幅、HIBOR 1M、USD/HKD。

    Returns:
        dict: macro_label, macro_bonus, hsi_20d_change, hibor_1m, usd_hkd
    """
    from ipo_analyzer.settings import SETTINGS
    st = SETTINGS.sentiment_macro

    result = {
        'macro_label': '中性',
        'macro_bonus': 0,
        'hsi_20d_change': None,
        'hibor_1m': None,
        'usd_hkd': None,
        'confidence': 'unavailable',
    }

    cache_key = 'macro_factors'
    now = datetime.now()
    if cache_key in _CACHE:
        cached_result, cached_time = _CACHE[cache_key]
        if (now - cached_time) < _CACHE_TTL:
            return cached_result

    try:
        import yfinance as yf

        hsi_change = _get_hsi_20d_change(yf)
        result['hsi_20d_change'] = hsi_change
        result['confidence'] = 'live'

        if hsi_change is not None:
            if hsi_change >= st.macro_tailwind_threshold:
                result['macro_label'] = '顺风'
                result['macro_bonus'] = st.macro_tailwind_bonus
            elif hsi_change >= 0:
                result['macro_label'] = '偏顺风'
                result['macro_bonus'] = st.macro_slight_tailwind_bonus
            elif hsi_change >= st.macro_headwind_threshold:
                result['macro_label'] = '偏逆风'
                result['macro_bonus'] = -1
            else:
                result['macro_label'] = '逆风'
                result['macro_bonus'] = st.macro_headwind_bonus

    except Exception as e:
        logger.warning("宏观因子获取失败: %s", e)
        result['confidence'] = 'unavailable'

    _CACHE[cache_key] = (result, now)
    return result


def _get_hsi_20d_change(yf):
    try:
        ticker = yf.Ticker("^HSI")
        hist = ticker.history(period="1mo")
        if hist is None or hist.empty or len(hist) < 3:
            return None
        start_price = float(hist['Close'].iloc[0])
        end_price = float(hist['Close'].iloc[-1])
        if start_price <= 0:
            return None
        return round((end_price - start_price) / start_price, 4)
    except Exception as e:
        logger.warning("HSI 20日涨跌幅获取失败: %s", e)
        return None
