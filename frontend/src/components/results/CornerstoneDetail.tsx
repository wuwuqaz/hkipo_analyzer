import { fmtNum, fmtPct } from "@/lib/utils";
import type { AnalysisResult } from "@/lib/types";

function Tag({ label, tone }: { label: string; tone: "green" | "blue" | "yellow" | "gray" | "red" }) {
  const colors: Record<string, string> = {
    green: "bg-[var(--success)]/10 text-[var(--success)] border-[var(--success)]/20",
    blue: "bg-[var(--accent)]/10 text-[var(--accent)] border-[var(--accent)]/20",
    yellow: "bg-[var(--warning)]/10 text-[var(--warning)] border-[var(--warning)]/20",
    gray: "bg-white/5 text-[var(--muted)] border-[var(--border)]",
    red: "bg-[var(--danger)]/10 text-[var(--danger)] border-[var(--danger)]/20",
  };
  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs ${colors[tone]}`}>
      {label}
    </span>
  );
}

export function CornerstoneDetail({ result }: { result: AnalysisResult }) {
  const pi = result.prospectus_info as Record<string, unknown> | undefined;
  const ca = (pi?.cornerstone_analysis as Record<string, unknown> | undefined) || {};

  if (!ca || Object.keys(ca).length === 0) {
    return <p className="text-sm text-[var(--muted)]">暂无基石投资者数据</p>;
  }

  const score = ca.score;
  const label = String(ca.label ?? "—");
  const cornerstonePct = ca.cornerstone_pct;
  const dims = (ca.dimension_scores as Record<string, Record<string, unknown>> | undefined) || {};
  const investors = (ca.cornerstone_investors as Record<string, unknown>[] | undefined) || [];
  const strengths = (ca.strengths as string[] | undefined) || [];
  const concerns = (ca.concerns as string[] | undefined) || [];
  const redFlags = (ca.red_flags as string[] | undefined) || [];
  const combination = String(ca.combination_summary || "");

  return (
    <div className="flex flex-col gap-5">
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-strong)] p-4">
          <p className="text-xs uppercase tracking-wider text-[var(--muted)]">基石评分</p>
          <p className="mt-1 text-sm font-semibold text-[var(--foreground)]">{typeof score === "number" ? `${score}/100` : "—"}</p>
        </div>
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-strong)] p-4">
          <p className="text-xs uppercase tracking-wider text-[var(--muted)]">评级</p>
          <p className="mt-1 text-sm font-semibold text-[var(--foreground)]">{label}</p>
        </div>
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-strong)] p-4">
          <p className="text-xs uppercase tracking-wider text-[var(--muted)]">占比</p>
          <p className="mt-1 text-sm font-semibold text-[var(--foreground)]">{typeof cornerstonePct === "number" ? `${cornerstonePct.toFixed(1)}%` : "—"}</p>
        </div>
      </div>
      {/* Combination summary */}
      {combination && (
        <p className="rounded-lg border border-[var(--accent)]/10 bg-[var(--accent)]/5 p-3 text-sm text-[var(--foreground)]">
          {combination}
        </p>
      )}

      {/* Dimension scores */}
      {Object.keys(dims).length > 0 && (
        <div className="flex flex-col gap-3">
          {Object.values(dims).map((item, i) => {
            const label = String(item.label || "--");
            const score = Number(item.score || 0);
            const maxScore = Number(item.max_score || 1) || 1;
            const detail = String(item.detail || "");
            const pct = Math.max(0, Math.min(100, (score / maxScore) * 100));
            return (
              <div key={i}>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-[var(--muted)]">
                    {label} {detail ? `· ${detail}` : ""}
                  </span>
                  <b className="text-[var(--foreground)]">
                    {score}/{maxScore}
                  </b>
                </div>
                <div className="mt-1 h-[7px] w-full overflow-hidden rounded bg-[var(--border)]">
                  <div
                    className="h-full rounded bg-[var(--warning)]"
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Investor rows */}
      {investors.length > 0 && (
        <div className="flex flex-col gap-3">
          {investors.map((row, i) => {
            const name = String(row.short_name || row.name || "--");
            const fullName = String(row.name || "");
            const tier = String(row.tier || "");
            const category = String(row.category || "未知");
            const roleNote = String(row.role_note || "");
            const matchNote = String(row.match_note || "");
            const tierScore = row.tier_score;
            const fitLabel = String(row.sector_fit_label || "--");
            const offerPct = row.offer_shares_pct;
            const amount = (row.investment_amount_hkd_m ?? undefined) as number | undefined;

            let tierTone: "green" | "blue" | "yellow" | "gray" = "gray";
            if (tier === "S") tierTone = "green";
            else if (tier === "A") tierTone = "blue";
            else if (tier === "B") tierTone = "yellow";

            return (
              <div
                key={i}
                className="flex flex-col gap-1 rounded-xl border border-[var(--border)] bg-white/[0.03] p-4 sm:flex-row sm:items-start sm:justify-between"
              >
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <b className="text-sm text-[var(--foreground)]">{name}</b>
                    {tier && <Tag label={tier} tone={tierTone} />}
                  </div>
                  {fullName && fullName !== name && (
                    <p className="mt-0.5 text-xs text-[var(--muted)]">{fullName}</p>
                  )}
                  <p className="mt-1 text-xs text-[var(--muted)]">
                    {category} · {tierScore !== undefined ? `${tierScore}分` : "--"} · {amount !== undefined ? fmtNum(amount, " M HKD") : "--"} · 占全球发售 {fmtPct(offerPct)}
                  </p>
                </div>
                <div className="mt-2 text-xs text-[var(--muted)] sm:mt-0 sm:text-right">
                  {roleNote && <p>{roleNote}</p>}
                  <p className="mt-0.5">{matchNote} · {fitLabel}</p>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Source excerpt */}
      {(() => {
        const excerpt = String(ca.source_excerpt || ca.raw_pdf_excerpt || "");
        if (!excerpt) return null;
        return (
          <details className="rounded-lg border border-[var(--border)] bg-white/[0.02]">
            <summary className="cursor-pointer p-3 text-xs font-medium text-[var(--muted)] hover:text-[var(--foreground)]">
              📖 招股书基石原文摘录
            </summary>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap p-3 pt-0 text-xs leading-relaxed text-[var(--muted)]">
              {excerpt}
            </pre>
          </details>
        );
      })()}

      {/* Signals */}
      <div className="flex flex-col gap-3">
        {strengths.length > 0 && (
          <div>
            <p className="text-sm font-semibold text-[var(--success)]">亮点</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {strengths.slice(0, 5).map((s, i) => (
                <span key={i} className="rounded-full bg-[var(--success)]/10 px-3 py-1 text-xs text-[var(--success)]">
                  {s}
                </span>
              ))}
            </div>
          </div>
        )}
        {concerns.length > 0 && (
          <div>
            <p className="text-sm font-semibold text-[var(--warning)]">隐忧</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {concerns.slice(0, 5).map((s, i) => (
                <span key={i} className="rounded-full bg-[var(--warning)]/10 px-3 py-1 text-xs text-[var(--warning)]">
                  {s}
                </span>
              ))}
            </div>
          </div>
        )}
        {redFlags.length > 0 && (
          <div>
            <p className="text-sm font-semibold text-[var(--danger)]">红旗</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {redFlags.slice(0, 5).map((s, i) => (
                <span key={i} className="rounded-full bg-[var(--danger)]/10 px-3 py-1 text-xs text-[var(--danger)]">
                  {s}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
