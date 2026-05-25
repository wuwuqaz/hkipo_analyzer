import sqlite3

from fastapi import Depends

from api.config import APIConfig, get_config as _get_config
from ipo_analyzer.blogger_monitor.db import BloggerMonitorDB


def get_config() -> APIConfig:
    return _get_config()


def get_db() -> sqlite3.Connection:
    config = get_config()
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(config.db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


def get_blogger_db(config: APIConfig = Depends(get_config)):
    db_path = str(config.storage_base_path / "blogger_monitor.db")
    db = BloggerMonitorDB(db_path=db_path)
    try:
        yield db
    finally:
        db.close()
