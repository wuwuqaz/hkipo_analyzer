"""回测结果持久化：SQLite 存储"""
import json
import logging
import os
import sqlite3
import uuid

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS backtest_runs (
    id            TEXT PRIMARY KEY,
    run_at        TEXT NOT NULL,
    weights       TEXT NOT NULL,
    sample_count  INTEGER,
    qualified_count INTEGER,
    win_rate      REAL,
    expected_return REAL,
    max_drawdown  REAL,
    sharpe_like   REAL,
    ic_rank       REAL,
    break_rate    REAL,
    coverage      REAL,
    decile_returns TEXT,
    is_optimized  INTEGER DEFAULT 0,
    notes         TEXT
);

CREATE TABLE IF NOT EXISTS optimization_runs (
    id            TEXT PRIMARY KEY,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    iterations    INTEGER,
    best_weights  TEXT,
    best_objective REAL,
    default_objective REAL,
    improvement_pct REAL,
    cv_enabled    INTEGER DEFAULT 1,
    cv_objective  REAL DEFAULT 0,
    sample_count  INTEGER DEFAULT 0,
    convergence   TEXT,
    status        TEXT DEFAULT 'completed'
);
"""


class BacktestStore:
    def __init__(self, db_path="data/backtest.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = self._connect()
        conn.executescript(SCHEMA)
        conn.commit()
        conn.close()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _dict_row(self, row):
        if row is None:
            return None
        return dict(row)

    def save_backtest_run(self, result, notes=""):
        run_id = str(uuid.uuid4())[:8]
        from datetime import datetime
        conn = self._connect()
        conn.execute(
            """INSERT INTO backtest_runs
               (id, run_at, weights, sample_count, qualified_count,
                win_rate, expected_return, max_drawdown, sharpe_like,
                ic_rank, break_rate, coverage, decile_returns,
                is_optimized, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                datetime.now().isoformat(),
                json.dumps(result.weights),
                result.sample_count,
                result.qualified_count,
                result.win_rate,
                result.expected_return,
                result.max_drawdown,
                result.sharpe_like,
                result.ic_rank,
                result.break_rate,
                result.coverage,
                json.dumps(result.decile_returns),
                0,
                notes,
            ),
        )
        conn.commit()
        conn.close()
        return run_id

    def save_optimization_run(self, opt_result, iterations, cv_enabled=True):
        opt_id = str(uuid.uuid4())[:8]
        from datetime import datetime
        conn = self._connect()
        conn.execute(
            """INSERT INTO optimization_runs
               (id, started_at, finished_at, iterations, best_weights,
                best_objective, default_objective, improvement_pct,
                cv_enabled, cv_objective, sample_count, convergence, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                opt_id,
                datetime.now().isoformat(),
                datetime.now().isoformat(),
                iterations,
                json.dumps(opt_result.weights),
                opt_result.objective,
                opt_result.default_objective,
                opt_result.improvement_pct,
                1 if cv_enabled else 0,
                opt_result.cv_objective,
                opt_result.sample_count,
                json.dumps(opt_result.convergence),
                "completed",
            ),
        )
        conn.commit()
        conn.close()
        return opt_id

    def get_latest_backtest_run(self):
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM backtest_runs ORDER BY run_at DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return self._dict_row(row)

    def get_best_backtest_run(self):
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM backtest_runs ORDER BY expected_return DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return self._dict_row(row)

    def get_latest_optimization(self):
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM optimization_runs ORDER BY finished_at DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return self._dict_row(row)
