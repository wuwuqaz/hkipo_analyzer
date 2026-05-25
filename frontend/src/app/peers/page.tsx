"use client";

import { useEffect, useState } from "react";
import { fetchPeers, fetchPeerMeta, refreshPeers } from "@/lib/api";
import type { PeerRecord } from "@/lib/types";
import { Loading } from "@/components/Loading";
import { ErrorDisplay } from "@/components/ErrorDisplay";
import { EmptyState } from "@/components/EmptyState";

export default function PeersPage() {
  const [peers, setPeers] = useState<PeerRecord[]>([]);
  const [sectors, setSectors] = useState<string[]>([]);
  const [subsectors, setSubsectors] = useState<string[]>([]);
  const [meta, setMeta] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [sector, setSector] = useState("");
  const [subsector, setSubsector] = useState("");
  const [listedOnly, setListedOnly] = useState(false);

  const [refreshing, setRefreshing] = useState(false);
  const [refreshResult, setRefreshResult] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function fetchData() {
      setLoading(true);
      try {
        const [peerData, metaData] = await Promise.all([
          fetchPeers(sector || undefined, subsector || undefined, listedOnly),
          fetchPeerMeta(),
        ]);
        if (cancelled) return;
        setPeers(peerData.peers);
        setSectors(peerData.sectors);
        setSubsectors(peerData.subsectors);
        setMeta(metaData);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load peers");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    fetchData();
    return () => { cancelled = true; };
  }, [sector, subsector, listedOnly]);

  async function load() {
    setLoading(true);
    try {
      const [peerData, metaData] = await Promise.all([
        fetchPeers(sector || undefined, subsector || undefined, listedOnly),
        fetchPeerMeta(),
      ]);
      setPeers(peerData.peers);
      setSectors(peerData.sectors);
      setSubsectors(peerData.subsectors);
      setMeta(metaData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load peers");
    } finally {
      setLoading(false);
    }
  }

  async function handleRefresh(dryRun: boolean) {
    setRefreshing(true);
    setRefreshResult(null);
    try {
      const result = await refreshPeers(dryRun, true);
      setRefreshResult(result);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refresh failed");
    } finally {
      setRefreshing(false);
    }
  }

  function fmt(v: number | null, suffix = ""): string {
    if (v === null || v === undefined) return "--";
    if (typeof v !== "number") return String(v);
    if (v !== Math.floor(v)) return `${v.toFixed(2)}${suffix}`;
    return `${Math.round(v)}${suffix}`;
  }

  if (loading && peers.length === 0) {
    return (
      <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-6 py-10 sm:px-10 lg:px-12">
        <Loading message="Loading peer database…" />
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-6 py-10 sm:px-10 lg:px-12">
      <section className="relative overflow-hidden rounded-[2rem] border border-[var(--border)] bg-[var(--surface-strong)] px-6 py-8 shadow-[0_32px_120px_rgba(3,8,18,0.55)] backdrop-blur sm:px-8 sm:py-10">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(114,230,255,0.18),transparent_32%),radial-gradient(circle_at_bottom_left,rgba(88,230,169,0.14),transparent_28%)]" />
        <div className="relative">
          <h1 className="text-3xl font-semibold tracking-tight text-white">同行库管理</h1>
          <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
            管理同行对比数据库 · 更新行情数据 · 查看过期标记
          </p>
        </div>
      </section>

      {/* Meta */}
      {meta && (
        <section className="mt-6 grid gap-3 md:grid-cols-4">
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4">
            <p className="text-xs uppercase tracking-wider text-[var(--muted)]">数据日期</p>
            <p className="mt-1.5 text-base font-semibold text-[var(--foreground)]">{String(meta.peer_data_source_date ?? "--")}</p>
          </div>
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4">
            <p className="text-xs uppercase tracking-wider text-[var(--muted)]">最近检查</p>
            <p className="mt-1.5 text-base font-semibold text-[var(--foreground)]">{String(meta.peer_data_last_checked_at ?? "--")}</p>
          </div>
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4">
            <p className="text-xs uppercase tracking-wider text-[var(--muted)]">数据年龄</p>
            <p className={`mt-1.5 text-base font-semibold ${meta.peer_data_is_stale ? "text-[var(--danger)]" : "text-[var(--success)]"}`}>
              {String(meta.peer_data_age_days ?? "?")} 天
            </p>
          </div>
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4">
            <p className="text-xs uppercase tracking-wider text-[var(--muted)]">过期阈值</p>
            <p className="mt-1.5 text-base font-semibold text-[var(--foreground)]">{String(meta.peer_data_stale_after_days ?? 90)} 天</p>
          </div>
        </section>
      )}

      {/* Controls */}
      <section className="mt-6 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5 shadow-[0_8px_32px_rgba(3,8,18,0.25)] backdrop-blur">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
          <div>
            <label className="block text-sm font-medium text-[var(--muted)]">行业</label>
            <select
              value={sector}
              onChange={(e) => { setSector(e.target.value); setSubsector(""); }}
              className="mt-1.5 rounded-xl border border-[var(--border)] bg-white/5 px-4 py-2.5 text-sm text-[var(--foreground)] focus:border-[var(--accent)]/50 focus:outline-none"
            >
              <option value="">全部行业</option>
              {sectors.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-[var(--muted)]">细分赛道</label>
            <select
              value={subsector}
              onChange={(e) => setSubsector(e.target.value)}
              className="mt-1.5 rounded-xl border border-[var(--border)] bg-white/5 px-4 py-2.5 text-sm text-[var(--foreground)] focus:border-[var(--accent)]/50 focus:outline-none"
            >
              <option value="">全部赛道</option>
              {subsectors.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-[var(--border)] bg-white/5 px-4 py-2.5 text-sm text-[var(--foreground)] transition hover:bg-white/8">
            <input type="checkbox" className="h-4 w-4 accent-[var(--accent)]" checked={listedOnly} onChange={(e) => setListedOnly(e.target.checked)} />
            仅上市
          </label>
          <div className="flex-1" />
          <div className="flex gap-3">
            <button
              onClick={() => handleRefresh(true)}
              disabled={refreshing}
              aria-label="预览过期同行数据"
              className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-[var(--border)] bg-white/5 px-5 py-2.5 text-sm font-medium text-[var(--foreground)] transition hover:bg-white/8 disabled:opacity-50"
            >
              {refreshing ? "刷新中…" : "👁 预览过期同行"}
            </button>
            <button
              onClick={() => handleRefresh(false)}
              disabled={refreshing}
              aria-label="写入过期同行数据"
              className="inline-flex cursor-pointer items-center gap-2 rounded-xl bg-[var(--accent)]/10 px-5 py-2.5 text-sm font-semibold text-[var(--accent)] transition hover:bg-[var(--accent)]/20 disabled:opacity-50"
            >
              {refreshing ? "写入中…" : "✅ 写入过期同行"}
            </button>
          </div>
        </div>
        {refreshResult && (
          <div className="mt-4 rounded-xl border border-[var(--success)]/20 bg-[var(--success)]/5 p-4 text-sm text-[var(--success)]">
            处理 {String(refreshResult.total ?? 0)} 条，已更新 {String(refreshResult.updated ?? 0)}，跳过 {String(refreshResult.skipped ?? 0)}，失败 {String(refreshResult.failed ?? 0)}
          </div>
        )}
      </section>

      {error && (
        <section className="mt-6">
          <ErrorDisplay message={error} onRetry={load} />
        </section>
      )}

      {/* Table */}
      <section className="mt-6 flex-1">
        {peers.length === 0 ? (
          <EmptyState message="同行数据库为空。请确认 data/peer_comps.yaml 存在。" />
        ) : (
          <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-[0_8px_32px_rgba(3,8,18,0.25)] backdrop-blur">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-[var(--border)] text-xs uppercase tracking-wider text-[var(--muted)]">
                    <th className="px-5 py-4 font-medium">名称</th>
                    <th className="px-5 py-4 font-medium">Ticker</th>
                    <th className="px-5 py-4 font-medium">类型</th>
                    <th className="px-5 py-4 font-medium">行业</th>
                    <th className="px-5 py-4 font-medium">赛道</th>
                    <th className="px-5 py-4 font-medium text-right">PS</th>
                    <th className="px-5 py-4 font-medium text-right">PE</th>
                    <th className="px-5 py-4 font-medium text-right">市值(M)</th>
                    <th className="px-5 py-4 font-medium text-right">收入增速</th>
                    <th className="px-5 py-4 font-medium text-right">毛利率</th>
                    <th className="px-5 py-4 font-medium">状态</th>
                  </tr>
                </thead>
                <tbody>
                  {peers.map((p, idx) => (
                    <tr key={idx} className="border-b border-[var(--border)]/50 transition hover:bg-white/[0.03]">
                      <td className="px-5 py-4 font-medium text-[var(--foreground)]">{p.name}</td>
                      <td className="px-5 py-4 font-mono text-[var(--accent)]">{p.ticker}</td>
                      <td className="px-5 py-4">{p.type}</td>
                      <td className="px-5 py-4">{p.sector}</td>
                      <td className="px-5 py-4">{p.subsector}</td>
                      <td className="px-5 py-4 text-right">{fmt(p.ps, "x")}</td>
                      <td className="px-5 py-4 text-right">{fmt(p.pe, "x")}</td>
                      <td className="px-5 py-4 text-right">{fmt(p.market_cap_hkd_million)}</td>
                      <td className="px-5 py-4 text-right">{fmt(p.revenue_growth_pct, "%")}</td>
                      <td className="px-5 py-4 text-right">{fmt(p.gross_margin_pct, "%")}</td>
                      <td className="px-5 py-4">
                        {p.is_stale ? (
                          <span className="text-xs text-[var(--danger)]">⚠ 过期</span>
                        ) : (
                          <span className="text-xs text-[var(--success)]">✓ 有效</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>
    </main>
  );
}
