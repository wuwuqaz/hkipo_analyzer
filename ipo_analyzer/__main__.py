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

    args = parser.parse_args()

    if args.command == "reanalyze":
        if not args.code and not args.pdf:
            reanalyze_parser.error("请提供 --code 或 --pdf 参数")
        cmd_reanalyze(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
