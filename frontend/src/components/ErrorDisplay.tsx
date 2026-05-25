export function ErrorDisplay({
  title = "Something went wrong",
  message,
  onRetry,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="rounded-3xl border border-[var(--danger)]/30 bg-[var(--surface)] p-6 text-center shadow-[0_8px_32px_rgba(3,8,18,0.25)] backdrop-blur">
      <p className="text-lg font-semibold text-[var(--danger)]">{title}</p>
      <p className="mt-2 text-sm leading-6 text-[var(--muted)]">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-4 inline-flex cursor-pointer items-center rounded-full border border-[var(--border)] bg-white/8 px-5 py-2 text-sm font-medium text-[var(--accent)] transition hover:bg-white/12"
        >
          Retry
        </button>
      )}
    </div>
  );
}
