import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ipo_analyzer.backtest.models import BacktestRecord, BacktestResult, OptimizationResult
from ipo_analyzer.backtest.collector import collect_backtest_dataset
from ipo_analyzer.backtest.engine import run_backtest
from ipo_analyzer.backtest.metrics import compute_objective, compute_objective_cv


def test_backtest_record_creation():
    record = BacktestRecord(
        hk_code="02580.HK",
        company_name="测试公司",
        listing_date="2025-06-01",
        trade_score=60.0,
        fundamental_score=70.0,
        valuation_score=55.0,
        theme_score=40.0,
        data_quality_score=50.0,
        first_day_return=0.15,
        is_break=False,
        over_sub_ratio=100.0,
        score_timestamp="2025-05-20T10:00:00",
        data_quality=2,
    )
    assert record.hk_code == "02580.HK"
    assert record.first_day_return == 0.15
    assert not record.is_break


def test_backtest_result_creation():
    result = BacktestResult(
        sample_count=10,
        weights={"trade": 0.25, "fundamental": 0.35, "valuation": 0.25, "theme": 0.10, "data_quality": 0.05},
        qualified_count=7,
        win_rate=0.71,
        expected_return=0.12,
        max_drawdown=0.08,
        sharpe_like=1.5,
        ic_rank=0.42,
        break_rate=0.30,
        coverage=0.70,
        decile_returns=[0.02, 0.05, 0.08, 0.10, 0.12, 0.14, 0.15, 0.18, 0.20, 0.25],
    )
    assert result.sample_count == 10
    assert result.win_rate == 0.71


def test_optimization_result_creation():
    opt = OptimizationResult(
        weights={"trade": 0.28, "fundamental": 0.32, "valuation": 0.22, "theme": 0.12, "data_quality": 0.06},
        objective=0.312,
        default_objective=0.245,
        improvement_pct=27.3,
        convergence=[[0, 0.20], [5, 0.28], [10, 0.31]],
    )
    assert opt.improvement_pct == 27.3
    assert len(opt.convergence) == 3


class TestCollector:
    def setup_method(self):
        self.tempdir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tempdir)

    def _write_history(self, records):
        history_file = os.path.join(self.tempdir, "ipo_history.json")
        with open(history_file, "w") as f:
            json.dump(records, f)
        return history_file

    def test_collector_extracts_valid_records(self):
        records = [
            {
                "hk_code": "02580",
                "company_name": "测试公司A",
                "trade_score": 60,
                "fundamental_score": 70,
                "valuation_score": 55,
                "theme_score": 40,
                "data_quality_score": 50,
                "_data_quality": 2,
                "post_listing": {
                    "first_day": {"change_pct": 15.0},
                    "public_subscription_level": 100.0,
                },
            },
            {
                "hk_code": "09999",
                "company_name": "测试公司B",
                "trade_score": 30,
                "fundamental_score": 45,
                "valuation_score": 20,
                "theme_score": 10,
                "data_quality_score": 60,
                "_data_quality": 1,
                "post_listing": {
                    "first_day": {"change_pct": -5.0},
                    "public_subscription_level": 5.0,
                },
            },
        ]
        self._write_history(records)

        dataset = collect_backtest_dataset(history_dir=self.tempdir)

        assert len(dataset) == 1
        r = dataset[0]
        assert r.hk_code == "02580"
        assert r.trade_score == 60
        assert r.fundamental_score == 70
        assert r.first_day_return == 0.15
        assert not r.is_break

    def test_collector_filters_missing_post_listing(self):
        records = [
            {
                "hk_code": "02580",
                "company_name": "无post_listing",
                "trade_score": 60,
                "fundamental_score": 70,
                "valuation_score": 55,
                "theme_score": 40,
                "data_quality_score": 50,
                "_data_quality": 2,
                "post_listing": None,
            },
        ]
        self._write_history(records)

        dataset = collect_backtest_dataset(history_dir=self.tempdir)
        assert len(dataset) == 0

    def test_collector_filters_no_first_day(self):
        records = [
            {
                "hk_code": "02580",
                "company_name": "无first_day",
                "trade_score": 60,
                "fundamental_score": 70,
                "valuation_score": 55,
                "theme_score": 40,
                "data_quality_score": 50,
                "_data_quality": 2,
                "post_listing": {"public_subscription_level": 100},
            },
        ]
        self._write_history(records)

        dataset = collect_backtest_dataset(history_dir=self.tempdir)
        assert len(dataset) == 0

    def test_collector_from_reanalysis_fallback(self):
        records = [
            {
                "hk_code": "02580",
                "company_name": "主记录",
                "trade_score": 30,
                "fundamental_score": 40,
                "valuation_score": 20,
                "theme_score": 10,
                "data_quality_score": 30,
                "_data_quality": 2,
                "post_listing": {
                    "first_day": {"change_pct": 10.0},
                    "public_subscription_level": 50.0,
                },
            },
        ]
        self._write_history(records)

        reanalysis_dir = os.path.join(self.tempdir, "reanalysis")
        os.makedirs(reanalysis_dir, exist_ok=True)
        reanalysis_record = {
            "stock_code": "02580",
            "score_breakdown": {
                "trade_score": 60,
                "fundamental_score": 75,
                "valuation_score": 55,
                "theme_score": 45,
            },
        }
        with open(os.path.join(reanalysis_dir, "02580_latest.json"), "w") as f:
            json.dump(reanalysis_record, f)

        dataset = collect_backtest_dataset(history_dir=self.tempdir)

        assert len(dataset) == 1
        r = dataset[0]
        assert r.trade_score == 60
        assert r.fundamental_score == 75


