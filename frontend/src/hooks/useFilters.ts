"use client";

import { useMemo, useState } from "react";
import { safeNumber } from "@/lib/utils";

export function useFilters<T extends Record<string, unknown>>(items: T[]) {
  const [filterHighScore, setFilterHighScore] = useState(false);
  const [filterLowRisk, setFilterLowRisk] = useState(false);
  const [filterHasCornerstone, setFilterHasCornerstone] = useState(false);
  const [filterValuationOk, setFilterValuationOk] = useState(false);

  const filtered = useMemo(() => {
    return items.filter((ipo) => {
      const tradeScore = safeNumber(ipo["strict_ipo_score"] ?? ipo["ipo_trade_score"] ?? ipo["trade_score"] ?? ipo["score"] ?? 0);
      const riskPenalty = safeNumber(ipo["risk_penalty"] ?? 0);
      const cs = (ipo["prospectus_info"] as Record<string, unknown> | undefined)?.["cornerstone_analysis"] as Record<string, unknown> | undefined;
      const hasCs = cs && safeNumber(cs["score"] ?? 0) > 0;
      const valLabel = String(ipo["valuation_pressure_label"] ?? "");
      const valOk = valLabel === "合理" || valLabel === "低估";

      if (filterHighScore && tradeScore < 65) return false;
      if (filterLowRisk && riskPenalty > 3) return false;
      if (filterHasCornerstone && !hasCs) return false;
      if (filterValuationOk && !valOk) return false;
      return true;
    });
  }, [items, filterHighScore, filterLowRisk, filterHasCornerstone, filterValuationOk]);

  return {
    filtered,
    filterHighScore, setFilterHighScore,
    filterLowRisk, setFilterLowRisk,
    filterHasCornerstone, setFilterHasCornerstone,
    filterValuationOk, setFilterValuationOk,
    total: items.length,
  };
}
