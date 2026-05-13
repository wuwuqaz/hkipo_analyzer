import argparse
import json
import logging
import sys

from .service import BloggerMonitorService


def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _cmd_run(args):
    service = BloggerMonitorService()
    company_name = args.company_name

    if company_name is None:
        company_name = service._resolve_company_name(args.stock_code)

    if company_name is None:
        print(
            f"错误: 无法找到 stock_code={args.stock_code} 对应的公司名称，请通过 --company-name 指定",
            file=sys.stderr,
        )
        sys.exit(1)

    result = service.run_full_pipeline(args.stock_code, company_name)

    if result is None:
        print("错误: 流程执行失败", file=sys.stderr)
        sys.exit(1)

    print(f"共识评分: {result.consensus_score}")
    print(f"覆盖度: {result.coverage_score}")
    print(f"观点分布: 看好={result.positive_count} 中性={result.neutral_count} 看空={result.negative_count}")
    if result.top_reasons:
        print("主要理由:")
        for reason in result.top_reasons:
            print(f"  - {reason}")
    if result.top_risks:
        print("主要风险:")
        for risk in result.top_risks:
            print(f"  - {risk}")
    if result.data_quality_warning:
        print(f"数据质量警告: {result.data_quality_warning}")


def _cmd_search(args):
    service = BloggerMonitorService()
    results = service.search_only(args.stock_code, args.company_name)

    print(f"搜索到 {len(results)} 篇文章:")
    for i, r in enumerate(results, 1):
        print(f"  {i}. {r.title}")
        print(f"     {r.url}")


def _cmd_consensus(args):
    service = BloggerMonitorService()
    result = service.get_consensus(args.stock_code)

    if result is None:
        print(f"未找到 stock_code={args.stock_code} 的共识数据", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))


def main():
    _setup_logging()

    parser = argparse.ArgumentParser(
        prog="python -m ipo_analyzer.blogger_monitor",
        description="港股IPO博主观点监控工具",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="执行完整流程：搜索→过滤→分析→汇总")
    run_parser.add_argument("--stock-code", required=True, help="股票代码")
    run_parser.add_argument("--company-name", default=None, help="公司名称（可选）")

    search_parser = subparsers.add_parser("search", help="仅搜索文章")
    search_parser.add_argument("--stock-code", required=True, help="股票代码")
    search_parser.add_argument("--company-name", default=None, help="公司名称（可选）")

    consensus_parser = subparsers.add_parser("consensus", help="查看共识汇总")
    consensus_parser.add_argument("--stock-code", required=True, help="股票代码")

    args = parser.parse_args()

    if args.command == "run":
        _cmd_run(args)
    elif args.command == "search":
        _cmd_search(args)
    elif args.command == "consensus":
        _cmd_consensus(args)


if __name__ == "__main__":
    main()
