import { useMemo } from "react";
import { fmtInt, fmtPct, fmtNum, safeNumber, compactShares } from "@/lib/utils";

function PricePerf({ payload }: { payload: Record<string, unknown> | undefined }) {
  if (!payload || payload.status === "missing") {
    return <span className="text-[var(--muted)]">--</span>;
  }
  const price = (payload.price ?? undefined) as number | undefined;
  const change = (payload.change_pct ?? undefined) as number | undefined;
  const date = (payload.date ?? undefined) as string | undefined;
  return (
    <div>
      {price !== undefined && price !== null ? (
        <span>{fmtNum(price, " HKD")}</span>
      ) : (
        <span className="text-[var(--muted)]">--</span>
      )}
      {change !== undefined && change !== null && (
        <span className={`ml-1 text-xs ${change > 0 ? "text-[var(--danger)]" : change < 0 ? "text-[var(--success)]" : "text-[var(--muted)]"}`}>
          ({change > 0 ? "+" : ""}{change.toFixed(1)}%)
        </span>
      )}
      {date && <div className="text-xs text-[var(--muted)]">{date}</div>}
    </div>
  );
}

function KpiGrid({ items }: { items: [string, React.ReactNode][] }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-5">
      {items.map(([label, value]) => (
        <div key={label} className="rounded-xl border border-[var(--border)] bg-white/[0.03] p-3">
          <p className="text-xs text-[var(--muted)]">{label}</p>
          <p className="mt-1 text-sm font-medium text-[var(--foreground)]">{value}</p>
        </div>
      ))}
    </div>
  );
}

