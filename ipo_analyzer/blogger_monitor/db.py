from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Optional


_CREATE_POSTS_TABLE = """
CREATE TABLE IF NOT EXISTS blogger_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT NOT NULL,
    keyword TEXT NOT NULL,
    search_source TEXT NOT NULL DEFAULT 'tavily',
    search_rank INTEGER,
    url TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    domain TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    published_at TEXT,
    raw_content TEXT NOT NULL DEFAULT '',
    content_length INTEGER NOT NULL DEFAULT 0,
    fetch_status TEXT NOT NULL DEFAULT 'pending',
    relevance_score REAL DEFAULT 0.0,
    fetched_at TEXT NOT NULL,
    UNIQUE(stock_code, canonical_url, content_hash)
);
"""

_CREATE_ANALYSIS_TABLE = """
CREATE TABLE IF NOT EXISTS blogger_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    stock_code TEXT NOT NULL,
    company_name TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT '',
    author_type TEXT NOT NULL DEFAULT 'blogger',
    title TEXT NOT NULL DEFAULT '',
    published_at TEXT,
    stance TEXT NOT NULL DEFAULT 'neutral',
    stance_score INTEGER NOT NULL DEFAULT 50,
    apply_suggestion TEXT NOT NULL DEFAULT '',
    suggested_capital_ratio TEXT NOT NULL DEFAULT '',
    main_reasons TEXT NOT NULL DEFAULT '[]',
    risk_points TEXT NOT NULL DEFAULT '[]',
    valuation_comment TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    confidence_score INTEGER NOT NULL DEFAULT 50,
    evidence_quotes TEXT NOT NULL DEFAULT '[]',
    is_actionable INTEGER NOT NULL DEFAULT 0,
    analysis_status TEXT NOT NULL DEFAULT 'pending',
    analyzed_at TEXT NOT NULL,
    FOREIGN KEY (post_id) REFERENCES blogger_posts(id)
);
"""

_CREATE_CONSENSUS_TABLE = """
CREATE TABLE IF NOT EXISTS ipo_blogger_consensus (
    stock_code TEXT PRIMARY KEY,
    total_posts INTEGER NOT NULL DEFAULT 0,
    positive_count INTEGER NOT NULL DEFAULT 0,
    neutral_count INTEGER NOT NULL DEFAULT 0,
    negative_count INTEGER NOT NULL DEFAULT 0,
    consensus_score REAL NOT NULL DEFAULT 0.0,
    top_reasons TEXT NOT NULL DEFAULT '[]',
    top_risks TEXT NOT NULL DEFAULT '[]',
    representative_posts TEXT NOT NULL DEFAULT '[]',
    coverage_score REAL NOT NULL DEFAULT 0.0,
    last_crawled_at TEXT,
    data_quality_warning TEXT NOT NULL DEFAULT '',
    failed_posts_count INTEGER NOT NULL DEFAULT 0,
    skipped_posts_count INTEGER NOT NULL DEFAULT 0,
    last_error_message TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);
"""

_POSTS_JSON_FIELDS = frozenset()
_ANALYSIS_JSON_FIELDS = frozenset({"main_reasons", "risk_points", "evidence_quotes"})
_CONSENSUS_JSON_FIELDS = frozenset({"top_reasons", "top_risks", "representative_posts"})

_POST_COLUMNS = [
    "stock_code",
    "keyword",
    "search_source",
    "search_rank",
    "url",
    "canonical_url",
    "domain",
    "content_hash",
    "title",
    "author",
    "source",
    "published_at",
    "raw_content",
    "content_length",
    "fetch_status",
    "relevance_score",
    "fetched_at",
]

_ANALYSIS_COLUMNS = [
    "post_id",
    "stock_code",
    "company_name",
    "source",
    "author",
    "author_type",
    "title",
    "published_at",
    "stance",
    "stance_score",
    "apply_suggestion",
    "suggested_capital_ratio",
    "main_reasons",
    "risk_points",
    "valuation_comment",
    "summary",
    "confidence_score",
    "evidence_quotes",
    "is_actionable",
    "analysis_status",
    "analyzed_at",
]

