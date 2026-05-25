"use client";

import { useEffect, useMemo, useState } from "react";
import type { AnalysisResult } from "@/lib/types";
import { safeNumber } from "@/lib/utils";
import { Loading } from "@/components/Loading";
import { ErrorDisplay } from "@/components/ErrorDisplay";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge } from "@/components/dashboard/StatusBadge";
import { FilterCheckbox } from "@/components/dashboard/FilterCheckbox";
import { ScorePill } from "@/components/dashboard/ScorePill";
import { HeatPill } from "@/components/dashboard/HeatPill";
import { DataQualityBadge } from "@/components/dashboard/DataQualityBadge";
import { useLiveData } from "@/hooks/useLiveData";
import { useFilters } from "@/hooks/useFilters";
import { IpoDetailPanel } from "@/components/dashboard/IpoDetailPanel";

function fmtDate(val: unknown, fallback?: unknown): string {
  const s = String(val || "").trim();
  if (s && s !== "--" && s !== "null" && s !== "undefined") return s;
  const fb = String(fallback || "").trim();
  if (fb && fb !== "--" && fb !== "null" && fb !== "undefined") return fb;
  return "--";
}

export default function DashboardPage() {
  const { data, loading, refreshing, error, refresh, load } = useLiveData();
  const {
    filtered,
    filterHighScore, setFilterHighScore,
    filterLowRisk, setFilterLowRisk,
    filterHasCornerstone, setFilterHasCornerstone,
    filterValuationOk, setFilterValuationOk,
  } = useFilters(data?.results ?? []);

  const [selectedCode, setSelectedCode] = useState<string | null>(null);

  // 默认展开：只有一只IPO时自动展开详情
  useEffect(() => {
    let cancelled = false;
    if (data?.results && data.results.length === 1 && !selectedCode) {
      const code = String(data.results[0]["hk_code"] ?? data.results[0]["stock_code"] ?? "");
      if (code) {
        queueMicrotask(() => {
          if (!cancelled) setSelectedCode(code);
        });
      }
    }
    return () => {
      cancelled = true;
    };
  }, [data, selectedCode]);

  const selectedIpo = useMemo(() => {
    if (!selectedCode || !data?.results) return null;
    const found = data.results.find((r) => String(r["hk_code"] ?? r["stock_code"] ?? "") === selectedCode) ?? null;
    return found as unknown as AnalysisResult | null;
  }, [selectedCode, data]);

  if (loading) {
    return (
      <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col overflow-x-hidden px-6 py-10 sm:px-10 lg:px-12">
        <Loading message="Loading live IPO data…" />
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-6 py-10 sm:px-10 lg:px-12">
      {/* Hero */}
      <section className="relative overflow-hidden rounded-[2rem] border border-[var(--border)] bg-[var(--surface-strong)] px-6 py-8 shadow-[0_32px_120px_rgba(3,8,18,0.55)] backdrop-blur sm:px-8 sm:py-10">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(114,230,255,0.18),transparent_32%),radial-gradient(circle_at_bottom_left,rgba(88,230,169,0.14),transparent_28%)]" />
        <div className="relative flex flex-col gap-6">
          <StatusBadge label="Live Dashboard" tone="text-[var(--accent)]" />
          <div className="max-w-3xl">
            <h1 className="text-4xl font-semibold tracking-tight text-white sm:text-5xl">
              港股 IPO 打新分析
            </h1>
            <p className="mt-4 text-base leading-7 text-[var(--muted)] sm:text-lg">
              智能招股书解析 · 多维评分体系 · 一键生成报告
            </p>
          </div>
        </div>
      </section>

      {/* Controls */}
      <section className="mt-8">
        <div className="flex flex-col gap-4 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5 shadow-[0_8px_32px_rgba(3,8,18,0.25)] backdrop-blur sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => refresh(false)}
              disabled={refreshing}
              aria-label="更新IPO（使用缓存）"
              className="inline-flex cursor-pointer items-center gap-2 rounded-xl bg-[var(--accent)]/10 px-5 py-2.5 text-sm font-semibold text-[var(--accent)] transition hover:bg-[var(--accent)]/20 disabled:opacity-50"
            >
              {refreshing ? (
                <>
                  <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-[var(--border)] border-t-[var(--accent)]" />
                  刷新中…
                </>
              ) : (
                <>🔄 更新IPO（使用缓存）</>
              )}
            </button>
            <button
              onClick={() => refresh(true)}
              disabled={refreshing}
              aria-label="强制刷新（重新下载）"
              className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-[var(--border)] bg-white/5 px-5 py-2.5 text-sm font-medium text-[var(--foreground)] transition hover:bg-white/8 disabled:opacity-50"
            >
              ⚡ 强制刷新（重新下载）
            </button>
          </div>

          <div className="flex items-center gap-4">
            <div className="text-right">
              <p className="text-xs text-[var(--muted)]">最新缓存时间</p>
              <p className="text-sm font-medium text-[var(--foreground)]">{data?.cache_time ?? "暂无缓存"}</p>
            </div>
            <div className="text-right">
              <p className="text-xs text-[var(--muted)]">正在招股</p>
              <p className="text-sm font-medium text-[var(--accent)]">{data?.total ?? 0} 只</p>
            </div>
          </div>
        </div>

      </section>

      {/* Filters */}
      <section className="mt-6">
        <div className="flex flex-wrap gap-3">
          <FilterCheckbox label="🏆 打新高分（≥65）" checked={filterHighScore} onChange={setFilterHighScore} />
          <FilterCheckbox label="🛡️ 低风险" checked={filterLowRisk} onChange={setFilterLowRisk} />
          <FilterCheckbox label="🏛️ 有基石" checked={filterHasCornerstone} onChange={setFilterHasCornerstone} />
          <FilterCheckbox label="💰 估值合理" checked={filterValuationOk} onChange={setFilterValuationOk} />
        </div>
        <p className="mt-3 text-xs text-[var(--muted)]">
          显示 {filtered.length} / {data?.results.length ?? 0} 只IPO
        </p>
      </section>

      {error && (
        <section className="mt-6" aria-live="polite" aria-atomic="true">
          <ErrorDisplay message={error} onRetry={load} />
        </section>
      )}

      {/* Table */}
      <section className="mt-6 min-w-0 flex-1">
        {filtered.length === 0 ? (
          <EmptyState message="暂无正在招股的新股。点击「更新IPO」按钮获取最新数据。" />
        ) : (
          <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-[0_8px_32px_rgba(3,8,18,0.25)] backdrop-blur">
            <div className="max-w-full overflow-x-auto">
              <table className="w-full min-w-max text-left text-sm">
                <thead>
                  <tr className="border-b border-[var(--border)] text-xs uppercase tracking-wider text-[var(--muted)]">
                    <th className="px-5 py-4 font-medium">股票代码</th>
                    <th className="px-5 py-4 font-medium">公司名称</th>
                    <th className="px-5 py-4 font-medium text-right">打新分</th>
                    <th className="hidden px-5 py-4 font-medium text-right sm:table-cell">长线分</th>
                    <th className="px-5 py-4 font-medium">结论</th>
                    <th className="px-5 py-4 font-medium">热度</th>
                    <th className="hidden px-5 py-4 font-medium text-right md:table-cell">超购</th>
                    <th className="hidden px-5 py-4 font-medium text-right md:table-cell">孖展</th>
                    <th className="hidden px-5 py-4 font-medium sm:table-cell">截止日</th>
                    <th className="px-5 py-4 font-medium"></th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((ipo) => {
                    const tradeScore = safeNumber(ipo["strict_ipo_score"] ?? ipo["ipo_trade_score"] ?? ipo["trade_score"] ?? ipo["score"] ?? 0);
                    const longTermScore = safeNumber(ipo["long_term_score"] ?? 0);
                    const overSub =
                      (ipo["actual_over_sub_ratio"] ?? undefined) as number | undefined ??
                      (ipo["forecast_over_sub_ratio"] ?? undefined) as number | undefined ??
                      (ipo["over_sub_ratio"] ?? undefined) as number | undefined;
                    const ipoCode = String(ipo["hk_code"] ?? ipo["stock_code"] ?? "");
                    const md = ipo["margin_detail"] as Record<string, unknown> | undefined;
                    const pi = ipo["prospectus_info"] as Record<string, unknown> | undefined;
                    const applyEnd = fmtDate(ipo["apply_end_date"], md?.["EndDate"] ?? pi?.["apply_end_date"]);
                    const dqFlags = ipo["financial_data_quality_flags"] as string[] | undefined;
                    const dqConfidence = ipo["financial_extract_confidence"] as string | undefined;
                    return (
                      <tr
                        key={ipoCode}
                        onClick={() => setSelectedCode(selectedCode === ipoCode ? null : ipoCode)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            setSelectedCode(selectedCode === ipoCode ? null : ipoCode);
                          }
                        }}
                        tabIndex={0}
                        role="button"
                        aria-expanded={selectedCode === ipoCode}
                        aria-label={`查看 ${String(ipo["company_name"] ?? ipoCode)} 详情`}
                        className="cursor-pointer border-b border-[var(--border)]/50 transition hover:bg-white/[0.03] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]/50"
                      >
                        <td className="px-5 py-4 font-mono text-[var(--accent)]">{String(ipo["hk_code"] ?? "--")}</td>
                        <td className="px-5 py-4 font-medium text-[var(--foreground)]">{String(ipo["company_name"] ?? "--")}</td>
                        <td className="px-5 py-4 text-right"><ScorePill score={tradeScore} /></td>
                        <td className="hidden px-5 py-4 text-right sm:table-cell"><ScorePill score={longTermScore} /></td>
                        <td className="px-5 py-4">{String(ipo["subscription_recommendation"] ?? "--")}</td>
                        <td className="px-5 py-4"><HeatPill label={String(ipo["market_heat"] ?? "--")} /></td>
                        <td className="hidden px-5 py-4 text-right md:table-cell">{overSub ? `${Number(overSub).toFixed(1)}x` : "--"}</td>
                        <td className="hidden px-5 py-4 text-right md:table-cell">{ipo["margin_total_hkd_billion"] ? `${Number(ipo["margin_total_hkd_billion"]).toFixed(1)}亿` : (ipo["margin_total"] ? `${Number(ipo["margin_total"]).toFixed(1)}亿` : "--")}</td>
                        <td className="hidden px-5 py-4 sm:table-cell">{applyEnd}</td>
                        <td className="px-5 py-4">
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-[var(--muted)]">{selectedCode === ipoCode ? "收起" : "详情"}</span>
                            <DataQualityBadge flags={dqFlags} confidence={dqConfidence} />
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

      {/* Selected IPO detail */}
      {selectedIpo && (
        <section className="mt-8">
          <IpoDetailPanel ipo={selectedIpo} onClose={() => setSelectedCode(null)} />
        </section>
      )}
    </main>
  );
}
