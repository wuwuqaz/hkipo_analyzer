from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from api.schemas.common import JobStatus


class JobCreateRequest(BaseModel):
    stock_code: Optional[str] = None
    company_name: Optional[str] = None


class ReanalyzeRequest(BaseModel):
    stock_code: str
    company_name: Optional[str] = None
    historical_market_data: Optional[dict] = None


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    created_at: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    stock_code: Optional[str] = None
    company_name: Optional[str] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class AnalyzeResultResponse(BaseModel):
    job_id: str
    stock_code: Optional[str] = None
    company_name: Optional[str] = None
    result: dict