_CONSENSUS_COLUMNS = [
    "stock_code",
    "total_posts",
    "positive_count",
    "neutral_count",
    "negative_count",
    "consensus_score",
    "top_reasons",
    "top_risks",
    "representative_posts",
    "coverage_score",
    "last_crawled_at",
    "data_quality_warning",
    "failed_posts_count",
    "skipped_posts_count",
    "last_error_message",
    "updated_at",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize_json_fields(data: dict, json_fields: frozenset[str]) -> dict:
    result = dict(data)
    for field in json_fields:
        if field in result and isinstance(result[field], (list, dict)):
            result[field] = json.dumps(result[field], ensure_ascii=False)
    return result


def _deserialize_json_fields(data: dict, json_fields: frozenset[str]) -> dict:
    result = dict(data)
    for field in json_fields:
        if field in result and isinstance(result[field], str):
            try:
                result[field] = json.loads(result[field])
            except (json.JSONDecodeError, TypeError):
                result[field] = []
    return result


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


class BloggerMonitorDB:
    def __init__(self, db_path: str = "temp/blogger_monitor.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    @contextmanager
    def get_cursor(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()

    def _init_db(self):
        with self.get_cursor() as cursor:
            cursor.execute(_CREATE_POSTS_TABLE)
            cursor.execute(_CREATE_ANALYSIS_TABLE)
            cursor.execute(_CREATE_CONSENSUS_TABLE)

    def insert_post(self, post: dict) -> Optional[int]:
        data = _serialize_json_fields(post, _POSTS_JSON_FIELDS)
        if "fetched_at" not in data or not data["fetched_at"]:
            data["fetched_at"] = _now_iso()
        columns = [c for c in _POST_COLUMNS if c in data]
        placeholders = ", ".join(["?"] * len(columns))
        col_str = ", ".join(columns)
        values = [data[c] for c in columns]
        with self.get_cursor() as cursor:
            try:
                cursor.execute(
                    f"INSERT OR IGNORE INTO blogger_posts ({col_str}) VALUES ({placeholders})",
                    values,
                )
                if cursor.rowcount == 0:
                    return None
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                return None

    def insert_analysis(self, analysis: dict) -> int:
        data = _serialize_json_fields(analysis, _ANALYSIS_JSON_FIELDS)
        if "analyzed_at" not in data or not data["analyzed_at"]:
            data["analyzed_at"] = _now_iso()
        if "is_actionable" in data and isinstance(data["is_actionable"], bool):
            data["is_actionable"] = int(data["is_actionable"])
        columns = [c for c in _ANALYSIS_COLUMNS if c in data]
        placeholders = ", ".join(["?"] * len(columns))
        col_str = ", ".join(columns)
        values = [data[c] for c in columns]
        with self.get_cursor() as cursor:
            cursor.execute(
                f"INSERT INTO blogger_analysis ({col_str}) VALUES ({placeholders})",
                values,
            )
            return cursor.lastrowid

    def upsert_consensus(self, consensus: dict) -> None:
        data = _serialize_json_fields(consensus, _CONSENSUS_JSON_FIELDS)
        if "updated_at" not in data or not data["updated_at"]:
            data["updated_at"] = _now_iso()
        columns = [c for c in _CONSENSUS_COLUMNS if c in data]
        col_str = ", ".join(columns)
        placeholders = ", ".join(["?"] * len(columns))
        values = [data[c] for c in columns]
        update_sets = ", ".join(f"{c} = excluded.{c}" for c in columns if c != "stock_code")
        with self.get_cursor() as cursor:
            cursor.execute(
                f"INSERT INTO ipo_blogger_consensus ({col_str}) VALUES ({placeholders}) "
                f"ON CONFLICT(stock_code) DO UPDATE SET {update_sets}",
                values,
            )

    def get_consensus(self, stock_code: str) -> Optional[dict]:
        with self.get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM ipo_blogger_consensus WHERE stock_code = ?",
                (stock_code,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return _deserialize_json_fields(_row_to_dict(row), _CONSENSUS_JSON_FIELDS)

    def get_posts_by_stock(self, stock_code: str) -> list[dict]:
        with self.get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM blogger_posts WHERE stock_code = ? ORDER BY fetched_at DESC",
                (stock_code,),
            )
            rows = cursor.fetchall()
            return [_row_to_dict(r) for r in rows]

    def get_analyses_by_stock(self, stock_code: str) -> list[dict]:
        with self.get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM blogger_analysis WHERE stock_code = ? ORDER BY analyzed_at DESC",
                (stock_code,),
            )
            rows = cursor.fetchall()
            return [_deserialize_json_fields(_row_to_dict(r), _ANALYSIS_JSON_FIELDS) for r in rows]

    def post_exists(self, stock_code: str, canonical_url: str, content_hash: str) -> bool:
        with self.get_cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM blogger_posts WHERE stock_code = ? AND canonical_url = ? AND content_hash = ?",
                (stock_code, canonical_url, content_hash),
            )
            return cursor.fetchone() is not None

    def get_pending_posts(self, stock_code: str) -> list[dict]:
        with self.get_cursor() as cursor:
            cursor.execute(
                "SELECT p.* FROM blogger_posts p "
                "LEFT JOIN blogger_analysis a ON p.id = a.post_id "
                "WHERE p.stock_code = ? AND p.fetch_status = 'fetched' AND a.id IS NULL "
                "ORDER BY p.relevance_score DESC",
                (stock_code,),
            )
            rows = cursor.fetchall()
            return [_row_to_dict(r) for r in rows]

    def update_post_relevance(self, post_id: int, relevance_score: float) -> None:
        with self.get_cursor() as cursor:
            cursor.execute(
                "UPDATE blogger_posts SET relevance_score = ? WHERE id = ?",
                (relevance_score, post_id),
            )

    def update_post_fetch_status(self, post_id: int, status: str) -> None:
        with self.get_cursor() as cursor:
            cursor.execute(
                "UPDATE blogger_posts SET fetch_status = ? WHERE id = ?",
                (status, post_id),
            )

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None
