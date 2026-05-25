"use client";

import Link from "next/link";
import type { AnalysisResult } from "@/lib/types";
import { safeNumber } from "@/lib/utils";
import { MetricCard } from "@/components/dashboard/MetricCard";
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

function fmtDate(val: unknown, fallback?: unknown): string {
  const s = String(val || "").trim();
  if (s && s !== "--" && s !== "null" && s !== "undefined") return s;
  const fb = String(fallback || "").trim();
  if (fb && fb !== "--" && fb !== "null" && fb !== "undefined") return fb;
  return "--";
}

export function IpoDetailPanel({ ipo, onClose }: { ipo: AnalysisResult; onClose?: () => void }) {
  const pi = ipo.prospectus_info;

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-strong)] p-5 shadow-[0_8px_32px_rgba(3,8,18,0.25)] backdrop-blur sm:p-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold text-white">{ipo.company_name}</h2>
          <p className="mt-1 text-sm text-[var(--muted)]">
            股票代码: {ipo.hk_code} · 截止日: {fmtDate(ipo.apply_end_date, ipo.margin_detail?.["EndDate"] ?? pi?.apply_end_date)}
          </p>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            aria-label="收起详情"
            className="rounded-full border border-[var(--border)] bg-white/8 px-4 py-2 text-sm text-[var(--accent)] transition hover:bg-white/12"
          >
            收起
          </button>
        )}
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard title="综合评分" value={String(ipo.score)} tone={ipo.score >= 60 ? "text-[var(--success)]" : "text-[var(--warning)]"} />
        <MetricCard title="交易信号" value={String(ipo.trade_score)} tone={ipo.trade_score >= 60 ? "text-[var(--accent)]" : "text-[var(--muted)]"} />
        <MetricCard title="长期价值" value={String(ipo.long_term_score)} tone={ipo.long_term_score >= 60 ? "text-[var(--success)]" : ipo.long_term_score >= 40 ? "text-[var(--warning)]" : "text-[var(--danger)]"} />
        <MetricCard title="估值吸引力" value={String(ipo.valuation_score)} tone={ipo.valuation_score >= 60 ? "text-[var(--success)]" : "text-[var(--warning)]"} />
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard title="基本面" value={String(ipo.fundamental_score)} tone={ipo.fundamental_score >= 60 ? "text-[var(--success)]" : "text-[var(--warning)]"} />
        <MetricCard title="估值压力" value={ipo.valuation_pressure_label} tone={ipo.valuation_pressure_label === "高" ? "text-[var(--danger)]" : ipo.valuation_pressure_label === "中" ? "text-[var(--warning)]" : "text-[var(--success)]"} />
        <MetricCard title="市场热度" value={ipo.market_heat || (ipo.over_sub_ratio ? `超购 ${ipo.over_sub_ratio.toFixed(1)}x` : "--")} tone={ipo.market_heat === "极热" || ipo.market_heat === "热门" ? "text-[var(--danger)]" : ipo.market_heat === "温和" ? "text-[var(--warning)]" : "text-[var(--muted)]"} />
        <MetricCard title="主题赛道" value={pi?.sector || (ipo.theme_score ? `主题分 ${ipo.theme_score}` : "--")} tone="text-[var(--foreground)]" />
      </div>
      {/* 严格打新限制与长期价值惩罚 */}
      {buildCapAndPenaltySection(ipo)}

      <div className="mt-6 flex flex-wrap gap-3">
        <Link
          href={`/reanalyze?stock_code=${encodeURIComponent(ipo.hk_code)}&company_name=${encodeURIComponent(ipo.company_name)}`}
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

      {/* Full analysis panels */}
      <div className="mt-8 space-y-8">
        {/* 公司简介 */}
        <div>
          <div className="mb-4 flex items-center gap-3">
            <span className="inline-block h-5 w-1 rounded-full bg-[var(--accent)]" />
            <h3 className="text-base font-semibold text-white">公司信息</h3>
          </div>
          <ResultSection title="公司信息"><CompanyHeader result={ipo} /></ResultSection>
          {pi?.company_profile && pi.company_profile.confidence !== "missing" && (
            <div className="mt-4">
              <ResultSection title="公司简介"><CompanyProfileCard result={ipo} /></ResultSection>
            </div>
          )}
        </div>

        {/* 评分分析 */}
        <div>
          <div className="mb-4 flex items-center gap-3">
            <span className="inline-block h-5 w-1 rounded-full bg-[var(--accent)]" />
            <h3 className="text-base font-semibold text-white">评分分析</h3>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <ResultSection title="评分概览"><ScoreBoard result={ipo} /></ResultSection>
            <ResultSection title="评分理由"><ScoreReasons result={ipo} /></ResultSection>
          </div>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <ResultSection title="综合分拆解 (Waterfall)"><ScoreWaterfall result={ipo} /></ResultSection>
            <ResultSection title="维度拆解"><DimensionGrid result={ipo} /></ResultSection>
          </div>
        </div>

        {/* 估值与同行 */}
        <div>
          <div className="mb-4 flex items-center gap-3">
            <span className="inline-block h-5 w-1 rounded-full bg-[var(--success)]" />
            <h3 className="text-base font-semibold text-white">估值与同行</h3>
          </div>
          <ResultSection title="估值分析"><ValuationCard result={ipo} /></ResultSection>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <ResultSection title="同行对比"><PeerTable result={ipo} /></ResultSection>
            <ResultSection title="同行对比 (详细)"><PeerComparisonFull result={ipo} /></ResultSection>
          </div>
        </div>

        {/* 投资参考 */}
        <div>
          <div className="mb-4 flex items-center gap-3">
            <span className="inline-block h-5 w-1 rounded-full bg-[var(--warning)]" />
            <h3 className="text-base font-semibold text-white">投资参考</h3>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <ResultSection title="交易信号"><SignalBreakdown result={ipo} /></ResultSection>
            <ResultSection title="基石投资者"><CornerstoneDetail result={ipo} /></ResultSection>
          </div>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <ResultSection title="股票质地"><StockQualityCard result={ipo} /></ResultSection>
            <ResultSection title="风险提示"><RiskPanel result={ipo} /></ResultSection>
          </div>
          {ipo.hk_code && (
            <div className="mt-4">
              <ResultSection title="博主观点"><BloggerConsensusCard stockCode={ipo.hk_code} /></ResultSection>
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
            <ResultSection title="基本信息"><InfoBasic result={ipo} /></ResultSection>
            <ResultSection title="核心财务"><InfoFinancials result={ipo} /></ResultSection>
          </div>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <ResultSection title="深度分析"><InfoDeep result={ipo} /></ResultSection>
            <div className="space-y-4">
              <ResultSection title="业务分部"><BusinessSegments result={ipo} /></ResultSection>
              <ResultSection title="长线视角"><FisherLynch result={ipo} /></ResultSection>
              <ResultSection title="专业投资框架"><InvestSkillPanel result={ipo} /></ResultSection>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function buildCapAndPenaltySection(ipo: AnalysisResult) {
  const strictScore = safeNumber(ipo.strict_ipo_score ?? ipo.ipo_trade_score ?? 0);
  const strictCapReasons = ipo.strict_cap_reasons ?? [];
  const hasStrictCap = strictCapReasons.length > 0 && strictScore < ipo.score;
  const rawLong = ipo.raw_long_term_score_before_penalty ?? 0;
  const longPen = ipo.long_term_penalty ?? 0;
  const longPenReasons = ipo.long_term_penalty_reasons ?? [];
  const longScore = ipo.long_term_score;

  if (!hasStrictCap && !(longPen > 0 && longPenReasons.length > 0)) return null;

  return (
    <div className="mt-3 grid gap-3 sm:grid-cols-2">
      {hasStrictCap && (
        <div className="rounded-xl border border-[var(--warning)]/20 bg-[var(--warning)]/5 p-3">
          <div className="flex items-center gap-2">
            <span className="text-sm text-[var(--warning)]">⚠️ 严格打新限制</span>
            <span className="font-mono text-sm text-[var(--foreground)]">
              {strictScore} <span className="text-[var(--muted)]">(原计算 {ipo.score})</span>
            </span>
          </div>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-[var(--muted)]">
            {strictCapReasons.map((r, i) => <li key={i}>{r}</li>)}
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
            {longPenReasons.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}
