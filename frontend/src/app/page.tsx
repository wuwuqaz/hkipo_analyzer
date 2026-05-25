"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { fetchJobStatus, fetchLiveResults, triggerLiveAnalyze } from "@/lib/api";
import type { LiveResultsResponse } from "@/lib/types";
import { Loading } from "@/components/Loading";
import { ErrorDisplay } from "@/components/ErrorDisplay";
import { EmptyState } from "@/components/EmptyState";
import { ResultSection } from "@/components/results/ResultSection";
import { CompanyHeader } from "@/components/results/CompanyHeader";
import { ScoreBoard } from "@/components/results/ScoreBoard";
import { DimensionGrid } from "@/components/results/DimensionGrid";
import { SignalBreakdown } from "@/components/results/SignalBreakdown";
import { ValuationCard } from "@/components/results/ValuationCard";
import { PeerTable } from "@/components/results/PeerTable";
import { PeerComparisonFull } from "@/components/results/PeerComparisonFull";
import { CornerstoneDetail } from "@/components/results/CornerstoneDetail";
import { StockQualityCard } from "@/components/results/StockQualityCard";
import { RiskPanel } from "@/components/results/RiskPanel";
import { BloggerConsensusCard } from "@/components/BloggerConsensusCard";
import {
  ScoreWaterfall,
  ScoreReasons,
  InfoBasic,
  InfoFinancials,
  InfoDeep,
  BusinessSegments,
  FisherLynch,
} from "@/components/results/DetailViewExtras";
import { InvestSkillPanel } from "@/components/results/InvestSkillPanel";
import { CompanyProfileCard } from "@/components/results/CompanyProfileCard";

function StatusBadge({ label, tone = "text-[var(--muted)]" }: { label: string; tone?: string }) {
  return (
    <span className={`inline-flex items-center rounded-full border border-[var(--border)] bg-white/8 px-3 py-1 text-xs font-semibold uppercase tracking-[0.28em] ${tone}`}>
      {label}
    </span>
  );
}

function MetricCard({ title, value, tone = "text-[var(--foreground)]" }: { title: string; value: string; tone?: string }) {
  return (
    <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3.5 shadow-[0_8px_32px_rgba(3,8,18,0.25)] backdrop-blur">
      <p className="text-xs uppercase tracking-[0.15em] text-[var(--muted)]">{title}</p>
      <p className={`mt-2 text-xl font-semibold ${tone}`}>{value}</p>
    </article>
  );
}

