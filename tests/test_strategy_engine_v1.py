import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ipo_analyzer.analyzers import CustomerSupplierAnalyzer, WorkingCapitalCashFlowAnalyzer, RiskFactorAnalyzer
from ipo_analyzer.core import _run_scoring_pipeline
from ipo_analyzer.history import HistoryStore
from ipo_analyzer.peer_comps import PeerComparableAnalyzer
from ipo_analyzer.signal_analyzer import SignalComponentAnalyzer
from ipo_analyzer.settings import SETTINGS


def test_final_price_revalues_market_cap_and_ps():
    ipo_data = {
        "company_name": "LDROBOT",
        "hk_code": "01236",
        "over_sub_ratio": 6707.66,
        "over_sub_ratio_source": "post_listing_actual",
        "market_heat": "极热",
        "post_listing": {"status": "ok", "final_offer_price": 26.36},
    }
    prospectus_info = {
        "parse_success": True,
        "offer_price": 30.0,
        "market_cap_hkd_million": 10000.0,
        "shares_in_issue_post_listing": 333333400,
        "global_offer_shares": 33333400,
        "hk_offer_shares": 3333400,
        "revenue": 748.0,
        "revenue_y1": 467.5,
        "net_profit": -62.5,
        "profitable": False,
        "gross_margin": 25.7,
        "financial_currency": "RMB",
        "sector": "hardtech",
        "cornerstone_analysis": {"score": 60, "label": "B级", "has_cornerstone_section": True},
    }

    result = _run_scoring_pipeline(ipo_data, prospectus_info, "")
    pi = result["prospectus_info"]
    expected_mc = round(333333400 * 26.36 / 1_000_000, 2)
    expected_ps = round(expected_mc / (748.0 * SETTINGS.fx.rmb_to_hkd), 2)

    assert pi["valuation_price_basis"] == "final_price"
    assert pi["indicative_offer_price"] == 30.0
    assert pi["offer_price"] == 26.36
    assert pi["market_cap_hkd_million"] == expected_mc
    assert pi["valuation"]["ps_ratio"] == expected_ps
    assert pi["valuation"]["final_ps_ratio"] == expected_ps
    assert result["ipo_trade_score"] >= 70
    assert result["subscription_recommendation"]


def test_post_listing_ok_clears_pending_message():
    temp_dir = tempfile.mkdtemp()
    try:
        store = HistoryStore(temp_dir)
        store.merge_analysis_result({
            "hk_code": "01236",
            "company_name": "LDROBOT",
            "post_listing": {
                "status": "pending_allotment",
                "message": "HKEX allotment announcement not found yet",
            },
        })
        updated = store.update_post_listing("01236", {
            "status": "ok",
            "final_offer_price": 26.36,
            "public_subscription_level": 6707.66,
        })
        assert updated["post_listing"]["status"] == "ok"
        assert "message" not in updated["post_listing"]
    finally:
        shutil.rmtree(temp_dir)


def test_growth_validation_explained_by_business_segments():
    prospectus_info = {
        "revenue": 748.0,
        "revenue_y1": 467.5,
        "net_profit": -62.5,
        "profitable": False,
        "market_cap_hkd_million": 8786.68,
        "sector": "hardtech",
        "financial_extract_confidence": "consolidated_statement",
        "business_breakdown": {
            "growth_source": "主业增长 + 新业务贡献",
            "segments": [
                {"name": "Visual Perception Products", "revenue_latest": 606.4, "revenue_previous": 439.3},
                {"name": "Robot lawn mowers", "revenue_latest": 136.9, "revenue_previous": 23.3},
            ],
        },
    }
    result = SignalComponentAnalyzer()._analyze_data_quality(prospectus_info)
    assert prospectus_info["growth_validation_status"] == "explained"
    assert not any("收入同比异常" in r for r in result["red_flags"])
    assert any("已由招股书分部数据验证" in r for r in result["reasons"])


