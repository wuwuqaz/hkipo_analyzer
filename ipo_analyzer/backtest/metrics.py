"""回测评估指标：目标函数 + 交叉验证"""
from .engine import run_backtest


def compute_objective(
    backtest_result,
    win_rate_w=0.4,
    expected_return_w=0.4,
    max_drawdown_w=0.2,
):
    """计算多目标复合函数值

    objective = win_rate*w1 + expected_return*w2 - max_drawdown*w3
    """
    if backtest_result.qualified_count == 0:
        return 0.0

    obj = (
        backtest_result.win_rate * win_rate_w
        + backtest_result.expected_return * expected_return_w
        - backtest_result.max_drawdown * max_drawdown_w
    )
    return round(obj, 6)


def compute_objective_cv(dataset, weights, qualify_threshold=50):
    """Leave-One-Out 交叉验证的目标函数值"""
    n = len(dataset)
    if n < 3:
        result = run_backtest(dataset, weights, qualify_threshold)
        return compute_objective(result)

    objectives = []
    for i in range(n):
        train = [r for j, r in enumerate(dataset) if j != i]
        result = run_backtest(train, weights, qualify_threshold)
        obj = compute_objective(result)
        objectives.append(obj)

    return round(sum(objectives) / len(objectives), 6)
