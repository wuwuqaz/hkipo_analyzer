"""回测框架 CLI 入口"""
import argparse
import logging
import os

import yaml

from .collector import collect_backtest_dataset
from .engine import run_backtest
from .optimizer import optimize_weights
from .store import BacktestStore
from ..settings import SETTINGS

logger = logging.getLogger(__name__)


def _get_default_weights():
    sw = SETTINGS.scoring
    return {
        "trade": sw.live_heat_trade,
        "fundamental": sw.live_heat_fundamental,
        "data_quality": sw.live_heat_data_quality,
        "valuation": sw.live_heat_valuation,
        "theme": sw.live_heat_theme,
    }


def cmd_run(args):
    bt = SETTINGS.backtest
    dataset = collect_backtest_dataset(
        history_dir=args.history_dir,
        data_quality_threshold=args.data_quality or bt.data_quality_threshold,
    )
    if len(dataset) < (args.min_samples or 1):
        print(f"样本数不足: {len(dataset)}，至少需要 {args.min_samples or 1}")
        return

    if args.weights:
        with open(args.weights) as f:
            w = yaml.safe_load(f).get("weights", _get_default_weights())
    else:
        w = _get_default_weights()

    result = run_backtest(dataset, w, qualify_threshold=bt.qualify_threshold)
    _print_result(result, w)

    if not args.no_save:
        store = BacktestStore(bt.backtest_db_path)
        store.save_backtest_run(result, notes="cli run")


