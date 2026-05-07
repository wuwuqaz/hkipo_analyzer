#!/usr/bin/env python3
"""基石分析 V2 回归测试"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ipo_analyzer.cornerstone import CornerstoneAnalyzer
from ipo_analyzer.parser import ProspectusParser


def _row_by_short_name(rows, keyword):
    keyword = keyword.lower()
    for row in rows:
        haystack = f"{row.get('short_name', '')} {row.get('name', '')}".lower()
        if keyword in haystack:
            return row
    return None


def test_jitai_cornerstone_v2():
    pdf_path = os.path.join("temp", "07666_prospectus.pdf")
    if not os.path.exists(pdf_path):
        print("SKIP: temp/07666_prospectus.pdf not found")
        return

    info = ProspectusParser().parse_pdf_file(pdf_path, stock_code="07666", company_name="剂泰科技")
    ca = info.get("cornerstone_analysis") or {}
    rows = ca.get("cornerstone_investors") or []

    print("label:", ca.get("label"), ca.get("grade_band"), ca.get("score"))
    print("summary:", ca.get("combination_summary"))
    print("concerns:", ca.get("concerns"))

    assert len(rows) == 18, f"Expected 18 cornerstone rows, got {len(rows)}"
    assert ca.get("label") == "A级", f"Expected A级, got {ca.get('label')}"
    assert ca.get("grade_band") == "强A", f"Expected 强A, got {ca.get('grade_band')}"
    assert 80 <= ca.get("score", 0) < 85, f"Expected strong A score, got {ca.get('score')}"
    assert ca.get("dimension_scores"), "Expected V2 dimension scores"
    assert "无国际主权" in "；".join(ca.get("concerns", [])), "Expected no-sovereign concern"
    assert "无产业药企" in "；".join(ca.get("concerns", [])), "Expected no-industrial concern"

    expected_tiers = {
        "BlackRock": "S",
        "UBS": "A",
        "China Venture": "A",
        "HHLRA": "A",
        "Deerfield": "A",
        "RTW": "A",
        "Lake Bleu": "A",
    }
    for name, tier in expected_tiers.items():
        row = _row_by_short_name(rows, name)
        assert row, f"Missing cornerstone row: {name}"
        assert row.get("tier") == tier, f"{name} expected {tier}, got {row.get('tier')}"
        assert row.get("category"), f"{name} missing category"
        assert row.get("role_note"), f"{name} missing role_note"


def test_cornerstone_edge_rules():
    analyzer = CornerstoneAnalyzer()
    assert analyzer._effective_tier_score("S", 0.8) == analyzer.TIER_BASE_SCORE["A"]
    assert analyzer._effective_tier_score("A", 0.8) == analyzer.TIER_BASE_SCORE["B"]

    empty = analyzer.analyze("This prospectus has no relevant investor chapter.")
    assert empty.get("label") == "未披露"
    assert empty.get("red_flags"), "Expected red flag for missing cornerstone chapter"

    spv = analyzer.analyze(
        "Cornerstone Investors\n"
        "BlackRock will subscribe as a cornerstone investor. "
        "The investor is a newly incorporated special purpose vehicle in the British Virgin Islands. "
        "The cornerstone investors represent approximately 85% of the offer shares."
    )
    assert any("超过80" in item for item in spv.get("red_flags", [])), "Expected high cornerstone pct red flag"


def main():
    test_jitai_cornerstone_v2()
    test_cornerstone_edge_rules()
    print("✅ cornerstone V2 tests passed")


if __name__ == "__main__":
    main()
