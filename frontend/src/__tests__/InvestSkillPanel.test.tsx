import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { InvestSkillPanel } from "@/components/results/InvestSkillPanel";
import type { AnalysisResult } from "@/lib/types";

describe("InvestSkillPanel", () => {
  it("renders backend InvestSkill result field names", () => {
    const result = {
      prospectus_info: {
        piotroski_f: {
          total_score: 5,
          max_score: 9,
          grade: "中等",
          profit_roa_improvement: false,
          profit_ocf_positive: false,
        },
        dcf_valuation: {
          intrinsic_value_hkd: 10028.79,
          upside_pct: 14.267,
        },
        sector_analysis: {
          sector_name: "硬科技（芯片/半导体/机器人）",
          sector_beta_score: 70,
          cycle_score: 75,
          policy_score: 90,
          sector_recommendation: "积极",
        },
      },
    } as unknown as AnalysisResult;

    render(<InvestSkillPanel result={result} />);

    expect(screen.getByText("5/9")).toBeDefined();
    expect(screen.getByText("中等")).toBeDefined();
    expect(screen.getByText("HK$10,028.79")).toBeDefined();
    expect(screen.getByText("14.3%")).toBeDefined();
    expect(screen.getByText("硬科技（芯片/半导体/机器人）")).toBeDefined();
    expect(screen.getByText("78/100")).toBeDefined();
    expect(screen.getByText("积极")).toBeDefined();
  });
});
