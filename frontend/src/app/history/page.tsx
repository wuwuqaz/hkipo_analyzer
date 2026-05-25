"use client";

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  fetchHistoryRecords,
  trackHistoryRecord,
  trackAllHistoryRecords,
  uploadAllotmentPdf,
} from "@/lib/api";
import type { HistoryRecord } from "@/lib/types";
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
import { PostListingCard } from "@/components/results/PostListingCard";
import type { AnalysisResult } from "@/lib/types";
import {
  ScoreWaterfall,
  ScoreReasons,
  InfoBasic,
  InfoFinancials,
  InfoDeep,
  BusinessSegments,
  FisherLynch,
} from "@/components/results/DetailViewExtras";

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    "已完成": "bg-[var(--success)]",
    "待公告": "bg-[var(--warning)]",
    "部分": "bg-[var(--accent)]",
    "异常": "bg-[var(--danger)]",
    "未跟踪": "bg-[var(--muted)]",
  };
  return <span className={`inline-block h-2 w-2 rounded-full ${colors[status] ?? "bg-[var(--muted)]"}`} />;
}

function ScorePill({ score }: { score: number }) {
  let tone = "text-[var(--danger)]";
  if (score >= 70) tone = "text-[var(--success)]";
  else if (score >= 50) tone = "text-[var(--warning)]";
  return <span className={`font-semibold ${tone}`}>{score}</span>;
}

function formatNumber(v: unknown): string {
  if (v === null || v === undefined || v === "") return "--";
  const n = Number(v);
  if (isNaN(n)) return "--";
  if (n >= 100000000) return `${(n / 100000000).toFixed(1)}亿`;
  if (n >= 10000) return `${(n / 10000).toFixed(1)}万`;
  if (n >= 1) return n.toFixed(0);
  return n.toFixed(2);
}

function formatPrice(v: unknown): string {
  if (v === null || v === undefined || v === "") return "--";
  const n = Number(v);
  if (isNaN(n)) return "--";
  return `HK$${n.toFixed(2)}`;
}

function formatLots(v: unknown): string {
  if (v === null || v === undefined || v === "") return "--";
  const n = Number(v);
  if (isNaN(n) || n <= 0) return "--";
  if (n >= 10000) return `${(n / 10000).toFixed(1)}万手`;
  return `${n.toFixed(0)}手`;
}

function getPublicOfferLots(r: HistoryRecord): string {
  const raw = r._raw || {};
  const lots = raw.public_offer_lots;
  if (lots !== null && lots !== undefined) return formatLots(lots);
  const hkShares = raw.hk_offer_shares;
  const lotSize = raw.lot_size || raw.board_lot;
  if (hkShares && lotSize) {
    const calculated = Number(hkShares) / Number(lotSize);
    return formatLots(calculated);
  }
  return "--";
}

