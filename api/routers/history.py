import copy
import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from api.auth import require_api_token
from api.config import APIConfig
from api.deps import get_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/history", tags=["history"])


def _load_history_records(output_dir: str = "temp") -> list[dict]:
    from ipo_analyzer.history import HistoryStore
    store = HistoryStore(output_dir)
    return store.load(include_live=True)


def _parse_date(value) -> Optional[date]:
    if not value:
        return None
    text = str(value).strip()
    if "T" in text:
        text = text.split("T", 1)[0]
    elif " " in text:
        text = text.split(" ", 1)[0]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except Exception:
        return None


def _num(value, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _is_live_or_future(item: dict) -> bool:
    end_date = _parse_date((item or {}).get("apply_end_date"))
    return end_date is not None and end_date >= datetime.now().date()


def _sort_history_records(records: list[dict], sort_by: str) -> list[dict]:
    if sort_by in ("评分从高到低", "打新分从高到低"):
        return sorted(
            records,
            key=lambda item: _num(item.get("strict_ipo_score", item.get("ipo_trade_score", item.get("trade_score", item.get("score"))))),
            reverse=True,
        )
    if sort_by in ("评分从低到高", "打新分从低到高"):
        return sorted(
            records,
            key=lambda item: _num(item.get("strict_ipo_score", item.get("ipo_trade_score", item.get("trade_score", item.get("score"))))),
        )
    if sort_by == "长期分从高到低":
        return sorted(
            records,
            key=lambda item: _num(item.get("long_term_score", item.get("fundamental_score"))),
            reverse=True,
        )

    with_dates = [item for item in records if _parse_date(item.get("apply_end_date")) is not None]
    without_dates = [item for item in records if _parse_date(item.get("apply_end_date")) is None]
    if sort_by == "截止日从远到近":
        return sorted(with_dates, key=lambda item: _parse_date(item.get("apply_end_date")), reverse=True) + without_dates
    return sorted(with_dates, key=lambda item: _parse_date(item.get("apply_end_date"))) + without_dates


def _format_history_row(item: dict) -> dict:
    post = item.get("post_listing", {}) or {}
    trade_score = item.get("strict_ipo_score", item.get("ipo_trade_score", item.get("trade_score", item.get("score", 0))))
    long_term_score = item.get("long_term_score", item.get("fundamental_score", 0))

    status_map = {
        "ok": "已完成",
        "pending_allotment": "待公告",
        "partial": "部分",
        "error": "异常",
    }

    # 当顶层字段缺失时，从 prospectus_info 中补充（兼容旧缓存数据）
    pi = item.get("prospectus_info", {}) or {}
    _offer_price = item.get("offer_price") if item.get("offer_price") is not None else pi.get("offer_price")
    _market_cap = item.get("market_cap_hkd_million") if item.get("market_cap_hkd_million") is not None else pi.get("market_cap_hkd_million")
    _lot_size = item.get("lot_size") if item.get("lot_size") is not None else pi.get("lot_size")
    _board_lot = item.get("board_lot") if item.get("board_lot") is not None else pi.get("board_lot")
    if _board_lot is None and _lot_size is not None:
        _board_lot = _lot_size
    _hk_offer_shares = item.get("hk_offer_shares") if item.get("hk_offer_shares") is not None else pi.get("hk_offer_shares")
    _global_offer_shares = item.get("global_offer_shares") if item.get("global_offer_shares") is not None else pi.get("global_offer_shares")
    _intl_offer_shares = item.get("international_offer_shares") if item.get("international_offer_shares") is not None else pi.get("international_offer_shares")

    _public_offer_ratio = item.get("public_offer_ratio") if item.get("public_offer_ratio") is not None else pi.get("public_offer_ratio_pct")
    _international_offer_ratio = item.get("international_offer_ratio") if item.get("international_offer_ratio") is not None else pi.get("international_offer_ratio_pct")

    _total_offer_shares = _global_offer_shares
    if _total_offer_shares is None and _hk_offer_shares and _intl_offer_shares:
        _total_offer_shares = _hk_offer_shares + _intl_offer_shares
    if _public_offer_ratio is None and _hk_offer_shares and _total_offer_shares and _total_offer_shares > 0:
        _public_offer_ratio = _hk_offer_shares / _total_offer_shares * 100
    if _international_offer_ratio is None and _intl_offer_shares and _total_offer_shares and _total_offer_shares > 0:
        _international_offer_ratio = _intl_offer_shares / _total_offer_shares * 100

    # 计算公开发售手数
    _public_offer_lots = item.get("public_offer_lots")
    if _public_offer_lots is None and _hk_offer_shares and (_lot_size or _board_lot):
        _public_offer_lots = _hk_offer_shares / (_lot_size or _board_lot)

    if _global_offer_shares is None and _hk_offer_shares and _intl_offer_shares:
        _global_offer_shares = _hk_offer_shares + _intl_offer_shares

    # 将补充后的字段写入 item，供 _raw 使用
    if _offer_price is not None:
        item["offer_price"] = _offer_price
    if _market_cap is not None:
        item["market_cap_hkd_million"] = _market_cap
    if _lot_size is not None:
        item["lot_size"] = _lot_size
    if _board_lot is not None:
        item["board_lot"] = _board_lot
    if _hk_offer_shares is not None:
        item["hk_offer_shares"] = _hk_offer_shares
    if _global_offer_shares is not None:
        item["global_offer_shares"] = _global_offer_shares
    if _public_offer_ratio is not None:
        item["public_offer_ratio"] = _public_offer_ratio
    if _international_offer_ratio is not None:
        item["international_offer_ratio"] = _international_offer_ratio
    if _public_offer_lots is not None:
        item["public_offer_lots"] = _public_offer_lots
    if _intl_offer_shares is not None:
        item["international_offer_shares"] = _intl_offer_shares

    raw_item = copy.deepcopy(item)
    raw_item.pop("_full_result", None)
    pi_raw = raw_item.get("prospectus_info")
    if isinstance(pi_raw, dict):
        pi_raw.pop("_extracted_text", None)

    return {
        "stock_code": item.get("hk_code", "--"),
        "company_name": item.get("company_name", "--"),
        "trade_score": trade_score,
        "strict_ipo_score": trade_score,
        "raw_trade_signal_score": item.get("raw_trade_signal_score", item.get("trade_score", 0)),
        "long_term_score": long_term_score,
        "subscription_recommendation": item.get("subscription_recommendation", "--"),
        "valuation_pressure": item.get("valuation_pressure_label", "--"),
        "market_heat": item.get("market_heat", "--"),
        "apply_end_date": item.get("apply_end_date", "--"),
        "tracking_status": status_map.get(post.get("status"), "未跟踪"),
        "has_post_listing": bool(post),
        "score": item.get("score", 0),
        "_raw": raw_item,
    }


class HistoryListResponse(BaseModel):
    records: list[dict]
    total: int


class HistoryExportResponse(BaseModel):
    data: list[dict]
    exported_at: str


class TrackResponse(BaseModel):
    stock_code: str
    status: str
    message: Optional[str] = None
    post_listing: Optional[dict] = None


class TrackAllResponse(BaseModel):
    processed: int
    updated: int
    failed: int
    details: list[dict]


@router.get("/records", response_model=HistoryListResponse)
async def list_history_records(
    query: Optional[str] = Query(None),
    show_live: bool = Query(True),
    sort_by: str = Query("截止日从近到远"),
    tracking_status: Optional[str] = Query(None),
    config: APIConfig = Depends(get_config),
):
    from ipo_analyzer.history import HistoryStore

    store = HistoryStore(str(config.storage_base_path))
    records = store.load(include_live=True)

    # Text search
    if query:
        q = query.strip().lower()
        records = [
            r for r in records
            if q in str(r.get("hk_code", "")).lower()
            or q in str(r.get("company_name", "")).lower()
        ]

    # Show live filter
    if not show_live:
        records = [r for r in records if not _is_live_or_future(r)]

    # Tracking status filter
    if tracking_status and tracking_status != "全部":
        records = [
            r for r in records
            if (r.get("post_listing") or {}).get("status") == tracking_status
            or (tracking_status == "未跟踪" and not (r.get("post_listing") or {}).get("status"))
        ]

    # Sort
    records = _sort_history_records(records, sort_by)

    formatted = [_format_history_row(r) for r in records]
    return HistoryListResponse(records=formatted, total=len(formatted))


@router.get("/export", response_model=HistoryExportResponse)
async def export_history(config: APIConfig = Depends(get_config)):
    records = _load_history_records(str(config.storage_base_path))
    return HistoryExportResponse(
        data=records,
        exported_at=datetime.now().isoformat(),
    )


@router.get("/records/{stock_code}", response_model=dict)
async def get_history_record(stock_code: str, config: APIConfig = Depends(get_config)):
    records = _load_history_records(str(config.storage_base_path))
    for r in records:
        if str(r.get("hk_code", "")).strip() == stock_code.strip():
            return r
    raise HTTPException(status_code=404, detail="Record not found")


@router.post("/track/{stock_code}", response_model=TrackResponse)
async def track_history_record(
    stock_code: str,
    force_refresh: bool = Query(False),
    _token: str = Depends(require_api_token),
    config: APIConfig = Depends(get_config),
):
    from ipo_analyzer.history import HistoryStore
    from ipo_analyzer.post_listing import track_post_listing

    store = HistoryStore(str(config.storage_base_path))
    records = store.load(include_live=True)

    base_record = None
    company_name = None
    for r in records:
        if str(r.get("hk_code", "")).strip() == stock_code.strip():
            base_record = r
            company_name = r.get("company_name")
            break

    if not base_record:
        raise HTTPException(status_code=404, detail="Record not found")

    try:
        post_listing = track_post_listing(
            stock_code=stock_code,
            company_name=company_name,
            base_record=base_record,
            output_dir=str(config.storage_base_path),
            force_refresh=force_refresh,
        )
        updated_record = store.update_post_listing(stock_code, post_listing)
        status = post_listing.get("status", "error")
        message = None
        if status == "pending_allotment":
            message = "配发结果公告暂未找到，已记录为待公告。"
        elif status == "error":
            message = post_listing.get("error", "跟踪异常")

        return TrackResponse(
            stock_code=stock_code,
            status=status,
            message=message,
            post_listing=updated_record.get("post_listing") if updated_record else post_listing,
        )
    except Exception as e:
        logger.exception("Track post listing failed for %s", stock_code)
        raise HTTPException(status_code=500, detail=f"跟踪失败: {e}")


@router.post("/track-all", response_model=TrackAllResponse)
async def track_all_history_records(
    force_refresh: bool = Query(False),
    only_missing: bool = Query(True),
    _token: str = Depends(require_api_token),
    config: APIConfig = Depends(get_config),
):
    from ipo_analyzer.post_listing import track_ended_ipos

    try:
        summary = track_ended_ipos(
            output_dir=str(config.storage_base_path),
            only_missing=only_missing,
            force_refresh=force_refresh,
        )
        return TrackAllResponse(
            processed=summary.get("processed", 0),
            updated=summary.get("updated", 0),
            failed=summary.get("failed", 0),
            details=summary.get("details", []),
        )
    except Exception as e:
        logger.exception("Track all failed")
        raise HTTPException(status_code=500, detail=f"批量跟踪失败: {e}")


@router.post("/parse-allotment/{stock_code}", response_model=TrackResponse)
async def parse_allotment_pdf_upload(
    stock_code: str,
    pdf: UploadFile = File(...),
    _token: str = Depends(require_api_token),
    config: APIConfig = Depends(get_config),
):
    from ipo_analyzer.history import HistoryStore
    from ipo_analyzer.post_listing import parse_allotment_pdf, track_post_listing

    if not pdf.filename or not pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    file_bytes = await pdf.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    store = HistoryStore(str(config.storage_base_path))
    records = store.load(include_live=True)

    base_record = None
    company_name = None
    for r in records:
        if str(r.get("hk_code", "")).strip() == stock_code.strip():
            base_record = r
            company_name = r.get("company_name")
            break

    if not base_record:
        raise HTTPException(status_code=404, detail="Record not found")

    try:
        parsed = parse_allotment_pdf(pdf_bytes=file_bytes)
        if not parsed or not parsed.get("final_offer_price"):
            raise HTTPException(status_code=422, detail="解析结果不完整，请确认上传的是配发结果公告PDF")

        post_listing = track_post_listing(
            stock_code=stock_code,
            company_name=company_name,
            base_record=base_record,
            output_dir=str(config.storage_base_path),
            force_refresh=True,
        )
        if parsed:
            post_listing.update(parsed)
            post_listing["status"] = "ok"

        updated_record = store.update_post_listing(stock_code, post_listing)
        return TrackResponse(
            stock_code=stock_code,
            status="ok",
            message="配发公告解析完成",
            post_listing=updated_record.get("post_listing") if updated_record else post_listing,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Parse allotment PDF failed for %s", stock_code)
        raise HTTPException(status_code=500, detail=f"解析失败: {e}")
