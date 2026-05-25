import asyncio
import json
import logging
import os
import traceback
from typing import Optional

from api.config import get_config
from api.services.history_service import HistoryService
from api.services.storage_service import StorageService

logger = logging.getLogger(__name__)

_semaphore: Optional[asyncio.Semaphore] = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        config = get_config()
        _semaphore = asyncio.Semaphore(config.max_concurrent_analyses)
    return _semaphore


async def _refresh_live_blogger_consensus_async(results, output_dir: str) -> None:
    from ipo_analyzer.core import _refresh_live_blogger_consensus

    await asyncio.to_thread(_refresh_live_blogger_consensus, results, output_dir)


def _cornerstone_quality(item: dict) -> tuple[int, int, int]:
    ca = ((item or {}).get("prospectus_info") or {}).get("cornerstone_analysis") or {}
    rows = ca.get("cornerstone_investors") or []
    unknown = sum(1 for row in rows if not row.get("category") or row.get("category") == "未知")
    known = max(0, len(rows) - unknown)
    try:
        score = int(ca.get("score") or 0)
    except (TypeError, ValueError):
        score = 0
    return (known, len(rows), score)


def _protect_cornerstone_regressions(results: list[dict], output_dir: str) -> list[dict]:
    """Avoid replacing a well-classified cornerstone result with a weaker live parse."""
    cache_file = os.path.join(output_dir, "results_cache.json")
    if not os.path.exists(cache_file):
        return results
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            existing_items = json.load(f)
    except Exception:
        return results
    if not isinstance(existing_items, list):
        return results

    existing_by_code = {
        str(item.get("hk_code") or item.get("stock_code") or "").zfill(5): item
        for item in existing_items
        if isinstance(item, dict) and (item.get("hk_code") or item.get("stock_code"))
    }

    for item in results:
        code = str(item.get("hk_code") or item.get("stock_code") or "").zfill(5)
        existing = existing_by_code.get(code)
        if not existing:
            continue
        old_ca = ((existing.get("prospectus_info") or {}).get("cornerstone_analysis") or {})
        new_pi = item.get("prospectus_info") or {}
        new_ca = new_pi.get("cornerstone_analysis") or {}
        if not old_ca or not new_ca:
            continue
        if _cornerstone_quality(existing) > _cornerstone_quality(item):
            new_pi["cornerstone_analysis"] = old_ca
            new_pi["cornerstone_investors"] = old_ca.get("cornerstone_investors", [])
            new_pi["cornerstone_pct"] = old_ca.get("cornerstone_pct")
            item["prospectus_info"] = new_pi
    return results


def run_upload_analysis(job_id: str, upload_path: str,
                        stock_code: Optional[str], company_name: Optional[str]):
    config = get_config()
    history_svc = HistoryService(str(config.db_path))
    storage_svc = StorageService(config)

    semaphore = _get_semaphore()

    async def _run():
        await semaphore.acquire()
        try:
            history_svc.update_job_status(job_id, "running")
            logger.info(f"Job {job_id}: starting upload analysis for {upload_path}")

            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                _call_analyze_uploaded_pdf,
                upload_path,
                stock_code,
                company_name,
            )

            if "error" in result:
                history_svc.update_job_status(job_id, "failed", error=result["error"])
                logger.error(f"Job {job_id}: analysis failed: {result['error']}")
                return

            resolved_code = stock_code or result.get("hk_code") or "UNKNOWN"
            resolved_name = company_name or result.get("company_name") or ""

            result_path = storage_svc.save_result(resolved_code, result)
            history_svc.update_job_status(job_id, "success", result_path=str(result_path))

            score = result.get("score")
            suggestion = result.get("suggestion")
            history_svc.create_history(
                stock_code=resolved_code,
                result_path=str(result_path),
                score=score,
                suggestion=suggestion,
                company_name=resolved_name,
                source="upload",
            )

            storage_svc.cleanup_tmp()
            logger.info(f"Job {job_id}: analysis complete, result at {result_path}")
        except Exception as e:
            tb = traceback.format_exc()
            history_svc.update_job_status(job_id, "failed", error=f"{e}\n{tb}")
            logger.error(f"Job {job_id}: unexpected error: {e}\n{tb}")
        finally:
            semaphore.release()

    asyncio.get_running_loop().create_task(_run())


