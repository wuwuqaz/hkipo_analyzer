import type { AnalysisResult, StockQuality } from "@/lib/types";

export function StockQualityCard({ result }: { result: AnalysisResult }) {
  const sq = (result.stock_quality ?? result.prospectus_info?.stock_quality) as StockQuality | undefined;
  const dims = sq?.dimensions ?? {};

  const map: Record<string, string> = {
    growth: "成长性",
    profitability: "盈利质量",
    valuation: "估值压力",
    risk: "风险点",
  };

  const entries = Object.entries(map)
    .map(([key, label]) => {
      const d = dims[key];
      return { key, label, detail: String(d?.detail ?? "—"), labelVal: String(d?.label ?? "—") };
    })
    .filter((e) => e.detail !== "—" || e.labelVal !== "—");

  if (entries.length === 0 && !sq?.score) {
    return <p className="text-sm text-[var(--muted)]">暂无股票质地数据</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      {sq && typeof sq.score === "number" && (
        <div className="flex items-center gap-3">
          <span className="text-2xl font-bold text-[var(--foreground)]">{sq.score}</span>
          <span className="text-sm text-[var(--muted)]">{String(sq.label ?? "")}</span>
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        {entries.map((e) => (
          <div key={e.key} className="rounded-xl border border-[var(--border)] bg-[var(--surface-strong)] p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs uppercase tracking-wider text-[var(--muted)]">{e.label}</span>
              <span className="text-xs font-semibold text-[var(--accent)]">{e.labelVal}</span>
            </div>
            <p className="mt-1 text-xs text-[var(--muted)] line-clamp-3">{e.detail}</p>
          </div>
        ))}
      </div>
      {sq && Array.isArray(sq.reasons) && sq.reasons.length > 0 && (
        <ul className="list-disc space-y-1 pl-4 text-xs text-[var(--muted)]">
          {(sq.reasons as string[]).map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
