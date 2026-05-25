import type { AnalysisResult } from "@/lib/types";

export function InvestmentThesisCard({ result }: { result: AnalysisResult }) {
  const pi = result.prospectus_info;
  const thesis = result.investment_thesis ?? pi?.investment_thesis ?? {};

  if (!Object.keys(thesis).length) {
    return <p className="text-sm text-[var(--muted)]">暂无投研结论数据。</p>;
  }

  const shortCase = (thesis.short_seller_case as Record<string, unknown> | undefined) ?? {};
  const targetRange = shortCase.target_price_range_hkd as unknown;

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-[160px_1fr_170px]">
        <Metric label="整体口径" value={String(thesis.overall_tone ?? "—")} />
        <Metric label="一句话结论" value={String(thesis.one_line_conclusion ?? thesis.conclusion ?? "—")} />
        <Metric label="做空重估区间" value={fmtRange(targetRange)} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ListBlock title="基本面诊断" items={asList(thesis.fundamental_diagnosis)} />
        <ListBlock title="商业模式要点" items={asList(thesis.business_model_takeaways)} />
        <ListBlock title="估值要点" items={asList(thesis.valuation_takeaways)} />
        <ListBlock title="做空视角" items={asList(shortCase.bear_points)} />
        <ListBlock title="催化观察" items={asList(thesis.catalysts)} />
        <ListBlock title="反证指标" items={asList(thesis.invalidation_signals)} />
      </div>

      {asList(thesis.missing_angles).length > 0 && (
        <div className="rounded-xl border border-[var(--warning)]/30 bg-[var(--warning)]/5 p-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--warning)]">缺失角度</p>
          <ul className="mt-2 list-disc space-y-1 pl-4 text-sm text-[var(--foreground)]">
            {asList(thesis.missing_angles).map((item, idx) => (
              <li key={idx}>{item}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-strong)] p-4">
      <p className="text-xs uppercase tracking-wider text-[var(--muted)]">{label}</p>
      <p className="mt-1 text-sm font-semibold leading-6 text-[var(--foreground)]">{value || "—"}</p>
    </div>
  );
}

function ListBlock({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-strong)] p-4">
      <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted)]">{title}</p>
      {items.length ? (
        <ul className="mt-2 list-disc space-y-1 pl-4 text-sm leading-6 text-[var(--foreground)]">
          {items.slice(0, 5).map((item, idx) => (
            <li key={idx}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-[var(--muted)]">暂无明确结论。</p>
      )}
    </div>
  );
}

function asList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item)).filter(Boolean);
}

function fmtRange(value: unknown) {
  if (!Array.isArray(value) || value.length < 2) return "—";
  const [low, high] = value;
  if (typeof low !== "number" || typeof high !== "number") return "—";
  return `HK$${low.toFixed(2)}-${high.toFixed(2)}`;
}
