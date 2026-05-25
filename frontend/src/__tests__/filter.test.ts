import { describe, it, expect } from "vitest";
import type { AnalysisResult } from "@/lib/types";

function applyFilters(
  ipo: AnalysisResult,
  filters: { highScore?: boolean; lowRisk?: boolean; hasCornerstone?: boolean; valuationOk?: boolean }
): boolean {
  const tradeScore = ipo.strict_ipo_score ?? ipo.ipo_trade_score ?? ipo.trade_score ?? 0;
  const riskPenalty = ipo.risk_penalty ?? 0;
  const cs = ipo.prospectus_info?.cornerstone_analysis;
  const hasCs = cs !== undefined && cs.score > 0;
  const valLabel = ipo.valuation_pressure_label;
  const valOk = valLabel === "合理" || valLabel === "低估";

  if (filters.highScore && tradeScore < 65) return false;
  if (filters.lowRisk && riskPenalty > 3) return false;
  if (filters.hasCornerstone && !hasCs) return false;
  if (filters.valuationOk && !valOk) return false;
  return true;
}

function makeMockIpo(overrides: Partial<AnalysisResult> = {}): AnalysisResult {
  return {
    hk_code: "00000",
    stock_code: "00000",
    company_name: "Test",
    score: 50,
    trade_score: 50,
    long_term_score: 50,
    valuation_score: 50,
    fundamental_score: 50,
    valuation_pressure_label: "合理",
    market_heat: "温",
    subscription_recommendation: "中等",
    ...overrides,
  };
}

describe("IPO filter logic", () => {
  it("passes with no filters active", () => {
    expect(applyFilters(makeMockIpo(), {})).toBe(true);
  });

  it("filters low score when highScore filter is on", () => {
    const ipo = makeMockIpo({ strict_ipo_score: 40 });
    expect(applyFilters(ipo, { highScore: true })).toBe(false);
  });

  it("keeps high score when highScore filter is on", () => {
    const ipo = makeMockIpo({ strict_ipo_score: 80 });
    expect(applyFilters(ipo, { highScore: true })).toBe(true);
  });

  it("filters high risk when lowRisk filter is on", () => {
    const ipo = makeMockIpo({ risk_penalty: 10 });
    expect(applyFilters(ipo, { lowRisk: true })).toBe(false);
  });

  it("keeps low risk when lowRisk filter is on", () => {
    const ipo = makeMockIpo({ risk_penalty: 0 });
    expect(applyFilters(ipo, { lowRisk: true })).toBe(true);
  });

  it("filters no cornerstone when hasCornerstone filter is on", () => {
    const ipo = makeMockIpo();
    expect(applyFilters(ipo, { hasCornerstone: true })).toBe(false);
  });

  it("keeps has cornerstone when filter is on", () => {
    const ipo = makeMockIpo({
      prospectus_info: {
        sector: "healthcare",
        offer_price: 10,
        lot_size: 1000,
        market_cap_hkd_million: 1000,
        cornerstone_analysis: { score: 50, investors: [] },
      },
    });
    expect(applyFilters(ipo, { hasCornerstone: true })).toBe(true);
  });

  it("filters bad valuation when valuationOk filter is on", () => {
    const ipo = makeMockIpo({ valuation_pressure_label: "高" });
    expect(applyFilters(ipo, { valuationOk: true })).toBe(false);
  });
});
