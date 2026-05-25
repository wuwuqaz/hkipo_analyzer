"""CLI入口 — 支持重新分析等命令"""

import argparse
import json
import logging
import os
import sys
from typing import Optional

from .core import reanalyze_ipo

logger = logging.getLogger(__name__)


def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )


def _build_historical_market_data(args) -> Optional[dict]:
    data = {}
    if args.margin_total is not None:
        data["margin_total"] = args.margin_total
    if args.public_offer is not None:
        data["public_offer"] = args.public_offer
    if args.actual_over is not None:
        data["actual_over_sub_ratio"] = args.actual_over
    if args.forecast_over is not None:
        data["forecast_over_sub_ratio"] = args.forecast_over
    if args.market_heat:
        data["market_heat"] = args.market_heat
    return data if data else None


def cmd_reanalyze(args):
    historical_market_data = _build_historical_market_data(args)

    response = reanalyze_ipo(
        stock_code=args.code,
        company_name=args.name,
        pdf_path=args.pdf,
        uploaded_file=None,
        historical_market_data=historical_market_data,
        force_refresh=args.force_refresh,
        output_dir=args.output_dir,
    )

    status = response.get("status", "error")
    result = response.get("result", {})

    if status == "error":
        logger.error("❌ 重新分析失败: %s", response.get("message", ""))
        if response.get("suggestion"):
            logger.info("💡 建议: %s", response["suggestion"])
        sys.exit(1)

    logger.info("✅ 重新分析完成")
    if response.get("message"):
        logger.info("ℹ️ %s", response["message"])

    score = result.get("score", 0)
    logger.info("📊 综合评分: %d/100", score)

    weight_profile = result.get("weight_profile", {})
    if weight_profile:
        logger.info("⚖️ 权重配置: %s (%s)", weight_profile.get("name", ""), weight_profile.get("reason", ""))

    version_delta = result.get("version_delta")
    if version_delta:
        prev = version_delta.get("previous_score")
        curr = version_delta.get("current_score")
        delta = version_delta.get("score_delta")
        logger.info("📈 版本对比: %s → %s (变化: %s)", prev, curr, delta)

    # 保存JSON结果
    if args.save_json:
        output_path = os.path.join(args.output_dir, f"reanalysis_{args.code or 'unknown'}.json")
        os.makedirs(args.output_dir, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)
        logger.info("💾 结果已保存: %s", output_path)

    return result


def cmd_ipo_first_day(args):
    import json
    from ipo_analyzer.backtest.ipo_models import IPOBacktestRecord
    from ipo_analyzer.backtest.ipo_backtester import (
        run_ipo_first_day_backtest,
        write_ipo_backtest_csv,
        write_ipo_backtest_report,
    )

    if not os.path.exists(args.input):
        logger.error("输入文件不存在: %s", args.input)
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, list):
        logger.error("输入文件格式错误: 期望 JSON 数组")
        sys.exit(1)

    records = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        post = item.get("post_listing")
        if not isinstance(post, dict):
            continue
        first_day = post.get("first_day")
        if not isinstance(first_day, dict):
            continue
        change_pct = first_day.get("change_pct")
        if not isinstance(change_pct, (int, float)):
            continue

        pi = item.get("prospectus_info", {})
        ca = pi.get("cornerstone_analysis") if isinstance(pi.get("cornerstone_analysis"), dict) else {}
        cornerstone_list = pi.get("cornerstone_investors") or ca.get("cornerstone_investors") or []
        if isinstance(cornerstone_list, list):
            cs_names = [
                c.get("name", "") if isinstance(c, dict) else str(c)
                for c in cornerstone_list
            ]
        else:
            cs_names = []

        cs_pct = pi.get("cornerstone_pct") or ca.get("cornerstone_pct")
        cs_total = pi.get("cornerstone_total_investment")
        cs_offer_size = pi.get("offer_size")
        if cs_pct is None and cs_total and cs_offer_size:
            try:
                cs_pct = float(cs_total) / float(cs_offer_size) * 100
            except (ValueError, ZeroDivisionError):
                pass

        sponsors = []
        sponsor_info = pi.get("sponsor_info")
        if isinstance(sponsor_info, list):
            sponsors = [
                s.get("name", "") if isinstance(s, dict) else str(s)
                for s in sponsor_info
            ]
        elif isinstance(sponsor_info, str):
            sponsors = [sponsor_info]

        listing_date = (
            item.get("listing_date")
            or post.get("listing_date")
            or first_day.get("date")
            or pi.get("listing_date")
            or ""
        )
        offer_price = (
            post.get("final_offer_price")
            or pi.get("final_offer_price")
            or item.get("offer_price")
            or pi.get("offer_price")
        )
        first_day_close = first_day.get("close") or first_day.get("price")

        one_lot_success_rate = None
        pools = post.get("allocation_pools")
        if isinstance(pools, dict):
            pool_a = pools.get("A")
            rows = pool_a.get("rows") if isinstance(pool_a, dict) else None
            if isinstance(rows, list) and rows:
                one_lot_success_rate = rows[0].get("success_rate_pct")
                if isinstance(one_lot_success_rate, (int, float)):
                    one_lot_success_rate = float(one_lot_success_rate) / 100.0

        clawback_ratio = None
        initial_hk = post.get("initial_hk_offer_shares")
        final_hk = post.get("final_hk_offer_shares")
        global_offer = pi.get("global_offer_shares")
        try:
            if final_hk and global_offer:
                clawback_ratio = float(final_hk) / float(global_offer)
            elif initial_hk and final_hk and float(initial_hk) > 0:
                clawback_ratio = float(final_hk) / float(initial_hk)
        except (TypeError, ValueError, ZeroDivisionError):
            clawback_ratio = None

        rec = IPOBacktestRecord(
            hk_code=str(item.get("hk_code", "")),
            stock_code=str(item.get("stock_code") or item.get("hk_code") or ""),
            company_name=str(item.get("company_name", "")),
            listing_date=str(listing_date),
            offer_price=float(offer_price) if isinstance(offer_price, (int, float)) else None,
            first_day_open=float(first_day.get("open")) if isinstance(first_day.get("open"), (int, float)) else None,
            first_day_close=float(first_day_close) if isinstance(first_day_close, (int, float)) else None,
            first_day_high=float(first_day.get("high")) if isinstance(first_day.get("high"), (int, float)) else None,
            first_day_low=float(first_day.get("low")) if isinstance(first_day.get("low"), (int, float)) else None,
            first_day_return=float(change_pct),
            over_sub_ratio=float(post.get("public_subscription_level", 0) or 0),
            has_greenshoe=pi.get("has_greenshoe"),
            sponsors=sponsors,
            cornerstone_investors=cs_names,
            cornerstone_pct=float(cs_pct) if isinstance(cs_pct, (int, float)) else None,
            cornerstone_independence=pi.get("cornerstone_independence"),
            fundamental_score=float(item.get("fundamental_score", 0) or 0) or None,
            one_lot_success_rate=one_lot_success_rate,
            clawback_ratio=clawback_ratio,
            extra={
                "sponsors": sponsors,
                "trade_score": float(item.get("trade_score", 0) or 0),
            },
        )
        records.append(rec)

    if not records:
        logger.warning("无有效 IPO 首日数据样本")
        print("无有效样本")
        return

    print(f"加载 {len(records)} 条 IPO 首日样本")

    summary = run_ipo_first_day_backtest(records)

    csv_path = write_ipo_backtest_csv(summary["records"], args.output_csv)
    print(f"CSV 已写入: {csv_path}")

    report_path = write_ipo_backtest_report(summary, args.report)
    print(f"报告已写入: {report_path}")

    total = summary["total"]
    print(f"\n总样本: {total['count']}, 上涨率: {total['win_rate']:.1%}, "
          f"中位涨幅: {total['median_return']:+.2f}%, 破发率: {total['break_rate']:.1%}")


