import { useMemo } from "react";
import type { AnalysisResult } from "@/lib/types";

interface CompanyProfileProps {
  result: AnalysisResult;
}

interface ProfileData {
  company_summary: string;
  what_do: string;
  who_for: string;
  how_money: string;
  is_segmented: boolean;
  industry: string;
  main_business: string;
  market_position: string;
  key_products: string[];
  geographic_focus: string;
  founded_year: number | null;
  headquarters: string;
  business_model: string;
  customer_type: string;
  customer_industries: string;
  revenue_scale: string;
  confidence: string;
}

function parseSegments(summary: string): { what_do: string; who_for: string; how_money: string; is_segmented: boolean } {
  const whatMatch = summary.match(/做什么[：:]\s*(.+?)(?=\n\s*(?:卖给谁|怎么赚钱)|$)/);
  const whoMatch = summary.match(/卖给谁[：:]\s*(.+?)(?=\n\s*(?:怎么赚钱)|$)/);
  const howMatch = summary.match(/怎么赚钱[：:]\s*(.+)$/);

  const segments = [
    (whatMatch?.[1] || "").trim(),
    (whoMatch?.[1] || "").trim(),
    (howMatch?.[1] || "").trim(),
  ];
  const filledCount = segments.filter((s) => s.length > 0).length;

  // 至少需要 2/3 段有内容才用分段展示，否则退化为纯文摘要
  if (filledCount >= 2) {
    return {
      what_do: segments[0],
      who_for: segments[1],
      how_money: segments[2],
      is_segmented: true,
    };
  }

  const plainLines = summary
    .split(/\n+/)
    .map((line) => line.replace(/^[\s\-*•\d.、）)]+/, "").trim())
    .filter((line) => line && !/^以下.*(?:三段|格式|提炼|描述)/.test(line));

  if (plainLines.length >= 3) {
    return {
      what_do: plainLines[0],
      who_for: plainLines[1],
      how_money: plainLines[2],
      is_segmented: true,
    };
  }

  return { what_do: "", who_for: "", how_money: "", is_segmented: false };
}

function useProfileData(result: AnalysisResult): ProfileData | null {
  return useMemo(() => {
    const pi = result.prospectus_info as Record<string, unknown> | undefined;
    const profile = pi?.company_profile as Record<string, unknown> | undefined;
    if (!profile) return null;

    const summary = String(profile.company_summary ?? "");
    const segments = parseSegments(summary);

    return {
      company_summary: summary,
      ...segments,
      industry: String(profile.industry ?? ""),
      main_business: String(profile.main_business ?? ""),
      market_position: String(profile.market_position ?? ""),
      key_products: (profile.key_products as string[] | undefined) || [],
      geographic_focus: String(profile.geographic_focus ?? ""),
      founded_year: profile.founded_year as number | null,
      headquarters: String(profile.headquarters ?? ""),
      business_model: String(profile.business_model ?? ""),
      customer_type: String(profile.customer_type ?? ""),
      customer_industries: String(profile.customer_industries ?? ""),
      revenue_scale: String(profile.revenue_scale ?? ""),
      confidence: String(profile.confidence ?? "missing"),
    };
  }, [result]);
}