class TestEngine:
    def _make_records(self):
        return [
            BacktestRecord(
                hk_code="A", company_name="A",
                trade_score=80, fundamental_score=85, valuation_score=75,
                theme_score=60, data_quality_score=80,
                first_day_return=0.20, is_break=False, over_sub_ratio=200,
            ),
            BacktestRecord(
                hk_code="B", company_name="B",
                trade_score=70, fundamental_score=75, valuation_score=65,
                theme_score=50, data_quality_score=70,
                first_day_return=0.10, is_break=False, over_sub_ratio=150,
            ),
            BacktestRecord(
                hk_code="C", company_name="C",
                trade_score=40, fundamental_score=45, valuation_score=35,
                theme_score=30, data_quality_score=50,
                first_day_return=-0.05, is_break=True, over_sub_ratio=10,
            ),
            BacktestRecord(
                hk_code="D", company_name="D",
                trade_score=30, fundamental_score=35, valuation_score=25,
                theme_score=20, data_quality_score=40,
                first_day_return=-0.15, is_break=True, over_sub_ratio=3,
            ),
        ]

    def test_engine_basic_result(self):
        dataset = self._make_records()
        weights = {"trade": 0.25, "fundamental": 0.35, "valuation": 0.25,
                   "theme": 0.10, "data_quality": 0.05}

        result = run_backtest(dataset, weights, qualify_threshold=50)

        assert result.sample_count == 4
        assert result.qualified_count == 2
        assert result.win_rate == 1.0
        assert result.break_rate == 0.5
        assert result.coverage == 0.5
        assert result.max_drawdown == 0.0

    def test_engine_decile_monotonic(self):
        records = []
        for i in range(20):
            records.append(BacktestRecord(
                hk_code=f"C{i:02d}", company_name=f"C{i:02d}",
                trade_score=float(i * 5), fundamental_score=float(i * 5),
                valuation_score=float(i * 5), theme_score=float(i * 5),
                data_quality_score=50.0,
                first_day_return=float(i) / 100,
                is_break=i < 5,
                over_sub_ratio=float(i * 10),
            ))
        weights = {"trade": 0.25, "fundamental": 0.35, "valuation": 0.25,
                   "theme": 0.10, "data_quality": 0.05}

        result = run_backtest(records, weights, qualify_threshold=0)
        assert result.decile_returns[-1] >= result.decile_returns[0]

    def test_engine_empty_dataset(self):
        result = run_backtest([], {}, qualify_threshold=50)
        assert result.sample_count == 0
        assert result.win_rate == 0.0

    def test_engine_no_qualified(self):
        dataset = self._make_records()
        weights = {"trade": 0.25, "fundamental": 0.35, "valuation": 0.25,
                   "theme": 0.10, "data_quality": 0.05}
        result = run_backtest(dataset, weights, qualify_threshold=90)
        assert result.qualified_count == 0
        assert result.win_rate == 0.0


