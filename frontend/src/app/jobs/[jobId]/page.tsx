"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { downloadJobJson, downloadJobPdf } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import type { JobStatusResponse, AnalyzeResultResponse, AnalysisResult } from "@/lib/types";
import { ErrorDisplay } from "@/components/ErrorDisplay";
import { Loading } from "@/components/Loading";
import { useJobPolling } from "@/hooks/useJobPolling";
import { ResultSection } from "@/components/results/ResultSection";
import { CompanyHeader } from "@/components/results/CompanyHeader";
import { ScoreBoard } from "@/components/results/ScoreBoard";
import { DimensionGrid } from "@/components/results/DimensionGrid";
import { RiskPanel } from "@/components/results/RiskPanel";
import { ValuationCard } from "@/components/results/ValuationCard";
import { InvestmentThesisCard } from "@/components/results/InvestmentThesisCard";
import { PeerTable } from "@/components/results/PeerTable";
import { CornerstoneDetail } from "@/components/results/CornerstoneDetail";
import { PeerComparisonFull } from "@/components/results/PeerComparisonFull";
import { StockQualityCard } from "@/components/results/StockQualityCard";
import { SignalBreakdown } from "@/components/results/SignalBreakdown";
import { RawJsonCollapse } from "@/components/results/RawJsonCollapse";
import { BloggerConsensusCard } from "@/components/BloggerConsensusCard";
import { PostListingCard } from "@/components/results/PostListingCard";
import {
  ScoreWaterfall,
  ScoreReasons,
  DiagnosisPanel,
  InfoBasic,
  InfoFinancials,
  InfoDeep,
  BusinessSegments,
  FisherLynch,
} from "@/components/results/DetailViewExtras";
import { CompanyProfileCard } from "@/components/results/CompanyProfileCard";

