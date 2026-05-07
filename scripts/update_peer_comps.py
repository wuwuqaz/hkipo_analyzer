#!/usr/bin/env python3
"""同行库更新脚本

用法:
    python3 scripts/update_peer_comps.py --all
    python3 scripts/update_peer_comps.py --all --dry-run
    python3 scripts/update_peer_comps.py --all --write
    python3 scripts/update_peer_comps.py --stale-only --dry-run
    python3 scripts/update_peer_comps.py --stale-only --write
    python3 scripts/update_peer_comps.py --ticker 2498.HK --dry-run
    python3 scripts/update_peer_comps.py --ticker 2498.HK --write
    python3 scripts/update_peer_comps.py --sector hardtech --subsector robotics_visual_perception --write
"""

import sys
import os
import argparse
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("yfinance").setLevel(logging.WARNING)


def main():
    parser = argparse.ArgumentParser(description="同行库更新工具")
    parser.add_argument("--all", action="store_true", help="更新所有 listed peers")
    parser.add_argument("--stale-only", action="store_true", help="仅更新过期 peers")
    parser.add_argument("--dry-run", action="store_true", help="预览模式（不写入 YAML，默认）")
    parser.add_argument("--write", action="store_true", help="写入 YAML")
    parser.add_argument("--ticker", type=str, help="更新单个 ticker")
    parser.add_argument("--sector", type=str, help="与 --subsector 搭配指定细分赛道")
    parser.add_argument("--subsector", type=str, help="细分赛道键名")
    args = parser.parse_args()

    # dry-run / write 逻辑
    if args.write and args.dry_run:
        print("⚠ 同时指定 --dry-run 和 --write，以 --write 为准")
        dry_run = False
    elif args.write:
        dry_run = False
    else:
        dry_run = True  # 默认预览

    try:
        from ipo_analyzer.peer_data import PeerMetricsUpdater
    except ImportError as e:
        print(f"✗ 导入失败: {e}")
        sys.exit(1)

    updater = PeerMetricsUpdater()

    if not dry_run:
        print("=" * 50)
        print("  【写入模式】将修改 data/peer_comps.yaml")
        print("  更新前会自动备份到 data/backups/")
        print("=" * 50)
    else:
        print("=" * 50)
        print("  预览模式 (dry-run) — 不会写入 YAML")
        print("  使用 --write 正式更新")
        print("=" * 50)
    print()

    # 高优先级: --ticker
    if args.ticker:
        print(f"→ 更新 ticker: {args.ticker}")
        r = updater.update_ticker(args.ticker, dry_run=dry_run)
        _print_result(r, dry_run)
        return

    # 高优先级: --sector + --subsector
    if args.sector and args.subsector:
        print(f"→ 更新 sector={args.sector} subsector={args.subsector}")
        r = updater.update_subsector(args.sector, args.subsector, dry_run=dry_run)
        print(f"  更新: {r['updated']}  跳过(private): {r['skipped']}  失败: {r['failed']}")
        for d in r.get("details", []):
            _print_result(d, dry_run)
        return

    # 批量模式
    if args.all:
        r = updater.update_all(stale_only=False, dry_run=dry_run)
    elif args.stale_only:
        r = updater.update_all(stale_only=True, dry_run=dry_run)
    else:
        parser.print_help()
        return

    _print_batch_summary(r, dry_run)


def _print_batch_summary(r, dry_run):
    action_label = "预览可更新" if dry_run else "已更新"
    print(f"\n=== 更新摘要 ===")
    print(f"  总处理: {r.get('total', 0)}")
    print(f"  {action_label}: {r['updated']}")
    print(f"  跳过(private): {r['skipped_private']}")
    print(f"  失败: {r['failed']}")
    if r.get("stale_count"):
        print(f"  过期: {r['stale_count']}")
    for d in r.get("details", []):
        _print_result(d, dry_run, compact=True)
    if dry_run:
        print("\n🔔 预览模式完成，使用 --write 写入 YAML")


def _print_result(r, dry_run, compact=False):
    t = r.get("ticker", "?")
    failed = r.get("failed", 0)

    if failed:
        err = r.get("error") or r.get("warning", "unknown error")
        print(f"  ⚠ {t}: FAILED — {err}"[:150])
        return

    # 展示字段
    mkt_cap = r.get("market_cap")
    rev = r.get("revenue")
    ps = r.get("ps")
    pe = r.get("pe")
    dq = r.get("data_quality", "?")
    nr = r.get("needs_refresh")
    warning = r.get("warning")
    currency = r.get("currency")

    status = "WRITE" if not dry_run else "preview"
    parts = [f"PS={ps}" if ps is not None else "PS=--"]
    parts.append(f"PE={pe}" if pe is not None else "PE=--")
    if mkt_cap is not None:
        parts.append(f"市值(HKD M)={mkt_cap}")
    if rev is not None:
        parts.append(f"收入(HKD M)={rev}")
    if currency:
        parts.append(f"币种={currency}")
    parts.append(f"质量={dq}")
    parts.append(f"{'需刷新' if nr else 'ok'}")

    icon = "✓" if not warning else "⚠"
    line = f"  {icon} {t}: {' | '.join(parts)} ({status})"
    print(line[:160])

    if warning:
        print(f"     ⚠ warning: {warning}"[:150])


if __name__ == "__main__":
    main()