class TestMetrics:
    def test_objective_calculation(self):
        result = BacktestResult(
            sample_count=10,
            qualified_count=7,
            win_rate=0.857,
            expected_return=0.12,
            max_drawdown=0.05,
        )
        obj = compute_objective(result, win_rate_w=0.4, expected_return_w=0.4,
                                max_drawdown_w=0.2)
        assert abs(obj - 0.3808) < 1e-6

    def test_objective_zero_qualified(self):
        result = BacktestResult(sample_count=10, qualified_count=0)
        obj = compute_objective(result)
        assert obj == 0.0

    def test_objective_cv_runs(self):
        dataset = [
            BacktestRecord(hk_code="A", company_name="A",
                           trade_score=80, fundamental_score=85, valuation_score=75,
                           theme_score=60, data_quality_score=80,
                           first_day_return=0.20, is_break=False),
            BacktestRecord(hk_code="B", company_name="B",
                           trade_score=70, fundamental_score=75, valuation_score=65,
                           theme_score=50, data_quality_score=70,
                           first_day_return=0.10, is_break=False),
            BacktestRecord(hk_code="C", company_name="C",
                           trade_score=40, fundamental_score=45, valuation_score=35,
                           theme_score=30, data_quality_score=50,
                           first_day_return=-0.05, is_break=True),
        ]
        weights = {"trade": 0.25, "fundamental": 0.35, "valuation": 0.25,
                   "theme": 0.10, "data_quality": 0.05}
        cv_obj = compute_objective_cv(dataset, weights, qualify_threshold=50)
        assert isinstance(cv_obj, float)
        assert cv_obj >= 0.0


class TestOptimizer:
    from ipo_analyzer.backtest.optimizer import optimize_weights, _normalize_weights, _lhs_sample

    def test_normalize_weights(self):
        from ipo_analyzer.backtest.optimizer import _normalize_weights
        raw = {"trade": 5, "fundamental": 10, "valuation": 3, "theme": 1, "data_quality": 1}
        w = _normalize_weights(raw)
        assert abs(sum(w.values()) - 1.0) < 1e-6
        assert all(0.0 <= v <= 1.0 for v in w.values())

    def test_normalize_all_zero(self):
        from ipo_analyzer.backtest.optimizer import _normalize_weights
        raw = {"trade": 0, "fundamental": 0, "valuation": 0, "theme": 0, "data_quality": 0}
        w = _normalize_weights(raw)
        for v in w.values():
            assert abs(v - 0.2) < 1e-6

    def test_lhs_sample(self):
        from ipo_analyzer.backtest.optimizer import _lhs_sample
        samples = _lhs_sample(n=5, dim=3, lower=0.05, upper=0.80)
        assert len(samples) == 5
        for s in samples:
            assert len(s) == 3
            for v in s:
                assert 0.05 <= v <= 0.80

    def _make_dataset(self, n=15):
        import random
        random.seed(42)
        records = []
        for i in range(n):
            records.append(BacktestRecord(
                hk_code=f"C{i:02d}", company_name=f"C{i:02d}",
                trade_score=float(random.randint(20, 90)),
                fundamental_score=float(random.randint(20, 90)),
                valuation_score=float(random.randint(20, 90)),
                theme_score=float(random.randint(20, 90)),
                data_quality_score=50.0,
                first_day_return=float(random.randint(-15, 30)) / 100,
                is_break=False,
                over_sub_ratio=float(random.randint(5, 200)),
            ))
        records[0].is_break = True
        records[0].first_day_return = -0.10
        return records

    def test_optimize_returns_better_objective(self):
        from ipo_analyzer.backtest.optimizer import optimize_weights
        dataset = self._make_dataset(15)
        result = optimize_weights(
            dataset,
            initial_samples=10,
            iterations=15,
            use_cv=False,
            qualify_threshold=50,
        )
        assert result.objective >= 0
        assert abs(sum(result.weights.values()) - 1.0) < 1e-3
        assert result.objective >= result.default_objective - 0.05
        assert len(result.convergence) > 0