function AllocationPoolTable({ pool, label }: { pool: Record<string, unknown>; label: string }) {
  const rows = (pool.rows as Record<string, unknown>[]) || [];
  const summary = `有效申请人数：${fmtInt(pool.valid_applications)} | 中签总数：${fmtInt(pool.successful_applications)} | 中签率：${fmtPct(pool.success_rate_pct)}`;

  return (
    <div className="overflow-hidden rounded-xl border border-[var(--border)]">
      <div className="flex items-center gap-3 border-b border-[var(--border)] bg-white/[0.03] px-4 py-3">
        <span className="inline-flex min-w-[44px] items-center justify-center rounded-md bg-[var(--surface-strong)] px-2.5 py-1 text-xs font-bold text-[var(--muted)]">
          {label}
        </span>
        <span className="text-xs text-[var(--muted)]">{summary}</span>
      </div>
      <div className="max-h-[360px] overflow-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-[var(--surface-strong)] text-[var(--muted)]">
            <tr>
              <th className="px-3 py-2 text-right">申请股数</th>
              <th className="px-3 py-2 text-right">有效申请人</th>
              <th className="px-3 py-2 text-right">中签人</th>
              <th className="px-3 py-2 text-right">一手中签率</th>
              <th className="px-3 py-2 text-right">中签率</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="border-b border-[var(--border)]/30">
                <td className="px-3 py-2 text-right">{fmtInt(row.applied_shares)}</td>
                <td className="px-3 py-2 text-right">{fmtInt(row.valid_applications)}</td>
                <td className="px-3 py-2 text-right">{fmtInt(row.successful_applications)}</td>
                <td className="px-3 py-2 text-right">{fmtPct(row.allotment_pct)}</td>
                <td className="px-3 py-2 text-right font-semibold">{fmtPct(row.success_rate_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function AllocationTrendSvg({ rows }: { rows: Record<string, unknown>[] }) {
  const trendRows = useMemo(() => {
    return rows.filter((r) => typeof r.success_rate_pct === "number" && typeof r.applied_shares === "number");
  }, [rows]);

  if (trendRows.length < 2) return null;

  const width = 920;
  const height = 260;
  const left = 48;
  const right = 22;
  const top = 32;
  const bottom = 42;
  const plotW = width - left - right;
  const plotH = height - top - bottom;
  const maxRate = Math.max(...trendRows.map((r) => Number(r.success_rate_pct)));
  const yMax = Math.max(100, (Math.floor(maxRate / 10) + 1) * 10);

  const points: string[] = [];
  const pointsA: string[] = [];
  const pointsB: string[] = [];
  const labels: React.ReactNode[] = [];

  trendRows.forEach((row, idx) => {
    const x = left + (plotW * idx) / Math.max(1, trendRows.length - 1);
    const y = top + plotH - (plotH * Number(row.success_rate_pct)) / yMax;
    const pt = `${x.toFixed(1)},${y.toFixed(1)}`;
    points.push(pt);
    if (row.pool === "B") {
      pointsB.push(pt);
    } else {
      pointsA.push(pt);
    }
    if (idx === 0 || idx === trendRows.length - 1 || idx % 3 === 0) {
      labels.push(
        <text
          key={idx}
          x={x.toFixed(1)}
          y={height - 12}
          textAnchor="middle"
          fontSize={9}
          fill="#64748B"
        >
          {compactShares(row.applied_shares)}
        </text>
      );
    }
  });

  const gridLines: React.ReactNode[] = [];
  for (let pct = 0; pct <= yMax; pct += 20) {
    const y = top + plotH - (plotH * pct) / yMax;
    gridLines.push(
      <line key={pct} x1={left} y1={y} x2={width - right} y2={y} stroke="rgba(0,229,255,0.12)" strokeDasharray="4 4" />
    );
    gridLines.push(
      <text key={`l${pct}`} x={left - 10} y={y + 4} textAnchor="end" fontSize={10} fill="#64748B">
        {pct}%
      </text>
    );
  }

  const splitIdx = trendRows.findIndex((r) => r.pool === "B");
  let splitHtml: React.ReactNode[] = [];
  if (splitIdx > 0) {
    const x = left + (plotW * splitIdx) / Math.max(1, trendRows.length - 1);
    splitHtml = [
      <line key="sl" x1={x} y1={top} x2={x} y2={top + plotH} stroke="rgba(0,229,255,0.22)" strokeDasharray="5 5" />,
      <rect key="sr" x={x - 58} y={top + 6} width={116} height={22} rx={6} fill="#0b1020" stroke="rgba(0,229,255,0.22)" />,
      <text key="st" x={x} y={top + 21} textAnchor="middle" fontSize={11} fill="#94a3b8">
        甲组结束 / 乙组开始
      </text>,
    ];
  }

  const colorA = "#22d3ee";
  const colorB = "#f59e0b";

  const dots = trendRows.map((row, i) => {
    const [x, y] = points[i].split(",");
    const fill = row.pool === "B" ? colorB : colorA;
    return (
      <circle
        key={i}
        cx={x}
        cy={y}
        r={3.2}
        fill={fill}
        stroke="#0b1020"
        strokeWidth={1.5}
      >
        <title>{`${fmtInt(row.applied_shares)}股: ${fmtPct(row.success_rate_pct)}`}</title>
      </circle>
    );
  });

  const polylines: React.ReactNode[] = [];
  if (pointsA.length >= 2) {
    polylines.push(<polyline key="a" points={pointsA.join(" ")} fill="none" stroke={colorA} strokeWidth={2.4} />);
  }
  if (pointsB.length >= 2) {
    polylines.push(<polyline key="b" points={pointsB.join(" ")} fill="none" stroke={colorB} strokeWidth={2.4} />);
  }
  if (pointsA.length >= 1 && pointsB.length >= 1) {
    polylines.push(<polyline key="ab" points={`${pointsA[pointsA.length - 1]} ${pointsB[0]}`} fill="none" stroke={colorA} strokeWidth={2.4} />);
  }

  return (
    <div className="mt-4 overflow-x-auto rounded-xl border border-[var(--border)] bg-white/[0.02] p-4">
      <p className="mb-2 text-center text-sm font-bold text-[var(--foreground)]">甲乙组中签率趋势</p>
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" style={{ minWidth: 720, display: "block" }}>
        <g transform={`translate(${width - right - 120}, 10)`}>
          <circle cx={0} cy={0} r={3} fill={colorA} />
          <text x={8} y={3} fontSize={10} fill="#64748B">甲组</text>
          <circle cx={50} cy={0} r={3} fill={colorB} />
          <text x={58} y={3} fontSize={10} fill="#64748B">乙组</text>
        </g>
        {gridLines}
        {splitHtml}
        {polylines}
        {dots}
        {labels}
        <text x={width / 2} y={height - 2} textAnchor="middle" fontSize={11} fill="#64748B">
          申请股数
        </text>
      </svg>
    </div>
  );
}

import type { AnalysisResult } from "@/lib/types";

export function PostListingCard({ result }: { result: AnalysisResult }) {
  const raw = result as unknown as Record<string, unknown>;
  const post = (raw.post_listing as Record<string, unknown> | undefined) || {};

  if (!post || Object.keys(post).length === 0) {
    return (
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6">
        <p className="text-sm font-medium text-[var(--muted)]">📌 上市后跟踪</p>
        <p className="mt-3 text-sm text-[var(--muted)]">
          IPO 结束后系统将自动抓取 HKEX 配发公告与价格表现数据。
        </p>
      </div>
    );
  }

  const status = String(post.status || "");
  const statusLabel: Record<string, string> = {
    ok: "已完成",
    pending_allotment: "待公告",
    partial: "部分完成",
    error: "异常",
  };

  const allotmentKpis: [string, React.ReactNode][] = [
    ["跟踪状态", <span key="s" className={status === "ok" ? "text-[var(--success)]" : status === "error" ? "text-[var(--danger)]" : "text-[var(--warning)]"}>{statusLabel[status] || status || "--"}</span>],
    ["最终发售价", fmtNum(post.final_offer_price, " HKD")],
    ["上市日期", String(post.listing_date || "--")],
    ["一手中签率", fmtPct(post.one_lot_success_rate_pct)],
    ["整体中签率", fmtPct(post.overall_success_rate_pct)],
    ["有效申请", fmtInt(post.valid_applications)],
    ["成功申请", fmtInt(post.successful_applications)],
    ["公配倍数", fmtNum(post.public_subscription_level, "x")],
    ["国配倍数", fmtNum(post.international_subscription_level, "x")],
    ["承配人数", fmtInt(post.placees_count)],
  ];

  const priceKpis: [string, React.ReactNode][] = [
    ["暗盘", <PricePerf key="g" payload={post.grey_market as Record<string, unknown> | undefined} />],
    ["首日", <PricePerf key="f" payload={post.first_day as Record<string, unknown> | undefined} />],
    ["至今", <PricePerf key="l" payload={post.latest as Record<string, unknown> | undefined} />],
  ];

  const poolsRaw = post.allocation_pools;
  const pools = (typeof poolsRaw === "object" && poolsRaw !== null ? poolsRaw : {}) as Record<string, unknown>;
  const poolA = pools.A as Record<string, unknown> | undefined;
  const poolB = pools.B as Record<string, unknown> | undefined;
  const poolARows = Array.isArray(poolA?.rows) ? (poolA.rows as Record<string, unknown>[]) : [];
  const poolBRows = Array.isArray(poolB?.rows) ? (poolB.rows as Record<string, unknown>[]) : [];
  const hasPoolA = poolARows.length > 0;
  const hasPoolB = poolBRows.length > 0;

  const oneLotRate = (post.one_lot_success_rate_pct ?? undefined) as number | undefined;
  const oneLotShares = (post.one_lot_applied_shares ?? undefined) as number | undefined;

  const pdf = (post.allotment_pdf as Record<string, unknown> | undefined) || {};
  const sourceUrl = String(pdf.source_url || post.source_url || "");
  const message = String(post.message || post.error || "");

  // Build trend rows
  const trendRows: Record<string, unknown>[] = [];
  poolARows.forEach((r) => trendRows.push({ ...r, pool: "A" }));
  poolBRows.forEach((r) => trendRows.push({ ...r, pool: "B" }));

  // Basic info text
  const basicInfo: string[] = [];
  const publicSub = (post.public_subscription_level ?? undefined) as number | undefined;
  const intlSub = (post.international_subscription_level ?? undefined) as number | undefined;
  const valid = (post.valid_applications ?? undefined) as number | undefined;
  const successful = (post.successful_applications ?? undefined) as number | undefined;
  const overallRate = (post.overall_success_rate_pct ?? undefined) as number | undefined;
  if (publicSub !== undefined && !isNaN(publicSub)) basicInfo.push(`公开发售认购：${publicSub.toLocaleString()}倍`);
  if (intlSub !== undefined && !isNaN(intlSub)) basicInfo.push(`国际配售认购：${intlSub.toLocaleString()}倍`);
  if (valid !== undefined && !isNaN(valid)) basicInfo.push(`有效申请：${Math.floor(valid).toLocaleString()}份`);
  if (successful !== undefined && !isNaN(successful)) basicInfo.push(`成功申请：${Math.floor(successful).toLocaleString()}份`);
  if (overallRate !== undefined && !isNaN(overallRate)) basicInfo.push(`整体中签率：${overallRate.toFixed(2)}%`);

  return (
    <div className="flex flex-col gap-5">
      <KpiGrid items={allotmentKpis} />
      <KpiGrid items={priceKpis} />

      {/* 中签复盘 */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6">
        <p className="text-sm font-medium text-[var(--foreground)]">中签复盘</p>

        {hasPoolA || hasPoolB ? (
          <>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              {hasPoolA && <AllocationPoolTable pool={poolA as Record<string, unknown>} label="甲组" />}
              {hasPoolB && <AllocationPoolTable pool={poolB as Record<string, unknown>} label="乙组" />}
            </div>
            {trendRows.length >= 2 && <AllocationTrendSvg rows={trendRows} />}
          </>
        ) : (
          <p className="mt-3 text-sm text-[var(--muted)]">
            {oneLotRate !== undefined && !isNaN(oneLotRate)
              ? `一手中签率 ${oneLotRate.toFixed(2)}%${oneLotShares ? `（每手${Math.floor(oneLotShares)}股）` : ""}，完整配发明细暂未解析。`
              : basicInfo.length > 0
              ? `${basicInfo.join(" · ")}，详细甲乙组配发明细暂未解析。`
              : "配发数据待补充，IPO 结束后系统将自动抓取 HKEX 配发公告。"}
          </p>
        )}

        {sourceUrl && (
          <p className="mt-3 text-xs text-[var(--muted)]">
            配发公告：
            <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className="text-[var(--accent)] hover:underline">
              HKEX PDF
            </a>
          </p>
        )}
        {message && (
          <p className="mt-2 text-xs text-[var(--warning)]">{message}</p>
        )}
      </div>
    </div>
  );
}