def cmd_optimize(args):
    bt = SETTINGS.backtest
    dataset = collect_backtest_dataset(
        history_dir=args.history_dir,
        data_quality_threshold=args.data_quality or bt.data_quality_threshold,
    )
    min_samples = args.min_samples or bt.min_samples
    if len(dataset) < min_samples:
        print(f"样本数不足 ({len(dataset)} < {min_samples})，无法优化")
        return

    default_weights = _get_default_weights()
    print(f"数据集: {len(dataset)} 条, 迭代: {args.iterations or bt.opt_iterations}, CV: {not args.no_cv}")

    opt_result = optimize_weights(
        dataset,
        initial_samples=bt.opt_initial_samples,
        iterations=args.iterations or bt.opt_iterations,
        use_cv=not args.no_cv,
        qualify_threshold=bt.qualify_threshold,
        default_weights=default_weights,
    )

    print("\n=== 优化结果 ===")
    print(f"最优权重: {opt_result.weights}")
    print(f"优化目标值: {opt_result.objective:.4f}")
    print(f"默认目标值: {opt_result.default_objective:.4f}")
    print(f"提升: {opt_result.improvement_pct:+.1f}%")
    print(f"收敛: {len(opt_result.convergence)} 轮")

    store = BacktestStore(bt.backtest_db_path)
    store.save_optimization_run(opt_result, iterations=args.iterations or bt.opt_iterations,
                                cv_enabled=not args.no_cv)

    output_path = bt.optimized_weights_path
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    from datetime import datetime
    optimized_yaml = {
        "optimized_at": datetime.now().isoformat(),
        "sample_count": opt_result.sample_count,
        "cv_objective": opt_result.cv_objective,
        "weights": opt_result.weights,
        "default_objective": opt_result.default_objective,
        "optimized_objective": opt_result.objective,
        "improvement_pct": opt_result.improvement_pct,
    }
    with open(output_path, "w") as f:
        yaml.dump(optimized_yaml, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    print(f"\n优化权重已写入: {output_path}")


def cmd_report(args):
    bt = SETTINGS.backtest
    store = BacktestStore(bt.backtest_db_path)

    if args.compare:
        opt = store.get_latest_optimization()
        if opt:
            print("=== 默认 vs 优化 对比 ===")
            print(f"默认目标值:    {opt['default_objective']:.4f}")
            print(f"优化目标值:    {opt['best_objective']:.4f}")
            print(f"提升:         {opt['improvement_pct']:+.1f}%")
            print(f"优化权重:     {opt['best_weights']}")
        else:
            print("无优化记录")
    else:
        run = store.get_latest_backtest_run()
        if not run:
            print("无回测记录")
            return
        print("=== 最近回测 ===")
        print(f"样本数: {run['sample_count']}")
        print(f"Qualified: {run['qualified_count']}")
        print(f"胜率: {run['win_rate']:.2%}")
        print(f"期望收益: {run['expected_return']:.2%}")
        print(f"最大回撤: {run['max_drawdown']:.2%}")
        print(f"Sharpe: {run['sharpe_like']:.2f}")
        print(f"IC Rank: {run['ic_rank']:.3f}")
        print(f"破发率: {run['break_rate']:.2%}")
        print(f"覆盖率: {run['coverage']:.2%}")
        print(f"权重: {run['weights']}")


def cmd_status(args):
    bt = SETTINGS.backtest

    dataset = collect_backtest_dataset(
        history_dir=args.history_dir,
        data_quality_threshold=bt.data_quality_threshold,
    )
    print(f"历史数据集: {len(dataset)} 条有效样本")

    store = BacktestStore(bt.backtest_db_path)
    opt = store.get_latest_optimization()
    if opt:
        print(f"\n最近优化: {opt['finished_at']}")
        print(f"最优权重: {opt['best_weights']}")
        print(f"提升: {opt['improvement_pct']:+.1f}%")

    opt_path = bt.optimized_weights_path
    if os.path.exists(opt_path):
        print(f"\n优化配置文件已存在: {opt_path}")
    else:
        print("\n优化配置文件不存在，使用默认权重")


def _print_result(result, weights):
    print("=== 回测结果 ===")
    print(f"样本数: {result.sample_count}")
    print(f"权重: {weights}")
    print(f"Qualified (score≥50): {result.qualified_count}")
    print(f"胜率: {result.win_rate:.2%}")
    print(f"期望收益: {result.expected_return:.2%}")
    print(f"最大回撤: {result.max_drawdown:.2%}")
    print(f"Sharpe: {result.sharpe_like:.2f}")
    print(f"IC Rank: {result.ic_rank:.3f}")
    print(f"破发率(全体): {result.break_rate:.2%}")
    print(f"覆盖率: {result.coverage:.2%}")
    print(f"十分位收益: {result.decile_returns}")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m ipo_analyzer.backtest",
        description="回测框架 & 贝叶斯权重优化",
    )
    sub = parser.add_subparsers(dest="command", help="子命令")

    p_run = sub.add_parser("run", help="运行回测")
    p_run.add_argument("--history-dir", default=os.getenv("BACKTEST_HISTORY_DIR", "storage"), help="历史数据目录")
    p_run.add_argument("--weights", type=str, help="权重 YAML 文件路径")
    p_run.add_argument("--min-samples", type=int, help="最小样本数")
    p_run.add_argument("--data-quality", type=int, help="数据质量阈值")
    p_run.add_argument("--no-save", action="store_true", help="不保存到数据库")

    p_opt = sub.add_parser("optimize", help="贝叶斯优化权重")
    p_opt.add_argument("--history-dir", default=os.getenv("BACKTEST_HISTORY_DIR", "storage"), help="历史数据目录")
    p_opt.add_argument("--iterations", type=int, help="优化迭代轮数 (默认30)")
    p_opt.add_argument("--no-cv", action="store_true", help="禁用交叉验证")
    p_opt.add_argument("--min-samples", type=int, help="最小样本数")
    p_opt.add_argument("--data-quality", type=int, help="数据质量阈值")

    p_report = sub.add_parser("report", help="查看回测报告")
    p_report.add_argument("--compare", action="store_true", help="对比默认vs优化")
    p_report.add_argument("--last", action="store_true", help="最近一次（默认）")
    p_report.add_argument("--best", action="store_true", help="历史最优")

    p_status = sub.add_parser("status", help="回测系统状态查询")
    p_status.add_argument("--history-dir", default=os.getenv("BACKTEST_HISTORY_DIR", "storage"), help="历史数据目录")

    return parser


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run":
        cmd_run(args)
    elif args.command == "optimize":
        cmd_optimize(args)
    elif args.command == "report":
        cmd_report(args)
    elif args.command == "status":
        cmd_status(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
