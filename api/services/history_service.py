import uuid
from datetime import datetime
from functools import lru_cache
from typing import Optional

from ipo_analyzer.db_pool import SQLiteConnectionPool


@lru_cache(maxsize=16)
def _get_shared_pool(db_path: str) -> SQLiteConnectionPool:
    return SQLiteConnectionPool(db_path, max_connections=256)


class HistoryService:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._pool: Optional[SQLiteConnectionPool] = None

    def _get_pool(self) -> SQLiteConnectionPool:
        if self._pool is None:
            self._pool = _get_shared_pool(self.db_path)
        return self._pool

    def init_db(self):
        pool = self._get_pool()
        conn = pool.get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS analyze_jobs (
                id TEXT PRIMARY KEY,
                job_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                stock_code TEXT,
                company_name TEXT NOT NULL DEFAULT '',
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

    def recover_stale_jobs(self):
        pool = self._get_pool()
        now = datetime.now().isoformat()
        with pool.transaction() as conn:
            conn.execute(
                "UPDATE analyze_jobs SET status = 'failed', error = 'Service restarted during analysis', updated_at = ? WHERE status = 'running'",
                (now,),
            )
            conn.execute(
                "UPDATE analyze_jobs SET status = 'failed', error = 'Service restarted before job started', updated_at = ? WHERE status = 'queued' AND datetime(created_at, '+30 minutes') < datetime('now')",
                (now,),
            )

    def create_job(self, job_type: str, stock_code: Optional[str] = None,
                   company_name: Optional[str] = None,
                   upload_path: Optional[str] = None) -> dict:
        job_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        pool = self._get_pool()
        with pool.transaction() as conn:
            conn.execute(
                "INSERT INTO analyze_jobs (id, job_type, status, stock_code, company_name, upload_path, created_at, updated_at) VALUES (?, ?, 'queued', ?, ?, ?, ?, ?)",
                (job_id, job_type, stock_code, company_name or '', upload_path, now, now),
            )
        return {"job_id": job_id, "status": "queued", "created_at": now}

    def get_job(self, job_id: str) -> Optional[dict]:
        pool = self._get_pool()
        conn = pool.get_connection()
        row = conn.execute("SELECT * FROM analyze_jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def update_job_status(self, job_id: str, status: str,
                          error: Optional[str] = None,
                          result_path: Optional[str] = None):
        now = datetime.now().isoformat()
        pool = self._get_pool()
        with pool.transaction() as conn:
            conn.execute(
                "UPDATE analyze_jobs SET status = ?, updated_at = ?, started_at = COALESCE(?, started_at), finished_at = COALESCE(?, finished_at), error = COALESCE(?, error), result_path = COALESCE(?, result_path) WHERE id = ?",
                [
                    status, now,
                    now if status == "running" else None,
                    now if status in ("success", "failed") else None,
                    error, result_path, job_id,
                ],
            )

    def count_jobs(self) -> int:
        pool = self._get_pool()
        conn = pool.get_connection()
        row = conn.execute("SELECT COUNT(*) as cnt FROM analyze_jobs").fetchone()
        return row["cnt"] if row else 0

    def list_jobs(self, limit: int = 50, offset: int = 0) -> list[dict]:
        pool = self._get_pool()
        conn = pool.get_connection()
        rows = conn.execute(
            "SELECT * FROM analyze_jobs ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]

    def create_history(self, stock_code: str, result_path: str,
                       score: Optional[float] = None,
                       suggestion: Optional[str] = None,
                       company_name: str = "",
                       source: str = "upload") -> int:
        now = datetime.now().isoformat()
        pool = self._get_pool()
        with pool.transaction() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO ipo_history (stock_code, company_name, result_path, score, suggestion, source, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (stock_code, company_name, result_path, score, suggestion, source, now, now),
            )
            conn.commit()
            return cursor.lastrowid

    def get_history(self, stock_code: str) -> list[dict]:
        pool = self._get_pool()
        conn = pool.get_connection()
        rows = conn.execute(
            "SELECT * FROM ipo_history WHERE stock_code = ? ORDER BY created_at DESC",
            (stock_code,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_history(self, limit: int = 50, offset: int = 0) -> list[dict]:
        pool = self._get_pool()
        conn = pool.get_connection()
        rows = conn.execute(
            "SELECT * FROM ipo_history ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]
