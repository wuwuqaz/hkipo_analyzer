export function StatusBadge({ label, tone = "text-[var(--muted)]" }: { label: string; tone?: string }) {
  return (
    <span className={`inline-flex items-center rounded-full border border-[var(--border)] bg-white/8 px-3 py-1 text-xs font-semibold uppercase tracking-[0.28em] ${tone}`}>
      {label}
    </span>
  );
}
