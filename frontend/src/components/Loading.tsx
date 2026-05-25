export function Loading({ message = "Loading…" }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-12">
      <div
        className="h-8 w-8 rounded-full border-2 border-[var(--border)] border-t-[var(--accent)] motion-safe:animate-spin"
        aria-hidden="true"
      />
      <p className="text-sm tracking-wide text-[var(--muted)]">{message}</p>
    </div>
  );
}
