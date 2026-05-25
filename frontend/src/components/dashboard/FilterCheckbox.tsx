export function FilterCheckbox({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  const id = `filter-${label.replace(/[^a-zA-Z0-9]/g, '-')}`;
  return (
    <label htmlFor={id} className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-[var(--border)] bg-white/5 px-4 py-2.5 text-sm text-[var(--foreground)] transition hover:bg-white/8">
      <input id={id} type="checkbox" className="h-4 w-4 accent-[var(--accent)]" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}