def main():
    _setup_logging()
    parser = argparse.ArgumentParser(
        prog="python -m ipo_analyzer",
        description="港股IPO打新分析器 CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # reanalyze 子命令
    reanalyze_parser = subparsers.add_parser("reanalyze", help="重新分析已结束招股的IPO")
    reanalyze_parser.add_argument("--code", type=str, default=None, help="股票代码（如 9995）")
    reanalyze_parser.add_argument("--name", type=str, default=None, help="公司名称（如 荣昌生物）")
    reanalyze_parser.add_argument("--pdf", type=str, default=None, help="本地PDF文件路径")
    reanalyze_parser.add_argument("--margin-total", type=float, default=None, help="孖展资金总计（亿港元）")
    reanalyze_parser.add_argument("--public-offer", type=float, default=None, help="公开集资额（亿港元）")
    reanalyze_parser.add_argument("--actual-over", type=float, default=None, help="实际超购倍数")
    reanalyze_parser.add_argument("--forecast-over", type=float, default=None, help="预测超购倍数")
    reanalyze_parser.add_argument("--market-heat", type=str, default=None, help="市场热度（极热/热门/温和/冷清）")
    reanalyze_parser.add_argument("--force-refresh", action="store_true", help="强制刷新缓存")
    reanalyze_parser.add_argument("--output-dir", type=str, default="temp", help="输出目录")
    reanalyze_parser.add_argument("--save-json", action="store_true", help="保存JSON结果")

    # backtest 子命令
    subparsers.add_parser("backtest", help="回测 & 权重优化")

    # ipo-first-day 子命令
    ipo_fd = subparsers.add_parser("ipo-first-day", help="IPO 首日表现/情绪面回测")
    ipo_fd.add_argument("--input", type=str, default="temp/ipo_history.json", help="历史数据 JSON 路径")
    ipo_fd.add_argument("--output-csv", type=str, default="data/backtest/ipo_backtest_records.csv", help="CSV 输出路径")
    ipo_fd.add_argument("--report", type=str, default="reports/ipo_backtest_summary.md", help="Markdown 报告路径")
    ipo_fd.add_argument("--pdf-dir", type=str, default="storage/uploads", help="本地 PDF 扫描目录")

    args, remaining = parser.parse_known_args()

    if args.command == "reanalyze":
        if not args.code and not args.pdf:
            reanalyze_parser.error("请提供 --code 或 --pdf 参数")
        cmd_reanalyze(args)
    elif args.command == "backtest":
        from ipo_analyzer.backtest.cli import main as backtest_main
        sys.argv = [sys.argv[0], *remaining]
        backtest_main()
    elif args.command == "ipo-first-day":
        cmd_ipo_first_day(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