function ConfidenceBadge({ confidence }: { confidence: string }) {
  const config: Record<string, { label: string; tone: string; bg: string }> = {
    high: { label: "高置信", tone: "text-[var(--success)]", bg: "bg-[var(--success)]/10 border-[var(--success)]/20" },
    medium: { label: "中置信", tone: "text-[var(--warning)]", bg: "bg-[var(--warning)]/10 border-[var(--warning)]/20" },
    low: { label: "低置信", tone: "text-[var(--danger)]", bg: "bg-[var(--danger)]/10 border-[var(--danger)]/20" },
    missing: { label: "缺失", tone: "text-[var(--muted)]", bg: "bg-[var(--muted)]/10 border-[var(--muted)]/20" },
  };
  const c = config[confidence] || config.missing;
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${c.bg} ${c.tone}`}>
      {c.label}
    </span>
  );
}

function TagChip({ children, tone = "default" }: { children: React.ReactNode; tone?: string }) {
  const toneMap: Record<string, string> = {
    default: "border-[var(--border)] bg-white/5 text-[var(--foreground)]",
    accent: "border-[var(--accent)]/30 bg-[var(--accent)]/10 text-[var(--accent)]",
    success: "border-[var(--success)]/30 bg-[var(--success)]/10 text-[var(--success)]",
    warning: "border-[var(--warning)]/30 bg-[var(--warning)]/10 text-[var(--warning)]",
  };
  return (
    <span className={`inline-flex items-center rounded-lg border px-2.5 py-1 text-xs font-medium ${toneMap[tone] || toneMap.default}`}>
      {children}
    </span>
  );
}

export function CompanyProfileCard({ result }: CompanyProfileProps) {
  const profile = useProfileData(result);

  if (!profile || profile.confidence === "missing") return null;

  const hasContent = profile.company_summary || profile.industry || profile.main_business || profile.market_position || profile.key_products.length > 0 || profile.geographic_focus || profile.founded_year || profile.headquarters || profile.business_model || profile.customer_type || profile.customer_industries || profile.revenue_scale;
  if (!hasContent) return null;

  return (
    <div className="space-y-4">
      {/* 三段式摘要（LLM模式） */}
      {profile.is_segmented ? (
        <div className="rounded-xl border border-[var(--border)]/50 bg-[var(--surface)] p-4">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted)]">公司简介</p>
            <ConfidenceBadge confidence={profile.confidence} />
          </div>
          <div className="space-y-3">
            {profile.what_do && (
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--accent)]">📌 做什么</p>
                <p className="mt-1 text-sm leading-relaxed text-[var(--foreground)]">{profile.what_do}</p>
              </div>
            )}
            <div className="grid gap-3 sm:grid-cols-2">
              {profile.who_for && (
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--warning)]">🎯 卖给谁</p>
                  <p className="mt-1 text-sm leading-relaxed text-[var(--foreground)]"><TagChip tone="warning">{profile.who_for}</TagChip></p>
                </div>
              )}
              {profile.how_money && (
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--success)]">💰 怎么赚钱</p>
                  <p className="mt-1 text-sm leading-relaxed text-[var(--foreground)]"><TagChip tone="success">{profile.how_money}</TagChip></p>
                </div>
              )}
            </div>
          </div>
        </div>
      ) : (
        /* 降级模式：单段摘要 */
        profile.company_summary && (
          <div className="rounded-xl border border-[var(--border)]/50 bg-[var(--surface)] p-4">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted)]">公司简介</p>
              <ConfidenceBadge confidence={profile.confidence} />
            </div>
            <p className="text-sm leading-relaxed text-[var(--foreground)] whitespace-pre-line">
              {profile.company_summary}
            </p>
          </div>
        )
      )}

      {/* 结构化标签网格 */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {profile.industry && (
          <div className="rounded-xl border border-[var(--border)]/50 bg-[var(--surface)] p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--muted)]">行业</p>
            <p className="mt-1.5 text-sm font-medium text-[var(--foreground)]">
              <TagChip tone="accent">{profile.industry}</TagChip>
            </p>
          </div>
        )}

        {profile.business_model && (
          <div className="rounded-xl border border-[var(--border)]/50 bg-[var(--surface)] p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--muted)]">商业模式</p>
            <p className="mt-1.5 text-sm font-medium text-[var(--foreground)]">
              <TagChip tone="accent">{profile.business_model}</TagChip>
            </p>
          </div>
        )}

        {profile.customer_type && (
          <div className="rounded-xl border border-[var(--border)]/50 bg-[var(--surface)] p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--muted)]">客户类型</p>
            <p className="mt-1.5 text-sm font-medium text-[var(--foreground)]">{profile.customer_type}</p>
          </div>
        )}

        {profile.customer_industries && (
          <div className="rounded-xl border border-[var(--border)]/50 bg-[var(--surface)] p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--muted)]">客户行业</p>
            <p className="mt-1.5 text-sm font-medium text-[var(--foreground)]">{profile.customer_industries}</p>
          </div>
        )}

        {profile.market_position && (
          <div className="rounded-xl border border-[var(--border)]/50 bg-[var(--surface)] p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--muted)]">市场地位</p>
            <p className="mt-1.5 text-sm font-medium text-[var(--foreground)]">
              <TagChip tone="success">{profile.market_position}</TagChip>
            </p>
          </div>
        )}

        {profile.revenue_scale && (
          <div className="rounded-xl border border-[var(--border)]/50 bg-[var(--surface)] p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--muted)]">营收规模</p>
            <p className="mt-1.5 text-sm font-medium text-[var(--foreground)]">{profile.revenue_scale}</p>
          </div>
        )}

        {profile.geographic_focus && (
          <div className="rounded-xl border border-[var(--border)]/50 bg-[var(--surface)] p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--muted)]">地域布局</p>
            <p className="mt-1.5 text-sm font-medium text-[var(--foreground)]">{profile.geographic_focus}</p>
          </div>
        )}

        {profile.founded_year && (
          <div className="rounded-xl border border-[var(--border)]/50 bg-[var(--surface)] p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--muted)]">成立年份</p>
            <p className="mt-1.5 text-sm font-medium text-[var(--foreground)]">{profile.founded_year}年</p>
          </div>
        )}

        {profile.headquarters && (
          <div className="rounded-xl border border-[var(--border)]/50 bg-[var(--surface)] p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--muted)]">总部</p>
            <p className="mt-1.5 text-sm font-medium text-[var(--foreground)]">{profile.headquarters}</p>
          </div>
        )}
      </div>

      {/* 核心产品 */}
      {profile.key_products.length > 0 && (
        <div className="rounded-xl border border-[var(--border)]/50 bg-[var(--surface)] p-4">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--muted)]">核心产品/业务线</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {profile.key_products.map((product, i) => (
              <TagChip key={i} tone="warning">{product}</TagChip>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
