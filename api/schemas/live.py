from typing import Optional

from pydantic import BaseModel


class LiveAnalyzeRequest(BaseModel):
    force_refresh: bool = False


class LiveResultsResponse(BaseModel):
    results: list[dict]
    cache_time: Optional[str] = None
    total: int


class LiveStatusResponse(BaseModel):
    has_running_job: bool
    latest_job_id: Optional[str] = None
    latest_job_status: Optional[str] = None
