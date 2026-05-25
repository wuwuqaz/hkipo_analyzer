"""Backtest API router — IPO 首日表现回测"""
import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.config import APIConfig
from api.deps import get_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


def _load_history_json(storage_path: str) -> list[dict]:
    import json
    history_file = os.path.join(storage_path, "ipo_history.json")
    if not os.path.exists(history_file):
        return []
    with open(history_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def _build_backtest_records(raw: list[dict]) -> list:
    from ipo_analyzer.backtest.ipo_models import IPOBacktestRecord

    records = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        post = item.get("post_listing")
        if not isinstance(post, dict):
            continue
        first_day = post.get("first_day")
        if not isinstance(first_day, dict):
            continue
        change_pct = first_day.get("change_pct")
        if not isinstance(change_pct, (int, float)):
            continue

        pi = item.get("prospectus_info", {})
        ca = pi.get("cornerstone_analysis") if isinstance(pi.get("cornerstone_analysis"), dict) else {}
        cornerstone_list = pi.get("cornerstone_investors") or ca.get("cornerstone_investors") or []
        if isinstance(cornerstone_list, list):
            cs_names = [
                c.get("name", "") if isinstance(c, dict) else str(c)
                for c in cornerstone_list
            ]
        else:
            cs_names = []

        cs_pct = pi.get("cornerstone_pct") or ca.get("cornerstone_pct")
        cs_total = pi.get("cornerstone_total_investment")
        cs_offer_size = pi.get("offer_size")
        if cs_pct is None and cs_total and cs_offer_size:
            try:
                cs_pct = float(cs_total) / float(cs_offer_size) * 100
            except (ValueError, ZeroDivisionError):
                pass

        sponsors = []
        sponsor_info = pi.get("sponsor_info")
        if isinstance(sponsor_info, list):
            sponsors = [
                s.get("name", "") if isinstance(s, dict) else str(s)
                for s in sponsor_info
            ]
        elif isinstance(sponsor_info, str):
            sponsors = [sponsor_info]

        listing_date = (
            item.get("listing_date")
            or post.get("listing_date")
            or first_day.get("date")
            or pi.get("listing_date")
            or ""
        )
        offer_price = (
            post.get("final_offer_price")
            or pi.get("final_offer_price")
            or item.get("offer_price")
            or pi.get("offer_price")
        )
        first_day_close = first_day.get("close") or first_day.get("price")

        one_lot_success_rate = None
        pools = post.get("allocation_pools")
        if isinstance(pools, dict):
            pool_a = pools.get("A")
            rows = pool_a.get("rows") if isinstance(pool_a, dict) else None
            if isinstance(rows, list) and rows:
                one_lot_success_rate = rows[0].get("success_rate_pct")
                if isinstance(one_lot_success_rate, (int, float)):
                    one_lot_success_rate = float(one_lot_success_rate) / 100.0

        clawback_ratio = None
        initial_hk = post.get("initial_hk_offer_shares")
        final_hk = post.get("final_hk_offer_shares")
        global_offer = pi.get("global_offer_shares")
        try:
            if final_hk and global_offer:
                clawback_ratio = float(final_hk) / float(global_offer)
            elif initial_hk and final_hk and float(initial_hk) > 0:
                clawback_ratio = float(final_hk) / float(initial_hk)
        except (TypeError, ValueError, ZeroDivisionError):
            clawback_ratio = None

        rec = IPOBacktestRecord(
            hk_code=str(item.get("hk_code", "")),
            stock_code=str(item.get("stock_code") or item.get("hk_code") or ""),
            company_name=str(item.get("company_name", "")),
            listing_date=str(listing_date),
            offer_price=float(offer_price) if isinstance(offer_price, (int, float)) else None,
            first_day_open=float(first_day.get("open")) if isinstance(first_day.get("open"), (int, float)) else None,
            first_day_close=float(first_day_close) if isinstance(first_day_close, (int, float)) else None,
            first_day_high=float(first_day.get("high")) if isinstance(first_day.get("high"), (int, float)) else None,
            first_day_low=float(first_day.get("low")) if isinstance(first_day.get("low"), (int, float)) else None,
            first_day_return=float(change_pct),
            over_sub_ratio=float(post.get("public_subscription_level", 0) or 0),
            has_greenshoe=pi.get("has_greenshoe"),
            sponsors=sponsors,
            cornerstone_investors=cs_names,
            cornerstone_pct=float(cs_pct) if isinstance(cs_pct, (int, float)) else None,
            cornerstone_independence=pi.get("cornerstone_independence"),
            fundamental_score=float(item.get("fundamental_score", 0) or 0) or None,
            one_lot_success_rate=one_lot_success_rate,
            clawback_ratio=clawback_ratio,
            extra={
                "sponsors": sponsors,
                "trade_score": float(item.get("trade_score", 0) or 0),
            },
        )
        records.append(rec)
    return records


class BacktestGroupStats(BaseModel):
    count: int
    win_rate: float
    median_return: float
    mean_return: float
    big_meat_50_rate: float
    break_rate: float


class BacktestRecordItem(BaseModel):
    hk_code: str
    stock_code: str
    company_name: str
    listing_date: str
    offer_price: Optional[float] = None
    first_day_open: Optional[float] = None
    first_day_close: Optional[float] = None
    first_day_high: Optional[float] = None
    first_day_low: Optional[float] = None
    first_day_return: float
    is_break: bool
    is_big_meat_50: bool
    over_sub_ratio: float
    has_greenshoe: Optional[bool] = None
    cornerstone_pct: Optional[float] = None
    cornerstone_independence: Optional[str] = None
    has_related_support: bool = False
    fundamental_score: Optional[float] = None
    sponsor_elastic_group: Optional[str] = None
    subscription_heat_group: Optional[str] = None
    one_lot_success_rate: Optional[float] = None
    clawback_ratio: Optional[float] = None
    market_wind_score: Optional[float] = None
    market_wind_group: Optional[str] = None
    bottom_group: Optional[str] = None
    wind_group: Optional[str] = None
    sponsors: list[str] = []
    cornerstone_investors: list[str] = []


class IpoFirstDayBacktestResponse(BaseModel):
    total: BacktestGroupStats
    greenshoe: dict[str, BacktestGroupStats]
    sponsor_elastic: dict[str, BacktestGroupStats]
    cornerstone_pct: dict[str, BacktestGroupStats]
    cornerstone_independence: dict[str, BacktestGroupStats]
    subscription_heat: dict[str, BacktestGroupStats]
    market_wind: dict[str, BacktestGroupStats]
    bottom_x_wind: dict[str, BacktestGroupStats]
    records: list[BacktestRecordItem]
    run_at: str


class BacktestStatusResponse(BaseModel):
    sample_count: int
    ready: bool
    message: str


def _convert_summary_to_response(summary: dict) -> dict:
    def to_group_stats(s: dict) -> dict:
        return {
            "count": s.get("count", 0),
            "win_rate": s.get("win_rate", 0.0),
            "median_return": s.get("median_return", 0.0),
            "mean_return": s.get("mean_return", 0.0),
            "big_meat_50_rate": s.get("big_meat_50_rate", 0.0),
            "break_rate": s.get("break_rate", 0.0),
        }

    def to_record_item(r) -> dict:
        return {
            "hk_code": r.hk_code,
            "stock_code": r.stock_code or r.hk_code,
            "company_name": r.company_name,
            "listing_date": r.listing_date,
            "offer_price": r.offer_price,
            "first_day_open": r.first_day_open,
            "first_day_close": r.first_day_close,
            "first_day_high": r.first_day_high,
            "first_day_low": r.first_day_low,
            "first_day_return": r.first_day_return,
            "is_break": r.is_break,
            "is_big_meat_50": r.is_big_meat_50,
            "over_sub_ratio": r.over_sub_ratio,
            "has_greenshoe": r.has_greenshoe,
            "cornerstone_pct": r.cornerstone_pct,
            "cornerstone_independence": r.cornerstone_independence,
            "has_related_support": r.has_related_support,
            "fundamental_score": r.fundamental_score,
            "sponsor_elastic_group": r.sponsor_elastic_group,
            "subscription_heat_group": r.subscription_heat_group,
            "one_lot_success_rate": r.one_lot_success_rate,
            "clawback_ratio": r.clawback_ratio,
            "market_wind_score": r.market_wind_score,
            "market_wind_group": r.market_wind_group,
            "bottom_group": r.bottom_group,
            "wind_group": r.wind_group,
            "sponsors": r.sponsors,
            "cornerstone_investors": r.cornerstone_investors,
        }

    gs = summary.get("greenshoe", {})
    se = summary.get("sponsor_elastic", {})
    cp = summary.get("cornerstone_pct", {})
    ci = summary.get("cornerstone_independence", {})
    sh = summary.get("subscription_heat", {})
    mw = summary.get("market_wind", {})
    bx = summary.get("bottom_x_wind", {})

    return {
        "total": to_group_stats(summary.get("total", {})),
        "greenshoe": {k: to_group_stats(v) for k, v in gs.items()},
        "sponsor_elastic": {k: to_group_stats(v) for k, v in se.items()},
        "cornerstone_pct": {k: to_group_stats(v) for k, v in cp.items()},
        "cornerstone_independence": {k: to_group_stats(v) for k, v in ci.items()},
        "subscription_heat": {k: to_group_stats(v) for k, v in sh.items()},
        "market_wind": {k: to_group_stats(v) for k, v in mw.items()},
        "bottom_x_wind": {k: to_group_stats(v) for k, v in bx.items()},
        "records": [to_record_item(r) for r in summary.get("records", [])],
        "run_at": summary.get("run_at", datetime.now().isoformat()),
    }


@router.get("/ipo-first-day", response_model=IpoFirstDayBacktestResponse)
async def run_ipo_first_day_backtest_api(
    config: APIConfig = Depends(get_config),
):
    from ipo_analyzer.backtest.ipo_backtester import run_ipo_first_day_backtest

    raw = _load_history_json(str(config.storage_base_path))
    records = _build_backtest_records(raw)

    if not records:
        raise HTTPException(
            status_code=404,
            detail="无有效 IPO 首日数据样本。请确保历史数据中包含 post_listing.first_day.change_pct",
        )

    summary = run_ipo_first_day_backtest(records)
    return _convert_summary_to_response(summary)


@router.get("/status", response_model=BacktestStatusResponse)
async def backtest_status(
    config: APIConfig = Depends(get_config),
):
    raw = _load_history_json(str(config.storage_base_path))
    count = 0
    for item in raw:
        if not isinstance(item, dict):
            continue
        post = item.get("post_listing")
        if not isinstance(post, dict):
            continue
        first_day = post.get("first_day")
        if not isinstance(first_day, dict):
            continue
        if isinstance(first_day.get("change_pct"), (int, float)):
            count += 1

    ready = count >= 3
    return BacktestStatusResponse(
        sample_count=count,
        ready=ready,
        message=f"找到 {count} 条有效样本" if count > 0 else "暂无有效样本，需要至少 3 条才能运行回测",
    )
