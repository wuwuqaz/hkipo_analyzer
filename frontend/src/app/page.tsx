import { fetchHealth, fetchVersion } from "@/lib/api";

export const dynamic = "force-dynamic";

function StatusBadge({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center rounded-full border border-[var(--border)] bg-white/8 px-3 py-1 text-xs font-semibold uppercase tracking-[0.28em] text-[var(--accent)]">
      {label}
    </span>
  );
}

function MetricCard({
  title,
  value,
  tone = "text-[var(--foreground)]",
}: {
  title: string;
  value: string;
  tone?: string;
}) {
  return (
    <article className="rounded-3xl border border-[var(--border)] bg-[var(--surface)] p-5 shadow-[0_24px_80px_rgba(3,8,18,0.35)] backdrop-blur">
      <p className="text-sm uppercase tracking-[0.2em] text-[var(--muted)]">{title}</p>
      <p className={`mt-3 text-2xl font-semibold ${tone}`}>{value}</p>
    </article>
  );
}

export default async function Home() {
  const [health, version] = await Promise.all([fetchHealth(), fetchVersion()]);

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-6xl flex-col px-6 py-10 sm:px-10 lg:px-12">
      <section className="relative overflow-hidden rounded-[2rem] border border-[var(--border)] bg-[var(--surface-strong)] px-6 py-8 shadow-[0_32px_120px_rgba(3,8,18,0.55)] backdrop-blur sm:px-8 sm:py-10">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(114,230,255,0.18),transparent_32%),radial-gradient(circle_at_bottom_left,rgba(88,230,169,0.14),transparent_28%)]" />
        <div className="relative flex flex-col gap-6">
          <StatusBadge label="Migration Console" />
          <div className="max-w-3xl">
            <h1 className="text-4xl font-semibold tracking-tight text-white sm:text-5xl">
              HK IPO Analyzer
            </h1>
            <p className="mt-4 text-base leading-7 text-[var(--muted)] sm:text-lg">
              System Status for the FastAPI + Next.js migration. This page verifies that the frontend can
              reach the backend health and version endpoints before we move business workflows over.
            </p>
          </div>
        </div>
      </section>

      <section className="mt-8">
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="text-sm uppercase tracking-[0.26em] text-[var(--muted)]">System Status</p>
            <h2 className="mt-2 text-2xl font-semibold text-white">Live service snapshot</h2>
          </div>
          <p className="text-sm text-[var(--muted)]">Rendered on the server from the API responses.</p>
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            title="API status"
            value={health.status}
            tone={health.status === "ok" ? "text-[var(--success)]" : "text-[var(--danger)]"}
          />
          <MetricCard title="Database" value={health.dbStatus} />
          <MetricCard title="Worker" value={health.workerStatus} />
          <MetricCard title="Uptime" value={`${health.uptimeSeconds.toFixed(1)}s`} />
        </div>
      </section>

      <section className="mt-8 grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
        <article className="rounded-[2rem] border border-[var(--border)] bg-[var(--surface)] p-6 backdrop-blur">
          <p className="text-sm uppercase tracking-[0.22em] text-[var(--muted)]">Version Signals</p>
          <div className="mt-6 grid gap-4 sm:grid-cols-3">
            <MetricCard title="App version" value={version.appVersion} />
            <MetricCard title="Python" value={version.pythonVersion} />
            <MetricCard title="Analyzer" value={version.ipoAnalyzerVersion} />
          </div>
        </article>

        <aside className="rounded-[2rem] border border-[var(--border)] bg-[var(--surface)] p-6 backdrop-blur">
          <p className="text-sm uppercase tracking-[0.22em] text-[var(--muted)]">Next Step</p>
          <h3 className="mt-3 text-2xl font-semibold text-white">Frontend skeleton is online</h3>
          <p className="mt-4 text-sm leading-7 text-[var(--muted)]">
            Upload, history, and reanalyze flows can now move behind this shell in later commits without
            changing the deployment topology again.
          </p>
        </aside>
      </section>
    </main>
  );
}
