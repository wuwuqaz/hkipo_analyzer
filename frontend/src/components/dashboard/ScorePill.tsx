export function ScorePill({ score }: { score: number }) {
  let tone = "text-[var(--danger)]";
  if (score >= 70) tone = "text-[var(--success)]";
  else if (score >= 50) tone = "text-[var(--warning)]";
  return <span className={`font-semibold ${tone}`}>{score}</span>;
}