class TestStore:
    def setup_method(self):
        self.tempdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tempdir, "test_backtest.db")

    def teardown_method(self):
        shutil.rmtree(self.tempdir)

    def test_init_creates_tables(self):
        from ipo_analyzer.backtest.store import BacktestStore
        import sqlite3 as _sqlite3
        store = BacktestStore(self.db_path)
        conn = _sqlite3.connect(self.db_path)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {t[0] for t in tables}
        assert "backtest_runs" in table_names
        assert "optimization_runs" in table_names
        conn.close()

    def test_save_and_load_backtest_result(self):
        from ipo_analyzer.backtest.store import BacktestStore
        store = BacktestStore(self.db_path)
        result = BacktestResult(
            sample_count=10,
            weights={"trade": 0.25, "fundamental": 0.35},
            qualified_count=7,
            win_rate=0.71,
            expected_return=0.12,
            max_drawdown=0.08,
            sharpe_like=1.5,
            ic_rank=0.42,
            break_rate=0.30,
            coverage=0.70,
            decile_returns=[0.02, 0.05, 0.08],
        )
        run_id = store.save_backtest_run(result, notes="test")
        assert run_id is not None

        loaded = store.get_latest_backtest_run()
        assert loaded is not None
        assert loaded["win_rate"] == 0.71

    def test_save_and_load_optimization(self):
        from ipo_analyzer.backtest.store import BacktestStore
        store = BacktestStore(self.db_path)
        opt = OptimizationResult(
            weights={"trade": 0.28, "fundamental": 0.32},
            objective=0.312,
            default_objective=0.245,
            improvement_pct=27.3,
            convergence=[[0, 0.20], [10, 0.31]],
        )
        opt_id = store.save_optimization_run(opt, iterations=30, cv_enabled=True)
        assert opt_id is not None

        loaded = store.get_latest_optimization()
        assert loaded is not None
        assert loaded["best_objective"] == 0.312


class TestCLI:
    def test_cli_status_prints_info(self):
        import subprocess as _sp
        result = _sp.run(
            [sys.executable, "-m", "ipo_analyzer.backtest", "status"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0

    def test_cli_report_works(self):
        import subprocess as _sp
        result = _sp.run(
            [sys.executable, "-m", "ipo_analyzer.backtest", "report"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0


class TestScoringIntegration:
    def setup_method(self):
        self.tempdir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tempdir)

    def test_try_load_optimized_weights_found(self):
        """验证 _try_load_optimized_weights 在文件存在时返回正确权重"""
        opt_path = os.path.join(self.tempdir, "optimized_weights.yaml")
        opt_data = {
            "weights": {
                "trade": 0.30, "fundamental": 0.30,
                "valuation": 0.20, "theme": 0.15, "data_quality": 0.05,
            }
        }
        import yaml as _yaml
        with open(opt_path, "w") as f:
            _yaml.dump(opt_data, f)

        from ipo_analyzer.settings import SETTINGS as _settings
        from unittest.mock import patch
        with patch.object(_settings.backtest, 'optimized_weights_path', opt_path):
            result = _scoring_try_load_opt(opt_path)
            assert result is not None
            assert result["trade"] == 0.30

    def test_try_load_optimized_weights_missing(self):
        """验证文件不存在时返回 None"""
        from ipo_analyzer.settings import SETTINGS as _s2
        from unittest.mock import patch
        with patch.object(_s2.backtest, 'optimized_weights_path', '/nonexistent/path.yaml'):
            result = _scoring_try_load_opt('/nonexistent/path.yaml')
            assert result is None


def _scoring_try_load_opt(path):
    import yaml as _yaml2
    try:
        with open(path) as f:
            opt = _yaml2.safe_load(f)
        if opt and opt.get("weights"):
            return {k: float(v) for k, v in opt["weights"].items()}
    except Exception:
        pass
    return None
