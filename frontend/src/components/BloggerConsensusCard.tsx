"use client";

import { useEffect, useState } from "react";
import { fetchBloggerConsensus, searchBloggerOpinions } from "@/lib/api";
import type { BloggerConsensusResponse } from "@/lib/types";
import { Loading } from "./Loading";
import { ErrorDisplay } from "./ErrorDisplay";

export function BloggerConsensusCard({ stockCode }: { stockCode: string }) {
  const [data, setData] = useState<BloggerConsensusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function fetchData() {
      setLoading(true);
      try {
        const res = await fetchBloggerConsensus(stockCode);
        if (!cancelled) {
          setData(res);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load blogger consensus");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    fetchData();
    return () => { cancelled = true; };
  }, [stockCode]);

  async function handleRetry() {
    setLoading(true);
    try {
      const res = await fetchBloggerConsensus(stockCode);
      setData(res);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load blogger consensus");
    } finally {
      setLoading(false);
    }
  }

  async function handleSearch() {
    setSearching(true);
    setError(null);
    try {
      const res = await searchBloggerOpinions(stockCode);
      setData(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setSearching(false);
    }
  }

  if (loading) {
    return <Loading message="Loading blogger consensus…" />;
  }

  return (
    <div className="flex flex-col gap-4">
      {error && <ErrorDisplay message={error} onRetry={handleRetry} />}

      {data?.message && !data.total_posts && (
        <div className="rounded-xl border border-[var(--warning)]/20 bg-[var(--warning)]/5 p-4 text-sm text-[var(--warning)]">
          {data.message}
        </div>
      )}

      {data && data.total_posts > 0 && (
        <div className="grid gap-4 md:grid-cols-3">
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
            <p className="text-xs uppercase tracking-wider text-[var(--muted)]">共识分</p>
            <p className="mt-2 text-2xl font-semibold text-[var(--accent)]">
              {data.consensus_score?.toFixed(1) ?? "--"}
            </p>
          </div>
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
            <p className="text-xs uppercase tracking-wider text-[var(--muted)]">情绪</p>
            <p className="mt-2 text-2xl font-semibold text-[var(--foreground)]">
              {data.sentiment_label ?? "--"}
            </p>
          </div>
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
            <p className="text-xs uppercase tracking-wider text-[var(--muted)]">覆盖文章</p>
            <p className="mt-2 text-2xl font-semibold text-[var(--foreground)]">{data.total_posts}</p>
            <p className="mt-1 text-xs text-[var(--muted)]">
              正 {data.positive_count} / 中 {data.neutral_count} / 负 {data.negative_count}
            </p>
          </div>
        </div>
      )}

      {data && data.top_reasons.length > 0 && (
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
          <p className="text-sm font-medium text-[var(--foreground)]">主要理由</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {data.top_reasons.map((r, i) => (
              <span key={i} className="rounded-full bg-[var(--success)]/10 px-3 py-1 text-xs text-[var(--success)]">
                {r}
              </span>
            ))}
          </div>
        </div>
      )}

      {data && data.top_risks.length > 0 && (
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
          <p className="text-sm font-medium text-[var(--foreground)]">主要风险</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {data.top_risks.map((r, i) => (
              <span key={i} className="rounded-full bg-[var(--danger)]/10 px-3 py-1 text-xs text-[var(--danger)]">
                {r}
              </span>
            ))}
          </div>
        </div>
      )}

      {data && data.representative_posts.length > 0 && (
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
          <p className="text-sm font-medium text-[var(--foreground)]">代表性文章</p>
          <div className="mt-3 flex flex-col gap-2">
            {data.representative_posts.map((p, i) => (
              <a
                key={i}
                href={p.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-between rounded-xl bg-white/5 px-4 py-3 text-sm transition hover:bg-white/8"
              >
                <span className="truncate text-[var(--foreground)]">{p.title}</span>
                <span className={`ml-3 shrink-0 text-xs ${
                  p.sentiment === "positive" ? "text-[var(--success)]" :
                  p.sentiment === "negative" ? "text-[var(--danger)]" :
                  "text-[var(--muted)]"
                }`}>
                  {p.sentiment}
                </span>
              </a>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <button
          onClick={handleSearch}
          disabled={searching}
          className="inline-flex cursor-pointer items-center gap-2 rounded-xl bg-[var(--accent)]/10 px-5 py-2.5 text-sm font-semibold text-[var(--accent)] transition hover:bg-[var(--accent)]/20 disabled:opacity-50"
        >
          {searching ? (
            <>
              <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-[var(--border)] border-t-[var(--accent)]" />
              搜索中…
            </>
          ) : (
            "🔍 搜索博主观点"
          )}
        </button>
      </div>
    </div>
  );
}
