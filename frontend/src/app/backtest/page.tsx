"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { fetchIpoFirstDayBacktest, fetchBacktestStatus } from "@/lib/api";
import type { BacktestGroupStats, BacktestRecordItem, IpoFirstDayBacktestResponse } from "@/lib/types";
import { Loading } from "@/components/Loading";
import { ErrorDisplay } from "@/components/ErrorDisplay";
import { EmptyState } from "@/components/EmptyState";

function fmtPct(v: number): string {
  if (v === 0) return "--";
  return `${(v * 100).toFixed(1)}%`;
}

function fmtRet(v: number): string {
  if (v === 0) return "--";
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function retColor(v: number): string {
  if (v > 0) return "text-[var(--success)]";
  if (v < 0) return "text-[var(--danger)]";
  return "text-[var(--muted)]";
}

function GroupTable({ title, groups }: { title: string; groups: Record<string, BacktestGroupStats> }) {
  const sorted = useMemo(
    () => Object.entries(groups).sort((a, b) => b[1].count - a[1].count),
    [groups]
  );

  if (sorted.length === 0) return null;

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5 shadow-[0_8px_32px_rgba(3,8,18,0.25)] backdrop-blur">
      <h3 className="mb-4 text-base font-semibold text-white">{title}</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] text-xs uppercase tracking-wider text-[var(--muted)]">
              <th className="px-3 py-2 font-medium">分组</th>
              <th className="px-3 py-2 font-medium text-right">样本数</th>
              <th className="px-3 py-2 font-medium text-right">上涨率</th>
              <th className="px-3 py-2 font-medium text-right">中位涨幅</th>
              <th className="px-3 py-2 font-medium text-right">平均涨幅</th>
              <th className="px-3 py-2 font-medium text-right">50%+大肉率</th>
              <th className="px-3 py-2 font-medium text-right">破发率</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map(([name, s]) => (
              <tr key={name} className="border-b border-[var(--border)]/30 hover:bg-white/[0.02]">
                <td className="px-3 py-2 font-medium text-[var(--foreground)]">{name}</td>
                <td className="px-3 py-2 text-right">{s.count}</td>
                <td className="px-3 py-2 text-right">{fmtPct(s.win_rate)}</td>
                <td className={`px-3 py-2 text-right font-medium ${retColor(s.median_return)}`}>{fmtRet(s.median_return)}</td>
                <td className={`px-3 py-2 text-right ${retColor(s.mean_return)}`}>{fmtRet(s.mean_return)}</td>
                <td className="px-3 py-2 text-right">{fmtPct(s.big_meat_50_rate)}</td>
                <td className="px-3 py-2 text-right text-[var(--danger)]">{fmtPct(s.break_rate)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MatrixTable({ matrix }: { matrix: Record<string, BacktestGroupStats> }) {
  const rows = ["good", "weak"];
  const cols = ["strong", "weak"];

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5 shadow-[0_8px_32px_rgba(3,8,18,0.25)] backdrop-blur">
      <h3 className="mb-4 text-base font-semibold text-white">底色 x 风向 矩阵</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] text-xs uppercase tracking-wider text-[var(--muted)]">
              <th className="px-3 py-2 font-medium">底色</th>
              <th className="px-3 py-2 font-medium">风向</th>
              <th className="px-3 py-2 font-medium text-right">样本数</th>
              <th className="px-3 py-2 font-medium text-right">上涨率</th>
              <th className="px-3 py-2 font-medium text-right">中位涨幅</th>
              <th className="px-3 py-2 font-medium text-right">平均涨幅</th>
              <th className="px-3 py-2 font-medium text-right">50%+大肉率</th>
              <th className="px-3 py-2 font-medium text-right">破发率</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((bg) =>
              cols.map((wg) => {
                const key = `${bg}_x_${wg}`;
                const s = matrix[key];
                if (!s) return null;
                return (
                  <tr key={key} className="border-b border-[var(--border)]/30 hover:bg-white/[0.02]">
                    <td className="px-3 py-2 font-medium text-[var(--accent)]">{bg}</td>
                    <td className="px-3 py-2 text-[var(--foreground)]">{wg}</td>
                    <td className="px-3 py-2 text-right">{s.count}</td>
                    <td className="px-3 py-2 text-right">{fmtPct(s.win_rate)}</td>
                    <td className={`px-3 py-2 text-right font-medium ${retColor(s.median_return)}`}>{fmtRet(s.median_return)}</td>
                    <td className={`px-3 py-2 text-right ${retColor(s.mean_return)}`}>{fmtRet(s.mean_return)}</td>
                    <td className="px-3 py-2 text-right">{fmtPct(s.big_meat_50_rate)}</td>
                    <td className="px-3 py-2 text-right text-[var(--danger)]">{fmtPct(s.break_rate)}</td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SortHeader({
  col,
  sortCol,
  sortAsc,
  onSort,
  children,
}: {
  col: string;
  sortCol: string;
  sortAsc: boolean;
  onSort: (col: string) => void;
  children: ReactNode;
}) {
  const active = sortCol === col;
  return (
    <th
      className="cursor-pointer px-3 py-2 font-medium select-none hover:text-[var(--accent)]"
      onClick={() => onSort(col)}
    >
      {children} {active ? (sortAsc ? "↑" : "↓") : ""}
    </th>
  );
}

function RecordsTable({ records }: { records: BacktestRecordItem[] }) {
  const [sortCol, setSortCol] = useState<string>("listing_date");
  const [sortAsc, setSortAsc] = useState(false);

  const sorted = useMemo(() => {
    const arr = [...records];
    arr.sort((a, b) => {
      const av = (a as Record<string, unknown>)[sortCol];
      const bv = (b as Record<string, unknown>)[sortCol];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      const cmp = typeof av === "string" ? av.localeCompare(bv as string) : (av as number) - (bv as number);
      return sortAsc ? cmp : -cmp;
    });
    return arr;
  }, [records, sortCol, sortAsc]);

  function handleSort(col: string) {
    if (sortCol === col) {
      setSortAsc(!sortAsc);
    } else {
      setSortCol(col);
      setSortAsc(true);
    }
  }

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5 shadow-[0_8px_32px_rgba(3,8,18,0.25)] backdrop-blur">
      <h3 className="mb-4 text-base font-semibold text-white">个股明细 ({records.length})</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] text-xs uppercase tracking-wider text-[var(--muted)]">
              <SortHeader col="hk_code" sortCol={sortCol} sortAsc={sortAsc} onSort={handleSort}>代码</SortHeader>
              <SortHeader col="company_name" sortCol={sortCol} sortAsc={sortAsc} onSort={handleSort}>公司</SortHeader>
              <SortHeader col="listing_date" sortCol={sortCol} sortAsc={sortAsc} onSort={handleSort}>上市日</SortHeader>
              <SortHeader col="first_day_return" sortCol={sortCol} sortAsc={sortAsc} onSort={handleSort}>首日涨幅</SortHeader>
              <th className="px-3 py-2 font-medium text-right">超购倍数</th>
              <th className="px-3 py-2 font-medium">绿鞋</th>
              <th className="px-3 py-2 font-medium text-right">基石%</th>
              <th className="px-3 py-2 font-medium">基石独立性</th>
              <th className="px-3 py-2 font-medium">保荐弹性</th>
              <th className="px-3 py-2 font-medium">认购热度</th>
              <th className="px-3 py-2 font-medium">底色</th>
              <th className="px-3 py-2 font-medium">风向</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.hk_code} className="border-b border-[var(--border)]/30 hover:bg-white/[0.02]">
                <td className="px-3 py-2 font-mono text-[var(--accent)]">{r.hk_code}</td>
                <td className="px-3 py-2 text-[var(--foreground)]">{r.company_name}</td>
                <td className="px-3 py-2 text-[var(--muted)]">{r.listing_date || "--"}</td>
                <td className={`px-3 py-2 text-right font-medium ${retColor(r.first_day_return)}`}>{fmtRet(r.first_day_return)}</td>
                <td className="px-3 py-2 text-right">{r.over_sub_ratio > 0 ? `${r.over_sub_ratio.toFixed(0)}x` : "--"}</td>
                <td className="px-3 py-2">
                  {r.has_greenshoe === true ? (
                    <span className="text-[var(--success)]">有</span>
                  ) : r.has_greenshoe === false ? (
                    <span className="text-[var(--danger)]">无</span>
                  ) : (
                    <span className="text-[var(--muted)]">--</span>
                  )}
                </td>
                <td className="px-3 py-2 text-right">{r.cornerstone_pct != null ? `${r.cornerstone_pct.toFixed(1)}%` : "--"}</td>
                <td className="px-3 py-2 text-xs text-[var(--muted)]">{r.cornerstone_independence || "--"}</td>
                <td className="px-3 py-2 text-xs">{r.sponsor_elastic_group || "--"}</td>
                <td className="px-3 py-2 text-xs">{r.subscription_heat_group || "--"}</td>
                <td className="px-3 py-2">
                  {r.bottom_group === "good" ? (
                    <span className="rounded-full bg-[var(--success)]/10 px-2 py-0.5 text-xs text-[var(--success)]">good</span>
                  ) : (
                    <span className="rounded-full bg-[var(--danger)]/10 px-2 py-0.5 text-xs text-[var(--danger)]">weak</span>
                  )}
                </td>
                <td className="px-3 py-2">
                  {r.wind_group === "strong" ? (
                    <span className="rounded-full bg-[var(--success)]/10 px-2 py-0.5 text-xs text-[var(--success)]">strong</span>
                  ) : (
                    <span className="rounded-full bg-[var(--danger)]/10 px-2 py-0.5 text-xs text-[var(--danger)]">weak</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function BacktestPage() {
  const [data, setData] = useState<IpoFirstDayBacktestResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sampleCount, setSampleCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function fetchData() {
      setLoading(true);
      try {
        const status = await fetchBacktestStatus();
        if (!cancelled) setSampleCount(status.sample_count);

        if (!status.ready) {
          if (!cancelled) {
            setError(status.message);
            setLoading(false);
          }
          return;
        }

        const result = await fetchIpoFirstDayBacktest();
        if (!cancelled) {
          setData(result);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load backtest data");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    fetchData();
    return () => { cancelled = true; };
  }, []);

  async function handleRetry() {
    setLoading(true);
    try {
      const result = await fetchIpoFirstDayBacktest();
      setData(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load backtest data");
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-6 py-10 sm:px-10 lg:px-12">
        <Loading message="Loading backtest data..." />
      </main>
    );
  }

  if (error && !data) {
    return (
      <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-6 py-10 sm:px-10 lg:px-12">
        <section className="relative overflow-hidden rounded-[2rem] border border-[var(--border)] bg-[var(--surface-strong)] px-6 py-8 shadow-[0_32px_120px_rgba(3,8,18,0.55)] backdrop-blur sm:px-8 sm:py-10">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(114,230,255,0.18),transparent_32%),radial-gradient(circle_at_bottom_left,rgba(88,230,169,0.14),transparent_28%)]" />
          <div className="relative">
            <h1 className="text-3xl font-semibold tracking-tight text-white">IPO 首日回测</h1>
            <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
              基于历史 IPO 样本的「底色 x 风向」分组统计
            </p>
          </div>
        </section>
        <section className="mt-6">
          <EmptyState message={error} />
        </section>
        <p className="mt-4 text-sm text-[var(--muted)]">
          当前有效样本数: {sampleCount}。需要至少 3 条含首日涨幅数据的样本才能运行回测。
        </p>
      </main>
    );
  }

  if (!data) return null;

  const t = data.total;

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-6 py-10 sm:px-10 lg:px-12">
      {/* Hero */}
      <section className="relative overflow-hidden rounded-[2rem] border border-[var(--border)] bg-[var(--surface-strong)] px-6 py-8 shadow-[0_32px_120px_rgba(3,8,18,0.55)] backdrop-blur sm:px-8 sm:py-10">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(114,230,255,0.18),transparent_32%),radial-gradient(circle_at_bottom_left,rgba(88,230,169,0.14),transparent_28%)]" />
        <div className="relative">
          <h1 className="text-3xl font-semibold tracking-tight text-white">IPO 首日回测</h1>
          <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
            基于历史 IPO 样本的「底色 x 风向」分组统计 · 绿鞋 · 保荐人弹性 · 基石投资者 · 认购热度 · 市场风向
          </p>
          <p className="mt-1 text-xs text-[var(--muted)]">
            生成时间: {data.run_at}
          </p>
        </div>
      </section>

      {/* Stats */}
      <section className="mt-6 grid gap-4 md:grid-cols-5">
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
          <p className="text-xs uppercase tracking-wider text-[var(--muted)]">总样本数</p>
          <p className="mt-2 text-2xl font-semibold text-[var(--foreground)]">{t.count}</p>
        </div>
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
          <p className="text-xs uppercase tracking-wider text-[var(--muted)]">上涨率</p>
          <p className="mt-2 text-2xl font-semibold text-[var(--success)]">{fmtPct(t.win_rate)}</p>
        </div>
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
          <p className="text-xs uppercase tracking-wider text-[var(--muted)]">中位首日涨幅</p>
          <p className={`mt-2 text-2xl font-semibold ${retColor(t.median_return)}`}>{fmtRet(t.median_return)}</p>
        </div>
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
          <p className="text-xs uppercase tracking-wider text-[var(--muted)]">50%+ 大肉率</p>
          <p className="mt-2 text-2xl font-semibold text-[var(--warning)]">{fmtPct(t.big_meat_50_rate)}</p>
        </div>
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
          <p className="text-xs uppercase tracking-wider text-[var(--muted)]">破发率</p>
          <p className="mt-2 text-2xl font-semibold text-[var(--danger)]">{fmtPct(t.break_rate)}</p>
        </div>
      </section>

      {error && (
        <section className="mt-6" aria-live="polite" aria-atomic="true">
          <ErrorDisplay message={error} onRetry={handleRetry} />
        </section>
      )}

      {/* Group Tables */}
      <section className="mt-6 space-y-6">
        <GroupTable title="绿鞋分组" groups={data.greenshoe} />
        <GroupTable title="保荐人弹性分组" groups={data.sponsor_elastic} />
        <GroupTable title="基石比例分组" groups={data.cornerstone_pct} />
        <GroupTable title="基石独立性分组" groups={data.cornerstone_independence} />
        <GroupTable title="认购热度分组" groups={data.subscription_heat} />
        <GroupTable title="市场风向分组" groups={data.market_wind} />
        <MatrixTable matrix={data.bottom_x_wind} />
        <RecordsTable records={data.records} />
      </section>
    </main>
  );
}
