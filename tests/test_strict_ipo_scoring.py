from ipo_analyzer.scoring import ScoringSystem


def _base_ipo(over_sub_ratio=80.0, market_heat="热门"):
    return {
        "company_name": "Strict TestCo",
        "hk_code": "09999",
        "over_sub_ratio": over_sub_ratio,
        "over_sub_ratio_source": "actual",
        "forecast_over_sub_ratio": over_sub_ratio,
        "market_heat": market_heat,
        "total_fund": 6.0,
        "public_offer": 0.6,
    }


def _prospectus(
    stock_quality_score,
    valuation_label="合理",
    relative_ps_premium_pct=0,
    scarcity_score=5,
    revenue_quality="standard",
    revenue_too_small_for_ps=False,
):
    return {
        "revenue": 500,
        "revenue_y1": 420,
        "market_cap_hkd_million": 6000,
        "sector": "hardtech",
        "stock_quality": {
            "score": stock_quality_score,
            "label": "强" if stock_quality_score >= 70 else "弱",
            "reasons": ["基本面质量测试"],
            "dimensions": {
                "growth": {"detail": "收入保持增长"},
                "profitability": {"detail": "利润质量测试"},
            },
        },
        "valuation": {
            "valuation_label": valuation_label,
            "relative_valuation_label": valuation_label,
            "revenue_quality": revenue_quality,
            "revenue_too_small_for_ps": revenue_too_small_for_ps,
        },
        "peer_comparison": {
            "quantitative_peer_count": 3,
            "relative_weighted_ps_premium_pct": relative_ps_premium_pct,
            "relative_ps_premium_pct": relative_ps_premium_pct,
            "scarcity_score": scarcity_score,
            "peer_score": 5,
            "valuation_position": "明显偏贵" if relative_ps_premium_pct >= 80 else "合理",
        },
        "cornerstone_analysis": {
            "score": 72,
            "label": "A级",
            "has_cornerstone_section": True,
            "cornerstone_investors": [{"name": "Long Fund", "tier": "A"}],
            "red_flags": [],
        },
        "cashflow": {"cash_runway_years": 2.5, "cash_quality_label": "一般"},
        "customer_supplier": {"customer_quality_score": 45, "customer_quality_label": "中"},
        "business_breakdown": {},
        "rnd_pipeline": {"technology_moat_score": 5},
        "risk_factors": {},
    }


def _signals(valuation_score=14, mainline=6, stock_connect=6, data_quality=4):
    return {
        "valuation_framework": {"score": valuation_score, "max_score": 20},
        "mainline_beta": {"score": mainline},
        "stock_connect_path": {"score": stock_connect},
        "data_quality": {"score": data_quality},
        "real_money": {"score": 12},
        "float_structure": {"score": 8},
    }


def test_high_heat_weak_fundamental_expensive_ipo_is_capped_to_cautious():
    result = ScoringSystem().calculate(
        _base_ipo(over_sub_ratio=260, market_heat="极热"),
        _prospectus(
            stock_quality_score=38,
            valuation_label="明显偏贵",
            relative_ps_premium_pct=120,
            scarcity_score=2,
        ),
        signal_components=_signals(valuation_score=6, mainline=1, stock_connect=1),
    )

    assert result["raw_trade_signal_score"] >= 70
    assert result["strict_ipo_score"] == result["ipo_trade_score"]
    assert result["ipo_trade_score"] < result["raw_trade_signal_score"]
    assert result["ipo_trade_score"] <= 58
    assert result["valuation_pressure_label"] == "高"
    assert result["subscription_recommendation"] in ("谨慎试水", "谨慎申购或观望")


def test_medium_heat_strong_fundamental_reasonable_valuation_can_participate():
    result = ScoringSystem().calculate(
        _base_ipo(over_sub_ratio=35, market_heat="温和"),
        _prospectus(
            stock_quality_score=84,
            valuation_label="合理",
            relative_ps_premium_pct=5,
            scarcity_score=7,
        ),
        signal_components=_signals(valuation_score=15, mainline=9, stock_connect=8),
    )

    assert result["strict_scoring_profile"] == "balanced_strict_2026"
    assert result["ipo_trade_score"] >= 60
    assert result["long_term_score"] >= 62
    assert result["valuation_score"] >= 55
    assert result["subscription_recommendation"] in (
        "积极申购，可跟踪中线持有条件",
        "可小注参与，基本面与估值需继续跟踪",
    )


def test_license_driven_biotech_ps_premium_does_not_trigger_hard_overvaluation_kill():
    prospectus = _prospectus(
        stock_quality_score=78,
        valuation_label="偏贵",
        relative_ps_premium_pct=120,
        scarcity_score=8,
        revenue_quality="license_upfront_driven",
        revenue_too_small_for_ps=True,
    )
    prospectus["sector"] = "healthcare"
    prospectus["rnd_pipeline"] = {"technology_moat_score": 8, "pipeline_quality_label": "强"}

    result = ScoringSystem().calculate(
        _base_ipo(over_sub_ratio=40, market_heat="温和"),
        prospectus,
        signal_components=_signals(valuation_score=12, mainline=8, stock_connect=6),
    )

    assert result["score_trace"]["peer_adj"] >= 0
    assert result["score_trace"]["val_penalty"] >= 0
    assert result["ipo_trade_score"] >= 55
