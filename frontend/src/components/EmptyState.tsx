export function EmptyState({ message = "No data yet." }: { message?: string }) {
  return (
    <div className="rounded-3xl border border-[var(--border)] bg-[var(--surface)] p-10 text-center shadow-[0_8px_32px_rgba(3,8,18,0.25)] backdrop-blur">
      <p className="text-sm tracking-wide text-[var(--muted)]">{message}</p>
    </div>
  );
}
