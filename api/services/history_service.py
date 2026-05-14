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
