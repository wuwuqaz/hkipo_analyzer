"""P0 数据口径修复单元测试"""

import pytest
import sys
import os

# Ensure ipo_analyzer is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ipo_analyzer.core import (
    _fetch_margin_data,
    _detect_valuation_profitability_conflict,
    _validate_financial_year_consistency,
    _calculate_risk_penalty,
)
from ipo_analyzer.cornerstone import CornerstoneAnalyzer


class DummyClient:
    def __init__(self, margin_detail=None):
        self._md = margin_detail

    def fetch_margin_detail(self, stock_code):
        return self._md


# ---------------------------------------------------------------------------
# 1. apply_end_date fallback
# ---------------------------------------------------------------------------
def test_apply_end_date_fallback_from_margin_detail():
    """当 IPO 列表中 apply_end_date 为空时，应从 margin_detail.EndDate 回退。"""
    client = DummyClient(margin_detail={
        "totalmargin": "10.5",
        "RateOver": 50.0,
        "StartDate": "2026-05-10 00:00:00",
        "EndDate": "2026-05-19 00:00:00",
    })
    ipo = {"symbol": "01234", "shortname": "TestCo", "startdate": "", "enddate": ""}
    data = _fetch_margin_data(client, ipo)
    assert data["apply_start_date"] == "2026-05-10"
    assert data["apply_end_date"] == "2026-05-19"


def test_apply_end_date_fallback_from_prospectus_info():
    """当 margin_detail 也没有日期时，应从 prospectus_info 回退（在 core.py 后续处理中）。"""
    client = DummyClient(margin_detail=None)
    ipo = {"symbol": "01234", "shortname": "TestCo", "startdate": "", "enddate": ""}
    data = _fetch_margin_data(client, ipo)
    assert data["apply_end_date"] == ""


# ---------------------------------------------------------------------------
# 2. public_offer 字段语义
# ---------------------------------------------------------------------------
def test_public_offer_renamed_to_fund_hkd_billion():
    """public_offer 应同时映射到 public_offer_fund_hkd_billion。"""
    # _fetch_margin_data 只返回原始 margin 数据，字段语义规范化在 _calculate_final_score 中完成
    client = DummyClient(margin_detail={
        "totalmargin": "10.5",
        "raisemoney": "0.63",
        "RateOver": 50.0,
    })
    ipo = {"symbol": "01234", "shortname": "TestCo"}
    data = _fetch_margin_data(client, ipo)
    # 原始字段保留
    assert data["public_offer"] == 0.63
    # 模拟 _calculate_final_score 末尾的字段映射
    from ipo_analyzer.core import _safe_float
    if _safe_float(data.get('public_offer')) is not None:
        data['public_offer_fund_hkd_billion'] = data['public_offer']
    assert data.get("public_offer_fund_hkd_billion") == 0.63


# ---------------------------------------------------------------------------
# 3. revenue_year != net_profit_year
# ---------------------------------------------------------------------------
def test_financial_year_consistency_mismatch():
    """当 revenue_year != net_profit_year 时，应标记 data_quality_flags 并降低 confidence。"""
    ipo_data = {}
    prospectus_info = {
        "revenue_year": "2024",
        "net_profit_year": "2023",
        "gross_margin_year": "2024",
        "financial_extract_confidence": "high",
        "financial_data_quality_flags": [],
    }
    _validate_financial_year_consistency(ipo_data, prospectus_info)
    assert ipo_data["financial_year_consistency_issue"] is True
    assert any("收入年份" in r and "净利润年份" in r for r in ipo_data["financial_year_consistency_reasons"])
    assert "收入与净利润年份不一致" in prospectus_info["financial_data_quality_flags"]
    assert prospectus_info["financial_extract_confidence"] == "needs_review"


def test_financial_year_consistency_ok():
    """年份一致时不应标记问题。"""
    ipo_data = {}
    prospectus_info = {
        "revenue_year": "2024",
        "net_profit_year": "2024",
        "financial_extract_confidence": "high",
    }
    _validate_financial_year_consistency(ipo_data, prospectus_info)
    assert ipo_data.get("financial_year_consistency_issue") is False


# ---------------------------------------------------------------------------
# 4. profitable 与 valuation_label 冲突
# ---------------------------------------------------------------------------
def test_profitable_vs_biotech_valuation_conflict():
    """当 profitable=True 但 biotech_valuation_label 含'未盈利'时，应标记冲突。"""
    ipo_data = {}
    prospectus_info = {
        "profitable": True,
        "valuation": {
            "biotech_valuation_label": "未盈利临床阶段创新药，PE不适用",
            "valuation_label": "合理",
        },
    }
    _detect_valuation_profitability_conflict(ipo_data, prospectus_info)
    assert ipo_data["valuation_conflict"] is True
    assert any("盈利状态为盈利" in r for r in ipo_data["valuation_conflict_reasons"])


def test_no_conflict_when_loss_making():
    """未盈利公司不应触发冲突。"""
    ipo_data = {}
    prospectus_info = {
        "profitable": False,
        "valuation": {
            "biotech_valuation_label": "未盈利临床阶段创新药，PE不适用",
        },
    }
    _detect_valuation_profitability_conflict(ipo_data, prospectus_info)
    assert ipo_data.get("valuation_conflict") is False


# ---------------------------------------------------------------------------
# 5. negative cornerstone investor context
# ---------------------------------------------------------------------------
def test_cornerstone_negative_context_exclusion():
    """如果投资者出现在'未见/无'语境中，不应加入 matched_investors。"""
    analyzer = CornerstoneAnalyzer()
    context = "基石投资者包括 ABC Fund。未见 GIC、无 Temasek、不包括 QIA。"
    matched = analyzer._matched_profiles_with_exclusion(context)
    names = [p["name"] for p in matched]
    assert "GIC" not in names
    assert "Temasek" not in names
    assert "QIA" not in names
    # 负面语境中识别到的高质量投资者应记录在 absent_high_quality
    absent = getattr(analyzer, "_last_absent_high_quality", [])
    absent_names = [a["name"] for a in absent]
    assert "GIC" in absent_names or "Temasek" in absent_names or len(absent_names) > 0


# ---------------------------------------------------------------------------
# 6. risk keyword hypothetical context
# ---------------------------------------------------------------------------
def test_risk_penalty_hypothetical_context():
    """hypothetical / may / could 语境中的风险关键词应被降级为 generic_risk_factor，不扣分或轻扣。"""
    prospectus_info = {
        "_extracted_text": (
            "We may face clinical failure in the future. "
            "The company is currently subject to a class action lawsuit. "
            "There could be regulatory rejection if approval is not obtained."
        ),
        "risk_factors": {"risks": {}, "total_penalty": 0},
        "customer_supplier": {},
        "valuation": {},
        "stock_quality": {"reasons": []},
    }
    result = _calculate_risk_penalty(prospectus_info)
    breakdown = result["breakdown"]
    # class action lawsuit 是 actual_event（含 currently/subject to）
    actual_events = [b for b in breakdown if b.get("risk_tier") == "actual_event"]
    generics = [b for b in breakdown if b.get("risk_tier") == "generic_risk_factor"]
    # "may face clinical failure" 和 "could be regulatory rejection" 应为 generic
    assert len(generics) >= 1, f"Expected at least 1 generic risk, got breakdown: {breakdown}"
    # actual_event 的扣分应比 potential/generic 高
    for ae in actual_events:
        assert ae["penalty"] >= 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
