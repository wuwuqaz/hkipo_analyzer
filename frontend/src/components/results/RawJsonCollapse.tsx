"use client";

import { useState } from "react";

export function RawJsonCollapse({ data }: { data: unknown }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-strong)] overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full cursor-pointer items-center justify-between px-4 py-3 text-sm font-medium text-[var(--muted)] transition hover:text-[var(--foreground)]"
      >
        <span>原始 JSON</span>
        <span className="text-xs">{open ? "收起 ▲" : "展开 ▼"}</span>
      </button>
      {open && (
        <pre className="max-h-96 overflow-auto border-t border-[var(--border)] p-4 text-xs leading-relaxed text-[var(--foreground)]">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}
