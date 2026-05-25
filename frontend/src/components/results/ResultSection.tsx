export function ResultSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5 shadow-[0_8px_32px_rgba(3,8,18,0.25)] backdrop-blur">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--muted)]">{title}</p>
      <div className="mt-4">{children}</div>
    </section>
  );
}
