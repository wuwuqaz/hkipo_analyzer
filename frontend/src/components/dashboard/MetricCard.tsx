export function MetricCard({ title, value, tone = "text-[var(--foreground)]" }: { title: string; value: string; tone?: string }) {
  return (
    <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3.5 shadow-[0_8px_32px_rgba(3,8,18,0.25)] backdrop-blur">
      <p className="text-xs uppercase tracking-[0.15em] text-[var(--muted)]">{title}</p>
      <p className={`mt-2 text-xl font-semibold ${tone}`}>{value}</p>
    </article>
  );
}