function StatusBadge({ status }: { status: string }) {
  const tones: Record<string, string> = {
    queued: "text-[var(--warning)] bg-[var(--warning)]/10",
    running: "text-[var(--accent)] bg-[var(--accent)]/10",
    success: "text-[var(--success)] bg-[var(--success)]/10",
    failed: "text-[var(--danger)] bg-[var(--danger)]/10",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wider ${tones[status] ?? "text-[var(--muted)] bg-white/5"}`}
    >
      {status}
    </span>
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs uppercase tracking-wider text-[var(--muted)]">{label}</span>
      <span className="text-sm font-medium text-[var(--foreground)]">{value ?? "—"}</span>
    </div>
  );
}

export default function JobPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const [job, setJob] = useState<JobStatusResponse | null>(null);
  const [result, setResult] = useState<AnalyzeResultResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resultError, setResultError] = useState<string | null>(null);

  useJobPolling({
    jobId,
    onStatusChange: (status) => { setJob(status); setError(null); },
    onResult: (res) => { setResult(res); setResultError(null); },
    onError: (msg) => {
      if (!job) setError(msg);
      else setResultError(msg);
    },
    interval: 3000,
  });

  if (!job && !error) {
    return (
      <main className="mx-auto w-full max-w-4xl px-6 py-10 sm:px-10 lg:px-12">
        <Loading message="Loading job status…" />
      </main>
    );
  }

  if (error || !job || job.status === "not_found") {
    return (
      <main className="mx-auto w-full max-w-4xl px-6 py-10 sm:px-10 lg:px-12">
        <ErrorDisplay
          title="Job not found"
          message={error ?? "Could not retrieve job details."}
        />
        <div className="mt-6 text-center">
          <Link
            href="/upload"
            className="inline-flex items-center rounded-full border border-[var(--border)] bg-white/8 px-5 py-2 text-sm font-medium text-[var(--accent)] transition hover:bg-white/12"
          >
            Upload another file
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-4xl px-6 py-10 sm:px-10 lg:px-12">
      <section className="relative overflow-hidden rounded-[2rem] border border-[var(--border)] bg-[var(--surface-strong)] px-6 py-8 shadow-[0_32px_120px_rgba(3,8,18,0.55)] backdrop-blur sm:px-8 sm:py-10">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(114,230,255,0.18),transparent_32%),radial-gradient(circle_at_bottom_left,rgba(88,230,169,0.14),transparent_28%)]" />
        <div className="relative flex flex-col gap-4">
          <div className="flex items-center gap-3">
            <StatusBadge status={job.status} />
            <span className="text-xs text-[var(--muted)]">{job.job_id}</span>
          </div>
          <h1 className="text-3xl font-semibold tracking-tight text-white">
            {job.company_name ?? "Analysis Job"}
          </h1>
          {job.stock_code && (
            <p className="text-sm text-[var(--muted)]">Stock code: {job.stock_code}</p>
          )}
        </div>
      </section>

      <section className="mt-8 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5 shadow-[0_8px_32px_rgba(3,8,18,0.25)] backdrop-blur sm:p-8">
        <p className="text-sm uppercase tracking-[0.22em] text-[var(--muted)]">Details</p>
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <Field label="Status" value={job.status} />
          <Field label="Stock code" value={job.stock_code} />
          <Field label="Company name" value={job.company_name} />
          <Field label="Created" value={formatDateTime(job.created_at)} />
          <Field label="Updated" value={formatDateTime(job.updated_at)} />
          <Field
            label="Started"
            value={job.started_at ? formatDateTime(job.started_at) : "—"}
          />
          <Field
            label="Finished"
            value={job.finished_at ? formatDateTime(job.finished_at) : "—"}
          />
        </div>
        {job.error && (
          <div className="mt-5 rounded-xl border border-[var(--danger)]/20 bg-[var(--danger)]/5 p-4">
            <p className="text-sm font-semibold text-[var(--danger)]">Error</p>
            <p className="mt-1 text-sm text-[var(--danger)]/80">{job.error}</p>
          </div>
        )}
      </section>

      {job.status === "success" && (
        <>
          {!result && !resultError && <Loading message="Loading result…" />}
          {resultError && <ErrorDisplay message={resultError} />}
          {result && (
            <>
              <section className="mt-8 flex flex-wrap gap-3">
                <a
                  href="#"
                  onClick={(event) => {
                    event.preventDefault();
                    downloadJobJson(jobId).catch((err) =>
                      setResultError(err instanceof Error ? err.message : "Failed to download JSON")
                    );
                  }}
                  className="inline-flex items-center gap-2 rounded-xl border border-[var(--border)] bg-white/5 px-5 py-2.5 text-sm font-medium text-[var(--foreground)] transition hover:bg-white/8"
                >
                  📥 下载 JSON
                </a>
                <a
                  href="#"
                  onClick={(event) => {
                    event.preventDefault();
                    downloadJobPdf(jobId).catch((err) =>
                      setResultError(err instanceof Error ? err.message : "Failed to download PDF")
                    );
                  }}
                  className="inline-flex items-center gap-2 rounded-xl border border-[var(--border)] bg-white/5 px-5 py-2.5 text-sm font-medium text-[var(--foreground)] transition hover:bg-white/8"
                >
                  📄 下载 PDF
                </a>
              </section>
              <ResultSection title="公司信息">
                {(() => {
                  const ar = result.result as unknown as AnalysisResult;
                  return <CompanyHeader result={ar} />;
                })()}
              </ResultSection>
              {(() => {
                const ar = result.result as unknown as AnalysisResult;
                const pi = ar.prospectus_info as Record<string, unknown> | undefined;
                const profile = pi?.company_profile as Record<string, unknown> | undefined;
                if (!profile) return null;
                const confidence = String(profile.confidence ?? "");
                if (confidence === "missing") return null;
                return (
                  <ResultSection title="公司简介">
                    <CompanyProfileCard result={ar} />
                  </ResultSection>
                );
              })()}
              <ResultSection title="投研结论">
                {(() => {
                  const ar = result.result as unknown as AnalysisResult;
                  return <InvestmentThesisCard result={ar} />;
                })()}
              </ResultSection>
              <ResultSection title="评分概览">
                {(() => { const ar = result.result as unknown as AnalysisResult; return <ScoreBoard result={ar} />; })()}
              </ResultSection>
              <ResultSection title="评分理由">
                {(() => { const ar = result.result as unknown as AnalysisResult; return <ScoreReasons result={ar} />; })()}
              </ResultSection>
              <ResultSection title="综合分拆解 (Waterfall)">
                {(() => { const ar = result.result as unknown as AnalysisResult; return <ScoreWaterfall result={ar} />; })()}
              </ResultSection>
              <ResultSection title="上市后跟踪">
                {(() => { const ar = result.result as unknown as AnalysisResult; return <PostListingCard result={ar} />; })()}
              </ResultSection>
              <ResultSection title="维度拆解">
                {(() => { const ar = result.result as unknown as AnalysisResult; return <DimensionGrid result={ar} />; })()}
              </ResultSection>
              <ResultSection title="交易信号">
                {(() => { const ar = result.result as unknown as AnalysisResult; return <SignalBreakdown result={ar} />; })()}
              </ResultSection>
              <ResultSection title="估值分析">
                {(() => { const ar = result.result as unknown as AnalysisResult; return <ValuationCard result={ar} />; })()}
              </ResultSection>
              <ResultSection title="同行对比">
                {(() => { const ar = result.result as unknown as AnalysisResult; return <PeerTable result={ar} />; })()}
              </ResultSection>
              <ResultSection title="同行对比 (详细)">
                {(() => { const ar = result.result as unknown as AnalysisResult; return <PeerComparisonFull result={ar} />; })()}
              </ResultSection>
              <ResultSection title="基石投资者">
                {(() => { const ar = result.result as unknown as AnalysisResult; return <CornerstoneDetail result={ar} />; })()}
              </ResultSection>
              <ResultSection title="股票质地">
                {(() => { const ar = result.result as unknown as AnalysisResult; return <StockQualityCard result={ar} />; })()}
              </ResultSection>
              <ResultSection title="风险提示">
                {(() => { const ar = result.result as unknown as AnalysisResult; return <RiskPanel result={ar} />; })()}
              </ResultSection>
              {job.stock_code && (
                <ResultSection title="博主观点">
                  <BloggerConsensusCard stockCode={job.stock_code} />
                </ResultSection>
              )}
              <ResultSection title="解析诊断">
                {(() => { const ar = result.result as unknown as AnalysisResult; return <DiagnosisPanel result={ar} />; })()}
              </ResultSection>
              <ResultSection title="基本信息">
                {(() => { const ar = result.result as unknown as AnalysisResult; return <InfoBasic result={ar} />; })()}
              </ResultSection>
              <ResultSection title="核心财务">
                {(() => { const ar = result.result as unknown as AnalysisResult; return <InfoFinancials result={ar} />; })()}
              </ResultSection>
              <ResultSection title="深度分析">
                {(() => { const ar = result.result as unknown as AnalysisResult; return <InfoDeep result={ar} />; })()}
              </ResultSection>
              <ResultSection title="业务分部">
                {(() => { const ar = result.result as unknown as AnalysisResult; return <BusinessSegments result={ar} />; })()}
              </ResultSection>
              <ResultSection title="长线视角">
                {(() => { const ar = result.result as unknown as AnalysisResult; return <FisherLynch result={ar} />; })()}
              </ResultSection>
              <ResultSection title="原始数据">
                <RawJsonCollapse data={result.result} />
              </ResultSection>
            </>
          )}
        </>
      )}

      {job.status === "failed" && (
        <section className="mt-8 text-center">
          <Link
            href="/upload"
            className="inline-flex items-center rounded-full border border-[var(--border)] bg-white/8 px-5 py-2 text-sm font-medium text-[var(--accent)] transition hover:bg-white/12"
          >
            Try uploading again
          </Link>
        </section>
      )}
    </main>
  );
}
