import { ScoreBadge } from "./ScoreBadge";
import { fmtPrice, fmtMillion, formatDate } from "@/lib/utils";
import type { AnalysisResult } from "@/lib/types";

export function CompanyHeader({ result }: { result: AnalysisResult }) {
  const pi = result.prospectus_info;
  const recommendation = result.subscription_recommendation || "—";
  const sector = pi?.sector ?? "unknown";
  const sectorMap: Record<string, string> = {
    healthcare: "医疗保健",
    hardtech: "硬科技",
    consumer: "消费",
    unknown: "未明确",
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <ScoreBadge label={recommendation} />
        <span className="text-xs text-[var(--muted)]">
          {sectorMap[sector] ?? sector}
        </span>
        <span className="text-xs text-[var(--muted)]">
          {result.hk_code ? `${result.hk_code}.HK` : "—"}
        </span>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="招股价" value={fmtPrice(pi?.offer_price)} />
        <Field label="每手股数" value={pi?.lot_size ? `${pi.lot_size}` : "—"} />
        <Field label="市值" value={fmtMillion(pi?.market_cap_hkd_million)} />
        <Field label="招股期" value={`${formatDate(result.apply_start_date as string)} ~ ${formatDate(result.apply_end_date as string)}`} />
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs uppercase tracking-wider text-[var(--muted)]">{label}</span>
      <span className="text-sm font-medium text-[var(--foreground)]">{value ?? "—"}</span>
    </div>
  );
}
