import platform
import sys
import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_config, get_db
from api.config import APIConfig
from ipo_analyzer import __version__ as IPO_ANALYZER_VERSION

router = APIRouter(prefix="/api", tags=["health"])

_start_time = time.time()


class HealthResponse(BaseModel):
    status: str
    db_status: str
    worker_status: str
    uptime_seconds: float


class VersionResponse(BaseModel):
    app_version: str
    python_version: str
    ipo_analyzer_version: str


@router.get("/health", response_model=HealthResponse)
def health_check(config: APIConfig = Depends(get_config), db=Depends(get_db)):
    db_status = "ok"
    try:
        db.execute("SELECT 1")
    except Exception:
        db_status = "error"

    worker_status = "idle"

    return HealthResponse(
        status="ok",
        db_status=db_status,
        worker_status=worker_status,
        uptime_seconds=round(time.time() - _start_time, 1),
    )


@router.get("/version", response_model=VersionResponse)
def version_check():
    ipo_analyzer_version = "unknown"
    try:
        from ipo_analyzer import __version__
        ipo_analyzer_version = __version__
    except Exception:
        pass

    return VersionResponse(
        app_version=IPO_ANALYZER_VERSION,
        python_version=f"{platform.python_version()} ({sys.implementation.name})",
        ipo_analyzer_version=ipo_analyzer_version,
    )
