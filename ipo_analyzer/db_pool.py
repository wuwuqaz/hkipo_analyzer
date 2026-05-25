"""SQLite 连接池 — 复用数据库连接，避免频繁创建/关闭。"""

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path


class SQLiteConnectionPool:
    """线程安全的 SQLite 连接池。

    每个线程持有一个独立连接（SQLite 连接不能跨线程共享）。
    使用 thread-local storage 实现线程安全。
    """

    def __init__(self, db_path: str, max_connections: int = 10):
        self.db_path = db_path
        self.max_connections = max_connections
        self._local = threading.local()
        self._lock = threading.Lock()
        self._connection_count = 0
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    def _create_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA cache_size=-8000")
        conn.execute("PRAGMA temp_store=MEMORY")
        return conn

    def get_connection(self) -> sqlite3.Connection:
        """获取当前线程的连接。"""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            with self._lock:
                if self._connection_count >= self.max_connections:
                    raise RuntimeError(f"连接池已满（最大 {self.max_connections} 个连接）")
                self._local.connection = self._create_connection()
                self._connection_count += 1
        return self._local.connection

    def close(self):
        """关闭当前线程的连接。"""
        if hasattr(self._local, 'connection') and self._local.connection is not None:
            try:
                self._local.connection.close()
            except Exception:
                pass
            with self._lock:
                self._connection_count = max(0, self._connection_count - 1)
            self._local.connection = None

    def close_all(self):
        """关闭所有连接（仅在主线程调用）。"""
        self._lock.acquire()
        try:
            self._connection_count = 0
        finally:
            self._lock.release()
        if hasattr(self._local, 'connection') and self._local.connection is not None:
            try:
                self._local.connection.close()
            except Exception:
                pass
            self._local.connection = None

    @contextmanager
    def transaction(self):
        """事务上下文管理器。"""
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
