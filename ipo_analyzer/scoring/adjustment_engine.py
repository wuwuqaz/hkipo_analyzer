"""集中计算所有调整项."""

from __future__ import annotations

from .models import ScoringInput, DimensionScores, Adjustments


class AdjustmentEngine:
    def calculate(self, inp: ScoringInput, dims: DimensionScores) -> Adjustments:
        # peer_adj
        peer_adj = 0.0
        if inp.peer_adj_label == "excellent":
            peer_adj = 6.0
        elif inp.peer_adj_label == "fair":
            peer_adj = 0.0
        elif inp.peer_adj_label in ("overvalued", "clearly_overvalued"):
            peer_adj = -6.0

        # val_penalty
        val_penalty = 0.0
        if inp.valuation_label == "很贵":
            val_penalty = -5.0
        elif inp.valuation_label == "偏贵":
            val_penalty = -3.0
        elif inp.valuation_label == "合理":
            val_penalty = 0.0
        elif inp.valuation_label == "便宜":
            val_penalty = 2.0

        # pricing_gap_adj
        pricing_gap_adj = inp.pricing_gap_adj

        # risk_penalty
        severe_categories = {"legal", "regulatory", "accounting"}
        extra_risk = 0.0
        for cat in severe_categories:
            if cat in inp.risk_categories and inp.risk_categories[cat]:
                extra_risk += 2.0
        risk_penalty = min(inp.risk_penalty + extra_risk, 20.0)

        # cornerstone_penalty
        cornerstone_penalty = min(len(inp.cornerstone_red_flags) * 3.0, 15.0)

        return Adjustments(
            peer_adj=peer_adj,
            val_penalty=val_penalty,
            pricing_gap_adj=pricing_gap_adj,
            risk_penalty=risk_penalty,
            cornerstone_penalty=cornerstone_penalty,
        )
