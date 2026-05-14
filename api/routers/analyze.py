import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile

from api.config import APIConfig
from api.deps import get_config
from api.schemas.analyze import (
    AnalyzeResultResponse,
    JobResponse,
    JobStatusResponse,
    ReanalyzeRequest,
)
from api.schemas.common import JobStatus
from api.services.history_service import HistoryService
from api.services.storage_service import StorageService
from api.workers.analyze_worker import run_reanalyze, run_upload_analysis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analyze", tags=["analyze"])


@router.post("/upload", response_model=JobResponse)
async def upload_and_analyze(
    background_tasks: BackgroundTasks,
    pdf: UploadFile = File(...),
    stock_code: Optional[str] = Form(None),
    company_name: Optional[str] = Form(None),
    config: APIConfig = Depends(get_config),
):
    if not pdf.filename or not pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    file_bytes = await pdf.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    storage_svc = StorageService(config)
    upload_path = storage_svc.save_upload(file_bytes, pdf.filename)

    history_svc = HistoryService(str(config.db_path))
    job = history_svc.create_job(
        job_type="upload",
        stock_code=stock_code,
        company_name=company_name,
        upload_path=str(upload_path),
    )

    run_upload_analysis(job["job_id"], str(upload_path), stock_code, company_name)

    return JobResponse(job_id=job["job_id"], status=JobStatus.QUEUED, created_at=job["created_at"])


@router.post("/reanalyze", response_model=JobResponse)
async def reanalyze(
    request: ReanalyzeRequest,
    config: APIConfig = Depends(get_config),
):
    history_svc = HistoryService(str(config.db_path))
    job = history_svc.create_job(
        job_type="reanalyze",
        stock_code=request.stock_code,
        company_name=request.company_name,
    )

    run_reanalyze(
        job["job_id"],
        request.stock_code,
        request.company_name,
        request.historical_market_data,
    )

    return JobResponse(job_id=job["job_id"], status=JobStatus.QUEUED, created_at=job["created_at"])


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str, config: APIConfig = Depends(get_config)):
    history_svc = HistoryService(str(config.db_path))
    job = history_svc.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatusResponse(
        job_id=job["id"],
        status=job["status"],
        stock_code=job.get("stock_code"),
        company_name=job.get("company_name"),
        error=job.get("error"),
        created_at=job["created_at"],
        updated_at=job["updated_at"],
        started_at=job.get("started_at"),
        finished_at=job.get("finished_at"),
    )


@router.get("/jobs/{job_id}/result", response_model=AnalyzeResultResponse)
async def get_job_result(job_id: str, config: APIConfig = Depends(get_config)):
    history_svc = HistoryService(str(config.db_path))
    job = history_svc.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "success":
        raise HTTPException(
            status_code=409,
            detail=f"Job status is '{job['status']}', result only available for 'success' jobs",
        )

    result_path = job.get("result_path")
    if not result_path:
        raise HTTPException(status_code=404, detail="Result path not found for job")

    storage_svc = StorageService(config)
    try:
        result_data = storage_svc.read_result(result_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Result file not found on disk")

    return AnalyzeResultResponse(
        job_id=job["id"],
        stock_code=job.get("stock_code"),
        company_name=job.get("company_name"),
        result=result_data,
    )
