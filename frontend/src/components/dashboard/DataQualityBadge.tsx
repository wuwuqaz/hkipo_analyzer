export function DataQualityBadge({ flags, confidence }: { flags?: string[]; confidence?: string }) {
  const hasIssue = (flags && flags.length > 0) || confidence === "needs_review" || confidence === "low";
  const severe = flags && flags.some((f) => f.includes("不一致") || f.includes("冲突"));
  if (severe) {
    return <span className="ml-2 inline-flex items-center rounded-full bg-[var(--danger)]/10 px-2 py-0.5 text-xs font-medium text-[var(--danger)]">需复核</span>;
  }
  if (hasIssue) {
    return <span className="ml-2 inline-flex items-center rounded-full bg-[var(--warning)]/10 px-2 py-0.5 text-xs font-medium text-[var(--warning)]">中</span>;
  }
  return <span className="ml-2 inline-flex items-center rounded-full bg-[var(--success)]/10 px-2 py-0.5 text-xs font-medium text-[var(--success)]">高</span>;
}
