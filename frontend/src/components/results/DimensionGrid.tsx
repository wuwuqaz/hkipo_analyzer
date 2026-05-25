import { scoreTone } from "@/lib/utils";

const dimNames: Record<string, string> = {
  heat: "热度",
  quality: "质地",
  scale: "规模",
  cornerstone: "基石",
};

const dimColors = [
  "border-t-[var(--danger)]",
  "border-t-[var(--accent)]",
  "border-t-[var(--accent-strong)]",
  "border-t-[var(--success)]",
];

import type { AnalysisResult } from "@/lib/types";

export function DimensionGrid({ result }: { result: AnalysisResult }) {
  const breakdown = result.score_breakdown ?? {};
  const entries = Object.entries(dimNames)
    .map(([key, label]) => {
      const item = breakdown[key];
      const rawScore = typeof item?.score === "number" ? item.score : 0;
      const maxScore = typeof item?.max_score === "number" ? item.max_score : 100;
      const normalized = typeof item?.normalized_score === "number" ? item.normalized_score : (maxScore ? Math.round((rawScore / maxScore) * 100) : 0);
      return {
        key,
        label,
        score: normalized,
        rawScore,
        maxScore,
        detail: String(item?.detail ?? "—"),
      };
    })
    .filter((_, i) => i < 4);

  if (entries.length === 0) return null;

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {entries.map((item, idx) => (
        <div
          key={item.key}
          className={`rounded-xl border border-[var(--border)] bg-[var(--surface-strong)] p-4 border-t-4 ${dimColors[idx % dimColors.length]}`}
        >
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-[var(--muted)]">{item.label}</span>
            <div className="text-right">
              <span className={`text-lg font-bold ${scoreTone(item.score)}`}>{item.score}</span>
              <span className="ml-1 text-[10px] text-[var(--muted)]">/100</span>
            </div>
          </div>
          <p className="mt-1 text-[10px] text-[var(--muted)]">
            原始分 {item.rawScore}/{item.maxScore}
          </p>
          <p className="mt-0.5 text-xs text-[var(--muted)] line-clamp-2">{item.detail}</p>
        </div>
      ))}
    </div>
  );
}


