import asyncio
import logging
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

            loop = asyncio.get_event_loop()
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

    asyncio.get_event_loop().create_task(_run())


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

            loop = asyncio.get_event_loop()
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

    asyncio.get_event_loop().create_task(_run())


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
