from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import get_config
from api.routers import health


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = get_config()
    config.storage_base_path.mkdir(parents=True, exist_ok=True)
    (config.storage_base_path / "uploads").mkdir(parents=True, exist_ok=True)
    (config.storage_base_path / "results").mkdir(parents=True, exist_ok=True)
    (config.storage_base_path / "tmp").mkdir(parents=True, exist_ok=True)

    from api.services.history_service import HistoryService
    history_svc = HistoryService(str(config.db_path))
    history_svc.init_db()
    history_svc.recover_stale_jobs()

    yield


app = FastAPI(
    title="HK IPO Analyzer API",
    version="0.1.0",
    lifespan=lifespan,
)

config = get_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
