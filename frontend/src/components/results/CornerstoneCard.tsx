export function CornerstoneCard({ result }: { result: Record<string, unknown> }) {
  const pi = (result.prospectus_info as Record<string, unknown> | undefined) ?? {};
  const cs = (pi.cornerstone_analysis as Record<string, unknown> | undefined) ?? {};
  const investors = (cs.cornerstone_investors as Array<Record<string, unknown>> | undefined) ?? [];

  if (!cs.score && investors.length === 0) {
    return <p className="text-sm text-[var(--muted)]">暂无基石投资者数据</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <Metric label="基石评分" value={typeof cs.score === "number" ? `${cs.score}/100` : "—"} />
        <Metric label="评级" value={String(cs.label ?? "—")} />
        <Metric label="占比" value={typeof cs.cornerstone_pct === "number" ? `${cs.cornerstone_pct.toFixed(1)}%` : "—"} />
      </div>
      {investors.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-[var(--border)] text-xs uppercase tracking-wider text-[var(--muted)]">
                <th className="pb-2 pr-4">投资者</th>
                <th className="pb-2 pr-4">分级</th>
                <th className="pb-2">占比</th>
              </tr>
            </thead>
            <tbody className="text-[var(--foreground)]">
              {investors.slice(0, 8).map((inv, i) => (
                <tr key={i} className="border-b border-[var(--border)]/50 last:border-0">
                  <td className="py-2 pr-4 font-medium">{String(inv.name ?? "—")}</td>
                  <td className="py-2 pr-4">{String(inv.tier ?? "—")}</td>
                  <td className="py-2">
                    {typeof inv.offer_shares_pct === "number"
                      ? `${inv.offer_shares_pct.toFixed(2)}%`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {Array.isArray(cs.red_flags) && cs.red_flags.length > 0 && (
        <div className="rounded-xl border border-[var(--danger)]/20 bg-[var(--danger)]/5 p-3">
          <p className="text-xs font-semibold text-[var(--danger)]">基石红旗</p>
          <ul className="mt-1 list-disc space-y-1 pl-4 text-xs text-[var(--danger)]/80">
            {(cs.red_flags as string[]).map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-strong)] p-4">
      <p className="text-xs uppercase tracking-wider text-[var(--muted)]">{label}</p>
      <p className="mt-1 text-sm font-semibold text-[var(--foreground)]">{value}</p>
    </div>
  );
}