function FilterCheckbox({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-[var(--border)] bg-white/5 px-4 py-2.5 text-sm text-[var(--foreground)] transition hover:bg-white/8">
      <input type="checkbox" className="h-4 w-4 accent-[var(--accent)]" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

function ScorePill({ score }: { score: number }) {
  let tone = "text-[var(--danger)]";
  if (score >= 70) tone = "text-[var(--success)]";
  else if (score >= 50) tone = "text-[var(--warning)]";
  return <span className={`font-semibold ${tone}`}>{score}</span>;
}

function HeatPill({ label }: { label: string }) {
  let tone = "text-[var(--foreground)]";
  if (label === "热门" || label === "极热") tone = "text-[var(--danger)]";
  else if (label === "温" || label === "一般") tone = "text-[var(--warning)]";
  return <span className={`text-sm ${tone}`}>{label}</span>;
}

function safeNumber(val: unknown): number {
  const n = Number(val);
  return Number.isFinite(n) ? n : 0;
}

function formatDate(val: unknown, fallback?: unknown): string {
  const s = String(val || "").trim();
  if (s && s !== "--" && s !== "null" && s !== "undefined") return s;
  const fb = String(fallback || "").trim();
  if (fb && fb !== "--" && fb !== "null" && fb !== "undefined") return fb;
  return "--";
}

function DataQualityBadge({ flags, confidence }: { flags?: string[]; confidence?: string }) {
  const hasIssue = (flags && flags.length > 0) || confidence === "needs_review" || confidence === "low";
  const severe = flags && flags.some((f) => f.includes("不一致") || f.includes("冲突"));
  if (severe) {
    return <span className="ml-2 inline-flex items-center rounded-full bg-[var(--danger)]/10 px-2 py-0.5 text-xs font-medium text-[var(--danger)]">需复核</span>;
  }
  if (hasIssue) {
    return <span className="ml-2 inline-flex items-center rounded-full bg-[var(--warning)]/10 px-2 py-0.5 text-xs font-medium text-[var(--warning)]">中</span>;
  }
  return <span className="ml-2 inline-flex items-center rounded-full bg-[var(--success)]/10 px-2 py-0.5 text-xs font-medium text-[var(--success)]">高</span>;
}

export default function DashboardPage() {
  const [data, setData] = useState<LiveResultsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [filterHighScore, setFilterHighScore] = useState(false);
  const [filterLowRisk, setFilterLowRisk] = useState(false);
  const [filterHasCornerstone, setFilterHasCornerstone] = useState(false);
  const [filterValuationOk, setFilterValuationOk] = useState(false);

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
    return data.results.find((r) => String(r["hk_code"] ?? r["stock_code"] ?? "") === selectedCode) ?? null;
  }, [selectedCode, data]);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetchLiveResults();
      setData(res);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load live IPO data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
      if (!cancelled) {
        load().catch(() => {});
      }
    }, 0);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [load]);

  async function handleRefresh(force: boolean) {
    if (pollRef.current) clearInterval(pollRef.current);
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    pollRef.current = null;
    timeoutRef.current = null;
    setRefreshing(true);
    setError(null);
    try {
      const job = await triggerLiveAnalyze(force);
      let done = false;

      const stopPolling = () => {
        if (pollRef.current) clearInterval(pollRef.current);
        if (timeoutRef.current) clearTimeout(timeoutRef.current);
        pollRef.current = null;
        timeoutRef.current = null;
      };

      const pollJob = async () => {
        try {
          const status = await fetchJobStatus(job.job_id);
          if (status.status === "success") {
            done = true;
            stopPolling();
            await load();
            setRefreshing(false);
            return;
          }
          if (status.status === "failed" || status.status === "not_found") {
            done = true;
            stopPolling();
            setRefreshing(false);
            setError(status.error || `Refresh job ${status.status}`);
          }
        } catch (err) {
          done = true;
          stopPolling();
          setRefreshing(false);
          setError(err instanceof Error ? err.message : "Refresh status check failed");
        }
      };

      await pollJob();
      if (done) return;

      const poll = setInterval(pollJob, 2000);
      pollRef.current = poll;
      const safetyTimeout = setTimeout(() => {
        stopPolling();
        setRefreshing(false);
        load().catch((err) => {
          setError(err instanceof Error ? err.message : "Refresh timed out");
        });
      }, 120000);
      timeoutRef.current = safetyTimeout;
    } catch (err) {
      if (pollRef.current) clearInterval(pollRef.current);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      pollRef.current = null;
      timeoutRef.current = null;
      setRefreshing(false);
      setError(err instanceof Error ? err.message : "Refresh failed");
    }
  }

  const filtered = useMemo(() => {
    if (!data?.results) return [];
    return data.results.filter((ipo) => {
      const tradeScore = safeNumber(ipo["strict_ipo_score"] ?? ipo["ipo_trade_score"] ?? ipo["trade_score"] ?? ipo["score"] ?? 0);
      const riskPenalty = safeNumber(ipo["risk_penalty"] ?? 0);
      const cs = (ipo["prospectus_info"] as Record<string, unknown> | undefined)?.["cornerstone_analysis"] as Record<string, unknown> | undefined;
      const hasCs = cs && safeNumber(cs["score"] ?? 0) > 0;
      const valLabel = String(ipo["valuation_pressure_label"] ?? "");
      const valOk = valLabel === "合理" || valLabel === "低估";

      if (filterHighScore && tradeScore < 65) return false;
      if (filterLowRisk && riskPenalty > 3) return false;
      if (filterHasCornerstone && !hasCs) return false;
      if (filterValuationOk && !valOk) return false;
      return true;
    });
  }, [data, filterHighScore, filterLowRisk, filterHasCornerstone, filterValuationOk]);

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
              onClick={() => handleRefresh(false)}
              disabled={refreshing}
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
              onClick={() => handleRefresh(true)}
              disabled={refreshing}
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
        <section className="mt-6">
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
                    const applyEnd = formatDate(ipo["apply_end_date"], md?.["EndDate"] ?? pi?.["apply_end_date"]);
                    const dqFlags = ipo["financial_data_quality_flags"] as string[] | undefined;
                    const dqConfidence = ipo["financial_extract_confidence"] as string | undefined;
                    return (
                      <tr
                        key={ipoCode}
                        onClick={() => setSelectedCode(selectedCode === ipoCode ? null : ipoCode)}
                        className="cursor-pointer border-b border-[var(--border)]/50 transition hover:bg-white/[0.03]"
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
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-strong)] p-5 shadow-[0_8px_32px_rgba(3,8,18,0.25)] backdrop-blur sm:p-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-2xl font-semibold text-white">
                  {String(selectedIpo["company_name"] ?? "--")}
                </h2>
                <p className="mt-1 text-sm text-[var(--muted)]">
                  股票代码: {String(selectedIpo["hk_code"] ?? "--")} · 截止日: {formatDate(selectedIpo["apply_end_date"], (selectedIpo["margin_detail"] as Record<string, unknown> | undefined)?.["EndDate"] ?? (selectedIpo["prospectus_info"] as Record<string, unknown> | undefined)?.["apply_end_date"])}
                </p>
              </div>
              <button
                onClick={() => setSelectedCode(null)}
                className="rounded-full border border-[var(--border)] bg-white/8 px-4 py-2 text-sm text-[var(--accent)] transition hover:bg-white/12"
              >
                收起
              </button>
            </div>

            <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {(() => {
                const detailScore = safeNumber(selectedIpo["score"]);
                const detailTradeScore = safeNumber(selectedIpo["trade_score"]);
                const longScore = safeNumber(selectedIpo["long_term_score"]);
                const valuationScore = safeNumber(selectedIpo["valuation_score"]);
                const fundamentalScore = safeNumber(selectedIpo["fundamental_score"]);
                const themeScore = safeNumber(selectedIpo["theme_score"]);
                const valuationPressure = String(selectedIpo["valuation_pressure_label"] ?? "--");
                const marketHeat = String(selectedIpo["market_heat"] ?? "");
                const overSub = selectedIpo["over_sub_ratio"];
                return (
                  <>
                    <MetricCard
                      title="综合评分"
                      value={detailScore ? String(detailScore) : "--"}
                      tone={detailScore >= 60 ? "text-[var(--success)]" : "text-[var(--warning)]"}
                    />
                    <MetricCard
                      title="交易信号"
                      value={detailTradeScore ? String(detailTradeScore) : "--"}
                      tone={detailTradeScore >= 60 ? "text-[var(--accent)]" : "text-[var(--muted)]"}
                    />
                    <MetricCard
                      title="长期价值"
                      value={longScore ? String(longScore) : "--"}
                      tone={longScore >= 60 ? "text-[var(--success)]" : longScore >= 40 ? "text-[var(--warning)]" : "text-[var(--danger)]"}
                    />
                    <MetricCard
                      title="估值吸引力"
                      value={valuationScore ? String(valuationScore) : "--"}
                      tone={valuationScore >= 60 ? "text-[var(--success)]" : "text-[var(--warning)]"}
                    />
                  </>
                );
              })()}
            </div>
            {/* 维度分解与关键信息 */}
            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {(() => {
                const fundamentalScore = safeNumber(selectedIpo["fundamental_score"]);
                const valuationPressure = String(selectedIpo["valuation_pressure_label"] ?? "--");
                const marketHeat = String(selectedIpo["market_heat"] ?? "");
                const overSub = selectedIpo["over_sub_ratio"];
                const themeScore = safeNumber(selectedIpo["theme_score"]);
                const sector = String((selectedIpo["prospectus_info"] as Record<string, unknown> | undefined)?.["sector"] ?? "");
                return (
                  <>
                    <MetricCard
                      title="基本面"
                      value={fundamentalScore ? String(fundamentalScore) : "--"}
                      tone={fundamentalScore >= 60 ? "text-[var(--success)]" : "text-[var(--warning)]"}
                    />
                    <MetricCard
                      title="估值压力"
                      value={valuationPressure}
                      tone={valuationPressure === "高" ? "text-[var(--danger)]" : valuationPressure === "中" ? "text-[var(--warning)]" : "text-[var(--success)]"}
                    />
                    <MetricCard
                      title="市场热度"
                      value={marketHeat || (overSub !== undefined && overSub !== null ? `超购 ${Number(overSub).toFixed(1)}x` : "--")}
                      tone={marketHeat === "极热" || marketHeat === "热门" ? "text-[var(--danger)]" : marketHeat === "温和" ? "text-[var(--warning)]" : "text-[var(--muted)]"}
                    />
                    <MetricCard
                      title="主题赛道"
                      value={sector || (themeScore ? `主题分 ${themeScore}` : "--")}
                      tone="text-[var(--foreground)]"
                    />
                  </>
                );
              })()}
            </div>
            {/* 严格打新限制与长期价值惩罚 */}
            {(() => {
              const strictScore = safeNumber(selectedIpo["strict_ipo_score"] ?? selectedIpo["ipo_trade_score"] ?? 0);
              const strictCapReasons = (selectedIpo["strict_cap_reasons"] as string[] | undefined) ?? [];
              const hasStrictCap = strictCapReasons.length > 0 && strictScore < safeNumber(selectedIpo["score"]);
              const rawLong = safeNumber(selectedIpo["raw_long_term_score_before_penalty"]);
              const longPen = safeNumber(selectedIpo["long_term_penalty"]);
              const longPenReasons = (selectedIpo["long_term_penalty_reasons"] as string[] | undefined) ?? [];
              const longScore = safeNumber(selectedIpo["long_term_score"]);
              if (!hasStrictCap && !(longPen > 0 && longPenReasons.length > 0)) return null;
              return (
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  {hasStrictCap && (
                    <div className="rounded-xl border border-[var(--warning)]/20 bg-[var(--warning)]/5 p-3">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-[var(--warning)]">⚠️ 严格打新限制</span>
                        <span className="font-mono text-sm text-[var(--foreground)]">
                          {strictScore} <span className="text-[var(--muted)]">(原计算 {safeNumber(selectedIpo["score"])})</span>
                        </span>
                      </div>
                      <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-[var(--muted)]">
                        {strictCapReasons.map((r, i) => (
                          <li key={i}>{r}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {longPen > 0 && longPenReasons.length > 0 && (
                    <div className="rounded-xl border border-[var(--border)]/50 bg-[var(--surface)] p-3">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-[var(--muted)]">长期价值分计算</span>
                        <span className="font-mono text-sm text-[var(--foreground)]">
                          {rawLong} − {longPen} = {longScore}
                        </span>
                      </div>
                      <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[10px] text-[var(--muted)]">
                        {longPenReasons.map((r, i) => (
                          <li key={i}>{r}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              );
            })()}

            <div className="mt-6 flex flex-wrap gap-3">
              <Link
                href={`/reanalyze?stock_code=${encodeURIComponent(String(selectedIpo["hk_code"] ?? ""))}&company_name=${encodeURIComponent(String(selectedIpo["company_name"] ?? ""))}`}
                className="inline-flex items-center gap-2 rounded-xl bg-[var(--accent)]/10 px-5 py-2.5 text-sm font-semibold text-[var(--accent)] transition hover:bg-[var(--accent)]/20"
              >
                🔁 重新分析
              </Link>
              <Link
                href="/upload"
                className="inline-flex items-center gap-2 rounded-xl border border-[var(--border)] bg-white/5 px-5 py-2.5 text-sm font-medium text-[var(--foreground)] transition hover:bg-white/8"
              >
                📤 上传招股书
              </Link>
            </div>
          </div>

          {/* Full analysis panels */}
          <div className="mt-8 space-y-8">
            {/* 公司简介 */}
            <div>
              <div className="mb-4 flex items-center gap-3">
                <span className="inline-block h-5 w-1 rounded-full bg-[var(--accent)]" />
                <h3 className="text-base font-semibold text-white">公司信息</h3>
              </div>
              <ResultSection title="公司信息">
                <CompanyHeader result={selectedIpo} />
              </ResultSection>
              {(() => {
                const pi = (selectedIpo.prospectus_info as Record<string, unknown> | undefined) || {};
                const profile = pi.company_profile as Record<string, unknown> | undefined;
                if (!profile) return null;
                const confidence = String(profile.confidence ?? "");
                if (confidence === "missing") return null;
                return (
                  <div className="mt-4">
                    <ResultSection title="公司简介">
                      <CompanyProfileCard result={selectedIpo} />
                    </ResultSection>
                  </div>
                );
              })()}
            </div>

            {/* 评分分析 */}
            <div>
              <div className="mb-4 flex items-center gap-3">
                <span className="inline-block h-5 w-1 rounded-full bg-[var(--accent)]" />
                <h3 className="text-base font-semibold text-white">评分分析</h3>
              </div>
              <div className="grid gap-4 lg:grid-cols-2">
                <ResultSection title="评分概览">
                  <ScoreBoard result={selectedIpo} />
                </ResultSection>
                <ResultSection title="评分理由">
                  <ScoreReasons result={selectedIpo} />
                </ResultSection>
              </div>
              <div className="mt-4 grid gap-4 lg:grid-cols-2">
                <ResultSection title="综合分拆解 (Waterfall)">
                  <ScoreWaterfall result={selectedIpo} />
                </ResultSection>
                <ResultSection title="维度拆解">
                  <DimensionGrid result={selectedIpo} />
                </ResultSection>
              </div>
            </div>

            {/* 估值与同行 */}
            <div>
              <div className="mb-4 flex items-center gap-3">
                <span className="inline-block h-5 w-1 rounded-full bg-[var(--success)]" />
                <h3 className="text-base font-semibold text-white">估值与同行</h3>
              </div>
              <ResultSection title="估值分析">
                <ValuationCard result={selectedIpo} />
              </ResultSection>
              <div className="mt-4 grid gap-4 lg:grid-cols-2">
                <ResultSection title="同行对比">
                  <PeerTable result={selectedIpo} />
                </ResultSection>
                <ResultSection title="同行对比 (详细)">
                  <PeerComparisonFull result={selectedIpo} />
                </ResultSection>
              </div>
            </div>

            {/* 投资参考 */}
            <div>
              <div className="mb-4 flex items-center gap-3">
                <span className="inline-block h-5 w-1 rounded-full bg-[var(--warning)]" />
                <h3 className="text-base font-semibold text-white">投资参考</h3>
              </div>
              <div className="grid gap-4 lg:grid-cols-2">
                <ResultSection title="交易信号">
                  <SignalBreakdown result={selectedIpo} />
                </ResultSection>
                <ResultSection title="基石投资者">
                  <CornerstoneDetail result={selectedIpo} />
                </ResultSection>
              </div>
              <div className="mt-4 grid gap-4 lg:grid-cols-2">
                <ResultSection title="股票质地">
                  <StockQualityCard result={selectedIpo} />
                </ResultSection>
                <ResultSection title="风险提示">
                  <RiskPanel result={selectedIpo} />
                </ResultSection>
              </div>
              {Boolean(selectedIpo["hk_code"]) && (
                <div className="mt-4">
                  <ResultSection title="博主观点">
                    <BloggerConsensusCard stockCode={String(selectedIpo["hk_code"])} />
                  </ResultSection>
                </div>
              )}
            </div>

            {/* 深度分析 */}
            <div>
              <div className="mb-4 flex items-center gap-3">
                <span className="inline-block h-5 w-1 rounded-full bg-[var(--danger)]" />
                <h3 className="text-base font-semibold text-white">深度分析</h3>
              </div>
              <div className="mt-4 grid gap-4 lg:grid-cols-2">
                <ResultSection title="基本信息">
                  <InfoBasic result={selectedIpo} />
                </ResultSection>
                <ResultSection title="核心财务">
                  <InfoFinancials result={selectedIpo} />
                </ResultSection>
              </div>
              <div className="mt-4 grid gap-4 lg:grid-cols-2">
                <ResultSection title="深度分析">
                  <InfoDeep result={selectedIpo} />
                </ResultSection>
                <div className="space-y-4">
                  <ResultSection title="业务分部">
                    <BusinessSegments result={selectedIpo} />
                  </ResultSection>
                  <ResultSection title="长线视角">
                    <FisherLynch result={selectedIpo} />
                  </ResultSection>
                  <ResultSection title="专业投资框架">
                    <InvestSkillPanel result={selectedIpo} />
                  </ResultSection>
                </div>
              </div>
            </div>
          </div>
        </section>
      )}
    </main>
  );
}
