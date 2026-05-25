import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends

from api.auth import require_api_token
from api.config import APIConfig
from api.deps import get_config
from api.schemas.analyze import JobResponse
from api.schemas.common import JobStatus
from api.schemas.live import LiveResultsResponse, LiveStatusResponse, LiveAnalyzeRequest
from api.services.history_service import HistoryService
from api.workers.analyze_worker import run_live_analysis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/live", tags=["live"])

_RESULTS_CACHE: Optional[tuple[list[dict], Optional[str], float]] = None
_CACHE_TTL_SECONDS = 30


def _load_cached_results(output_dir: str = "temp", use_memory_cache: bool = True) -> tuple[list[dict], Optional[str]]:
    global _RESULTS_CACHE

    if use_memory_cache and _RESULTS_CACHE is not None:
        cached_results, cached_time, cached_at = _RESULTS_CACHE
        if time.time() - cached_at < _CACHE_TTL_SECONDS:
            return cached_results, cached_time

    paths_to_try = [output_dir]
    if output_dir != "temp":
        paths_to_try.append("temp")

    cache_file = None
    for try_dir in paths_to_try:
        candidate = os.path.join(try_dir, "results_cache.json")
        if os.path.exists(candidate):
            cache_file = candidate
            break

    if cache_file is None:
        return [], None

    try:
        file_mtime = os.path.getmtime(cache_file)
        if use_memory_cache and _RESULTS_CACHE is not None:
            cached_results, cached_time, cached_at = _RESULTS_CACHE
            if cached_at >= file_mtime:
                return cached_results, cached_time

        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return [], None

        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        today = datetime.now().date().isoformat()
        filtered = [
            item for item in data
            if item.get("_cached_at", "") >= cutoff
            and (not item.get("apply_end_date") or str(item.get("apply_end_date")) >= today)
        ]
        cache_times = [item.get("_cached_at", "") for item in filtered if item.get("_cached_at")]
        cache_time = None
        if cache_times:
            latest = max(cache_times)
            try:
                cache_time = datetime.fromisoformat(latest).strftime("%Y-%m-%d %H:%M")
            except Exception:
                cache_time = latest[:16] if len(latest) >= 16 else latest

        _RESULTS_CACHE = (filtered, cache_time, time.time())
        return filtered, cache_time
    except Exception as e:
        logger.warning(f"Failed to load cache: {e}")
        return [], None


def invalidate_results_cache():
    global _RESULTS_CACHE
    _RESULTS_CACHE = None


@router.get("/results", response_model=LiveResultsResponse)
async def get_live_results(config: APIConfig = Depends(get_config)):
    results, cache_time = _load_cached_results(str(config.storage_base_path))
    return LiveResultsResponse(
        results=results,
        cache_time=cache_time,
        total=len(results),
    )


@router.post("/analyze", response_model=JobResponse)
async def trigger_live_analysis(
    request: LiveAnalyzeRequest,
    _token: str = Depends(require_api_token),
    config: APIConfig = Depends(get_config),
):
    invalidate_results_cache()
    history_svc = HistoryService(str(config.db_path))
    job = history_svc.create_job(
        job_type="live",
        stock_code=None,
        company_name=None,
    )

    run_live_analysis(
        job["job_id"],
        force_refresh=request.force_refresh,
        output_dir=str(config.storage_base_path),
    )

    return JobResponse(
        job_id=job["job_id"],
        status=JobStatus.QUEUED,
        created_at=job["created_at"],
    )


@router.get("/status", response_model=LiveStatusResponse)
async def get_live_status(config: APIConfig = Depends(get_config)):
    history_svc = HistoryService(str(config.db_path))
    rows = history_svc.list_jobs(limit=10, offset=0)

    live_jobs = [r for r in rows if r.get("job_type") == "live"]
    running = [j for j in live_jobs if j.get("status") == "running"]
    latest = live_jobs[0] if live_jobs else None

    return LiveStatusResponse(
        has_running_job=len(running) > 0,
        latest_job_id=latest.get("id") if latest else None,
        latest_job_status=latest.get("status") if latest else None,
    )
