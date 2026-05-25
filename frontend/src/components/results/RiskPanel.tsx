import type { AnalysisResult } from "@/lib/types";

export function RiskPanel({ result }: { result: AnalysisResult }) {
  const pi = result.prospectus_info as Record<string, unknown> | undefined;
  const rf = (pi?.risk_factors as Record<string, unknown> | undefined) ?? {};
  const risks = (rf.risks as Record<string, Record<string, unknown>> | undefined) ?? {};
  const raw = result as unknown as Record<string, unknown>;
  const penaltyBreakdown = (raw.risk_penalty_breakdown as Array<Record<string, unknown>> | undefined) ?? [];

  const levelOrder: Record<string, number> = { "高": 3, "中": 2, "低": 1 };
  let entries = Object.entries(risks)
    .filter(([, v]) => v.risk_level && v.risk_level !== "低")
    .sort((a, b) => {
      const levelDiff = (levelOrder[String(b[1].risk_level)] ?? 0) - (levelOrder[String(a[1].risk_level)] ?? 0);
      if (levelDiff !== 0) return levelDiff;
      return (Number(b[1].score_penalty) ?? 0) - (Number(a[1].score_penalty) ?? 0);
    });

  const totalHighMid = entries.length;
  const showLimit = 3;
  const hasMore = totalHighMid > showLimit;
  entries = entries.slice(0, showLimit);

  if (entries.length === 0 && penaltyBreakdown.length === 0) {
    return (
      <div className="rounded-xl border border-[var(--success)]/20 bg-[var(--success)]/5 p-4 text-sm text-[var(--success)]">
        未发现显著风险标记
      </div>
    );
  }

  const tierLabel = (tier?: string) => {
    if (tier === "actual_event") return "已发生";
    if (tier === "potential_risk") return "潜在";
    if (tier === "generic_risk_factor") return "模板";
    return "";
  };

  const tierColor = (tier?: string) => {
    if (tier === "actual_event") return "text-[var(--danger)]";
    if (tier === "potential_risk") return "text-[var(--warning)]";
    if (tier === "generic_risk_factor") return "text-[var(--muted)]";
    return "text-[var(--muted)]";
  };

  return (
    <div className="flex flex-col gap-3">
      {entries.map(([key, item]) => {
        const level = String(item.risk_level);
        const isHigh = level === "高";
        const borderColor = isHigh ? "border-[var(--danger)]/30" : "border-[var(--warning)]/20";
        const bgColor = isHigh ? "bg-[var(--danger)]/5" : "bg-[var(--warning)]/5";
        const textColor = isHigh ? "text-[var(--danger)]" : "text-[var(--warning)]";
        const badgeBg = isHigh ? "bg-[var(--danger)]/10" : "bg-[var(--warning)]/10";
        const tiered = (item.tiered_evidence as Array<Record<string, unknown>> | undefined) ?? [];

        return (
          <div key={key} className={`rounded-xl border ${borderColor} ${bgColor} p-4`}>
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`text-xs font-bold uppercase tracking-wider ${textColor}`}>
                {riskLabel(key)}
              </span>
              <span className={`rounded-full ${badgeBg} px-2 py-0.5 text-xs ${textColor}`}>
                {level}
              </span>
              {tiered.map((t, i) => (
                <span key={i} className={`text-[10px] ${tierColor(String(t.risk_tier))}`}>
                  [{tierLabel(String(t.risk_tier))}]
                </span>
              ))}
              {isHigh && (
                <span className="ml-auto text-[10px] text-[var(--danger)]">⚠️ 重点关注</span>
              )}
            </div>
            {Array.isArray(item.evidence_sample) && item.evidence_sample.length > 0 && (
              <ul className={`mt-2 list-disc space-y-1 pl-4 text-xs ${isHigh ? "text-[var(--danger)]/80" : "text-[var(--warning)]/80"}`}>
                {(item.evidence_sample as string[]).slice(0, 2).map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            )}
          </div>
        );
      })}
      {hasMore && (
        <div className="text-center text-xs text-[var(--muted)]">
          还有 {totalHighMid - showLimit} 个风险项未显示
        </div>
      )}
      {penaltyBreakdown.length > 0 && (
        <div className="rounded-xl border border-[var(--warning)]/20 bg-[var(--warning)]/5 p-4">
          <p className="text-xs font-bold uppercase tracking-wider text-[var(--warning)]">风险惩罚</p>
          <ul className="mt-2 list-disc space-y-1 pl-4 text-xs text-[var(--warning)]/80">
            {penaltyBreakdown.map((p, i) => (
              <li key={i}>
                {String(p.reason ?? "")} (-{String(p.penalty ?? "")})
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function riskLabel(key: string) {
  const map: Record<string, string> = {
    price_competition_risk: "价格竞争风险",
    cash_flow_pressure_risk: "现金流压力风险",
    inventory_pressure_risk: "库存压力风险",
    customer_concentration_risk: "客户集中风险",
    supplier_concentration_risk: "供应商集中风险",
    overseas_channel_tariff_risk: "海外渠道/关税风险",
    social_insurance_housing_fund_risk: "社保公积金风险",
    product_liability_after_sales_risk: "产品责任/售后风险",
    foreign_exchange_risk: "外汇风险",
    seasonality_risk: "季节性风险",
    fundraising_dependency_risk: "融资依赖风险",
    competition_risk: "市场竞争风险",
    fvtpl_risk: "金融资产风险",
    regulatory_risk: "监管风险",
    market_competition_risk: "市场竞争风险",
    financial_risk: "财务风险",
    operational_risk: "运营风险",
    litigation_risk: "诉讼风险",
  };
  return map[key] ?? key;
}
