# P0 + P0.5 实施计划：基础设施 + API 骨架

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建 FastAPI 后端骨架、Next.js 前端骨架、SQLite 存储层、异步任务模型和 API Token 认证，跑通最小端到端链路（上传 PDF → job_id → 轮询 → 结果）。

**Architecture:** FastAPI 作为 API 层调用 ipo_analyzer/ 核心逻辑（零修改），SQLite 作为唯一事实源，BackgroundTasks + Semaphore 控制并发，API Token 保护写入接口。Next.js 前端仅实现 health 展示页。

**Tech Stack:** FastAPI 0.115+, Uvicorn, aiosqlite, Next.js 15, shadcn/ui, Tailwind CSS 4.x

**Spec:** `docs/superpowers/specs/2026-05-14-streamlit-to-react-fastapi-migration.md` v1.1

---

## 文件结构总览

### 新增文件

| 文件 | 职责 |
|------|------|
| `api/__init__.py` | 包初始化 |
| `api/main.py` | FastAPI app 入口, CORS, 路由挂载 |
| `api/config.py` | API 配置 (端口、存储路径、并发数等) |
| `api/deps.py` | 依赖注入 (DB 连接、配置) |
| `api/auth.py` | API Token 验证 |
| `api/routers/__init__.py` | 包初始化 |
| `api/routers/health.py` | GET /api/health, GET /api/version |
| `api/routers/analyze.py` | POST /api/analyze/upload, /reanalyze, GET /jobs/{id}, /jobs/{id}/result |
| `api/schemas/__init__.py` | 包初始化 |
| `api/schemas/common.py` | 通用模型 (JobStatus, ErrorResponse) |
| `api/schemas/analyze.py` | 分析相关模型 (JobCreateRequest, JobResponse, JobStatusResponse, AnalyzeResultResponse) |
| `api/services/__init__.py` | 包初始化 |
| `api/services/storage_service.py` | storage/ 目录管理 |
| `api/services/history_service.py` | SQLite 历史记录 CRUD |
| `api/workers/__init__.py` | 包初始化 |
| `api/workers/analyze_worker.py` | PDF 分析后台 worker |
| `storage/.gitkeep` | 确保 storage/ 目录存在 |
| `storage/uploads/.gitkeep` | 确保 uploads/ 目录存在 |
| `storage/results/.gitkeep` | 确保 results/ 目录存在 |
| `storage/tmp/.gitkeep` | 确保 tmp/ 目录存在 |
| `docker-compose.yml` | Docker 编排 |
| `nginx.conf` | Nginx 反向代理配置 |
| `api/tests/__init__.py` | 测试包初始化 |
| `api/tests/conftest.py` | pytest fixtures |
| `api/tests/test_health.py` | health/version 接口测试 |
| `api/tests/test_analyze.py` | 分析任务接口测试 |
| `api/tests/test_auth.py` | 认证测试 |
| `frontend/` | Next.js 项目 (由 create-next-app 生成) |

### 修改文件

