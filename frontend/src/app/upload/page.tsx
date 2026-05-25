"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { uploadPdf } from "@/lib/api";
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

export default function UploadPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [stockCode, setStockCode] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);

  const fileError = touched && !file ? "请选择招股书 PDF 文件" : null;
  const typeError = touched && file && !file.name.toLowerCase().endsWith(".pdf") ? "仅支持 PDF 文件" : null;
  const codeError = touched && stockCode.trim() && !/^\d{5}$/.test(stockCode.trim()) ? "股票代码应为 5 位数字" : null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setTouched(true);
    setError(null);

    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) return;
    if (stockCode.trim() && !/^\d{5}$/.test(stockCode.trim())) return;
    setSubmitting(true);
    try {
      const result = await uploadPdf(
        file,
        stockCode.trim() || undefined,
        companyName.trim() || undefined
      );
      router.push(`/jobs/${result.job_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传失败，请稍后重试。");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="mx-auto w-full max-w-2xl px-6 py-10 sm:px-10 lg:px-12">
      <section className="relative overflow-hidden rounded-[2rem] border border-[var(--border)] bg-[var(--surface-strong)] px-6 py-8 shadow-[0_32px_120px_rgba(3,8,18,0.55)] backdrop-blur sm:px-8 sm:py-10">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(114,230,255,0.18),transparent_32%),radial-gradient(circle_at_bottom_left,rgba(88,230,169,0.14),transparent_28%)]" />
        <div className="relative">
          <h1 className="text-3xl font-semibold tracking-tight text-white">上传招股书</h1>
          <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
            选择 PDF 招股书后启动分析。股票代码和公司名称可选，系统会尽量从文件中自动识别。
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
              <Label htmlFor="pdf">PDF 文件</Label>
              <input
                id="pdf"
                type="file"
                accept=".pdf,application/pdf"
                name="prospectus_pdf"
                aria-describedby={file ? "file-selected" : (fileError || typeError ? "file-error" : undefined)}
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className={`mt-1.5 block w-full text-sm file:mr-4 file:rounded-lg file:border-0 file:bg-[var(--accent)]/10 file:px-4 file:py-2.5 file:text-sm file:font-medium file:text-[var(--accent)] hover:file:bg-[var(--accent)]/20 ${
                  fileError || typeError
                    ? "text-[var(--danger)] file:bg-[var(--danger)]/10 file:text-[var(--danger)]"
                    : "text-[var(--muted)]"
                }`}
              />
              {fileError && <p id="file-error" className="mt-1.5 text-xs text-[var(--danger)]">{fileError}</p>}
              {typeError && <p id="file-error" className="mt-1.5 text-xs text-[var(--danger)]">{typeError}</p>}
              {file && !typeError && (
                <p id="file-selected" className="mt-2 text-xs text-[var(--muted)]">
                  已选择：{file.name} ({(file.size / 1024 / 1024).toFixed(2)} MB)
                </p>
              )}
            </div>

            <div>
              <Label htmlFor="stock_code">股票代码（可选）</Label>
              <Input
                id="stock_code"
                name="stock_code"
                placeholder="例如：01234"
                value={stockCode}
                onChange={(e) => setStockCode(e.target.value)}
                autoComplete="off"
                spellCheck={false}
              />
              {codeError && <p className="mt-1.5 text-xs text-[var(--danger)]">{codeError}</p>}
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
                    上传中…
                  </span>
                ) : (
                  "开始分析"
                )}
              </button>
            </div>
          </div>
        </form>
      </section>
    </main>
  );
}
