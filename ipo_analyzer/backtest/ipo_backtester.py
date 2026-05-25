"""IPO 首日表现回测引擎 — 输出 CSV 与 Markdown 分组统计报告"""
from __future__ import annotations

import csv
import logging
import os
from datetime import datetime
from statistics import median
from typing import Any

from ipo_analyzer.backtest.ipo_models import IPOBacktestRecord
from ipo_analyzer.backtest.feature_builder import build_ipo_features

logger = logging.getLogger(__name__)


def _safe_median(values: list[float]) -> float:
    if not values:
        return 0.0
    return median(values)


def _safe_mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _group_stats(records: list[IPOBacktestRecord]) -> dict[str, Any]:
    """计算单组统计指标。"""
    returns = [r.first_day_return for r in records]
    if not returns:
        return {
            "count": 0,
            "win_rate": 0.0,
            "median_return": 0.0,
            "mean_return": 0.0,
            "big_meat_50_rate": 0.0,
            "break_rate": 0.0,
        }
    wins = sum(1 for v in returns if v > 0)
    breaks = sum(1 for v in returns if v < 0)
    big_meat = sum(1 for v in returns if v >= 50.0)
    return {
        "count": len(records),
        "win_rate": wins / len(records),
        "median_return": _safe_median(returns),
        "mean_return": _safe_mean(returns),
        "big_meat_50_rate": big_meat / len(records),
        "break_rate": breaks / len(records),
    }


def run_ipo_first_day_backtest(
    records: list[IPOBacktestRecord],
) -> dict[str, Any]:
    """运行首日表现回测，返回分组统计。"""
    enriched = build_ipo_features(records)

    all_stats = _group_stats(enriched)

    greenshoe_yes = [r for r in enriched if r.has_greenshoe is True]
    greenshoe_no = [r for r in enriched if r.has_greenshoe is False]
    greenshoe_unknown = [r for r in enriched if r.has_greenshoe is None]

    sponsor_high = [r for r in enriched if r.sponsor_elastic_group == "high"]
    sponsor_low = [r for r in enriched if r.sponsor_elastic_group == "low"]
    sponsor_medium = [r for r in enriched if r.sponsor_elastic_group == "medium"]
    sponsor_unknown = [r for r in enriched if r.sponsor_elastic_group is None]

    cs_none = [
        r for r in enriched
        if (r.cornerstone_pct is None or r.cornerstone_pct <= 0)
        and not r.cornerstone_investors
    ]
    cs_low = [
        r for r in enriched
        if r.cornerstone_pct is not None and 0 < r.cornerstone_pct < 40
    ]
    cs_high = [
        r for r in enriched
        if r.cornerstone_pct is not None and r.cornerstone_pct >= 40
    ]
    cs_unknown = [
        r for r in enriched
        if r not in cs_none and r not in cs_low and r not in cs_high
    ]

    cs_indep = [r for r in enriched if r.cornerstone_independence == "independent"]
    cs_related = [r for r in enriched if r.cornerstone_independence == "related"]
    cs_mixed = [r for r in enriched if r.cornerstone_independence == "mixed"]
    cs_unk_indep = [r for r in enriched if r.cornerstone_independence in (None, "unknown")]

    heat_high = [r for r in enriched if r.subscription_heat_group in ("strong", "high")]
    heat_low = [r for r in enriched if r.subscription_heat_group in ("weak", "low")]
    heat_unknown = [r for r in enriched if r.subscription_heat_group is None]

    wind_strong = [r for r in enriched if r.market_wind_group == "strong"]
    wind_neutral = [r for r in enriched if r.market_wind_group == "neutral"]
    wind_weak = [r for r in enriched if r.market_wind_group in (None, "weak")]

    bottom_good = [r for r in enriched if r.bottom_group == "good"]
    bottom_weak = [r for r in enriched if r.bottom_group == "weak"]

    matrix: dict[str, dict[str, Any]] = {}
    for bg in ("good", "weak"):
        for wg in ("strong", "weak"):
            key = f"{bg}_x_{wg}"
            subset = [
                r for r in enriched
                if r.bottom_group == bg and r.wind_group == wg
            ]
            matrix[key] = _group_stats(subset)

    return {
        "total": all_stats,
        "greenshoe": {
            "yes": _group_stats(greenshoe_yes),
            "no": _group_stats(greenshoe_no),
            "unknown": _group_stats(greenshoe_unknown),
        },
        "sponsor_elastic": {
            "high": _group_stats(sponsor_high),
            "medium": _group_stats(sponsor_medium),
            "low": _group_stats(sponsor_low),
            "unknown": _group_stats(sponsor_unknown),
        },
        "cornerstone_pct": {
            "no_cornerstone": _group_stats(cs_none),
            "below_40pct": _group_stats(cs_low),
            "high_40pct": _group_stats(cs_high),
            "unknown": _group_stats(cs_unknown),
        },
        "cornerstone_independence": {
            "independent": _group_stats(cs_indep),
            "related": _group_stats(cs_related),
            "mixed": _group_stats(cs_mixed),
            "unknown": _group_stats(cs_unk_indep),
        },
        "subscription_heat": {
            "high": _group_stats(heat_high),
            "low": _group_stats(heat_low),
            "unknown": _group_stats(heat_unknown),
        },
        "market_wind": {
            "strong": _group_stats(wind_strong),
            "neutral": _group_stats(wind_neutral),
            "weak": _group_stats(wind_weak),
        },
        "bottom_x_wind": matrix,
        "records": enriched,
        "run_at": datetime.now().isoformat(),
    }


