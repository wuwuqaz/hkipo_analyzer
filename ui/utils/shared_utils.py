from html import escape as html_escape
from typing import Any

from ipo_analyzer.utils import _is_num, _normalize_gm


class SafeHtml(str):
    """Marker for HTML fragments built by this app after escaping data."""


def _num(value: Any, default: float = 0) -> float:
    if _is_num(value):
        return value
    try:
        return float(value)
    except Exception:
        return default


def _html(value: Any) -> str:
    if value is None:
        return "--"
    return html_escape(str(value), quote=True)


def _as_html(value: Any) -> str:
    if isinstance(value, SafeHtml):
        return str(value)
    return _html(value)


def score_class(score: float) -> str:
    score = _num(score)
    if score >= 70:
        return "score-excellent"
    elif score >= 55:
        return "score-good"
    elif score >= 40:
        return "score-medium"
    else:
        return "score-poor"


def score_color_hex(score: float) -> str:
    score = _num(score)
    if score >= 70:
        return "#4ade80"
    elif score >= 55:
        return "#a3e635"
    elif score >= 40:
        return "#facc15"
    else:
        return "#f87171"