export default function HistoryPage() {
  const [records, setRecords] = useState<HistoryRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedCode, setExpandedCode] = useState<string | null>(null);

  const [query, setQuery] = useState("");
  const [showLive, setShowLive] = useState(true);
  const [sortBy, setSortBy] = useState("截止日从近到远");
  const [trackingStatus, setTrackingStatus] = useState("全部");

  const [trackLoading, setTrackLoading] = useState<string | null>(null);
  const [trackAllLoading, setTrackAllLoading] = useState(false);
  const [trackAllResult, setTrackAllResult] = useState<string | null>(null);
  const [forceRefresh, setForceRefresh] = useState(false);

  const filtersRef = useRef({ query, showLive, sortBy, trackingStatus });
  useEffect(() => {
    filtersRef.current = { query, showLive, sortBy, trackingStatus };
  });

  useEffect(() => {
    let cancelled = false;
    async function fetchData() {
      const f = filtersRef.current;
      setLoading(true);
      try {
        const data = await fetchHistoryRecords(
          f.query || undefined,
          f.showLive,
          f.sortBy,
          f.trackingStatus === "全部" ? undefined : f.trackingStatus
        );
        if (!cancelled) {
          setRecords(data.records);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load history");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    fetchData();
    return () => { cancelled = true; };
  }, [showLive, sortBy, trackingStatus]);

  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(async () => {
      const f = filtersRef.current;
      setLoading(true);
      try {
        const data = await fetchHistoryRecords(
          f.query || undefined,
          f.showLive,
          f.sortBy,
          f.trackingStatus === "全部" ? undefined : f.trackingStatus
        );
        if (!cancelled) {
          setRecords(data.records);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load history");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }, 300);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [query]);

  async function handleRetry() {
    setLoading(true);
    try {
      const data = await fetchHistoryRecords(
        query || undefined,
        showLive,
        sortBy,
        trackingStatus === "全部" ? undefined : trackingStatus
      );
      setRecords(data.records);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load history");
    } finally {
      setLoading(false);
    }
  }

  const stats = useMemo(() => {
    const total = records.length;
    const tracked = records.filter((r) => r.has_post_listing).length;
    const live = records.filter((r) => {
      const end = r.apply_end_date;
      if (!end || end === "--") return false;
      return new Date(end) >= new Date();
    }).length;
    return { total, tracked, live };
  }, [records]);

  void expandedCode;

  if (loading && records.length === 0) {
    return (
      <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-6 py-10 sm:px-10 lg:px-12">
        <Loading message="Loading history…" />
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-6 py-10 sm:px-10 lg:px-12">
      {/* Hero */}
      <section className="relative overflow-hidden rounded-[2rem] border border-[var(--border)] bg-[var(--surface-strong)] px-6 py-8 shadow-[0_32px_120px_rgba(3,8,18,0.55)] backdrop-blur sm:px-8 sm:py-10">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(114,230,255,0.18),transparent_32%),radial-gradient(circle_at_bottom_left,rgba(88,230,169,0.14),transparent_28%)]" />
        <div className="relative">
          <h1 className="text-3xl font-semibold tracking-tight text-white">历史 IPO 分析</h1>
          <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
            历史归档 · 回溯重分析 · 配发结果与上市后表现跟踪
          </p>
        </div>
      </section>

      {/* Stats */}
      <section className="mt-6 grid gap-4 md:grid-cols-3">
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
          <p className="text-xs uppercase tracking-wider text-[var(--muted)]">历史股票数</p>
          <p className="mt-2 text-2xl font-semibold text-[var(--foreground)]">{stats.total}</p>
        </div>
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
          <p className="text-xs uppercase tracking-wider text-[var(--muted)]">已跟踪</p>
          <p className="mt-2 text-2xl font-semibold text-[var(--success)]">{stats.tracked}</p>
        </div>
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
          <p className="text-xs uppercase tracking-wider text-[var(--muted)]">仍在招股</p>
          <p className="mt-2 text-2xl font-semibold text-[var(--accent)]">{stats.live}</p>
        </div>
      </section>

      {/* Track All */}
      <section className="mt-4 flex flex-wrap items-center gap-3">
        <button
          onClick={async () => {
            setTrackAllLoading(true);
            setTrackAllResult(null);
            try {
              const result = await trackAllHistoryRecords(forceRefresh);
              setTrackAllResult(`处理 ${result.processed}，更新 ${result.updated}，失败 ${result.failed}`);
              handleRetry();
            } catch (err) {
              setTrackAllResult(err instanceof Error ? err.message : "跟踪失败");
            } finally {
              setTrackAllLoading(false);
            }
          }}
          disabled={trackAllLoading}
          aria-label="跟踪全部已结束待更新的IPO"
          className="inline-flex items-center gap-2 rounded-xl bg-[var(--accent)]/10 px-5 py-2.5 text-sm font-semibold text-[var(--accent)] transition hover:bg-[var(--accent)]/20 disabled:opacity-50"
        >
          {trackAllLoading ? "⏳ 跟踪中..." : "📡 跟踪全部已结束待更新"}
        </button>
        <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-[var(--muted)]">
          <input
            type="checkbox"
            className="h-4 w-4 accent-[var(--accent)]"
            checked={forceRefresh}
            onChange={(e) => setForceRefresh(e.target.checked)}
          />
          强制刷新
        </label>
        {trackAllResult && (
          <span className="text-sm text-[var(--muted)]" aria-live="polite" aria-atomic="true">{trackAllResult}</span>
        )}
      </section>

      {/* Filters */}
      <section className="mt-6 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5 shadow-[0_8px_32px_rgba(3,8,18,0.25)] backdrop-blur">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
          <div className="flex-1">
            <label className="block text-sm font-medium text-[var(--muted)]">搜索</label>
            <input
              type="text"
              placeholder="股票代码 / 公司名称"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="mt-1.5 w-full rounded-xl border border-[var(--border)] bg-white/5 px-4 py-2.5 text-sm text-[var(--foreground)] placeholder:text-[var(--muted)]/60 focus:border-[var(--accent)]/50 focus:outline-none focus:ring-1 focus:ring-[var(--accent)]/30"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-[var(--muted)]">排序</label>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="mt-1.5 rounded-xl border border-[var(--border)] bg-white/5 px-4 py-2.5 text-sm text-[var(--foreground)] focus:border-[var(--accent)]/50 focus:outline-none"
            >
              <option>截止日从近到远</option>
              <option>截止日从远到近</option>
              <option>打新分从高到低</option>
              <option>打新分从低到高</option>
              <option>长期分从高到低</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-[var(--muted)]">跟踪状态</label>
            <select
              value={trackingStatus}
              onChange={(e) => setTrackingStatus(e.target.value)}
              className="mt-1.5 rounded-xl border border-[var(--border)] bg-white/5 px-4 py-2.5 text-sm text-[var(--foreground)] focus:border-[var(--accent)]/50 focus:outline-none"
            >
              <option>全部</option>
              <option>未跟踪</option>
              <option>已完成</option>
              <option>待公告</option>
              <option>部分</option>
              <option>异常</option>
            </select>
          </div>
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-[var(--border)] bg-white/5 px-4 py-2.5 text-sm text-[var(--foreground)] transition hover:bg-white/8">
            <input type="checkbox" className="h-4 w-4 accent-[var(--accent)]" checked={showLive} onChange={(e) => setShowLive(e.target.checked)} />
            显示仍在招股
          </label>
        </div>
      </section>

      {error && (
        <section className="mt-6" aria-live="polite" aria-atomic="true">
          <ErrorDisplay message={error} onRetry={handleRetry} />
        </section>
      )}

      {/* Table */}
      <section className="mt-6 flex-1">
        {records.length === 0 ? (
          <EmptyState message="暂无历史记录。完成一次分析后，系统会自动归档到这里。" />
        ) : (
          <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-[0_8px_32px_rgba(3,8,18,0.25)] backdrop-blur">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-[var(--border)] text-xs uppercase tracking-wider text-[var(--muted)]">
                    <th className="px-5 py-4 font-medium"></th>
                    <th className="px-5 py-4 font-medium">状态</th>
                    <th className="px-5 py-4 font-medium">股票代码</th>
                    <th className="px-5 py-4 font-medium">公司名称</th>
                    <th className="px-5 py-4 font-medium text-right">发行价</th>
                    <th className="px-5 py-4 font-medium text-right">市值</th>
                    <th className="px-5 py-4 font-medium text-right">公开发售手数</th>
                    <th className="px-5 py-4 font-medium text-right">每手股数</th>
                    <th className="px-5 py-4 font-medium text-right">综合评分</th>
                    <th className="hidden px-5 py-4 font-medium text-right sm:table-cell">交易信号</th>
                    <th className="hidden px-5 py-4 font-medium text-right md:table-cell">长期价值</th>
                    <th className="px-5 py-4 font-medium">估值压力</th>
                    <th className="px-5 py-4 font-medium">市场热度</th>
                    <th className="px-5 py-4 font-medium">截止日</th>
                    <th className="px-5 py-4 font-medium"></th>
                  </tr>
                </thead>
                <tbody>
                  {records.map((r, idx) => {
                    const raw = (r._raw || {}) as unknown as AnalysisResult;
                    const isExpanded = expandedCode === r.stock_code;
                    return (
                      <Fragment key={r.stock_code}>
                        <tr
                          key={idx}
                          className={`border-b border-[var(--border)]/50 transition cursor-pointer ${
                            isExpanded ? "bg-[var(--accent)]/5" : "hover:bg-white/[0.03]"
                          } focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]/50`}
                          onClick={() => setExpandedCode(isExpanded ? null : r.stock_code)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault();
                              setExpandedCode(isExpanded ? null : r.stock_code);
                            }
                          }}
                          tabIndex={0}
                          role="button"
                          aria-expanded={isExpanded}
                          aria-label={`查看 ${r.company_name} (${r.stock_code}) 详情`}
                        >
                          <td className="px-5 py-4 text-[var(--muted)]">
                            <span className={`inline-block transition-transform ${isExpanded ? "rotate-90" : ""}`}>▶</span>
                          </td>
                          <td className="px-5 py-4"><StatusDot status={r.tracking_status} /></td>
                          <td className="px-5 py-4 font-mono text-[var(--accent)]">{r.stock_code}</td>
                          <td className="px-5 py-4 font-medium text-[var(--foreground)]">{r.company_name}</td>
                          <td className="px-5 py-4 text-right">{formatPrice(raw.offer_price)}</td>
                          <td className="px-5 py-4 text-right">{formatNumber(raw.market_cap_hkd_million)}M</td>
                          <td className="px-5 py-4 text-right">{getPublicOfferLots(r)}</td>
                          <td className="px-5 py-4 text-right">{formatNumber(raw.lot_size || raw.board_lot)}</td>
                          <td className="px-5 py-4 text-right"><ScorePill score={r.score} /></td>
                    <td className="hidden px-5 py-4 text-right sm:table-cell"><ScorePill score={r.trade_score} /></td>
                    <td className="hidden px-5 py-4 text-right md:table-cell"><ScorePill score={r.long_term_score} /></td>
                          <td className="px-5 py-4">{r.valuation_pressure}</td>
                          <td className="px-5 py-4">{r.market_heat}</td>
                          <td className="px-5 py-4">{r.apply_end_date}</td>
                          <td className="px-5 py-4" onClick={(e) => e.stopPropagation()}>
                            <Link
                              href={`/reanalyze?stock_code=${encodeURIComponent(r.stock_code)}&company_name=${encodeURIComponent(r.company_name)}`}
                              className="text-xs text-[var(--accent)] hover:underline"
                            >
                              重新分析 →
                            </Link>
                          </td>
                        </tr>
                        {isExpanded && (
                          <tr key={`${idx}-detail`}>
                            <td colSpan={14} className="px-0 py-0">
                              <div className="border-t border-[var(--border)] bg-[var(--surface-strong)]/50 px-6 py-8 sm:px-10">
                                <div className="mb-6">
                                  <div className="flex items-center justify-between">
                                    <div>
                                      <h2 className="text-2xl font-semibold text-white">
                                        {r.company_name}
                                      </h2>
                                      <p className="mt-1 text-sm text-[var(--muted)]">
                                        股票代码: {r.stock_code} · 截止日: {r.apply_end_date}
                                      </p>
                                    </div>
                                    <Link
                                      href={`/reanalyze?stock_code=${encodeURIComponent(r.stock_code)}&company_name=${encodeURIComponent(r.company_name)}`}
                                      className="inline-flex items-center gap-2 rounded-xl bg-[var(--accent)]/10 px-5 py-2.5 text-sm font-semibold text-[var(--accent)] transition hover:bg-[var(--accent)]/20"
                                    >
                                      🔁 重新分析
                                    </Link>
                                  </div>
                                  <div className="mt-3 flex flex-wrap items-center gap-3">
                                    <button
                                      onClick={async (e) => {
                                        e.stopPropagation();
                                        setTrackLoading(r.stock_code);
                                        try {
                                          const result = await trackHistoryRecord(r.stock_code, forceRefresh);
                                          if (result.status === "ok") {
                                            setTrackAllResult(`${r.stock_code} 跟踪完成 ✅`);
                                          } else if (result.status === "pending_allotment") {
                                            setTrackAllResult(`${r.stock_code} ${result.message ?? "配发公告暂未发布"}`);
                                          } else {
                                            setTrackAllResult(`${r.stock_code} 跟踪异常: ${result.message ?? ""}`);
                                          }
                                          handleRetry();
                                        } catch (err) {
                                          setTrackAllResult(err instanceof Error ? err.message : "跟踪失败");
                                        } finally {
                                          setTrackLoading(null);
                                        }
                                      }}
                                      disabled={trackLoading === r.stock_code}
                                      aria-label={`跟踪 ${r.stock_code} IPO`}
                                      className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--success)]/10 px-3 py-1.5 text-xs font-semibold text-[var(--success)] transition hover:bg-[var(--success)]/20 disabled:opacity-50"
                                    >
                                      {trackLoading === r.stock_code ? "⏳ 跟踪中..." : "📡 跟踪选中 IPO"}
                                    </button>
                                    <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-[var(--border)] bg-white/5 px-3 py-1.5 text-xs text-[var(--foreground)] transition hover:bg-white/8">
                                      <input
                                        type="file"
                                        accept=".pdf"
                                        className="hidden"
                                        onChange={async (e) => {
                                          const file = e.target.files?.[0];
                                          if (!file) return;
                                          setTrackLoading(r.stock_code);
                                          try {
                                            await uploadAllotmentPdf(r.stock_code, file);
                                            setTrackAllResult(`${r.stock_code} 配发公告解析完成 ✅`);
                                            handleRetry();
                                          } catch (err) {
                                            setTrackAllResult(err instanceof Error ? err.message : "解析失败");
                                          } finally {
                                            setTrackLoading(null);
                                          }
                                          e.target.value = "";
                                        }}
                                      />
                                      📋 上传配发公告PDF
                                    </label>
                                  </div>
                                </div>
                                <div className="space-y-8">
                                  {/* 评分分析 */}
                                  <div>
                                    <div className="mb-4 flex items-center gap-3">
                                      <span className="inline-block h-5 w-1 rounded-full bg-[var(--accent)]" />
                                      <h3 className="text-base font-semibold text-white">评分分析</h3>
                                    </div>
                                    <div className="grid gap-4 lg:grid-cols-2">
                                      <ResultSection title="评分概览">
                                        <ScoreBoard result={raw} />
                                      </ResultSection>
                                      <ResultSection title="评分理由">
                                        <ScoreReasons result={raw} />
                                      </ResultSection>
                                    </div>
                                    <div className="mt-4 grid gap-4 lg:grid-cols-2">
                                      <ResultSection title="综合分拆解 (Waterfall)">
                                        <ScoreWaterfall result={raw} />
                                      </ResultSection>
                                      <ResultSection title="维度拆解">
                                        <DimensionGrid result={raw} />
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
                                      <ValuationCard result={raw} />
                                    </ResultSection>
                                    <div className="mt-4 grid gap-4 lg:grid-cols-2">
                                      <ResultSection title="同行对比">
                                        <PeerTable result={raw} />
                                      </ResultSection>
                                      <ResultSection title="同行对比 (详细)">
                                        <PeerComparisonFull result={raw} />
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
                                        <SignalBreakdown result={raw} />
                                      </ResultSection>
                                      <ResultSection title="基石投资者">
                                        <CornerstoneDetail result={raw} />
                                      </ResultSection>
                                    </div>
                                    <div className="mt-4 grid gap-4 lg:grid-cols-2">
                                      <ResultSection title="股票质地">
                                        <StockQualityCard result={raw} />
                                      </ResultSection>
                                      <ResultSection title="风险提示">
                                        <RiskPanel result={raw} />
                                      </ResultSection>
                                    </div>
                                    {Boolean(raw["hk_code"]) && (
                                      <div className="mt-4">
                                        <ResultSection title="博主观点">
                                          <BloggerConsensusCard stockCode={String(raw["hk_code"])} />
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
                                    <ResultSection title="公司信息">
                                      <CompanyHeader result={raw} />
                                    </ResultSection>
                                    <div className="mt-4 grid gap-4 lg:grid-cols-2">
                                      <ResultSection title="基本信息">
                                        <InfoBasic result={raw} />
                                      </ResultSection>
                                      <ResultSection title="核心财务">
                                        <InfoFinancials result={raw} />
                                      </ResultSection>
                                    </div>
                                    <div className="mt-4 grid gap-4 lg:grid-cols-2">
                                      <ResultSection title="深度分析">
                                        <InfoDeep result={raw} />
                                      </ResultSection>
                                      <div className="space-y-4">
                                        <ResultSection title="业务分部">
                                          <BusinessSegments result={raw} />
                                        </ResultSection>
                                        <ResultSection title="长线视角">
                                          <FisherLynch result={raw} />
                                        </ResultSection>
                                      </div>
                                    </div>
                                  </div>

                                  {/* 中签复盘 */}
                                  <div>
                                    <div className="mb-4 flex items-center gap-3">
                                      <span className="inline-block h-5 w-1 rounded-full bg-[var(--accent)]" />
                                      <h3 className="text-base font-semibold text-white">中签复盘</h3>
                                    </div>
                                    <PostListingCard result={raw} />
                                  </div>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>
    </main>
  );
}