def write_ipo_backtest_csv(
    records: list[IPOBacktestRecord],
    path: str = "data/backtest/ipo_backtest_records.csv",
) -> str:
    """写入 CSV 文件。"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    fieldnames = [
        "hk_code", "company_name", "listing_date", "first_day_return",
        "stock_code", "offer_price", "first_day_open", "first_day_close",
        "first_day_high", "first_day_low",
        "is_break", "is_big_meat_50", "over_sub_ratio", "has_greenshoe",
        "cornerstone_pct", "cornerstone_independence", "has_related_support",
        "fundamental_score", "sponsor_elastic_group", "subscription_heat_group",
        "one_lot_success_rate", "clawback_ratio", "market_wind_score", "market_wind_group",
        "bottom_group", "wind_group", "sponsors", "cornerstone_investors",
    ]

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in records:
            row = {
                "hk_code": r.hk_code,
                "stock_code": r.stock_code or r.hk_code,
                "company_name": r.company_name,
                "listing_date": r.listing_date,
                "offer_price": f"{r.offer_price:.4f}" if r.offer_price is not None else "",
                "first_day_open": f"{r.first_day_open:.4f}" if r.first_day_open is not None else "",
                "first_day_close": f"{r.first_day_close:.4f}" if r.first_day_close is not None else "",
                "first_day_high": f"{r.first_day_high:.4f}" if r.first_day_high is not None else "",
                "first_day_low": f"{r.first_day_low:.4f}" if r.first_day_low is not None else "",
                "first_day_return": f"{r.first_day_return:.2f}",
                "is_break": r.is_break,
                "is_big_meat_50": r.is_big_meat_50,
                "over_sub_ratio": f"{r.over_sub_ratio:.2f}",
                "has_greenshoe": r.has_greenshoe,
                "cornerstone_pct": f"{r.cornerstone_pct:.2f}" if r.cornerstone_pct is not None else "",
                "cornerstone_independence": r.cornerstone_independence or "",
                "has_related_support": r.has_related_support,
                "fundamental_score": f"{r.fundamental_score:.1f}" if r.fundamental_score is not None else "",
                "sponsor_elastic_group": r.sponsor_elastic_group or "",
                "subscription_heat_group": r.subscription_heat_group or "",
                "one_lot_success_rate": f"{r.one_lot_success_rate:.4f}" if r.one_lot_success_rate is not None else "",
                "clawback_ratio": f"{r.clawback_ratio:.4f}" if r.clawback_ratio is not None else "",
                "market_wind_score": f"{r.market_wind_score:.2f}" if r.market_wind_score is not None else "",
                "market_wind_group": r.market_wind_group or "",
                "bottom_group": r.bottom_group or "",
                "wind_group": r.wind_group or "",
                "sponsors": "; ".join(r.sponsors),
                "cornerstone_investors": "; ".join(r.cornerstone_investors),
            }
            writer.writerow(row)

    logger.info("CSV 已写入: %s (%d 条)", path, len(records))
    return path


def _fmt_pct(v: float) -> str:
    return f"{v:.1%}"


def _fmt_ret(v: float) -> str:
    return f"{v:+.2f}%"


def _fmt_stat(stats: dict[str, Any], key: str, formatter) -> str:
    if stats.get("count", 0) == 0:
        return "N/A"
    return formatter(stats.get(key, 0.0))


def _render_group_table(
    title: str, groups: dict[str, dict[str, Any]], indent: int = 3
) -> str:
    lines = [f"{'#' * indent} {title}", ""]
    lines.append("| 分组 | 样本数 | 上涨率 | 中位涨幅 | 平均涨幅 | 50%+大肉率 | 破发率 |")
    lines.append("|------|--------|--------|----------|----------|------------|--------|")
    for name, stats in groups.items():
        lines.append(
            f"| {name} "
            f"| {stats['count']} "
            f"| {_fmt_stat(stats, 'win_rate', _fmt_pct)} "
            f"| {_fmt_stat(stats, 'median_return', _fmt_ret)} "
            f"| {_fmt_stat(stats, 'mean_return', _fmt_ret)} "
            f"| {_fmt_stat(stats, 'big_meat_50_rate', _fmt_pct)} "
            f"| {_fmt_stat(stats, 'break_rate', _fmt_pct)} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_ipo_backtest_report(
    summary: dict[str, Any],
    path: str = "reports/ipo_backtest_summary.md",
) -> str:
    """写入 Markdown 报告。"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    lines = [
        "# IPO 首日表现回测报告",
        "",
        f"生成时间: {summary.get('run_at', 'N/A')}",
        "",
        "## 总览",
        "",
    ]

    total = summary.get("total", {})
    lines.append(f"- 总样本数: {total.get('count', 0)}")
    lines.append(f"- 上涨率: {_fmt_stat(total, 'win_rate', _fmt_pct)}")
    lines.append(f"- 中位首日涨幅: {_fmt_stat(total, 'median_return', _fmt_ret)}")
    lines.append(f"- 平均首日涨幅: {_fmt_stat(total, 'mean_return', _fmt_ret)}")
    lines.append(f"- 50%+ 大肉率: {_fmt_stat(total, 'big_meat_50_rate', _fmt_pct)}")
    lines.append(f"- 破发率: {_fmt_stat(total, 'break_rate', _fmt_pct)}")
    lines.append("")

    sections = [
        ("绿鞋分组", summary.get("greenshoe", {})),
        ("保荐人弹性分组", summary.get("sponsor_elastic", {})),
        ("基石比例分组", summary.get("cornerstone_pct", {})),
        ("基石独立性分组", summary.get("cornerstone_independence", {})),
        ("认购热度分组", summary.get("subscription_heat", {})),
        ("市场风向分组", summary.get("market_wind", {})),
    ]

    for title, groups in sections:
        if groups:
            lines.append(_render_group_table(title, groups, indent=2))

    matrix = summary.get("bottom_x_wind", {})
    if matrix:
        lines.append("## 底色 × 风向 矩阵")
        lines.append("")
        lines.append("| 底色 | 风向 | 样本数 | 上涨率 | 中位涨幅 | 平均涨幅 | 50%+大肉率 | 破发率 |")
        lines.append("|------|------|--------|--------|----------|----------|------------|--------|")
        for key, stats in matrix.items():
            parts = key.split("_x_")
            bg = parts[0] if len(parts) == 2 else key
            wg = parts[1] if len(parts) == 2 else ""
            lines.append(
                f"| {bg} | {wg} "
                f"| {stats['count']} "
                f"| {_fmt_stat(stats, 'win_rate', _fmt_pct)} "
                f"| {_fmt_stat(stats, 'median_return', _fmt_ret)} "
                f"| {_fmt_stat(stats, 'mean_return', _fmt_ret)} "
                f"| {_fmt_stat(stats, 'big_meat_50_rate', _fmt_pct)} "
                f"| {_fmt_stat(stats, 'break_rate', _fmt_pct)} |"
            )
        lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info("报告已写入: %s", path)
    return path
