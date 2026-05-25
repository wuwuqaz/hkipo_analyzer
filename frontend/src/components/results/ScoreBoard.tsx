import { scoreColor, barColor, safeNumber } from "@/lib/utils";
import type { AnalysisResult } from "@/lib/types";

export function ScoreBoard({ result }: { result: AnalysisResult }) {
  const score = result.score;
  const tradeScore = result.trade_score;
  const longScore = result.long_term_score;
  const valuationScore = result.valuation_score;
  const fundamentalScore = result.fundamental_score;

  const strictScore = safeNumber(result.strict_ipo_score ?? result.ipo_trade_score);
  const strictCapReasons = result.strict_cap_reasons ?? [];
  const hasStrictCap = strictCapReasons.length > 0 && strictScore < score;

  const rawLongScore = result.raw_long_term_score_before_penalty ?? 0;
  const longPenalty = result.long_term_penalty ?? 0;
  const longPenaltyReasons = result.long_term_penalty_reasons ?? [];

  const overSubRatio = result.over_sub_ratio;
  const marketHeat = result.market_heat || "";

  return (
    <div className="flex flex-col gap-4">
      {/* 主评分区 */}
      <div className="grid gap-4 sm:grid-cols-3">
        <MainScoreCard
          title="综合评分"
          value={score}
          subtitle={result.ipo_trade_label || result.long_term_label || ""}
          size="lg"
        />
        <MainScoreCard
          title="交易信号"
          value={tradeScore}
          subtitle={marketHeat ? `${marketHeat}` : undefined}
          size="md"
        />
        <MainScoreCard
          title="长期价值"
          value={longScore}
          subtitle={longPenalty > 0 ? `−${longPenalty} 惩罚` : undefined}
          size="md"
        />
      </div>

      {/* 三大支柱分解 */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-strong)] p-4">
        <p className="mb-3 text-xs font-medium uppercase tracking-wider text-[var(--muted)]">
          维度分解
        </p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <PillarCard
            label="基本面"
            score={fundamentalScore}
            detail={result.stock_quality?.label ?? ""}
          />
          <PillarCard
            label="估值吸引力"
            score={valuationScore}
            detail={result.valuation_pressure_label || ""}
          />
          <PillarCard
            label="交易热度"
            score={tradeScore}
            detail={overSubRatio !== undefined && overSubRatio !== null ? `超购 ${Number(overSubRatio).toFixed(1)}x` : undefined}
          />
          <PillarCard
            label="主题赛道"
            score={result.theme_score ?? 0}
            detail={result.prospectus_info?.sector ?? ""}
          />
        </div>
      </div>

      {/* 严格打新限制说明 */}
      {hasStrictCap && (
        <div className="rounded-xl border border-[var(--warning)]/20 bg-[var(--warning)]/5 p-3">
          <div className="flex items-center gap-2">
            <span className="text-sm text-[var(--warning)]">⚠️ 严格打新限制</span>
            <span className="font-mono text-sm text-[var(--foreground)]">
              {strictScore} <span className="text-[var(--muted)]">(原计算 {score})</span>
            </span>
          </div>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-[var(--muted)]">
            {strictCapReasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}

      {/* 长期价值惩罚详情 */}
      {longPenalty > 0 && longPenaltyReasons.length > 0 && (
        <div className="rounded-xl border border-[var(--border)]/50 bg-[var(--surface)] p-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-[var(--muted)]">长期价值分计算</span>
            <span className="font-mono text-sm text-[var(--foreground)]">
              {rawLongScore} − {longPenalty} = {longScore}
            </span>
          </div>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[10px] text-[var(--muted)]">
            {longPenaltyReasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 主评分卡片                                                          */
/* ------------------------------------------------------------------ */
function MainScoreCard({
  title,
  value,
  subtitle,
  size = "md",
}: {
  title: string;
  value: number;
  subtitle?: string;
  size?: "lg" | "md";
}) {
  const isLg = size === "lg";
  return (
    <div
      className={`rounded-2xl border border-[var(--border)] bg-[var(--surface-strong)] p-4 text-center ${
        isLg ? "ring-1 ring-[var(--accent)]/20" : ""
      }`}
    >
      <p className={`text-xs uppercase tracking-wider text-[var(--muted)] ${isLg ? "font-medium" : ""}`}>
        {title}
      </p>
      <p className={`mt-2 font-bold ${scoreColor(value)} ${isLg ? "text-5xl" : "text-3xl"}`}>
        {value}
      </p>
      {subtitle && (
        <p className={`mt-1 text-[var(--muted)] ${isLg ? "text-sm" : "text-xs"}`}>{subtitle}</p>
      )}
      <div className="mx-auto mt-3 h-2 w-full overflow-hidden rounded-full bg-white/10">
        <div
          className="h-full rounded-full transition-all"
          style={{
            width: `${Math.min(100, Math.max(0, value))}%`,
            backgroundColor: barColor(value),
          }}
        />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 维度分解卡片                                                        */
/* ------------------------------------------------------------------ */
function PillarCard({
  label,
  score,
  detail,
}: {
  label: string;
  score: number;
  detail?: string;
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-[var(--border)]/50 bg-white/[0.03] p-3">
      <div className="flex-1">
        <p className="text-xs text-[var(--muted)]">{label}</p>
        <p className={`mt-0.5 text-lg font-bold ${scoreColor(score)}`}>{score}</p>
        {detail && detail !== "缺失" && (
          <p className="mt-0.5 text-[10px] text-[var(--muted)]">{detail}</p>
        )}
      </div>
      <div className="h-10 w-1.5 overflow-hidden rounded-full bg-white/10">
        <div
          className="w-full rounded-full transition-all"
          style={{
            height: `${Math.min(100, Math.max(0, score))}%`,
            backgroundColor: barColor(score),
            marginTop: "auto",
          }}
        />
      </div>
    </div>
  );
}


