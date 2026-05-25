export function HeatPill({ label }: { label: string }) {
  let tone = "text-[var(--foreground)]";
  if (label === "热门" || label === "极热") tone = "text-[var(--danger)]";
  else if (label === "温" || label === "一般") tone = "text-[var(--warning)]";
  return <span className={`text-sm ${tone}`}>{label}</span>;
}
