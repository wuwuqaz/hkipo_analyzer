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


def compute_objective_cv(
    dataset,
    weights,
    qualify_threshold=50,
    k=5,
    min_qualified_threshold=3,
):
    """K-Fold 交叉验证的目标函数值

    Args:
        dataset: 回测样本列表
        weights: 权重字典
        qualify_threshold: 合格评分阈值
        k: 折数（默认 5）
        min_qualified_threshold: 每折最少合格样本数，低于此值该折 objective=0
    """
    n = len(dataset)
    if n < 5:
        result = run_backtest(dataset, weights, qualify_threshold)
        return compute_objective(result)

    k = min(k, n)
    fold_size = n // k
    objectives = []

    for fold in range(k):
        start = fold * fold_size
        end = start + fold_size if fold < k - 1 else n
        test_fold = set(range(start, end))

        train = [r for i, r in enumerate(dataset) if i not in test_fold]
        result = run_backtest(train, weights, qualify_threshold)

        if result.qualified_count < min_qualified_threshold:
            objectives.append(0.0)
        else:
            obj = compute_objective(result)
            objectives.append(obj)

    return round(sum(objectives) / len(objectives), 6) if objectives else 0.0
