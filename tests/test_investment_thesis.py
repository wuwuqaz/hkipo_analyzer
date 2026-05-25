"""投研叙事综合分析器回归测试。"""

from ipo_analyzer.analyzers._investment_thesis import InvestmentThesisAnalyzer
from ipo_analyzer.history import _json_to_db_record
from ipo_analyzer.models import IPOData, PiotroskiFResult, ProspectusInfo


def _creality_like_info():
    return {
        "company_name": "创想三维",
        "sector": "hardtech",
        "revenue": 3127.04,
        "revenue_y1": 2288.33,
        "net_profit": -182.42,
        "net_profit_y1": 88.66,
        "adjusted_profit_latest_RMB": 92.39,
        "financial_currency": "RMB",
        "market_cap_hkd_million": 8776.6,
        "shares_in_issue_post_listing": 466_840_101,
        "business_breakdown": {
            "segments": [
                {
                    "name": "3D printers",
                    "revenue_latest": 1784.95,
                    "share_pct": 57.1,
                    "gross_profit_latest": 506.22,
                    "gross_margin_pct": 28.4,
                    "gross_profit_share_pct": 51.9,
                },
                {
                    "name": "3D printing filaments",
                    "revenue_latest": 418.41,
                    "share_pct": 13.4,
                    "gross_profit_latest": 148.70,
                    "gross_margin_pct": 35.5,
                    "gross_profit_share_pct": 15.3,
                },
                {
                    "name": "3D scanners",
                    "revenue_latest": 365.70,
                    "share_pct": 11.7,
                    "gross_profit_latest": 123.76,
                    "gross_margin_pct": 33.8,
                    "gross_profit_share_pct": 12.7,
                },
            ],
            "main_segment": "3D printers",
            "profit_driver_segment": "3D printers",
        },
        "cashflow": {
            "operating_cash_flow": -63.98,
            "operating_cash_flow_prev": 172.91,
            "inventory_amount": 620.0,
            "inventory_amount_prev": 383.2,
            "receivables_amount": 338.3,
            "receivables_amount_prev": 225.3,
            "working_capital_trend_label": "恶化",
            "working_capital_pressure_label": "中",
        },
        "valuation": {
            "ps_ratio": 2.45,
            "adjusted_pe_ratio": 83.1,
            "valuation_label": "偏贵",
        },
        "peer_comparison": {
            "peer_median_ps": 1.1,
            "relative_ps_premium_pct": 122.7,
            "valuation_position": "明显偏贵",
            "dominant_share_pct": 45.3,
            "dominant_segment": "consumer 3D scanners",
        },
        "cornerstone_analysis": {
            "cornerstone_pct": 49.9,
            "label": "A级",
        },
        "risk_factors": {
            "risks": {
                "overseas_channel_tariff_risk": {"risk_level": "高"},
                "competition_risk": {"risk_level": "中"},
                "inventory_pressure_risk": {"risk_level": "中"},
            }
        },
    }


def test_investment_thesis_flags_growth_quality_valuation_and_short_case():
    result = InvestmentThesisAnalyzer().analyze(_creality_like_info())

    assert result["overall_tone"] == "谨慎"
    assert any("收入增长" in item for item in result["fundamental_diagnosis"])
    assert any("经营现金流转负" in item for item in result["fundamental_diagnosis"])
    assert any("硬件" in item for item in result["business_model_takeaways"])
    assert result["short_seller_case"]["target_price_range_hkd"][0] < 12
    assert any("中报" in item for item in result["catalysts"])
    assert any("经营现金流转正" in item for item in result["invalidation_signals"])


def test_investment_thesis_survives_prospectus_info_normalization():
    info = _creality_like_info()
    info["investment_thesis"] = InvestmentThesisAnalyzer().analyze(info)

    normalized = ProspectusInfo.from_dict(info).to_dict(drop_runtime=False)

    assert normalized["investment_thesis"]["overall_tone"] == "谨慎"
    assert normalized["investment_thesis"]["coverage"]["short_seller_case"] is True


def test_ipo_data_normalization_keeps_thesis_and_score_breakdown_extras():
    raw = {
        "company_name": "样本IPO",
        "score_breakdown": {
            "valuation": {
                "score": 7,
                "max_score": 10,
                "normalized_score": 70,
                "label": "偏贵",
                "detail": "相对同行溢价",
                "debug_only": "ignored",
            }
        },
        "investment_thesis": {"overall_tone": "谨慎"},
        "prospectus_info": {"investment_thesis": {"overall_tone": "谨慎"}},
    }

    normalized = IPOData.from_dict(raw).to_dict(drop_runtime=False)

    assert normalized["score_breakdown"]["valuation"]["score"] == 7
    assert normalized["score_breakdown"]["valuation"]["max_score"] == 10
    assert normalized["investment_thesis"]["overall_tone"] == "谨慎"


def test_investment_thesis_is_exposed_in_frontend_and_pdf_report():
    page = "frontend/src/app/jobs/[jobId]/page.tsx"
    component = "frontend/src/components/results/InvestmentThesisCard.tsx"
    report = "ipo_analyzer/report.py"

    assert "InvestmentThesisCard" in open(page, encoding="utf-8").read()
    assert "投研结论" in open(component, encoding="utf-8").read()
    assert "build_investment_thesis_section" in open(report, encoding="utf-8").read()


def test_sqlite_record_serializes_dataclass_analysis_results():
    record = {
        "hk_code": "3388",
        "prospectus_info": {
            "piotroski_f": PiotroskiFResult(total_score=6, grade="中性"),
        },
    }

    row = _json_to_db_record(record)

    assert row[0] == "03388"
    assert '"total_score": 6' in row[1]
    assert "PiotroskiFResult" not in row[1]


def test_ipo_data_normalization_accepts_risk_tiered_evidence():
    normalized = IPOData.from_dict({
        "company_name": "样本IPO",
        "prospectus_info": {
            "risk_factors": {
                "risks": {
                    "competition_risk": {
                        "risk_level": "高",
                        "tiered_evidence": [{"tier": "table", "text": "同行竞争激烈"}],
                        "unexpected_debug": "ignored",
                    }
                }
            }
        },
    }).to_dict(drop_runtime=False)

    risk = normalized["prospectus_info"]["risk_factors"]["risks"]["competition_risk"]
    assert risk["risk_level"] == "高"
    assert risk["tiered_evidence"][0]["tier"] == "table"
