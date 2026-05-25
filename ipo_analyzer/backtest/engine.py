"""回测引擎：用给定权重对历史数据重算评分并统计表现"""
import statistics

from .models import BacktestResult


def _composite_score(record, weights):
    return (
        record.trade_score * weights.get("trade", 0)
        + record.fundamental_score * weights.get("fundamental", 0)
        + record.valuation_score * weights.get("valuation", 0)
        + record.theme_score * weights.get("theme", 0)
        + record.data_quality_score * weights.get("data_quality", 0)
    )


def _spearman_rank(x, y):
    """计算 Spearman 秩相关系数"""
    n = len(x)
    if n < 2:
        return 0.0
    rank_x = _rank(x)
    rank_y = _rank(y)
    d2 = sum((rx - ry) ** 2 for rx, ry in zip(rank_x, rank_y))
    return 1.0 - (6.0 * d2) / (n * (n * n - 1))


def _rank(values):
    """返回值的秩（从 1 开始）"""
    indexed = sorted(enumerate(values), key=lambda iv: iv[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


def run_backtest(dataset, weights, qualify_threshold=50):
    """运行回测"""
    n = len(dataset)
    if n == 0:
        return BacktestResult(sample_count=0, weights=dict(weights))

    scored = [
        (_composite_score(r, weights), r)
        for r in dataset
    ]
    scored.sort(key=lambda x: x[0])

    scores = [s for s, _ in scored]
    returns = [r.first_day_return for _, r in scored]

    qualified_returns = [
        r.first_day_return
        for s, r in scored
        if s >= qualify_threshold
    ]
    q_count = len(qualified_returns)

    if q_count > 0:
        win_rate = sum(1 for ret in qualified_returns if ret >= 0) / q_count
        expected_return = sum(qualified_returns) / q_count
        max_drawdown = abs(min(0.0, min(qualified_returns)))
        sharpe_like = (
            expected_return / statistics.stdev(qualified_returns)
            if len(qualified_returns) >= 2 and statistics.stdev(qualified_returns) > 1e-9
            else 0.0
        )
    else:
        win_rate = 0.0
        expected_return = 0.0
        max_drawdown = 0.0
        sharpe_like = 0.0

    ic_rank = _spearman_rank(scores, returns)

    break_count = sum(1 for r in dataset if r.is_break)
    break_rate = break_count / n if n else 0.0
    coverage = q_count / n if n else 0.0

    decile_size = max(1, n // 10)
    decile_returns = []
    for d in range(10):
        start = d * decile_size
        end = start + decile_size if d < 9 else n
        chunk_returns = [r.first_day_return for _, r in scored[start:end]]
        if chunk_returns:
            decile_returns.append(round(statistics.mean(chunk_returns), 4))
        else:
            decile_returns.append(0.0)

    return BacktestResult(
        sample_count=n,
        weights=dict(weights),
        qualified_count=q_count,
        win_rate=round(win_rate, 4),
        expected_return=round(expected_return, 4),
        max_drawdown=round(max_drawdown, 4),
        sharpe_like=round(sharpe_like, 4),
        ic_rank=round(ic_rank, 4),
        break_rate=round(break_rate, 4),
        coverage=round(coverage, 4),
        decile_returns=decile_returns,
    )
