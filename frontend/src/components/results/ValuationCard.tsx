import type { AnalysisResult } from "@/lib/types";

export function ValuationCard({ result }: { result: AnalysisResult }) {
  const pi = result.prospectus_info as Record<string, unknown> | undefined;
  const v = (pi?.valuation as Record<string, unknown> | undefined) ?? {};

  const conflict = v.valuation_conflict === true;
  const conflictReasons = (v.valuation_conflict_reasons as string[] | undefined) ?? [];

  const rows = [
    { label: "市盈率 PE", value: fmtRatio(v.pe_ratio) },
    { label: "市销率 PS", value: fmtRatio(v.ps_ratio) },
    { label: "EV/Sales", value: fmtRatio(v.ev_sales_ratio) },
    { label: "估值结论", value: String(v.valuation_label ?? "—") },
    { label: "现金 runway", value: fmtYears(v.cash_runway_years) },
    { label: "IPO 溢价", value: fmtPct(v.ipo_valuation_premium_pct) },
  ];

  return (
    <div className="space-y-3">
      {conflict && (
        <div className="rounded-xl border border-[var(--danger)]/30 bg-[var(--danger)]/5 p-4">
          <p className="text-sm font-semibold text-[var(--danger)]">⚠️ 盈利状态与估值框架冲突，需复核</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-[var(--danger)]/80">
            {conflictReasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {rows.map((r) => (
          <div
            key={r.label}
            className="rounded-xl border border-[var(--border)] bg-[var(--surface-strong)] p-4"
          >
            <p className="text-xs uppercase tracking-wider text-[var(--muted)]">{r.label}</p>
            <p className="mt-1 text-sm font-semibold text-[var(--foreground)]">{r.value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function fmtRatio(v: unknown) {
  if (typeof v === "number") return `${v.toFixed(2)}x`;
  return "—";
}

function fmtYears(v: unknown) {
  if (typeof v === "number") return `${v.toFixed(1)} 年`;
  return "—";
}

function fmtPct(v: unknown) {
  if (typeof v === "number") return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
  return "—";
}
