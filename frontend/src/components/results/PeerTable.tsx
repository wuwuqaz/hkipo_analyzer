import type { AnalysisResult } from "@/lib/types";

export function PeerTable({ result }: { result: AnalysisResult }) {
  const pi = result.prospectus_info as Record<string, unknown> | undefined;
  const pc = (pi?.peer_comparison as Record<string, unknown> | undefined) ?? {};
  const peers = (pc.matched_peers as Array<Record<string, unknown>> | undefined) ?? [];

  if (peers.length === 0) {
    return <p className="text-sm text-[var(--muted)]">暂无同行对比数据</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-[var(--border)] text-xs uppercase tracking-wider text-[var(--muted)]">
            <th className="pb-2 pr-4">公司</th>
            <th className="pb-2 pr-4">市场</th>
            <th className="pb-2 pr-4">PS</th>
            <th className="pb-2 pr-4">PE</th>
            <th className="pb-2">毛利率</th>
          </tr>
        </thead>
        <tbody className="text-[var(--foreground)]">
          {peers.slice(0, 6).map((p, i) => (
            <tr key={i} className="border-b border-[var(--border)]/50 last:border-0">
              <td className="py-2 pr-4 font-medium">{String(p.name ?? "—")}</td>
              <td className="py-2 pr-4">{String(p.market ?? (p.type === "listed" ? "其他" : "未上市"))}</td>
              <td className="py-2 pr-4">{typeof p.ps === "number" ? `${p.ps.toFixed(1)}x` : "—"}</td>
              <td className="py-2 pr-4">{typeof p.pe === "number" ? `${p.pe.toFixed(1)}x` : "—"}</td>
              <td className="py-2">
                {typeof p.gross_margin_pct === "number" ? `${p.gross_margin_pct.toFixed(1)}%` : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!!pc.valuation_position && (
        <p className="mt-3 text-xs text-[var(--muted)]">
          估值定位：{String(pc.valuation_position)}
          {typeof pc.relative_ps_premium_pct === "number" &&
            ` (${pc.relative_ps_premium_pct >= 0 ? "+" : ""}${Number(pc.relative_ps_premium_pct).toFixed(0)}%)`}
        </p>
      )}
    </div>
  );
}