def run_reanalyze(job_id: str, stock_code: str, company_name: Optional[str],
                  historical_market_data: Optional[dict]):
    config = get_config()
    history_svc = HistoryService(str(config.db_path))
    storage_svc = StorageService(config)

    semaphore = _get_semaphore()

    async def _run():
        await semaphore.acquire()
        try:
            history_svc.update_job_status(job_id, "running")
            logger.info(f"Job {job_id}: starting reanalyze for {stock_code}")

            tmp_dir = str(config.storage_base_path / "tmp")

            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                _call_reanalyze_ipo,
                stock_code,
                company_name,
                historical_market_data,
                tmp_dir,
            )

            status = result.get("status", "error")
            if status == "error":
                error_msg = result.get("message", "Unknown error")
                history_svc.update_job_status(job_id, "failed", error=error_msg)
                logger.error(f"Job {job_id}: reanalyze failed: {error_msg}")
                return

            inner_result = result.get("result", result)
            resolved_name = company_name or inner_result.get("company_name", "")

            result_path = storage_svc.save_result(stock_code, result)
            history_svc.update_job_status(job_id, "success", result_path=str(result_path))

            score = inner_result.get("score")
            suggestion = inner_result.get("suggestion") or result.get("suggestion")
            history_svc.create_history(
                stock_code=stock_code,
                result_path=str(result_path),
                score=score,
                suggestion=suggestion,
                company_name=resolved_name,
                source="reanalyze",
            )

            storage_svc.cleanup_tmp()
            logger.info(f"Job {job_id}: reanalyze complete, result at {result_path}")
        except Exception as e:
            tb = traceback.format_exc()
            history_svc.update_job_status(job_id, "failed", error=f"{e}\n{tb}")
            logger.error(f"Job {job_id}: unexpected error: {e}\n{tb}")
        finally:
            semaphore.release()

    asyncio.get_running_loop().create_task(_run())


def _call_analyze_uploaded_pdf(pdf_path: str, stock_code: Optional[str],
                                company_name: Optional[str]) -> dict:
    from ipo_analyzer.core import analyze_uploaded_pdf
    return analyze_uploaded_pdf(pdf_path, stock_code=stock_code, company_name=company_name)


def _call_reanalyze_ipo(stock_code: str, company_name: Optional[str],
                         historical_market_data: Optional[dict],
                         output_dir: str) -> dict:
    from ipo_analyzer.core import reanalyze_ipo
    return reanalyze_ipo(
        stock_code=stock_code,
        company_name=company_name,
        historical_market_data=historical_market_data,
        output_dir=output_dir,
    )


def run_live_analysis(job_id: str, force_refresh: bool = False, output_dir: str = "temp"):
    config = get_config()
    history_svc = HistoryService(str(config.db_path))

    semaphore = _get_semaphore()

    async def _run():
        await semaphore.acquire()
        try:
            history_svc.update_job_status(job_id, "running")
            logger.info(f"Job {job_id}: starting live IPO analysis")

            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                _call_analyze_live_ipos,
                force_refresh,
                output_dir,
            )

            status = result.get("status", "error")
            if status == "error":
                error_msg = result.get("message", "Unknown error")
                history_svc.update_job_status(job_id, "failed", error=error_msg)
                logger.error(f"Job {job_id}: live analysis failed: {error_msg}")
                return

            results = result.get("results", [])
            if results:
                results = _protect_cornerstone_regressions(results, output_dir)
                from ipo_analyzer.cache import ResultCache
                cache = ResultCache(output_dir)
                cache.save(results)

                from ipo_analyzer.history import HistoryStore
                HistoryStore(output_dir).archive_many(results, source="live")
                logger.info(f"Job {job_id}: cached {len(results)} IPOs")

            history_svc.update_job_status(job_id, "success")
            if results:
                asyncio.get_running_loop().create_task(_refresh_live_blogger_consensus_async(results, output_dir))
            logger.info(f"Job {job_id}: live analysis complete")
        except Exception as e:
            tb = traceback.format_exc()
            history_svc.update_job_status(job_id, "failed", error=f"{e}\n{tb}")
            logger.error(f"Job {job_id}: unexpected error: {e}\n{tb}")
        finally:
            semaphore.release()

    asyncio.get_running_loop().create_task(_run())


def _call_analyze_live_ipos(force_refresh: bool = False, output_dir: str = "temp") -> dict:
    from ipo_analyzer.core import analyze_live_ipos
    return analyze_live_ipos(output_dir=output_dir, force_refresh=force_refresh, return_status=True)
