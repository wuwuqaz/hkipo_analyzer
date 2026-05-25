import json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from api.auth import require_api_token
from api.config import APIConfig
from api.deps import get_config
from api.services.history_service import HistoryService
from api.services.storage_service import StorageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/jobs/{job_id}/json")
async def download_job_json(
    job_id: str,
    _token: str = Depends(require_api_token),
    config: APIConfig = Depends(get_config),
):
    history_svc = HistoryService(str(config.db_path))
    job = history_svc.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "success":
        raise HTTPException(status_code=409, detail="Job not completed")

    result_path = job.get("result_path")
    if not result_path or not os.path.exists(result_path):
        raise HTTPException(status_code=404, detail="Result file not found")

    storage_svc = StorageService(config)
    try:
        validated_path = storage_svc.validate_path(result_path)
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid result path")

    return FileResponse(
        str(validated_path),
        media_type="application/json",
        filename=f"{job_id}_result.json",
    )


@router.get("/jobs/{job_id}/pdf")
async def download_job_pdf(
    job_id: str,
    _token: str = Depends(require_api_token),
    config: APIConfig = Depends(get_config),
):
    history_svc = HistoryService(str(config.db_path))
    job = history_svc.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "success":
        raise HTTPException(status_code=409, detail="Job not completed")

    result_path = job.get("result_path")
    if not result_path or not os.path.exists(result_path):
        raise HTTPException(status_code=404, detail="Result file not found")

    storage_svc = StorageService(config)
    try:
        validated_path = storage_svc.validate_path(result_path)
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid result path")

    try:
        with open(str(validated_path), "r", encoding="utf-8") as f:
            result_data = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read result: {e}")

    # Handle nested result structure
    if "result" in result_data:
        result_data = result_data["result"]

    from ipo_analyzer.core import generate_pdf_report

    tmp_dir = str(config.storage_base_path / "tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    try:
        pdf_path = generate_pdf_report(result_data, output_dir=tmp_dir)
        if not pdf_path or not os.path.exists(pdf_path):
            raise HTTPException(status_code=500, detail="PDF generation failed")

        stock_code = result_data.get("hk_code", job_id)
        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            filename=f"{stock_code}_report.pdf",
        )
    except Exception as e:
        logger.error(f"PDF generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")
