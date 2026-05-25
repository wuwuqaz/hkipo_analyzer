from ipo_analyzer.quality_analyzer import ProspectusQualityAnalyzer
from ipo_analyzer.signal_analyzer import SignalComponentAnalyzer


def test_thin_profit_margin_caps_fundamental_quality():
    result = ProspectusQualityAnalyzer().analyze({
        "gross_margin": 25.5,
        "profitable": True,
        "revenue": 576.6,
        "revenue_y1": 537.8,
        "net_profit": 9.2,
        "net_profit_y1": 20.0,
        "customer_supplier": {"customer_quality_score": 90, "customer_quality_reasons": ["头部客户验证"]},
        "cashflow": {"cash_quality_label": "强", "operating_cash_flow": 80, "ocf_to_revenue": 0.14},
        "peer_comparison": {"scarcity_score": 7},
    })

    assert result["score"] <= 70
    assert any("净利率仅" in r for r in result["reasons"])
    assert any("净利润同比下滑" in r for r in result["reasons"])


def test_extreme_pe_caps_valuation_even_when_relative_ps_is_low():
    prospectus_info = {
        "sector": "technology",
        "market_cap_hkd_million": 5033,
        "revenue": 576.6,
        "revenue_y1": 537.8,
        "net_profit": 9.2,
        "net_profit_y1": 20.0,
        "valuation": {"pe_ratio": 507.9, "ps_ratio": 8.1, "valuation_label": "偏贵但可解释"},
        "peer_comparison": {
            "peer_score": 12,
            "valuation_position": "相对低估",
            "relative_ps_premium_pct": -80,
            "quantitative_peer_count": 3,
            "scarcity_score": 7,
        },
    }

    component = SignalComponentAnalyzer()._analyze_valuation_framework(prospectus_info)

    assert component["score"] <= 8
    assert component["label"] == "估值压力"
    assert any("PE" in r and ("下滑" in r or "盈利质量不足" in r or "极高" in r) for r in component["red_flags"])
