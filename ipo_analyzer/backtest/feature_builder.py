"""回测特征构建器 — 基于上市日前可知信息构建「底色 × 风向」特征

所有历史表现类特征只使用当前样本上市日前记录（防未来函数）。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from statistics import median
from typing import Any, Optional

from ipo_analyzer.backtest.ipo_models import IPOBacktestRecord

logger = logging.getLogger(__name__)

DEFAULT_MARKET_WIND_WINDOW_DAYS = 90
DEFAULT_SPONSOR_ROLLING_MONTHS = 24
DEFAULT_SPONSOR_ROLLING_COUNT = 20
FUNDAMENTAL_THRESHOLD = 50.0


def _parse_date(s: str) -> Optional[datetime]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _rolling_median_first_day(
    past_records: list[IPOBacktestRecord],
) -> Optional[float]:
    """计算历史样本首日涨幅中位数。"""
    values = [r.first_day_return for r in past_records if r.first_day_return is not None]
    if not values:
        return None
    return median(values)


def _rolling_percentile_rank(
    value: float, past_values: list[float], top_third: bool = True
) -> Optional[str]:
    """计算 value 在历史中的分位。"""
    if len(past_values) < 3:
        return None
    sorted_vals = sorted(past_values)
    n = len(sorted_vals)
    threshold_idx = n // 3
    if top_third:
        return "strong" if value >= sorted_vals[n - threshold_idx - 1] else "weak"
    else:
        return "strong" if value <= sorted_vals[threshold_idx] else "weak"


def _sponsor_elasticity(
    sponsors: list[str],
    past_records: list[IPOBacktestRecord],
    window_months: int = DEFAULT_SPONSOR_ROLLING_MONTHS,
    max_samples: int = DEFAULT_SPONSOR_ROLLING_COUNT,
) -> Optional[str]:
    """基于 rolling 历史样本计算保荐人弹性。

    使用过去 N 个月或最近 M 只相关保荐人样本的首日表现。
    """
    if not sponsors or not past_records:
        return None

    now = max(
        (_parse_date(r.listing_date) for r in past_records if _parse_date(r.listing_date)),
        default=datetime.now(),
    )
    cutoff = now - timedelta(days=window_months * 30)

    relevant: list[float] = []
    for r in reversed(past_records):
        ld = _parse_date(r.listing_date)
        if ld and ld < cutoff:
            continue
        r_sponsors = [s.lower() for s in (r.extra.get("sponsors") or r.sponsors or [])]
        if any(s.lower() in r_sponsors for s in sponsors):
            relevant.append(r.first_day_return)
        if len(relevant) >= max_samples:
            break

    if len(relevant) < 2:
        return None

    avg_return = sum(relevant) / len(relevant)
    win_count = sum(1 for v in relevant if v > 0)
    win_rate = win_count / len(relevant)

    if avg_return > 5.0 and win_rate >= 0.6:
        return "high"
    if avg_return < -5.0 or win_rate < 0.3:
        return "low"
    return "medium"


def _classify_bottom_group(record: IPOBacktestRecord) -> str:
    """底色分组：good / weak

    满足至少 2 项为 good：
    - 高弹性保荐人
    - 高比例且独立基石
    - 无明显关系户撑场
    - fundamental_score >= 50
    """
    good_count = 0

    if record.sponsor_elastic_group == "high":
        good_count += 1

    if (
        record.cornerstone_pct is not None
        and record.cornerstone_pct >= 10.0
        and record.cornerstone_independence in ("independent", "mixed")
    ):
        good_count += 1

    if not record.has_related_support:
        good_count += 1

    if record.fundamental_score is not None and record.fundamental_score >= FUNDAMENTAL_THRESHOLD:
        good_count += 1

    return "good" if good_count >= 2 else "weak"


def _classify_wind_group(record: IPOBacktestRecord) -> str:
    """风向分组：strong / weak

    满足至少 2 项为 strong：
    - 认购热度高
    - 市场顺风
    - （未来孖展快照热度加速占位，第一版不计分）
    """
    strong_count = 0

    if record.subscription_heat_group in ("strong", "high"):
        strong_count += 1

    market_wind = record.market_wind_group or record.extra.get("market_wind_group")
    if market_wind in ("strong",):
        strong_count += 1

    return "strong" if strong_count >= 2 else "weak"


def build_ipo_features(records: list[IPOBacktestRecord]) -> list[IPOBacktestRecord]:
    """对记录按 listing_date 排序，构建 rolling 特征。

    所有历史表现类特征只使用当前样本上市日前记录。
    """
    sorted_records = sorted(
        records, key=lambda r: _parse_date(r.listing_date) or datetime.min
    )

    past: list[IPOBacktestRecord] = []
    all_over_sub: list[float] = []

    for record in sorted_records:
        ld = _parse_date(record.listing_date)

        if ld:
            cutoff = ld - timedelta(days=DEFAULT_MARKET_WIND_WINDOW_DAYS)
            window_records = [
                r for r in past
                if _parse_date(r.listing_date) and _parse_date(r.listing_date) >= cutoff
            ]
        else:
            window_records = past

        market_wind = _rolling_median_first_day(window_records)
        record.market_wind_score = market_wind
        if market_wind is not None:
            record.market_wind_group = _rolling_percentile_rank(
                market_wind,
                [r.first_day_return for r in past],
                top_third=True,
            )

        if record.over_sub_ratio and record.over_sub_ratio > 0:
            heat_group = _rolling_percentile_rank(
                record.over_sub_ratio, all_over_sub, top_third=True
            )
            record.subscription_heat_group = heat_group
            all_over_sub.append(record.over_sub_ratio)

        sponsors = record.extra.get("sponsors", record.sponsors)
        if sponsors:
            record.sponsor_elastic_group = _sponsor_elasticity(
                sponsors, past
            )

        record.bottom_group = _classify_bottom_group(record)
        record.wind_group = _classify_wind_group(record)

        record.is_break = record.first_day_return < 0
        record.is_big_meat_50 = record.first_day_return >= 50.0

        past.append(record)

    return sorted_records
