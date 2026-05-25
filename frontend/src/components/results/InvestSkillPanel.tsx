"use client";

import { useMemo } from "react";
import type { AnalysisResult } from "@/lib/types";

/* ------------------------------------------------------------------ */
/* InvestSkill 集成框架 — 前端展示组件                                  */
/* ------------------------------------------------------------------ */

interface InvestSkillProps {
  result: AnalysisResult;
}

interface InvestSkillData {
  piotroski_f: Record<string, unknown> | null;
  dcf_valuation: Record<string, unknown> | null;
  sector_analysis: Record<string, unknown> | null;
}

function useInvestSkillData(result: AnalysisResult): InvestSkillData {
  return useMemo(() => {
    const pi = result.prospectus_info as Record<string, unknown> | undefined;
    const pf = (pi?.piotroski_f as Record<string, unknown> | undefined) || null;
    const dcf = (pi?.dcf_valuation as Record<string, unknown> | undefined) || null;
    const sector = (pi?.sector_analysis as Record<string, unknown> | undefined) || null;
    return { piotroski_f: pf, dcf_valuation: dcf, sector_analysis: sector };
  }, [result]);
}

function KpiGrid({ items }: { items: [string, React.ReactNode][] }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
      {items.map(([label, value]) => (
        <div key={label} className="rounded-xl border border-[var(--border)] bg-white/[0.03] p-3">
          <p className="text-xs text-[var(--muted)]">{label}</p>
          <p className="mt-1 text-sm font-medium text-[var(--foreground)]">{value}</p>
        </div>
      ))}
    </div>
  );
}

function fmtNum(v: unknown): string {
  if (v === null || v === undefined) return "--";
  const n = Number(v);
  if (isNaN(n)) return String(v);
  return n.toLocaleString();
}

function numOrNull(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function fmtPct(v: unknown): string {
  if (v === null || v === undefined) return "--";
  const n = Number(v);
  if (isNaN(n)) return String(v);
  return `${n.toFixed(1)}%`;
}

function boolLabel(v: unknown, yes: string, no: string): string {
  if (v === true) return yes;
  if (v === false) return no;
  return "--";
}

function sectorScore(sector: Record<string, unknown>): number | null {
  const direct = numOrNull(sector.score);
  if (direct !== null) return direct;
  const parts = [
    numOrNull(sector.sector_beta_score),
    numOrNull(sector.cycle_score),
    numOrNull(sector.policy_score),
  ].filter((v): v is number => v !== null);
  if (parts.length === 0) return null;
  return Math.round(parts.reduce((sum, v) => sum + v, 0) / parts.length);
}

export function InvestSkillPanel({ result }: InvestSkillProps) {
  const data = useInvestSkillData(result);

  const items: [string, React.ReactNode][] = [];

  const pf = data.piotroski_f;
  if (pf) {
    const score = numOrNull(pf.score ?? pf.total_score);
    const maxScore = numOrNull(pf.max_score) ?? 9;
    items.push(["Piotroski F-Score", score !== null ? `${score}/${maxScore}` : "--"]);
    items.push(["F-Score 评级", String(pf.label ?? pf.grade ?? "--")]);
    items.push(["ROA 趋势", String(pf.roa_trend ?? boolLabel(pf.profit_roa_improvement, "改善", "未改善"))]);
    items.push(["现金流", String(pf.cashflow_label ?? boolLabel(pf.profit_ocf_positive, "经营现金流为正", "经营现金流为负或未披露"))]);
  }

  const dcf = data.dcf_valuation;
  if (dcf) {
    const fv = numOrNull(dcf.fair_value_hkd ?? dcf.intrinsic_value_hkd ?? dcf.base_value_hkd);
    items.push(["DCF 公允价值", fv && fv > 0 ? `HK$${fv.toLocaleString(undefined, { maximumFractionDigits: 2 })}` : "--"]);
    items.push(["上行空间", fmtPct(dcf.upside_pct)]);
    items.push(["FCF 预测年数", fmtNum(dcf.forecast_years)]);
  }

  const sector = data.sector_analysis;
  if (sector) {
    const score = sectorScore(sector);
    items.push(["行业赛道", String(sector.sector_label ?? sector.sector_name ?? "--")]);
    items.push(["赛道评分", score !== null ? `${score}/100` : "--"]);
    items.push(["行业前景", String(sector.outlook ?? sector.sector_recommendation ?? sector.sector_growth_label ?? "--")]);
  }

  if (items.length === 0) {
    return <p className="text-sm text-[var(--muted)]">暂无专业投资框架数据。</p>;
  }

  return <KpiGrid items={items} />;
}
