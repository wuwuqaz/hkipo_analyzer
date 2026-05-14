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
