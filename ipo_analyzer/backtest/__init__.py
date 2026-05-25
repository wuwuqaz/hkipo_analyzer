"""回测框架 & 贝叶斯权重优化模块"""
__version__ = "0.1.0"

from .models import BacktestRecord, BacktestResult, OptimizationResult
from .collector import collect_backtest_dataset
from .engine import run_backtest
from .metrics import compute_objective, compute_objective_cv
from .optimizer import optimize_weights
from .store import BacktestStore

from .ipo_models import IPOBacktestRecord, AllotmentExtractionResult, ProspectusSignalResult
from .feature_builder import build_ipo_features
from .ipo_backtester import run_ipo_first_day_backtest, write_ipo_backtest_csv, write_ipo_backtest_report

__all__ = [
    "BacktestRecord",
    "BacktestResult",
    "OptimizationResult",
    "collect_backtest_dataset",
    "run_backtest",
    "compute_objective",
    "compute_objective_cv",
    "optimize_weights",
    "BacktestStore",
    "IPOBacktestRecord",
    "AllotmentExtractionResult",
    "ProspectusSignalResult",
    "build_ipo_features",
    "run_ipo_first_day_backtest",
    "write_ipo_backtest_csv",
    "write_ipo_backtest_report",
]
