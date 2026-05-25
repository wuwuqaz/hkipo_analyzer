const toneMap: Record<string, string> = {
  强: "text-[var(--success)] bg-[var(--success)]/10",
  高: "text-[var(--success)] bg-[var(--success)]/10",
  积极申购: "text-[var(--success)] bg-[var(--success)]/10",
  中等: "text-[var(--warning)] bg-[var(--warning)]/10",
  中: "text-[var(--warning)] bg-[var(--warning)]/10",
  中性试水: "text-[var(--accent)] bg-[var(--accent)]/10",
  弱: "text-[var(--danger)] bg-[var(--danger)]/10",
  低: "text-[var(--danger)] bg-[var(--danger)]/10",
  谨慎试水: "text-[var(--danger)] bg-[var(--danger)]/10",
  建议跳过: "text-[var(--danger)] bg-[var(--danger)]/10",
  缺失: "text-[var(--muted)] bg-white/5",
};

export function ScoreBadge({ label, className = "" }: { label: string; className?: string }) {
  const tone = toneMap[label] ?? "text-[var(--foreground)] bg-white/5";
  return (
    <span
      className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wider ${tone} ${className}`}
    >
      {label}
    </span>
  );
}
