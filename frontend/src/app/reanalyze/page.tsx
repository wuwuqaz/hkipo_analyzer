"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { reanalyzeJob } from "@/lib/api";
import { ErrorDisplay } from "@/components/ErrorDisplay";

function Label({ children, htmlFor }: { children: React.ReactNode; htmlFor: string }) {
  return (
    <label htmlFor={htmlFor} className="block text-sm font-medium text-[var(--muted)]">
      {children}
    </label>
  );
}

function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className="mt-1.5 w-full rounded-xl border border-[var(--border)] bg-white/5 px-4 py-2.5 text-sm text-[var(--foreground)] placeholder:text-[var(--muted)]/60 focus:border-[var(--accent)]/50 focus:outline-none focus:ring-1 focus:ring-[var(--accent)]/30"
    />
  );
}

function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className="mt-1.5 w-full rounded-xl border border-[var(--border)] bg-white/5 px-4 py-2.5 text-sm text-[var(--foreground)] placeholder:text-[var(--muted)]/60 focus:border-[var(--accent)]/50 focus:outline-none focus:ring-1 focus:ring-[var(--accent)]/30"
    />
  );
}

export default function ReanalyzePage() {
  const router = useRouter();
  const [stockCode, setStockCode] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [marketData, setMarketData] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);

  let jsonValid: boolean | null = null;
  if (marketData.trim()) {
    try {
      JSON.parse(marketData.trim());
      jsonValid = true;
    } catch {
      jsonValid = false;
    }
  }

  const codeError = touched && !stockCode.trim() ? "请输入股票代码" : null;
  const codeFormatError = touched && stockCode.trim() && !/^\d{5}$/.test(stockCode.trim()) ? "股票代码应为 5 位数字" : null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setTouched(true);
    setError(null);

    if (!stockCode.trim()) return;
    if (!/^\d{5}$/.test(stockCode.trim())) return;
    let historical_market_data: Record<string, unknown> | undefined;
    if (marketData.trim()) {
      try {
        historical_market_data = JSON.parse(marketData.trim());
      } catch {
        return;
      }
    }

    setSubmitting(true);
    try {
      const result = await reanalyzeJob(
        {
          stock_code: stockCode.trim(),
          company_name: companyName.trim() || undefined,
          historical_market_data,
        }
      );
      router.push(`/jobs/${result.job_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "重新分析失败，请稍后重试。");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="mx-auto w-full max-w-2xl px-6 py-10 sm:px-10 lg:px-12">
      <section className="relative overflow-hidden rounded-[2rem] border border-[var(--border)] bg-[var(--surface-strong)] px-6 py-8 shadow-[0_32px_120px_rgba(3,8,18,0.55)] backdrop-blur sm:px-8 sm:py-10">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(114,230,255,0.18),transparent_32%),radial-gradient(circle_at_bottom_left,rgba(88,230,169,0.14),transparent_28%)]" />
        <div className="relative">
          <h1 className="text-3xl font-semibold tracking-tight text-white">重新分析</h1>
          <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
            按股票代码重新跑一遍分析。可选填历史孖展、超购等市场数据，用 JSON 格式补充。
          </p>
        </div>
      </section>

      <section className="mt-8">
        <form
          onSubmit={handleSubmit}
          className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5 shadow-[0_8px_32px_rgba(3,8,18,0.25)] backdrop-blur sm:p-8"
        >
          <div className="flex flex-col gap-5">
            <div>
              <Label htmlFor="stock_code">股票代码</Label>
              <Input
                id="stock_code"
                name="stock_code"
                placeholder="例如：09995"
                value={stockCode}
                onChange={(e) => setStockCode(e.target.value)}
                required
                autoComplete="off"
                spellCheck={false}
              />
              {codeError && <p className="mt-1.5 text-xs text-[var(--danger)]">{codeError}</p>}
              {codeFormatError && <p className="mt-1.5 text-xs text-[var(--danger)]">{codeFormatError}</p>}
            </div>

            <div>
              <Label htmlFor="company_name">公司名称（可选）</Label>
              <Input
                id="company_name"
                name="company_name"
                placeholder="例如：某某控股有限公司"
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                autoComplete="off"
                spellCheck={false}
              />
            </div>

            <div>
              <Label htmlFor="market_data">历史市场数据（可选 JSON）</Label>
              <div className="relative">
                <Textarea
                  id="market_data"
                  rows={4}
                  placeholder={`{\n  "margin_total": 123.45,\n  "public_offer": 1.23,\n  "actual_over_sub_ratio": 456.7\n}`}
                  value={marketData}
                  onChange={(e) => setMarketData(e.target.value)}
                />
                {marketData.trim() && (
                  <span className={`absolute right-3 top-3 text-sm ${jsonValid ? "text-[var(--success)]" : "text-[var(--danger)]"}`}>
                    {jsonValid ? "✓" : "✗"}
                  </span>
                )}
              </div>
              {jsonValid === false && (
                <p className="mt-1.5 text-xs text-[var(--danger)]">JSON 格式无效，请检查语法</p>
              )}
            </div>

            {error && <ErrorDisplay message={error} />}

            <div className="pt-2">
              <button
                type="submit"
                disabled={submitting}
                className="inline-flex w-full cursor-pointer items-center justify-center rounded-xl bg-[var(--accent)]/10 px-6 py-3 text-sm font-semibold text-[var(--accent)] transition hover:bg-[var(--accent)]/20 disabled:opacity-50 sm:w-auto"
              >
                {submitting ? (
                  <span className="flex items-center gap-2">
                    <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-[var(--border)] border-t-[var(--accent)]" />
                    启动中…
                  </span>
                ) : (
                  "开始重新分析"
                )}
              </button>
            </div>
          </div>
        </form>
      </section>
    </main>
  );
}
