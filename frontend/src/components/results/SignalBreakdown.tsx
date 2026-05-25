const signalNames: Record<string, string> = {
  real_money: "资金热度",
  float_structure: "筹码弹性",
  float_dryness: "流通盘干涸度",
  cornerstone_quality: "基石质量",
  valuation_reading: "估值解释",
  market_heat: "实时热度",
  sector_flow: "板块资金流",
  sector_momentum: "板块动能",
  sector_board: "板块指数",
  theme_bonus: "主题催化",
  liquidity_bonus: "港股通路径",
  data_confidence: "数据置信度",
};

import type { AnalysisResult } from "@/lib/types";

export function SignalBreakdown({ result }: { result: AnalysisResult }) {
  const raw = result as unknown as Record<string, unknown>;
  const sb = (raw.signal_breakdown as Record<string, Record<string, unknown>> | undefined) ?? {};

  // 修复问题4&5: 检测实时热度和板块指数是否重复
  // 如果两者detail完全相同，只保留一个
  const marketHeatDetail = String(sb['market_heat']?.detail ?? "");
  const sectorBoardDetail = String(sb['sector_board']?.detail ?? "");
  const isDuplicate = marketHeatDetail && sectorBoardDetail && marketHeatDetail === sectorBoardDetail;

  // 修复问题5: 板块资金流如果与板块指数数据相同但显示"缺失"，同步显示
  const sectorFlowStrength = String(sb['sector_flow']?.strength ?? "—");
  const sectorBoardStrength = String(sb['sector_board']?.strength ?? "—");
  // 如果板块指数有数据但板块资金流显示缺失，用板块指数数据填充
  const shouldFillSectorFlow = sectorFlowStrength === "—" && sectorBoardStrength !== "—" && sectorBoardDetail;

  const entries = Object.entries(signalNames)
    .map(([key, label]) => {
      let item = sb[key];

      // 修复问题4: 跳过重复的板块指数
      if (isDuplicate && key === 'sector_board') {
        return null;
      }

      // 修复问题5: 用板块指数数据填充板块资金流
      if (key === 'sector_flow' && shouldFillSectorFlow) {
        item = {
          ...item,
          strength: sb['sector_board']?.strength ?? item?.strength,
          detail: sectorBoardDetail,
        };
      }

      // 流通盘干涸度 — 额外提取逼空风险和机制B标记
      if (key === 'float_dryness') {
        return {
          key,
          label,
          strength: String(item?.strength ?? "—"),
          detail: String(item?.detail ?? "—"),
          mechanism_b: Boolean(item?.mechanism_b),
          squeeze_risk_label: String(item?.squeeze_risk_label ?? "低"),
          squeeze_risk_score: Number(item?.squeeze_risk_score ?? 0),
          float_signals: (item?.float_signals as string[] | undefined) ?? [],
        };
      }

      return {
        key,
        label,
        strength: String(item?.strength ?? "—"),
        detail: String(item?.detail ?? "—"),
      };
    })
    .filter((e): e is NonNullable<typeof e> => e !== null && (e.strength !== "—" || e.detail !== "—"));

  if (entries.length === 0) return null;

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {entries.map((item) => {
        const isFloatDryness = item.key === "float_dryness";
        return (
          <div key={item.key} className="rounded-xl border border-[var(--border)] bg-[var(--surface-strong)] p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-[var(--foreground)]">{item.label}</span>
                {isFloatDryness && item.mechanism_b && (
                  <span className="rounded bg-[var(--warning)]/20 px-1.5 py-0.5 text-[10px] font-bold text-[var(--warning)]">
                    机制B
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1.5">
                {isFloatDryness && item.squeeze_risk_label && item.squeeze_risk_label !== "低" && (
                  <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${squeezeRiskStyle(item.squeeze_risk_label)}`}>
                    逼空{item.squeeze_risk_label}
                  </span>
                )}
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-semibold ${strengthStyle(item.strength)}`}
                >
                  {item.strength}
                </span>
              </div>
            </div>
            <p className="mt-1 text-xs text-[var(--muted)] line-clamp-2">{item.detail}</p>
            {isFloatDryness && (item.float_signals?.length ?? 0) > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {(item.float_signals as string[]).slice(0, 3).map((sig, i) => (
                  <span key={i} className="rounded bg-[var(--accent)]/10 px-1.5 py-0.5 text-[10px] text-[var(--accent)]">
                    {sig}
                  </span>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function squeezeRiskStyle(s: string) {
  if (s === "极高") return "text-[var(--danger)] bg-[var(--danger)]/20";
  if (s === "高") return "text-[var(--danger)] bg-[var(--danger)]/10";
  if (s === "中") return "text-[var(--warning)] bg-[var(--warning)]/10";
  return "text-[var(--success)] bg-[var(--success)]/10";
}

function strengthStyle(s: string) {
  if (s === "强" || s === "高") return "text-[var(--success)] bg-[var(--success)]/10";
  if (s === "中") return "text-[var(--warning)] bg-[var(--warning)]/10";
  if (s === "弱" || s === "低") return "text-[var(--danger)] bg-[var(--danger)]/10";
  return "text-[var(--muted)] bg-white/5";
}