def test_customer_quality_extracts_retention_ndr_and_top_customer_supply_chain():
    text = """
    Our customers included seven of the top ten global service robot companies
    and all of the top five global commercial service robot companies.
    Our customer retention rate in 2023, 2024 and 2025 was 91.0%, 98.0% and 100.0%.
    Our net dollar retention rate in 2023, 2024 and 2025 was 105.0%, 121.0% and 133.0%.
    """
    result = CustomerSupplierAnalyzer().analyze({}, text)
    assert result["top_global_service_robotics_customers_count"] == 7
    assert result["top_global_service_robotics_customers_total"] == 10
    assert result["top_global_commercial_service_robotics_customers_count"] == 5
    assert result["top_global_commercial_service_robotics_customers_total"] == 5
    assert result["customer_retention_rate_pct"] == 100.0
    assert result["net_dollar_retention_rate_pct"] == 133.0
    assert result["customer_quality_score"] >= 80


def test_cashflow_extracts_runway_and_ocf_to_revenue():
    text = """
    CONSOLIDATED STATEMENTS OF CASH FLOWS
    Year ended 31 December
    2023 2024 2025
    RMB'000 RMB'000 RMB'000
    Net cash used in operating activities
    (35,000) (90,000) (136,473)

    Financial assets
    As at 31 December
    2023 2024 2025
    RMB'000 RMB'000 RMB'000
    Cash and cash equivalents
    27,585 46,950 119,382
    """
    prospectus_info = {
        "revenue": 748.0,
        "net_profit": -62.5,
        "financial_currency": "RMB",
        "net_proceeds_hkd_million": 650.0,
    }
    result = WorkingCapitalCashFlowAnalyzer().analyze(prospectus_info, text)
    assert result["operating_cash_flow"] == -136.473
    assert result["cash_and_cash_equivalents"] == 119.382
    assert result["ocf_to_revenue"] == -0.18
    assert result["cash_runway_years"] == 0.9
    assert result["post_ipo_cash_runway_years"] > result["cash_runway_years"]


def test_specific_risk_factor_library_detects_asp_overseas_and_social_security():
    prospectus_info = {"cashflow": {"operating_cash_flow": -136.473}}
    text = """
    RISK FACTORS
    The average selling price of our sensors decreased by 13.7% and ASP of algorithm modules decreased by 21.0%.
    We sell robot lawn mowers through Amazon, our website and offline sales channels, and may face tariffs, logistics and after-sales pressure.
    We had underpaid social insurance and housing provident fund contributions with shortfalls of RMB16.6 million, RMB14.8 million and RMB20.2 million.
    """
    result = RiskFactorAnalyzer().analyze(prospectus_info, text)
    assert result["risks"]["price_competition_risk"]["score_penalty"] > 0
    assert result["risks"]["overseas_channel_tariff_risk"]["score_penalty"] > 0
    assert result["risks"]["social_insurance_housing_fund_risk"]["score_penalty"] > 0
    assert result["risks"]["cash_flow_pressure_risk"]["score_penalty"] > 0


def test_peer_filter_removes_industry_phrase_and_outputs_weighted_peer_ps():
    prospectus_info = {
        "sector": "hardtech",
        "market_cap_hkd_million": 8786.68,
        "revenue": 748.0,
        "revenue_y1": 467.5,
        "financial_currency": "RMB",
        "business_breakdown": {
            "segments": [
                {"name": "Visual Perception Products", "share_pct": 81.1},
                {"name": "Robot lawn mowers", "share_pct": 18.3},
            ],
            "growth_source": "主业增长 + 新业务贡献",
        },
    }
    text = """
    COMPETITION
    Intelligent Robot Visual Perception Technology is an industry category.
    Our products include visual perception products, sensors, algorithm modules and robot lawn mowers.
    """
    result = PeerComparableAnalyzer().analyze(prospectus_info, text)
    assert "Intelligent Robot Visual Perception Technology" not in result["unmatched_peer_candidates"]
    assert result["subsector"] == "robotics_visual_perception"
    assert result["weighted_peer_ps"] is not None
    assert result["business_line_peer_valuation"]