| 文件 | 改动 |
|------|------|
| `requirements.txt` | 新增 fastapi, uvicorn, aiosqlite, python-multipart |
| `.gitignore` | 新增 storage/history.db, storage/uploads/*.pdf, storage/results/*.json, storage/tmp/*, frontend/node_modules/, frontend/.next/ |

### 不修改的文件

`ipo_analyzer/` 全部文件、`ui/` 全部文件、`app.py`、`style.css` — 均不触碰。

---

## 数据库设计

### analyze_jobs 表

```sql
CREATE TABLE IF NOT EXISTS analyze_jobs (
    id TEXT PRIMARY KEY,              -- UUID4
    job_type TEXT NOT NULL,           -- 'upload' | 'reanalyze'
    status TEXT NOT NULL DEFAULT 'queued',  -- queued | running | success | failed
    stock_code TEXT,                  -- 股票代码
    company_name TEXT,                -- 公司名称
    upload_path TEXT,                 -- storage/uploads/{uuid}.pdf
    result_path TEXT,                 -- storage/results/{stock_code}_{ts}.json
    error TEXT,                       -- 失败原因
    created_at TEXT NOT NULL,         -- ISO 8601
    updated_at TEXT NOT NULL,         -- ISO 8601
    started_at TEXT,                  -- 开始执行时间
    finished_at TEXT                  -- 完成时间
);
```

### ipo_history 表

```sql
CREATE TABLE IF NOT EXISTS ipo_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT NOT NULL,
    company_name TEXT NOT NULL DEFAULT '',
    result_path TEXT NOT NULL,        -- storage/results/{stock_code}_{ts}.json
    score REAL,                       -- 综合评分
    suggestion TEXT,                  -- 申购建议
    source TEXT NOT NULL DEFAULT 'upload',  -- upload | reanalyze | live
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(stock_code, created_at)
);
```

### blogger_posts / blogger_analysis 表

**不迁移**。P0.5 阶段 blogger_monitor 仍使用自己的 SQLite 文件 (`ipo_analyzer/blogger_monitor/blogger.db`)。后续 P4 阶段再合并到 `storage/history.db`。

---

## 任务模型设计

### 状态流转

```
queued ──→ running ──→ success
  │          │
  │          └──→ failed
  │
  └──→ (服务重启时) → failed (stale_running)
```

### 服务重启处理

启动时扫描 `status = 'running'` 的任务，将其标记为 `failed`，error 记录 `"Service restarted during analysis"`。因为这些任务的内存状态已丢失，无法恢复。

### result_path 关联

- worker 完成后将结果 JSON 写入 `storage/results/{stock_code}_{timestamp}.json`
- 同时更新 `analyze_jobs.result_path` 和 `ipo_history.result_path`
- `GET /api/analyze/jobs/{job_id}/result` 读取 result_path 指向的文件

### 并发限制

- `asyncio.Semaphore(MAX_CONCURRENT_ANALYSES)` 默认值 2
- 环境变量 `MAX_CONCURRENT_ANALYSES` 可覆盖
- worker 在 semaphore 获取后才将 status 从 queued 改为 running
- 获取不到 semaphore 的任务保持 queued 状态，由后台轮询拾取

---

## 认证方案

- 环境变量 `HKIPO_API_TOKEN` 设置 token
- 写入接口 (POST/PUT/DELETE) 必须携带 `Authorization: Bearer {token}` 头
- GET 接口暂不认证
- 如果 `HKIPO_API_TOKEN` 未设置，写入接口返回 503 Service Unavailable（拒绝无保护运行）
- `api/auth.py` 实现 `require_api_token` 依赖

---

## Commit 1: API Skeleton

### Task 1.1: 创建 api/ 目录结构

- [ ] **Step 1: 创建目录**

```bash
cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer
mkdir -p api/routers api/schemas api/services api/workers api/tests
touch api/__init__.py api/routers/__init__.py api/schemas/__init__.py api/services/__init__.py api/workers/__init__.py api/tests/__init__.py
```

预期输出: 无报错，目录创建成功。

- [ ] **Step 2: 验证目录结构**

```bash
find api/ -type f | sort
```

预期输出:
```
api/__init__.py
api/routers/__init__.py
api/schemas/__init__.py
api/services/__init__.py
api/tests/__init__.py
api/workers/__init__.py
```

### Task 1.2: 创建 api/config.py

- [ ] **Step 3: 创建 APIConfig**

创建文件 `api/config.py`:

```python
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class APIConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    storage_base_path: Path = field(default_factory=lambda: Path(os.getenv("STORAGE_BASE_PATH", "storage")))
    max_concurrent_analyses: int = 2
    api_token_env: str = "HKIPO_API_TOKEN"
    cors_origins: list[str] = field(default_factory=lambda: [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ])
    db_path: Path = field(default_factory=lambda: Path(os.getenv("STORAGE_BASE_PATH", "storage")) / "history.db")

    def __post_init__(self):
        if isinstance(self.storage_base_path, str):
            self.storage_base_path = Path(self.storage_base_path)
        if isinstance(self.db_path, str):
            self.db_path = Path(self.db_path)
        self.max_concurrent_analyses = int(os.getenv("MAX_CONCURRENT_ANALYSES", str(self.max_concurrent_analyses)))
        self.host = os.getenv("API_HOST", self.host)
        self.port = int(os.getenv("API_PORT", str(self.port)))
        cors_raw = os.getenv("CORS_ORIGINS")
        if cors_raw:
            self.cors_origins = [origin.strip() for origin in cors_raw.split(",") if origin.strip()]


def get_config() -> APIConfig:
    return APIConfig()
```

- [ ] **Step 4: 验证 config 可导入**

```bash
cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer
python -c "from api.config import APIConfig, get_config; c = get_config(); print(f'host={c.host} port={c.port} max_concurrent={c.max_concurrent_analyses}')"
```

预期输出:
```
host=0.0.0.0 port=8000 max_concurrent=2
```

### Task 1.3: 创建 api/schemas/common.py

- [ ] **Step 5: 创建通用 schema**

创建文件 `api/schemas/common.py`:

```python
from enum import Enum

from pydantic import BaseModel


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class ErrorResponse(BaseModel):
    detail: str
```

### Task 1.4: 创建 api/deps.py

- [ ] **Step 6: 创建依赖注入**

创建文件 `api/deps.py`:

```python
import sqlite3

from api.config import APIConfig, get_config as _get_config


def get_config() -> APIConfig:
    return _get_config()


def get_db() -> sqlite3.Connection:
    config = get_config()
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(config.db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()
```

### Task 1.5: 创建 api/routers/health.py

- [ ] **Step 7: 创建 health 和 version 路由**

创建文件 `api/routers/health.py`:

```python
import platform
import sys
import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_config, get_db
from api.config import APIConfig

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
        app_version="0.1.0",
        python_version=f"{platform.python_version()} ({sys.implementation.name})",
        ipo_analyzer_version=ipo_analyzer_version,
    )
```

### Task 1.6: 创建 api/main.py

- [ ] **Step 8: 创建 FastAPI 应用入口**

创建文件 `api/main.py`:

```python
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
```

### Task 1.7: 修改 requirements.txt

- [ ] **Step 9: 添加 FastAPI 相关依赖**

修改 `requirements.txt`，在文件末尾添加四行：

```
fastapi>=0.115,<1.0
uvicorn[standard]>=0.30,<1.0
aiosqlite>=0.20,<1.0
python-multipart>=0.0.9,<1.0
```

完整文件内容：

```
streamlit>=1.32,<2.0
httpx>=0.24,<1.0
PyPDF2>=3.0,<4.0
pymupdf>=1.24,<2.0
reportlab>=4.0,<5.0
pandas>=2.0,<3.0
playwright>=1.40,<2.0
pyyaml>=6.0,<7.0
yfinance>=0.2.40,<1.0
tavily-python>=0.5,<1.0
python-dotenv>=1.0,<2.0
pydantic>=2.0,<3.0
fastapi>=0.115,<1.0
uvicorn[standard]>=0.30,<1.0
aiosqlite>=0.20,<1.0
python-multipart>=0.0.9,<1.0
```

- [ ] **Step 10: 安装新依赖**

```bash
cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer
pip install fastapi>=0.115 uvicorn[standard] aiosqlite python-multipart
```

预期输出: `Successfully installed ...` (或 `Requirement already satisfied`)

### Task 1.8: 验证 API 可启动（临时 — history_service 尚未创建，先创建最小 stub）

- [ ] **Step 11: 创建 history_service 最小 stub（Commit 2 会替换）**

创建文件 `api/services/history_service.py`:

```python
import sqlite3


class HistoryService:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def init_db(self):
        conn = self._connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS analyze_jobs (
                    id TEXT PRIMARY KEY,
                    job_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    stock_code TEXT,
                    company_name TEXT,
                    upload_path TEXT,
                    result_path TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ipo_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code TEXT NOT NULL,
                    company_name TEXT NOT NULL DEFAULT '',
                    result_path TEXT NOT NULL,
                    score REAL,
                    suggestion TEXT,
                    source TEXT NOT NULL DEFAULT 'upload',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(stock_code, created_at)
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def recover_stale_jobs(self):
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE analyze_jobs SET status = 'failed', error = 'Service restarted during analysis', updated_at = datetime('now') WHERE status = 'running'"
            )
            conn.commit()
        finally:
            conn.close()
```

- [ ] **Step 12: 启动 FastAPI 验证 health 接口**

```bash
cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 &
sleep 3
curl -s http://localhost:8000/api/health | python -m json.tool
curl -s http://localhost:8000/api/version | python -m json.tool
kill %1
```

预期 health 输出:
```json
{
    "status": "ok",
    "db_status": "ok",
    "worker_status": "idle",
    "uptime_seconds": 3.0
}
```

预期 version 输出:
```json
{
    "app_version": "0.1.0",
    "python_version": "3.x.x (cpython)",
    "ipo_analyzer_version": "0.5.0-alpha"
}
```

- [ ] **Step 13: 提交 Commit 1**

```bash
cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer
git add api/__init__.py api/config.py api/main.py api/deps.py api/routers/__init__.py api/routers/health.py api/schemas/__init__.py api/schemas/common.py api/services/__init__.py api/services/history_service.py api/workers/__init__.py api/tests/__init__.py requirements.txt
git commit -m "feat(api): add FastAPI skeleton with health and version endpoints

- Add api/ directory structure (routers, schemas, services, workers, tests)
- Add APIConfig dataclass with env var overrides
- Add GET /api/health (db_status, worker_status, uptime)
- Add GET /api/version (app_version, python_version, ipo_analyzer_version)
- Add SQLite schema for analyze_jobs and ipo_history tables
- Add history_service stub with init_db() and recover_stale_jobs()
- Add fastapi, uvicorn, aiosqlite, python-multipart to requirements.txt"
```

---

## Commit 2: Storage + SQLite

### Task 2.1: 创建 storage 目录结构

- [ ] **Step 1: 创建 storage 目录和 .gitkeep**

```bash
cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer
mkdir -p storage/uploads storage/results storage/tmp
touch storage/.gitkeep storage/uploads/.gitkeep storage/results/.gitkeep storage/tmp/.gitkeep
```

### Task 2.2: 修改 .gitignore

- [ ] **Step 2: 添加 storage 和 frontend 忽略规则**

在 `.gitignore` 文件末尾追加：

```
storage/history.db
storage/history.db-shm
storage/history.db-wal
storage/uploads/*.pdf
storage/results/*.json
storage/tmp/*
!storage/tmp/.gitkeep
frontend/node_modules/
frontend/.next/
```

### Task 2.3: 创建 api/services/storage_service.py

- [ ] **Step 3: 创建 StorageService**

创建文件 `api/services/storage_service.py`:

```python
import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from api.config import APIConfig, get_config


class StorageService:
    def __init__(self, config: APIConfig | None = None):
        self.config = config or get_config()
        self.base = self.config.storage_base_path
        self.uploads_dir = self.base / "uploads"
        self.results_dir = self.base / "results"
        self.tmp_dir = self.base / "tmp"

    def ensure_dirs(self):
        self.base.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def upload_path(self, file_uuid: str) -> Path:
        return self.uploads_dir / f"{file_uuid}.pdf"

    def result_path(self, stock_code: str, timestamp: str) -> Path:
        safe_code = stock_code.replace("/", "_").replace("\\", "_")
        safe_ts = timestamp.replace(":", "-").replace(" ", "_")
        return self.results_dir / f"{safe_code}_{safe_ts}.json"

    def save_upload(self, file_bytes: bytes, filename: str) -> Path:
        self.ensure_dirs()
        file_uuid = str(uuid.uuid4())
        dest = self.upload_path(file_uuid)
        dest.write_bytes(file_bytes)
        return dest

    def save_result(self, stock_code: str, data: dict) -> Path:
        self.ensure_dirs()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.result_path(stock_code, ts)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def read_result(self, result_path: str | Path) -> dict:
        p = Path(result_path)
        if not p.exists():
            raise FileNotFoundError(f"Result file not found: {p}")
        return json.loads(p.read_text(encoding="utf-8"))

    def cleanup_tmp(self):
        if self.tmp_dir.exists():
            for item in self.tmp_dir.iterdir():
                if item.name == ".gitkeep":
                    continue
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
```

- [ ] **Step 4: 验证 StorageService 可导入**

```bash
cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer
python -c "
from api.services.storage_service import StorageService
svc = StorageService()
svc.ensure_dirs()
print(f'base={svc.base} uploads={svc.uploads_dir} results={svc.results_dir} tmp={svc.tmp_dir}')
import tempfile, os
test_path = svc.save_upload(b'test pdf content', 'test.pdf')
print(f'upload saved to: {test_path}, exists: {test_path.exists()}')
os.remove(test_path)
print('StorageService OK')
"
```

预期输出:
```
base=storage uploads=storage/uploads results=storage/results tmp=storage/tmp
upload saved to: storage/uploads/<uuid>.pdf, exists: True
StorageService OK
```

### Task 2.4: 完善 api/services/history_service.py

- [ ] **Step 5: 替换 history_service.py 为完整版**

覆盖 `api/services/history_service.py`:

```python
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional


class HistoryService:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init_db(self):
        conn = self._connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS analyze_jobs (
                    id TEXT PRIMARY KEY,
                    job_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    stock_code TEXT,
                    company_name TEXT,
                    upload_path TEXT,
                    result_path TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ipo_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code TEXT NOT NULL,
                    company_name TEXT NOT NULL DEFAULT '',
                    result_path TEXT NOT NULL,
                    score REAL,
                    suggestion TEXT,
                    source TEXT NOT NULL DEFAULT 'upload',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(stock_code, created_at)
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def recover_stale_jobs(self):
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE analyze_jobs SET status = 'failed', error = 'Service restarted during analysis', updated_at = ? WHERE status = 'running'",
                (datetime.now().isoformat(),),
            )
            conn.commit()
        finally:
            conn.close()

    def create_job(self, job_type: str, stock_code: Optional[str] = None,
                   company_name: Optional[str] = None,
                   upload_path: Optional[str] = None) -> dict:
        job_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO analyze_jobs (id, job_type, status, stock_code, company_name, upload_path, created_at, updated_at) VALUES (?, ?, 'queued', ?, ?, ?, ?, ?)",
                (job_id, job_type, stock_code, company_name, upload_path, now, now),
            )
            conn.commit()
            return {"job_id": job_id, "status": "queued", "created_at": now}
        finally:
            conn.close()

    def get_job(self, job_id: str) -> Optional[dict]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM analyze_jobs WHERE id = ?", (job_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def update_job_status(self, job_id: str, status: str,
                          error: Optional[str] = None,
                          result_path: Optional[str] = None):
        now = datetime.now().isoformat()
        conn = self._connect()
        try:
            sets = ["status = ?", "updated_at = ?"]
            params = [status, now]
            if status == "running":
                sets.append("started_at = ?")
                params.append(now)
            if status in ("success", "failed"):
                sets.append("finished_at = ?")
                params.append(now)
            if error is not None:
                sets.append("error = ?")
                params.append(error)
            if result_path is not None:
                sets.append("result_path = ?")
                params.append(result_path)
            params.append(job_id)
            conn.execute(
                f"UPDATE analyze_jobs SET {', '.join(sets)} WHERE id = ?",
                params,
            )
            conn.commit()
        finally:
            conn.close()

    def list_jobs(self, limit: int = 50, offset: int = 0) -> list[dict]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM analyze_jobs ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def create_history(self, stock_code: str, result_path: str,
                       score: Optional[float] = None,
                       suggestion: Optional[str] = None,
                       company_name: str = "",
                       source: str = "upload") -> int:
        now = datetime.now().isoformat()
        conn = self._connect()
        try:
            cursor = conn.execute(
                "INSERT INTO ipo_history (stock_code, company_name, result_path, score, suggestion, source, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (stock_code, company_name, result_path, score, suggestion, source, now, now),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_history(self, stock_code: str) -> list[dict]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM ipo_history WHERE stock_code = ? ORDER BY created_at DESC",
                (stock_code,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def list_history(self, limit: int = 50, offset: int = 0) -> list[dict]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM ipo_history ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
```

- [ ] **Step 6: 验证 HistoryService 完整功能**

```bash
cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer
python -c "
import os, tempfile
db_path = os.path.join(tempfile.mkdtemp(), 'test_history.db')
from api.services.history_service import HistoryService
svc = HistoryService(db_path)
svc.init_db()

job = svc.create_job('upload', stock_code='09995', company_name='TestCo')
print(f'Created job: {job}')

svc.update_job_status(job['job_id'], 'running')
got = svc.get_job(job['job_id'])
print(f'Job status after running: {got[\"status\"]}, started_at: {got[\"started_at\"]}')

svc.update_job_status(job['job_id'], 'success', result_path='/tmp/result.json')
got = svc.get_job(job['job_id'])
print(f'Job status after success: {got[\"status\"]}, result_path: {got[\"result_path\"]}, finished_at: {got[\"finished_at\"]}')

hid = svc.create_history('09995', '/tmp/result.json', score=75.5, suggestion='申购', company_name='TestCo')
hist = svc.get_history('09995')
print(f'History: stock_code={hist[0][\"stock_code\"]}, score={hist[0][\"score\"]}, suggestion={hist[0][\"suggestion\"]}')

svc.update_job_status(job['job_id'], 'running')
svc.recover_stale_jobs()
got = svc.get_job(job['job_id'])
print(f'After recovery: status={got[\"status\"]}, error={got[\"error\"]}')

os.remove(db_path)
print('HistoryService OK')
"
```

预期输出:
```
Created job: {'job_id': '<uuid>', 'status': 'queued', 'created_at': '<iso>'}
Job status after running: running, started_at: <iso>
Job status after success: success, result_path: /tmp/result.json, finished_at: <iso>
History: stock_code=09995, score=75.5, suggestion=申购
After recovery: status=failed, error=Service restarted during analysis
HistoryService OK
```

- [ ] **Step 7: 提交 Commit 2**

```bash
cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer
git add api/services/storage_service.py api/services/history_service.py storage/.gitkeep storage/uploads/.gitkeep storage/results/.gitkeep storage/tmp/.gitkeep .gitignore
git commit -m "feat(api): add storage service and SQLite history service

- Add StorageService with upload save, result save/read, tmp cleanup
- Add HistoryService with full CRUD for analyze_jobs and ipo_history
- Add recover_stale_jobs() to mark orphaned running jobs as failed
- Add storage/ directory structure with .gitkeep files
- Update .gitignore for storage data files and frontend artifacts"
```

---

## Commit 3: Job Model + Worker

### Task 3.1: 创建 api/schemas/analyze.py

- [ ] **Step 1: 创建分析相关 schema**

创建文件 `api/schemas/analyze.py`:

```python
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
```

### Task 3.2: 创建 api/workers/analyze_worker.py

- [ ] **Step 2: 创建 AnalyzeWorker**

创建文件 `api/workers/analyze_worker.py`:

```python
import asyncio
import logging
import traceback

from api.config import get_config
from api.services.history_service import HistoryService
from api.services.storage_service import StorageService

logger = logging.getLogger(__name__)

_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        config = get_config()
        _semaphore = asyncio.Semaphore(config.max_concurrent_analyses)
    return _semaphore


def run_upload_analysis(job_id: str, upload_path: str,
                        stock_code: str | None, company_name: str | None):
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


def run_reanalyze(job_id: str, stock_code: str, company_name: str | None,
                  historical_market_data: dict | None):
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


def _call_analyze_uploaded_pdf(pdf_path: str, stock_code: str | None,
                                company_name: str | None) -> dict:
    from ipo_analyzer.core import analyze_uploaded_pdf
    return analyze_uploaded_pdf(pdf_path, stock_code=stock_code, company_name=company_name)


def _call_reanalyze_ipo(stock_code: str, company_name: str | None,
                         historical_market_data: dict | None,
                         output_dir: str) -> dict:
    from ipo_analyzer.core import reanalyze_ipo
    return reanalyze_ipo(
        stock_code=stock_code,
        company_name=company_name,
        historical_market_data=historical_market_data,
        output_dir=output_dir,
    )
```

### Task 3.3: 创建 api/routers/analyze.py

- [ ] **Step 3: 创建分析路由**

创建文件 `api/routers/analyze.py`:

```python
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile

from api.auth import require_api_token
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


@router.post("/upload", response_model=JobResponse, dependencies=[Depends(require_api_token)])
async def upload_and_analyze(
    background_tasks: BackgroundTasks,
    pdf: UploadFile = File(...),
    stock_code: str | None = Form(None),
    company_name: str | None = Form(None),
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


@router.post("/reanalyze", response_model=JobResponse, dependencies=[Depends(require_api_token)])
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
```

### Task 3.4: 注册 analyze 路由到 main.py

- [ ] **Step 4: 修改 api/main.py 添加 analyze 路由**

在 `api/main.py` 中添加 analyze 路由的导入和注册。修改后的完整文件：

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import get_config
from api.routers import health, analyze


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
app.include_router(analyze.router)
```

- [ ] **Step 5: 验证 API 可启动且路由已注册**

```bash
cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 &
sleep 3
curl -s http://localhost:8000/docs | head -5
curl -s http://localhost:8000/api/analyze/jobs/nonexistent | python -m json.tool
kill %1
```

预期: `/docs` 返回 HTML，`/jobs/nonexistent` 返回 `{"detail": "Job not found"}`。

- [ ] **Step 6: 提交 Commit 3**

```bash
cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer
git add api/schemas/analyze.py api/workers/analyze_worker.py api/routers/analyze.py api/main.py
git commit -m "feat(api): add analyze endpoints with async job model and worker

- Add POST /api/analyze/upload (multipart, returns job_id)
- Add POST /api/analyze/reanalyze (JSON body, returns job_id)
- Add GET /api/analyze/jobs/{job_id} (job status polling)
- Add GET /api/analyze/jobs/{job_id}/result (fetch result when success)
- Add AnalyzeWorker with asyncio.Semaphore concurrency control
- Worker calls ipo_analyzer.core directly in thread pool executor
- Job lifecycle: queued -> running -> success/failed
- Results saved to storage/results/ and ipo_history table"
```

---

## Commit 4: Auth

### Task 4.1: 创建 api/auth.py

- [ ] **Step 1: 创建 API Token 认证依赖**

创建文件 `api/auth.py`:

```python
import os

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer_scheme = HTTPBearer(auto_error=False)


async def require_api_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    expected_token = os.getenv("HKIPO_API_TOKEN")

    if not expected_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API token not configured. Set HKIPO_API_TOKEN environment variable.",
        )

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if credentials.credentials != expected_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return credentials.credentials
```

### Task 4.2: 创建 api/tests/test_auth.py

- [ ] **Step 2: 创建认证测试**

创建文件 `api/tests/test_auth.py`:

```python
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    os.environ.pop("HKIPO_API_TOKEN", None)
    from api.main import app
    return TestClient(app)


@pytest.fixture
def client_with_token():
    os.environ["HKIPO_API_TOKEN"] = "test-secret-token"
    from api.main import app
    client = TestClient(app)
    yield client
    os.environ.pop("HKIPO_API_TOKEN", None)


def test_no_token_configured_returns_503(client):
    response = client.post(
        "/api/analyze/reanalyze",
        json={"stock_code": "09995"},
    )
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"].lower()


def test_missing_token_returns_401(client_with_token):
    response = client_with_token.post(
        "/api/analyze/reanalyze",
        json={"stock_code": "09995"},
    )
    assert response.status_code == 401
    assert "missing" in response.json()["detail"].lower()


def test_invalid_token_returns_401(client_with_token):
    response = client_with_token.post(
        "/api/analyze/reanalyze",
        json={"stock_code": "09995"},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401
    assert "invalid" in response.json()["detail"].lower()


def test_valid_token_passes_auth(client_with_token):
    response = client_with_token.post(
        "/api/analyze/reanalyze",
        json={"stock_code": "09995"},
        headers={"Authorization": "Bearer test-secret-token"},
    )
    assert response.status_code != 401
    assert response.status_code != 503


def test_get_endpoints_do_not_require_auth(client_with_token):
    response = client_with_token.get("/api/health")
    assert response.status_code == 200
```

- [ ] **Step 3: 安装 pytest 并运行认证测试**

```bash
cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer
pip install pytest httpx
HKIPO_API_TOKEN="" python -m pytest api/tests/test_auth.py -v
```

预期输出:
```
test_no_token_configured_returns_503 PASSED
test_missing_token_returns_401 PASSED
test_invalid_token_returns_401 PASSED
test_valid_token_passes_auth PASSED
test_get_endpoints_do_not_require_auth PASSED
```

- [ ] **Step 4: 提交 Commit 4**

```bash
cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer
git add api/auth.py api/tests/test_auth.py
git commit -m "feat(api): add API token authentication for write endpoints

- Add require_api_token dependency using Bearer token scheme
- Return 503 if HKIPO_API_TOKEN env var not set
- Return 401 if token missing or invalid
- Apply auth to POST /api/analyze/upload and POST /api/analyze/reanalyze
- GET endpoints remain unauthenticated (internal network)
- Add auth tests covering all scenarios"
```

---

## Commit 5: Docker + Nginx

### Task 5.1: 创建 docker-compose.yml

- [ ] **Step 1: 创建 Docker Compose 配置**

创建文件 `docker-compose.yml`:

```yaml
version: "3.8"

services:
  fastapi:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - HKIPO_API_TOKEN=${HKIPO_API_TOKEN:-}
      - MAX_CONCURRENT_ANALYSES=${MAX_CONCURRENT_ANALYSES:-2}
      - STORAGE_BASE_PATH=/app/storage
      - API_HOST=0.0.0.0
      - API_PORT=8000
    volumes:
      - storage-data:/app/storage
    restart: unless-stopped

  nextjs:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://fastapi:8000
    depends_on:
      - fastapi
    restart: unless-stopped

  streamlit:
    build:
      context: .
      dockerfile: Dockerfile.streamlit
    ports:
      - "8501:8501"
    volumes:
      - storage-data:/app/storage
    restart: unless-stopped
    profiles:
      - transition

  nginx:
    image: nginx:1.27-alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - fastapi
      - nextjs
    restart: unless-stopped

volumes:
  storage-data:
```

### Task 5.2: 创建 Dockerfile (FastAPI)

- [ ] **Step 2: 创建 FastAPI Dockerfile**

创建文件 `Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ipo_analyzer/ ./ipo_analyzer/
COPY api/ ./api/
COPY storage/ ./storage/

RUN mkdir -p storage/uploads storage/results storage/tmp

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Task 5.3: 创建 Dockerfile.streamlit

- [ ] **Step 3: 创建 Streamlit Dockerfile（过渡期）**

创建文件 `Dockerfile.streamlit`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN playwright install chromium || true

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

### Task 5.4: 创建 nginx.conf

- [ ] **Step 4: 创建 Nginx 反向代理配置**

创建文件 `nginx.conf`:

```nginx
events {
    worker_connections 1024;
}

http {
    upstream nextjs {
        server nextjs:3000;
    }

    upstream fastapi {
        server fastapi:8000;
    }

    upstream streamlit {
        server streamlit:8501;
    }

    server {
        listen 80;
        server_name _;

        client_max_body_size 100M;

        location /api/ {
            proxy_pass http://fastapi;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;

            proxy_read_timeout 300s;
            proxy_send_timeout 300s;
        }

        location /docs {
            proxy_pass http://fastapi;
            proxy_set_header Host $host;
        }

        location /openapi.json {
            proxy_pass http://fastapi;
            proxy_set_header Host $host;
        }

        location /admin/ {
            proxy_pass http://streamlit/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;

            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_read_timeout 86400;
        }

        location / {
            proxy_pass http://nextjs;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
}
```

- [ ] **Step 5: 验证 nginx.conf 语法**

```bash
docker run --rm -v /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer/nginx.conf:/etc/nginx/nginx.conf:ro nginx:1.27-alpine nginx -t
```

预期输出:
```
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

- [ ] **Step 6: 提交 Commit 5**

```bash
cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer
git add docker-compose.yml Dockerfile Dockerfile.streamlit nginx.conf
git commit -m "feat(infra): add Docker Compose, Dockerfiles, and Nginx config

- Add docker-compose.yml with fastapi, nextjs, streamlit, nginx services
- Streamlit service uses profiles for optional transition period
- Add FastAPI Dockerfile (python:3.12-slim, uvicorn entrypoint)
- Add Streamlit Dockerfile for transition period
- Add nginx.conf with reverse proxy: / -> nextjs, /api -> fastapi, /admin -> streamlit
- Support file uploads up to 100MB, 300s read timeout for analysis"
```

---

## Commit 6: Frontend Skeleton

### Task 6.1: 初始化 Next.js 项目

- [ ] **Step 1: 创建 Next.js 应用**

```bash
cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer
npx create-next-app@latest frontend --typescript --tailwind --eslint --app --src-dir --import-alias "@/*" --use-npm
```

预期输出: 大量 npm install 日志，最后显示 `✓ Ready on http://localhost:3000`

- [ ] **Step 2: 验证 Next.js 项目创建成功**

```bash
ls /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer/frontend/package.json
cat /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer/frontend/package.json | python -m json.tool | head -10
```

预期输出: package.json 存在，包含 `next`, `react`, `typescript` 等依赖。

### Task 6.2: 初始化 shadcn/ui

- [ ] **Step 3: 初始化 shadcn/ui**

```bash
cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer/frontend
npx shadcn@latest init -d --base-color neutral --css-variables
```

预期输出: `components.json` 创建成功。

- [ ] **Step 4: 验证 shadcn/ui 配置**

```bash
cat /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer/frontend/components.json
```

预期输出: 包含 `style`, `tailwind`, `aliases` 等配置的 JSON。

### Task 6.3: 配置赛博朋克暗黑终端 CSS 变量

- [ ] **Step 5: 修改 frontend/src/app/globals.css**

覆盖 `frontend/src/app/globals.css`，将 Streamlit style.css 中的 CSS 变量迁移为 Tailwind CSS 变量格式：

```css
@import "tailwindcss";

@theme inline {
  --color-bg-primary: #05070d;
  --color-bg-secondary: #070b12;
  --color-bg-tertiary: #0b1020;
  --color-bg-card: rgba(11, 16, 32, 0.85);
  --color-bg-card-hover: rgba(15, 22, 42, 0.9);
  --color-bg-glass: rgba(0, 255, 255, 0.03);
  --color-bg-glass-hover: rgba(0, 255, 255, 0.06);

  --color-text-primary: #e2e8f0;
  --color-text-secondary: #94a3b8;
  --color-text-tertiary: #64748b;
  --color-text-emphasis: #f1f5f9;
  --color-text-dim: #475569;

  --color-accent-cyan: #00e5ff;
  --color-accent-cyan-dim: rgba(0, 229, 255, 0.08);
  --color-accent-cyan-glow: rgba(0, 229, 255, 0.15);
  --color-accent-blue: #3b82f6;
  --color-accent-emerald: #10b981;
  --color-accent-amber: #f59e0b;
  --color-accent-rose: #f43f5e;
  --color-accent-violet: #8b5cf6;

  --color-score-excellent: #10b981;
  --color-score-good: #22d3ee;
  --color-score-medium: #f59e0b;
  --color-score-poor: #f43f5e;

  --color-border-subtle: rgba(255, 255, 255, 0.08);
  --color-border-glow: rgba(0, 255, 255, 0.12);
  --color-border-glow-strong: rgba(0, 255, 255, 0.25);

  --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans SC', sans-serif;
  --font-mono: 'SF Mono', 'Cascadia Code', 'Fira Code', 'JetBrains Mono', 'Noto Sans SC', monospace;

  --radius-sm: 4px;
  --radius-md: 6px;
  --radius-lg: 8px;
}

body {
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
  font-family: var(--font-sans);
}
```

### Task 6.4: 创建 API 客户端

- [ ] **Step 6: 创建 frontend/src/lib/api.ts**

创建文件 `frontend/src/lib/api.ts`:

```typescript
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ApiResponse<T> {
  data: T | null;
  error: string | null;
}

export async function apiGet<T>(path: string): Promise<ApiResponse<T>> {
  try {
    const res = await fetch(`${API_BASE_URL}${path}`);
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      return { data: null, error: body.detail || res.statusText };
    }
    const data: T = await res.json();
    return { data, error: null };
  } catch (err) {
    return { data: null, error: err instanceof Error ? err.message : "Network error" };
  }
}

export async function apiPost<T>(
  path: string,
  body: FormData | Record<string, unknown>,
  token?: string,
): Promise<ApiResponse<T>> {
  try {
    const headers: Record<string, string> = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    const isFormData = body instanceof FormData;
    const res = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: isFormData ? headers : { ...headers, "Content-Type": "application/json" },
      body: isFormData ? body : JSON.stringify(body),
    });
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({ detail: res.statusText }));
      return { data: null, error: errBody.detail || res.statusText };
    }
    const data: T = await res.json();
    return { data, error: null };
  } catch (err) {
    return { data: null, error: err instanceof Error ? err.message : "Network error" };
  }
}

export interface HealthResponse {
  status: string;
  db_status: string;
  worker_status: string;
  uptime_seconds: number;
}

export interface VersionResponse {
  app_version: string;
  python_version: string;
  ipo_analyzer_version: string;
}

export interface JobResponse {
  job_id: string;
  status: string;
  created_at: string;
}
```

### Task 6.5: 创建首页

- [ ] **Step 7: 修改 frontend/src/app/page.tsx**

覆盖 `frontend/src/app/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import {
  apiGet,
  HealthResponse,
  VersionResponse,
} from "@/lib/api";

export default function HomePage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [version, setVersion] = useState<VersionResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [versionError, setVersionError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<HealthResponse>("/api/health").then(({ data, error }) => {
      if (data) setHealth(data);
      if (error) setHealthError(error);
    });
    apiGet<VersionResponse>("/api/version").then(({ data, error }) => {
      if (data) setVersion(data);
      if (error) setVersionError(error);
    });
  }, []);

  return (
    <div className="min-h-screen bg-bg-primary text-text-primary font-sans">
      <header className="border-b border-border-subtle px-6 py-4">
        <h1 className="text-2xl font-mono text-accent-cyan">
          HK IPO Analyzer
        </h1>
        <p className="text-text-secondary text-sm mt-1">
          港股打新分析系统
        </p>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-8 space-y-6">
        <section className="bg-bg-card border border-border-subtle rounded-radius-lg p-6">
          <h2 className="text-lg font-mono text-accent-cyan mb-4">
            System Status
          </h2>
          {healthError && (
            <p className="text-accent-rose">Health check failed: {healthError}</p>
          )}
          {health && (
            <div className="grid grid-cols-2 gap-4 text-sm font-mono">
              <div>
                <span className="text-text-tertiary">Status:</span>{" "}
                <span className="text-accent-emerald">{health.status}</span>
              </div>
              <div>
                <span className="text-text-tertiary">DB:</span>{" "}
                <span className={health.db_status === "ok" ? "text-accent-emerald" : "text-accent-rose"}>
                  {health.db_status}
                </span>
              </div>
              <div>
                <span className="text-text-tertiary">Worker:</span>{" "}
                <span className="text-accent-amber">{health.worker_status}</span>
              </div>
              <div>
                <span className="text-text-tertiary">Uptime:</span>{" "}
                <span className="text-text-primary">{health.uptime_seconds}s</span>
              </div>
            </div>
          )}
        </section>

        <section className="bg-bg-card border border-border-subtle rounded-radius-lg p-6">
          <h2 className="text-lg font-mono text-accent-cyan mb-4">
            Version Info
          </h2>
          {versionError && (
            <p className="text-accent-rose">Version check failed: {versionError}</p>
          )}
          {version && (
            <div className="grid grid-cols-1 gap-2 text-sm font-mono">
              <div>
                <span className="text-text-tertiary">App:</span>{" "}
                <span className="text-text-primary">{version.app_version}</span>
              </div>
              <div>
                <span className="text-text-tertiary">Python:</span>{" "}
                <span className="text-text-primary">{version.python_version}</span>
              </div>
              <div>
                <span className="text-text-tertiary">IPO Analyzer:</span>{" "}
                <span className="text-text-primary">{version.ipo_analyzer_version}</span>
              </div>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
```

### Task 6.6: 创建 Frontend Dockerfile

- [ ] **Step 8: 创建 frontend/Dockerfile**

创建文件 `frontend/Dockerfile`:

```dockerfile
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000

CMD ["node", "server.js"]
```

### Task 6.7: 验证前端构建

- [ ] **Step 9: 运行 npm run build**

```bash
cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer/frontend
npm run build
```

预期输出:
```
  ▲ Next.js 15.x.x
  ...
  ✓ Compiled successfully
  ✓ Linting and checking validity of types
  ✓ Collecting page data
  ✓ Generating static pages (1/1)
  ✓ Finalizing page optimization
```

- [ ] **Step 10: 提交 Commit 6**

```bash
cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer
git add frontend/
git commit -m "feat(frontend): initialize Next.js with shadcn/ui and cyberpunk theme

- Initialize Next.js 15 with TypeScript, Tailwind CSS, ESLint, App Router
- Initialize shadcn/ui with dark theme
- Configure cyberpunk terminal CSS variables from style.css design system
- Create minimal home page that fetches /api/health and /api/version
- Create API client with fetch wrapper (apiGet, apiPost)
- Add Frontend Dockerfile with standalone output mode
- npm run build passes successfully"
```

---

## Commit 7: E2E Smoke Test

### Task 7.1: 创建 api/tests/conftest.py

- [ ] **Step 1: 创建 pytest fixtures**

创建文件 `api/tests/conftest.py`:

```python
import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _set_test_env(monkeypatch):
    monkeypatch.setenv("HKIPO_API_TOKEN", "test-token")
    monkeypatch.setenv("STORAGE_BASE_PATH", tempfile.mkdtemp())


@pytest.fixture
def client():
    from api.main import app
    return TestClient(app)


@pytest.fixture
def api_token():
    return "test-token"


@pytest.fixture
def auth_headers(api_token):
    return {"Authorization": f"Bearer {api_token}"}
```

### Task 7.2: 创建 api/tests/test_health.py

- [ ] **Step 2: 创建 health 接口测试**

创建文件 `api/tests/test_health.py`:

```python
from api.tests.conftest import *


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["db_status"] == "ok"
    assert data["worker_status"] == "idle"
    assert "uptime_seconds" in data
    assert isinstance(data["uptime_seconds"], (int, float))


def test_version_endpoint(client):
    response = client.get("/api/version")
    assert response.status_code == 200
    data = response.json()
    assert "app_version" in data
    assert "python_version" in data
    assert "ipo_analyzer_version" in data
    assert data["app_version"] == "0.1.0"
    assert data["ipo_analyzer_version"] == "0.5.0-alpha"
```

### Task 7.3: 创建 api/tests/test_analyze.py

- [ ] **Step 3: 创建分析接口测试**

创建文件 `api/tests/test_analyze.py`:

```python
import io

from api.tests.conftest import *


def _make_pdf_bytes() -> bytes:
    minimal_pdf = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [] /Count 0 >>
endobj
xref
0 3
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
trailer
<< /Size 3 /Root 1 0 R >>
startxref
109
%%EOF"""
    return minimal_pdf


def test_upload_returns_job_id(client, auth_headers):
    pdf_bytes = _make_pdf_bytes()
    response = client.post(
        "/api/analyze/upload",
        files={"pdf": ("test.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        data={"stock_code": "09995", "company_name": "TestCo"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "queued"
    assert "created_at" in data


def test_upload_rejects_non_pdf(client, auth_headers):
    response = client.post(
        "/api/analyze/upload",
        files={"pdf": ("test.txt", io.BytesIO(b"hello"), "text/plain")},
        headers=auth_headers,
    )
    assert response.status_code == 400


def test_upload_rejects_empty_file(client, auth_headers):
    response = client.post(
        "/api/analyze/upload",
        files={"pdf": ("test.pdf", io.BytesIO(b""), "application/pdf")},
        headers=auth_headers,
    )
    assert response.status_code == 400


def test_reanalyze_returns_job_id(client, auth_headers):
    response = client.post(
        "/api/analyze/reanalyze",
        json={"stock_code": "09995", "company_name": "TestCo"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "queued"


def test_get_job_status_not_found(client):
    response = client.get("/api/analyze/jobs/nonexistent-id")
    assert response.status_code == 404


def test_get_job_status_after_upload(client, auth_headers):
    pdf_bytes = _make_pdf_bytes()
    upload_resp = client.post(
        "/api/analyze/upload",
        files={"pdf": ("test.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        data={"stock_code": "09995"},
        headers=auth_headers,
    )
    job_id = upload_resp.json()["job_id"]

    status_resp = client.get(f"/api/analyze/jobs/{job_id}")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["job_id"] == job_id
    assert data["status"] in ("queued", "running", "success", "failed")
    assert data["stock_code"] == "09995"


def test_get_job_result_not_success(client, auth_headers):
    pdf_bytes = _make_pdf_bytes()
    upload_resp = client.post(
        "/api/analyze/upload",
        files={"pdf": ("test.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        data={"stock_code": "09995"},
        headers=auth_headers,
    )
    job_id = upload_resp.json()["job_id"]

    result_resp = client.get(f"/api/analyze/jobs/{job_id}/result")
    assert result_resp.status_code in (404, 409)


def test_upload_requires_auth(client):
    pdf_bytes = _make_pdf_bytes()
    response = client.post(
        "/api/analyze/upload",
        files={"pdf": ("test.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        data={"stock_code": "09995"},
    )
    assert response.status_code == 401


def test_reanalyze_requires_auth(client):
    response = client.post(
        "/api/analyze/reanalyze",
        json={"stock_code": "09995"},
    )
    assert response.status_code == 401
```

### Task 7.4: 运行全部测试

- [ ] **Step 4: 运行 pytest**

```bash
cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer
pip install pytest httpx
HKIPO_API_TOKEN=test-token python -m pytest api/tests/ -v
```

预期输出:
```
api/tests/test_health.py::test_health_endpoint PASSED
api/tests/test_health.py::test_version_endpoint PASSED
api/tests/test_analyze.py::test_upload_returns_job_id PASSED
api/tests/test_analyze.py::test_upload_rejects_non_pdf PASSED
api/tests/test_analyze.py::test_upload_rejects_empty_file PASSED
api/tests/test_analyze.py::test_reanalyze_returns_job_id PASSED
api/tests/test_analyze.py::test_get_job_status_not_found PASSED
api/tests/test_analyze.py::test_get_job_status_after_upload PASSED
api/tests/test_analyze.py::test_get_job_result_not_success PASSED
api/tests/test_analyze.py::test_upload_requires_auth PASSED
api/tests/test_analyze.py::test_reanalyze_requires_auth PASSED
api/tests/test_auth.py::test_no_token_configured_returns_503 PASSED
api/tests/test_auth.py::test_missing_token_returns_401 PASSED
api/tests/test_auth.py::test_invalid_token_returns_401 PASSED
api/tests/test_auth.py::test_valid_token_passes_auth PASSED
api/tests/test_auth.py::test_get_endpoints_do_not_require_auth PASSED
```

### Task 7.5: 验证存储文件

- [ ] **Step 5: 验证 storage 目录结构**

```bash
cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer
ls -la storage/
ls -la storage/uploads/ 2>/dev/null || echo "uploads dir empty or not found"
ls -la storage/results/ 2>/dev/null || echo "results dir empty or not found"
ls -la storage/history.db 2>/dev/null || echo "history.db not found"
```

预期: `storage/` 目录存在，包含 `uploads/`, `results/`, `tmp/`, `history.db`。

### Task 7.6: 验证前端构建

- [ ] **Step 6: 运行前端构建**

```bash
cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer/frontend
npm run build
```

预期输出: `✓ Compiled successfully`

### Task 7.7: 端到端手动验证

- [ ] **Step 7: 启动 API 并手动验证完整链路**

```bash
cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer
export HKIPO_API_TOKEN="test-token"
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 &
sleep 3

echo "=== 1. Health Check ==="
curl -s http://localhost:8000/api/health | python -m json.tool

echo "=== 2. Version Check ==="
curl -s http://localhost:8000/api/version | python -m json.tool

echo "=== 3. Upload PDF (should fail auth without token) ==="
curl -s -X POST http://localhost:8000/api/analyze/upload \
  -F "pdf=@/dev/null;filename=test.pdf" | python -m json.tool

echo "=== 4. Reanalyze (with auth) ==="
curl -s -X POST http://localhost:8000/api/analyze/reanalyze \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d '{"stock_code":"09995","company_name":"TestCo"}' | python -m json.tool

kill %1
```

预期:
1. Health 返回 `{"status": "ok", "db_status": "ok", ...}`
2. Version 返回 `{"app_version": "0.1.0", "ipo_analyzer_version": "0.5.0-alpha", ...}`
3. Upload 无 token 返回 401
4. Reanalyze 返回 `{"job_id": "...", "status": "queued", ...}`

- [ ] **Step 8: 提交 Commit 7**

```bash
cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer
git add api/tests/conftest.py api/tests/test_health.py api/tests/test_analyze.py api/tests/test_auth.py
git commit -m "test(api): add E2E smoke tests for health, analyze, and auth

- Add pytest conftest with test client, auth headers fixtures
- Add test_health.py: health and version endpoint tests
- Add test_analyze.py: upload, reanalyze, job status, result, auth tests
- Add test_auth.py: token validation, missing/invalid token, no config
- All 16 tests pass
- Frontend npm run build passes"
```

---

## 验收清单

- [ ] `pip install -r requirements.txt` 成功
- [ ] `python -m uvicorn api.main:app` 启动无报错
- [ ] `GET /api/health` 返回 `{"status": "ok", "db_status": "ok", ...}`
- [ ] `GET /api/version` 返回 `{"app_version": "0.1.0", "ipo_analyzer_version": "0.5.0-alpha", ...}`
- [ ] `POST /api/analyze/upload` 无 token 返回 401，有 token 返回 job_id
- [ ] `POST /api/analyze/reanalyze` 无 token 返回 401，有 token 返回 job_id
- [ ] `GET /api/analyze/jobs/{job_id}` 返回任务状态
- [ ] `GET /api/analyze/jobs/{job_id}/result` 成功任务返回结果，非成功任务返回 409
- [ ] `storage/uploads/` 有上传的 PDF 文件
- [ ] `storage/results/` 有分析结果 JSON 文件
- [ ] `storage/history.db` 有 analyze_jobs 和 ipo_history 记录
- [ ] `HKIPO_API_TOKEN` 未设置时 POST 返回 503
- [ ] `pytest api/tests/ -v` 全部通过
- [ ] `cd frontend && npm run build` 通过
- [ ] `docker-compose config` 验证通过
- [ ] `ipo_analyzer/` 目录零修改
