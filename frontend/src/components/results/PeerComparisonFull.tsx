import { fmtNum, fmtPct } from "@/lib/utils";
import type { AnalysisResult } from "@/lib/types";

function Tag({ label, tone }: { label: string; tone: "green" | "yellow" | "gray" | "red" }) {
  const colors: Record<string, string> = {
    green: "bg-[var(--success)]/10 text-[var(--success)] border-[var(--success)]/20",
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

function isNum(v: unknown): v is number {
  return typeof v === "number" && !isNaN(v);
}

function marketTone(market: string): "green" | "yellow" | "gray" | "red" {
  if (market === "港股") return "green";
  if (market === "A股") return "yellow";
  if (market === "美股") return "red";
  return "gray";
}

export function PeerComparisonFull({ result }: { result: AnalysisResult }) {
  const pi = result.prospectus_info as Record<string, unknown> | undefined;
  const pc = (pi?.peer_comparison as Record<string, unknown> | undefined) || {};

  const pcSubsector = String(pc.subsector || "");
  const pcPeers = (pc.matched_peers as Record<string, unknown>[] | undefined) || [];
  const extractedComps = (pc.extracted_competitors as string[] | undefined) || [];
  const unmatchedCandidates = (pc.unmatched_peer_candidates as string[] | undefined) || [];
  const quantitativePeers = (pc.quantitative_peers as Record<string, unknown>[] | undefined) || [];
  const qualitativePeers = (pc.qualitative_peers as Record<string, unknown>[] | undefined) || [];
  const marketPeerStats = (pc.market_peer_stats as Record<string, Record<string, unknown>> | undefined) || {};

  if (!pcSubsector && !pcPeers.length && !extractedComps.length && !unmatchedCandidates.length) {
    return null;
  }

  const companyPs = (pc.company_ps ?? undefined) as number | undefined;
  const companyPe = (pc.company_pe ?? undefined) as number | undefined;
  const peerMedianPs = (pc.peer_median_ps ?? undefined) as number | undefined;
  const peerMedianPe = (pc.peer_median_pe ?? undefined) as number | undefined;
  const premiumPs = (pc.relative_ps_premium_pct ?? undefined) as number | undefined;
  const weightedPeerPs = (pc.weighted_peer_ps ?? undefined) as number | undefined;
  const weightedPremiumPs = (pc.relative_weighted_ps_premium_pct ?? undefined) as number | undefined;
  const scarcity = Number(pc.scarcity_score || 0);
  const scarcityDetail = String(pc.scarcity_detail || "");
  const scarcityPeersCount = (pc.scarcity_peers_count ?? undefined) as number | undefined;
  const dominantSegment = String(pc.dominant_segment || "");
  const dominantSharePct = (pc.dominant_share_pct ?? undefined) as number | undefined;
  const pcScore = Number(pc.peer_score || 0);
  const position = String(pc.valuation_position || "缺失");
  const summary = String(pc.summary || "");
  const warnings = (pc.warnings as string[] | undefined) || [];
  const peerSampleWarning = String(pc.peer_sample_warning || "");

  const marketConcentration = (pc.market_concentration as Record<string, unknown> | undefined) || {};
  const cr3 = (marketConcentration.cr3_pct ?? undefined) as number | undefined;
  const cr5 = (marketConcentration.cr5_pct ?? undefined) as number | undefined;
  const relativeMarketPosition = (pc.relative_market_position as Record<string, unknown> | undefined) || {};
  const rmpRank = (relativeMarketPosition.rank ?? undefined) as number | undefined;
  const rmpPeerCount = (relativeMarketPosition.peer_count ?? undefined) as number | undefined;
  const rmpPercentile = (relativeMarketPosition.revenue_percentile ?? undefined) as number | undefined;
  const rmpSharePct = (relativeMarketPosition.relative_share_pct ?? undefined) as number | undefined;

  const positionMap: Record<string, [string, "green" | "yellow" | "gray" | "red"]> = {
    明显偏贵: ["明显偏贵", "red"],
    偏贵: ["偏贵", "yellow"],
    偏贵但可解释: ["偏贵但有稀缺性支撑", "yellow"],
    合理: ["估值合理或偏低", "green"],
    相对低估: ["相对低估", "green"],
    赛道合理: ["赛道合理", "green"],
    偏高但稀缺赛道: ["偏高但赛道稀缺", "yellow"],
    "PS辅助(明显偏贵)": ["PS辅助(偏贵，收入基数小)", "yellow"],
    "PS辅助（明显偏贵）": ["PS辅助(偏贵，收入基数小)", "yellow"],
    "PS辅助(偏高但稀缺赛道)": ["PS辅助(偏高但赛道稀缺)", "yellow"],
    "PS辅助（偏高但稀缺赛道）": ["PS辅助(偏高但赛道稀缺)", "yellow"],
    "PS辅助(偏贵但可解释)": ["PS辅助(偏贵但可解释，收入基数小)", "yellow"],
    "PS辅助（偏贵但可解释）": ["PS辅助(偏贵但可解释，收入基数小)", "yellow"],
    "PS辅助(偏贵)": ["PS辅助(偏贵，收入基数小)", "yellow"],
    "PS辅助（偏贵）": ["PS辅助(偏贵，收入基数小)", "yellow"],
    "PS辅助(合理)": ["PS辅助(估值合理)", "green"],
    "PS辅助（合理）": ["PS辅助(估值合理)", "green"],
    "PS辅助(相对低估)": ["PS辅助(相对低估)", "green"],
    "PS辅助（相对低估）": ["PS辅助(相对低估)", "green"],
    "样本不足，仅作定性参考": ["样本不足，仅作定性参考", "gray"],
    PS辅助估值: ["PS辅助估值", "yellow"],
    "PS失真，仅作参考": ["PS失真，仅作参考", "yellow"],
    管线阶段估值: ["管线阶段估值", "yellow"],
    "数据不足，需人工核对": ["数据不足，需人工核对", "gray"],
  };
  const [posLabel, posTone] = positionMap[position] || [position, "gray"];

  return (
    <div className="flex flex-col gap-4">
      {pcSubsector && (
        <p className="text-sm text-[var(--foreground)]">
          <b>细分赛道:</b> {pcSubsector.replace(/_/g, " / ")}
        </p>
      )}

      {summary && <p className="text-sm leading-relaxed text-[var(--muted)]">{summary}</p>}

      {/* PS comparison */}
      {isNum(companyPs) && isNum(peerMedianPs) && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-5">
            <div className="rounded-xl border border-[var(--border)] bg-white/[0.03] p-3">
              <p className="text-xs text-[var(--muted)]">公司PS</p>
              <p className="mt-1 text-sm font-semibold text-[var(--foreground)]">{fmtNum(companyPs)}x</p>
            </div>
            <div className="rounded-xl border border-[var(--border)] bg-white/[0.03] p-3">
              <p className="text-xs text-[var(--muted)]">综合同行PS中位数({Number(pc.peer_ps_count ?? 0)}家)</p>
              <p className="mt-1 text-sm font-semibold text-[var(--foreground)]">{fmtNum(peerMedianPs)}x</p>
            </div>
            <div className="rounded-xl border border-[var(--border)] bg-white/[0.03] p-3">
              <p className="text-xs text-[var(--muted)]">业务加权同行PS</p>
              <p className="mt-1 text-sm font-semibold text-[var(--foreground)]">{fmtNum(weightedPeerPs, "x")}</p>
            </div>
            <div className="rounded-xl border border-[var(--border)] bg-white/[0.03] p-3">
              <p className="text-xs text-[var(--muted)]">相对溢价</p>
              <p className="mt-1 text-sm font-semibold text-[var(--foreground)]">
                {isNum(premiumPs) ? `${premiumPs > 0 ? "+" : ""}${premiumPs.toFixed(1)}%` : "--"}
              </p>
            </div>
            <div className="group relative rounded-xl border border-[var(--border)] bg-white/[0.03] p-3">
              <p className="text-xs text-[var(--muted)]">赛道稀缺性</p>
              <p className="mt-1 text-sm font-semibold text-[var(--foreground)]">{scarcity}/10</p>
              <div className="absolute bottom-full left-0 mb-2 hidden rounded-lg border border-[var(--border)] bg-[var(--surface-strong)] p-3 text-xs text-[var(--muted)] shadow-lg group-hover:block min-w-[220px] z-10">
                <p className="text-[var(--foreground)] font-semibold mb-1">稀缺性评分明细</p>
                <ul className="space-y-0.5">
                  {scarcityPeersCount !== undefined && (
                    <li>• 港股同行: {scarcityPeersCount} 家</li>
                  )}
                  {dominantSegment && dominantSharePct !== undefined && (
                    <li>• {dominantSegment} 市占: {dominantSharePct}%</li>
                  )}
                  {scarcityDetail && <li>• {scarcityDetail}</li>}
                </ul>
              </div>
            </div>
          </div>
          {isNum(weightedPeerPs) && isNum(weightedPremiumPs) && (
            <p className="text-xs text-[var(--muted)]">
              混合业务按分部收入占比重估：加权同行PS {weightedPeerPs.toFixed(1)}x，相对溢价 {weightedPremiumPs > 0 ? "+" : ""}
              {weightedPremiumPs.toFixed(1)}%
            </p>
          )}

          {/* 市场占有率分析 */}
          {(dominantSegment || isNum(cr3) || isNum(cr5) || isNum(rmpRank)) && (
            <div className="rounded-xl border border-[var(--border)] bg-white/[0.03] p-3">
              <p className="text-xs font-semibold text-[var(--foreground)] mb-2">市场占有率分析</p>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 text-xs">
                {dominantSegment && dominantSharePct !== undefined && (
                  <div>
                    <p className="text-[var(--muted)]">市场份额</p>
                    <p className="mt-0.5 font-semibold text-[var(--foreground)]">
                      {dominantSegment === "unknown" ? "细分市场" : dominantSegment}: {dominantSharePct}%
                    </p>
                  </div>
                )}
                {isNum(cr3) && (
                  <div>
                    <p className="text-[var(--muted)]">行业集中度 CR3</p>
                    <p className="mt-0.5 font-semibold text-[var(--foreground)]">{cr3}%</p>
                  </div>
                )}
                {isNum(cr5) && !isNum(cr3) && (
                  <div>
                    <p className="text-[var(--muted)]">行业集中度 CR5</p>
                    <p className="mt-0.5 font-semibold text-[var(--foreground)]">{cr5}%</p>
                  </div>
                )}
                {isNum(rmpRank) && isNum(rmpPeerCount) && rmpPeerCount > 0 && (
                  <div>
                    <p className="text-[var(--muted)]">同行收入排名</p>
                    <p className="mt-0.5 font-semibold text-[var(--foreground)]">
                      第{rmpRank}/{rmpPeerCount}名
                      {isNum(rmpPercentile) && ` (Top ${(100 - rmpPercentile).toFixed(0)}%)`}
                    </p>
                  </div>
                )}
                {isNum(rmpSharePct) && (
                  <div>
                    <p className="text-[var(--muted)]">同行收入占比</p>
                    <p className="mt-0.5 font-semibold text-[var(--foreground)]">{rmpSharePct}%</p>
                  </div>
                )}
              </div>
              {scarcityDetail && (
                <p className="mt-2 text-xs text-[var(--muted)]">{scarcityDetail}</p>
              )}
            </div>
          )}
        </>
      )}

      {/* PE comparison */}
      {isNum(companyPe) && isNum(peerMedianPe) && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-xl border border-[var(--border)] bg-white/[0.03] p-3">
            <p className="text-xs text-[var(--muted)]">公司PE</p>
            <p className="mt-1 text-sm font-semibold text-[var(--foreground)]">{fmtNum(companyPe)}x</p>
          </div>
          <div className="rounded-xl border border-[var(--border)] bg-white/[0.03] p-3">
            <p className="text-xs text-[var(--muted)]">同行PE中位数</p>
            <p className="mt-1 text-sm font-semibold text-[var(--foreground)]">{fmtNum(peerMedianPe)}x</p>
          </div>
          <div className="rounded-xl border border-[var(--border)] bg-white/[0.03] p-3">
            <p className="text-xs text-[var(--muted)]">PE相对溢价</p>
            <p className="mt-1 text-sm font-semibold text-[var(--foreground)]">
              {isNum(pc.relative_pe_premium_pct) ? `${(pc.relative_pe_premium_pct as number) > 0 ? "+" : ""}${(pc.relative_pe_premium_pct as number).toFixed(1)}%` : "--"}
            </p>
          </div>
          <div className="rounded-xl border border-[var(--border)] bg-white/[0.03] p-3">
            <p className="text-xs text-[var(--muted)]">估值定位</p>
            <p className="mt-1 text-sm font-semibold text-[var(--foreground)]">{position}</p>
          </div>
        </div>
      )}

      {/* Valuation position */}
      <div className="flex items-center gap-3 text-sm">
        <b>综合估值:</b> <Tag label={posLabel} tone={posTone} />
        <b>同行对比评分:</b> <span className="text-[var(--foreground)]">{Math.round(pcScore)}/15</span>
      </div>

      {peerSampleWarning && (
        <p className="rounded-lg border border-[var(--accent)]/10 bg-[var(--accent)]/5 p-2 text-xs text-[var(--accent)]">
          ℹ️ {peerSampleWarning}
        </p>
      )}

      {["hk", "a_share", "us"].some((k) => Number(marketPeerStats[k]?.peer_count || 0) > 0) && (
        <div className="flex flex-col gap-2">
          <p className="text-sm font-semibold text-[var(--foreground)]">分市场估值</p>
          <div className="grid gap-3 md:grid-cols-3">
            {(["hk", "a_share", "us"] as const).map((k) => {
              const stat = marketPeerStats[k] || {};
              const market = String(stat.market || (k === "hk" ? "港股" : k === "a_share" ? "A股" : "美股"));
              const count = Number(stat.peer_count || 0);
              if (count <= 0) return null;
              const ps = stat.peer_median_ps;
              const pe = stat.peer_median_pe;
              const premium = stat.relative_ps_premium_pct;
              const statPosition = String(stat.valuation_position || "--");
              const peers = (stat.peers as Record<string, unknown>[] | undefined) || [];
              return (
                <div key={k} className="rounded-lg border border-[var(--border)] bg-white/[0.03] p-3">
                  <div className="flex items-center justify-between gap-2">
                    <Tag label={market} tone={marketTone(market)} />
                    <span className="text-xs text-[var(--muted)]">{count}家</span>
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-[var(--muted)]">
                    <span>PS <b className="text-[var(--foreground)]">{fmtNum(ps, "x")}</b></span>
                    <span>PE <b className="text-[var(--foreground)]">{fmtNum(pe, "x")}</b></span>
                    <span className="col-span-2">
                      溢价{" "}
                      <b className="text-[var(--foreground)]">
                        {isNum(premium) ? `${premium > 0 ? "+" : ""}${premium.toFixed(1)}%` : "--"}
                      </b>
                    </span>
                  </div>
                  <p className="mt-2 text-xs text-[var(--foreground)]">{statPosition}</p>
                  {peers.length > 0 && (
                    <p className="mt-2 text-xs text-[var(--muted)]">
                      {peers.slice(0, 3).map((p) => String(p.name || "")).filter(Boolean).join("、")}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Peer list */}
      {pcPeers.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-sm font-semibold text-[var(--foreground)]">可比公司 ({Math.min(pcPeers.length, 8)}家)</p>
          {pcPeers.slice(0, 8).map((p, i) => {
            const pName = String(p.name || "");
            const pTicker = String(p.ticker || "");
            const pType = String(p.type || "");
            const pMarket = String(p.market || (pType === "listed" ? "其他" : "未上市"));
            const pPs = (p.ps ?? undefined) as number | undefined;
            const pPe = (p.pe ?? undefined) as number | undefined;
            const pGm = (p.gross_margin_pct ?? undefined) as number | undefined;
            const pGrowth = (p.revenue_growth_pct ?? undefined) as number | undefined;
            const pMatch = String(p.matched_by || "");
            const pNote = String(p.notes || "");
            return (
              <div
                key={i}
                className="flex flex-col gap-2 rounded-lg border border-[var(--border)] bg-white/[0.03] p-3"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <b className="text-sm text-[var(--foreground)]">{pName}</b>
                  <span className="text-xs text-[var(--muted)]">{pTicker}</span>
                  <Tag label={pMarket} tone={marketTone(pMarket)} />
                </div>
                <div className="text-xs text-[var(--muted)]">
                  PS {fmtNum(pPs)}x | PE {fmtNum(pPe)}x | 毛利率 {fmtPct(pGm)} | 收入增 {fmtNum(pGrowth, "%")}
                </div>
                {(pMatch || pNote) && (
                  <div className="text-xs text-[var(--muted)]">
                    {pMatch}{pNote ? ` | ${pNote}` : ""}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Quantitative / Qualitative peers */}
      {(quantitativePeers.length > 0 || qualitativePeers.length > 0) && (
        <div className="flex flex-col gap-1">
          <p className="text-xs text-[var(--muted)]">
            <b>quantitative peers:</b> 参与估值中位数计算；<b>qualitative peers:</b> 仅作定性参考
          </p>
          {quantitativePeers.slice(0, 6).map((p, i) => (
            <p key={`q${i}`} className="text-xs text-[var(--muted)]">• {String(p.name || "")} (quantitative)</p>
          ))}
          {qualitativePeers.slice(0, 4).map((p, i) => (
            <p key={`l${i}`} className="text-xs text-[var(--muted)]">• {String(p.name || "")} (qualitative)</p>
          ))}
        </div>
      )}

      {/* Warnings */}
      {warnings.map((w, i) => (
        <p key={i} className="text-xs text-[var(--danger)]">⚠️ {w}</p>
      ))}

      {/* Extracted competitors */}
      {extractedComps.length > 0 && (
        <p className="text-xs text-[var(--muted)]">
          📖 招股书明确提及的已收录同行: {extractedComps.slice(0, 10).join("、")}
        </p>
      )}

      {/* Unmatched candidates */}
      {unmatchedCandidates.length > 0 && (
        <div>
          <p className="text-xs text-[var(--warning)]">
            🔍 招股书提及但本地同行库未收录: {unmatchedCandidates.slice(0, 8).join("、")}
          </p>
          <p className="mt-0.5 text-xs text-[var(--muted)]">
            （不参与估值中位数，仅供人工维护同行库）
          </p>
        </div>
      )}
    </div>
  );
}
