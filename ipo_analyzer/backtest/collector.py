"""回测数据采集器：从 ipo_history.json 和 reanalysis/ 提取 BacktestRecord 列表"""
import json
import logging
import os

from .models import BacktestRecord

logger = logging.getLogger(__name__)


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_reanalysis_scores(reanalysis_dir, stock_code):
    """从 temp/reanalysis/{code}_latest.json 读取 score_breakdown"""
    safe_code = stock_code.replace(".HK", "").replace(".hk", "").strip()
    latest_path = os.path.join(reanalysis_dir, f"{safe_code}_latest.json")
    if not os.path.exists(latest_path):
        return {}
    try:
        data = _load_json(latest_path)
        return data.get("score_breakdown", {})
    except Exception as e:
        logger.debug("读取 reanalysis 失败 %s: %s", latest_path, e)
        return {}


def _coerce_data_quality(item, threshold):
    data_quality = item.get("_data_quality")
    if isinstance(data_quality, bool):
        return 2 if data_quality else 0
    if isinstance(data_quality, (int, float)):
        return int(data_quality)

    # Older archived analysis files did not persist _data_quality. If the
    # record has a completed parser/score payload, treat it as usable rather
    # than dropping every historical sample.
    if item.get("parse_success") or item.get("score_breakdown") or item.get("score") is not None:
        return max(2, int(threshold or 0))
    return 0


def _extract_outcome(post):
    first_day = post.get("first_day") if isinstance(post, dict) else None
    if isinstance(first_day, dict):
        change_pct = first_day.get("change_pct")
        if isinstance(change_pct, (int, float)):
            return float(change_pct), "first_day"

    grey_market = post.get("grey_market") if isinstance(post, dict) else None
    if isinstance(grey_market, dict) and grey_market.get("status") == "ok":
        change_pct = grey_market.get("change_pct")
        if isinstance(change_pct, (int, float)):
            return float(change_pct), "grey_market"

    return None, ""


def collect_backtest_dataset(
    history_dir="temp",
    data_quality_threshold=2,
):
    """从历史数据中提取 BacktestRecord 列表"""
    history_file = os.path.join(history_dir, "ipo_history.json")
    reanalysis_dir = os.path.join(history_dir, "reanalysis")

    if not os.path.exists(history_file):
        logger.warning("历史文件不存在: %s", history_file)
        return []

    records = _load_json(history_file)
    if not isinstance(records, list):
        return []

    dataset = []
    for item in records:
        if not isinstance(item, dict):
            continue

        post = item.get("post_listing")
        if not isinstance(post, dict):
            continue

        change_pct, outcome_source = _extract_outcome(post)
        if change_pct is None:
            continue

        data_quality = _coerce_data_quality(item, data_quality_threshold)
        if data_quality < data_quality_threshold:
            continue

        stock_code = item.get("hk_code") or item.get("stock_code") or ""
        reanalysis_scores = _load_reanalysis_scores(reanalysis_dir, stock_code)

        record = BacktestRecord(
            hk_code=str(stock_code),
            company_name=str(item.get("company_name", "")),
            listing_date=str(item.get("listing_date") or ""),
            trade_score=float(
                reanalysis_scores.get("trade_score", item.get("trade_score", 0)) or 0
            ),
            fundamental_score=float(
                reanalysis_scores.get("fundamental_score", item.get("fundamental_score", 0)) or 0
            ),
            valuation_score=float(
                reanalysis_scores.get("valuation_score", item.get("valuation_score", 0)) or 0
            ),
            theme_score=float(
                reanalysis_scores.get("theme_score", item.get("theme_score", 0)) or 0
            ),
            data_quality_score=float(item.get("data_quality_score", 0) or 0),
            first_day_return=float(change_pct) / 100.0,
            is_break=float(change_pct) < 0,
            over_sub_ratio=float(post.get("public_subscription_level", 0) or 0),
            score_timestamp=str(
                item.get("_post_listing_updated_at")
                or post.get("tracked_at")
                or outcome_source
                or ""
            ),
            data_quality=int(data_quality),
        )
        dataset.append(record)

    logger.info("采集回测样本: %d 条", len(dataset))
    return dataset
