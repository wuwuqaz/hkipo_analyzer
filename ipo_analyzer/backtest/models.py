"""回测框架数据模型"""
from dataclasses import dataclass, field


@dataclass
class BacktestRecord:
    """单只IPO的回测样本"""
    hk_code: str
    company_name: str
    listing_date: str = ""

    trade_score: float = 0.0
    fundamental_score: float = 0.0
    valuation_score: float = 0.0
    theme_score: float = 0.0
    data_quality_score: float = 0.0

    first_day_return: float = 0.0
    is_break: bool = False
    over_sub_ratio: float = 0.0

    score_timestamp: str = ""
    data_quality: int = 0


@dataclass
class BacktestResult:
    """一次回测运行的完整结果"""
    sample_count: int = 0
    weights: dict = field(default_factory=dict)
    qualified_count: int = 0

    win_rate: float = 0.0
    expected_return: float = 0.0
    max_drawdown: float = 0.0
    sharpe_like: float = 0.0

    ic_rank: float = 0.0
    break_rate: float = 0.0
    coverage: float = 0.0

    decile_returns: list[float] = field(default_factory=list)


@dataclass
class OptimizationResult:
    """一次贝叶斯优化运行的结果"""
    weights: dict = field(default_factory=dict)
    objective: float = 0.0
    default_objective: float = 0.0
    improvement_pct: float = 0.0
    convergence: list[list[float]] = field(default_factory=list)
    cv_objective: float = 0.0
    sample_count: int = 0
