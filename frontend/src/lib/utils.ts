/* ------------------------------------------------------------------ */
/* 数值格式化工具                                                      */
/* ------------------------------------------------------------------ */

/** 数据可用性状态 — 配合后端 data_availability 使用 */
export type AvailabilityStatus = "available" | "not_applicable" | "not_found";

export interface AvailabilityMeta {
  status: AvailabilityStatus;
  reason?: string;
  source_excerpt?: string | null;
  method?: "regex" | "computed" | "table";
}

export function safeNumber(v: unknown, fallback = 0): number {
  if (v === null || v === undefined) return fallback;
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

export function fmtNum(v: unknown, suffix = ""): string {
  if (v === null || v === undefined) return "--";
  const n = Number(v);
  if (isNaN(n)) return String(v);
  return `${n.toLocaleString()}${suffix}`;
}

export function fmtPct(v: unknown): string {
  if (v === null || v === undefined) return "--";
  const n = Number(v);
  if (isNaN(n)) return String(v);
  return `${n.toFixed(2)}%`;
}

export function fmtInt(v: unknown): string {
  if (v === null || v === undefined) return "--";
  const n = Number(v);
  if (isNaN(n)) return String(v);
  return n.toLocaleString();
}

export function fmtPrice(v: unknown): string {
  if (v === null || v === undefined) return "--";
  const n = Number(v);
  if (isNaN(n)) return "--";
  return `HK$${n.toFixed(2)}`;
}

export function fmtMillion(v: unknown): string {
  if (v === null || v === undefined) return "--";
  const n = Number(v);
  if (isNaN(n)) return "--";
  return `HK$${(n / 100).toFixed(2)}亿`;
}

function toValidDate(date: unknown): Date | null {
  if (date === null || date === undefined || date === "" || date === "--") {
    return null;
  }
  const d = date instanceof Date ? date : new Date(String(date));
  return Number.isNaN(d.getTime()) ? null : d;
}

export function formatDate(date: string | Date | null | undefined): string {
  const d = toValidDate(date);
  if (!d) return "--";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(d);
}

export function formatDateTime(date: string | Date | null | undefined): string {
  const d = toValidDate(date);
  if (!d) return "--";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(d);
}

export function formatNumber(v: unknown): string {
  if (v === null || v === undefined || v === "") return "--";
  const n = Number(v);
  if (isNaN(n)) return "--";
  if (n >= 100000000) return `${(n / 100000000).toFixed(1)}亿`;
  if (n >= 10000) return `${(n / 10000).toFixed(1)}万`;
  if (n >= 1) return n.toFixed(0);
  return n.toFixed(2);
}

export function formatPrice(v: unknown): string {
  if (v === null || v === undefined || v === "") return "--";
  const n = Number(v);
  if (isNaN(n)) return "--";
  return `HK$${n.toFixed(2)}`;
}

export function compactShares(v: unknown): string {
  const n = Number(v);
  if (isNaN(n)) return "--";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1000) return `${Math.floor(n / 1000)}K`;
  return String(n);
}

export function formatLots(v: unknown): string {
  if (v === null || v === undefined || v === "") return "--";
  const n = Number(v);
  if (isNaN(n) || n <= 0) return "--";
  if (n >= 10000) return `${(n / 10000).toFixed(1)}万手`;
  return `${n.toFixed(0)}手`;
}

export function scoreColor(v: number): string {
  if (v >= 70) return "text-[var(--success)]";
  if (v >= 40) return "text-[var(--warning)]";
  return "text-[var(--danger)]";
}

export function barColor(v: number): string {
  if (v >= 70) return "var(--success)";
  if (v >= 40) return "var(--warning)";
  return "var(--danger)";
}

export function scoreTone(v: number): string {
  if (v >= 70) return "text-[var(--success)]";
  if (v >= 40) return "text-[var(--warning)]";
  return "text-[var(--danger)]";
}
