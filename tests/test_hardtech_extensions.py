from ipo_analyzer.analyzers import BusinessBreakdownAnalyzer, WorkingCapitalCashFlowAnalyzer, RnDPipelineAnalyzer, ValuationAnalyzer
from ipo_analyzer.peer_comps import PeerComparableAnalyzer
from ipo_analyzer.scoring import SignalComponentAnalyzer
from ipo_analyzer.market_heat import LiveMarketHeatAnalyzer
from ipo_analyzer.board_heat import BoardHeatAnalyzer, _CACHE as BOARD_HEAT_CACHE
from unittest.mock import patch
import pandas as pd


def test_robotics_business_breakdown_detects_solution_mix():
    text = """
    Breakdown of our revenue by business line
    Robot bodies
    2024 50 25
    2025 60 22
    Robotic solutions
    2024 100 50
    2025 150 55
    Controllers
    2024 20 10
    2025 30 11
    Total revenue
    2024 170 100
    2025 240 100
    """
    result = BusinessBreakdownAnalyzer().analyze({"sector": "hardtech"}, text)
    assert result["segments"], "应提取到业务分部"
    assert result["business_model_label"] in ("机器人解决方案为主", "机器人本体为主", "分部结构待确认")
    assert result["segment_concentration_label"] in ("主业集中", "双轮驱动", "多元分散")
    assert result["evidence_excerpt"], "应输出业务分部原文证据"


def test_cashflow_extracts_inventory_receivables_and_monthly_burn():
    text = """
    Inventories 100 120 150
    Trade receivables 80 95 110
    Net cash used in operating activities 600 700 800
    Cash and cash equivalents 500 420 360
    """
    result = WorkingCapitalCashFlowAnalyzer().analyze(
        {"revenue": 200.0, "financial_currency": "RMB"},
        text,
    )
    assert result["inventory_amount"] is not None
    assert result["inventory_amount_prev"] is not None
    assert result["receivables_amount"] is not None
    assert result["receivables_amount_prev"] is not None
    assert result["monthly_cash_burn"] == 66.67
    assert result["working_capital_risks"], "应输出营运资本风险提示"
    assert result["working_capital_trend_label"] != "缺失"
    assert result["working_capital_trend_reasons"], "应输出营运资本趋势理由"
    assert result["working_capital_pressure_label"] in ("低", "中", "高", "可控")
    assert result["working_capital_pressure_reasons"], "应输出营运资本压力理由"
    assert result["evidence_excerpt"], "应输出营运资本原文证据"


def test_hardtech_rnd_parser_captures_moat_signals():
    text = """
    The company has 286 patents, 99 software copyrights and 227 R&D employees representing 36% of employees.
    Backlog amounted to RMB 501.6 million as of 31 March 2026.
    The company was ranked No. 4 in the market.
    """
    result = RnDPipelineAnalyzer().analyze({"sector": "hardtech", "revenue": 387.0}, text)
    assert result["patent_count"] == 286
    assert result["software_copyright_count"] == 99
    assert result["rd_staff_count"] == 227
    assert result["rd_staff_ratio"] == 36.0
    assert result["backlog_amount"] is not None
    assert result["industry_rank"] == "第4位"
    assert result["hardtech_moat_label"] in ("中", "强")
    assert result["evidence_excerpt"], "应输出研发原文证据"


def test_valuation_adds_ev_sales_and_pre_ipo_premium():
    text = """
    Offer price HK$30.5 per share and final market cap HK$7,471.0 million.
    PS 19.3x and EV/Sales 18.8x were used for comparison.
    The company raised gross proceeds and the IPO valuation premium is notable.
    """
    prospectus_info = {
        "sector": "hardtech",
        "financial_currency": "RMB",
        "revenue": 387.36,
        "net_profit": -152.94,
        "offer_price": 30.5,
        "market_cap_hkd_million": 7471.0,
        "indicative_market_cap_hkd_million": 3603.9,
        "final_total_fund": 977.0,
        "cashflow": {"cash_and_cash_equivalents": 400.0},
        "peer_comparison": {"valuation_position": "合理", "scarcity_score": 5},
    }
    result = ValuationAnalyzer().analyze(prospectus_info, text)
    assert result["ev_sales_ratio"] is not None
    assert result["pre_ipo_valuation_million"] is not None
    assert result["ipo_valuation_premium_pct"] is not None
    assert result["evidence_excerpt"], "应输出估值原文证据"


def test_robot_factory_automation_peer_matching_and_weighting():
    prospectus_info = {
        "sector": "hardtech",
        "revenue": 387.36,
        "revenue_y1": 267.83,
        "market_cap_hkd_million": 7471.0,
        "gross_margin": 24.8,
        "business_breakdown": {
            "growth_source": "主业增长 + 新业务贡献",
            "segments": [
                {"name": "Robot bodies", "share_pct": 32.0},
                {"name": "Robotic solutions", "share_pct": 68.0},
            ],
            "business_model_label": "机器人解决方案为主",
            "segment_moat_label": "方案驱动",
        },
        "rnd_pipeline": {
            "pipeline_quality_label": "中",
            "technology_moat_score": 6,
            "hardtech_moat_label": "中",
            "hardtech_moat_reasons": ["专利286项", "在手订单约501.6M"],
            "industry_rank": "第4位",
        },
        "_extracted_text": "Industrial robot body and robotic solution automation system",
    }
    result = PeerComparableAnalyzer().analyze(prospectus_info, prospectus_info["_extracted_text"], {"company_name": "拓璞数控", "hk_code": "07688"})
    assert result["subsector"] == "robotics_factory_automation"
    assert result["quantitative_peer_count"] >= 2
    assert result["weighted_peer_ps"] is not None
    assert result["valuation_position"] != "缺失"


def test_mainline_beta_combines_market_heat_with_sector_context():
    ipo = {"market_heat": "热门", "over_sub_ratio": 128.0}
    prospectus_info = {
        "sector": "hardtech",
        "peer_comparison": {"subsector": "robotics_factory_automation"},
        "business_breakdown": {"business_model_label": "机器人解决方案为主"},
        "rnd_pipeline": {"hardtech_moat_label": "强"},
    }
    text = "Industrial robot body and robotic solution automation system with AGV and SCARA."

    result = SignalComponentAnalyzer().analyze(ipo, prospectus_info, text)
    mainline = result["components"]["mainline_beta"]
    assert mainline["confidence"] != "keyword_only"
    assert "热度:热门" in mainline["detail"]
    assert "细分:robotics / factory / automation" in mainline["detail"]
    assert mainline["score"] >= 10


def test_live_market_heat_uses_peer_quotes_and_index_backdrop():
    peers = [
        {"name": "腾讯控股", "ticker": "00700.HK"},
        {"name": "小鹏集团-W", "ticker": "09868.HK"},
    ]

    payload = {
        "rc": 0,
        "data": {
            "diff": [
                {"f12": "HSI", "f13": 100, "f14": "恒生指数", "f3": -0.22, "f2": 26347.91, "f18": 26406.84},
                {"f12": "00700", "f13": 116, "f14": "腾讯控股", "f3": 4.50, "f2": 468.0, "f18": 447.85, "f20": 4000000},
                {"f12": "09868", "f13": 116, "f14": "小鹏集团-W", "f3": 3.20, "f2": 62.0, "f18": 60.08, "f20": 100000},
            ]
        },
    }

    class FakeResponse:
        status_code = 200

        def json(self):
            return payload

    with patch("ipo_analyzer.market_heat.httpx.get", return_value=FakeResponse()):
        snapshot = LiveMarketHeatAnalyzer().analyze(
            {"peer_comparison": {"quantitative_peers": peers}},
            "",
        )

    assert snapshot["sector_heat_label"] in ("极热", "热门")
    assert snapshot["sector_peer_count"] == 2
    assert snapshot["sector_index_change_pct"] == -0.22
    assert "恒指-0.22%" in snapshot["sector_heat_detail"]
    assert snapshot["sector_flow_label"] in ("放量", "活跃", "平稳", "偏弱", "缺失")
    assert snapshot["sector_flow_detail"], "应输出板块资金流说明"
    assert snapshot["sector_momentum_label"] in ("强势", "上行", "盘整", "偏弱", "缺失")
    assert snapshot["sector_momentum_detail"], "应输出板块动能说明"


def test_signal_breakdown_exposes_live_market_heat():
    ipo = {"market_heat": "热门", "over_sub_ratio": 128.0}
    prospectus_info = {
        "sector": "hardtech",
        "peer_comparison": {
            "subsector": "robotics_factory_automation",
            "quantitative_peers": [
                {"ticker": "00700.HK", "name": "腾讯控股"},
                {"ticker": "09868.HK", "name": "小鹏集团-W"},
            ],
        },
    }
    text = "robotic solution automation system"

    payload = {
        "rc": 0,
        "data": {
            "diff": [
                {"f12": "HSI", "f13": 100, "f14": "恒生指数", "f3": -0.22, "f2": 26347.91, "f18": 26406.84},
                {"f12": "00700", "f13": 116, "f14": "腾讯控股", "f3": 4.50, "f2": 468.0, "f18": 447.85, "f20": 4000000},
                {"f12": "09868", "f13": 116, "f14": "小鹏集团-W", "f3": 3.20, "f2": 62.0, "f18": 60.08, "f20": 100000},
            ]
        },
    }

    class FakeResponse:
        status_code = 200

        def json(self):
            return payload

    with patch("ipo_analyzer.market_heat.httpx.get", return_value=FakeResponse()):
        signal = SignalComponentAnalyzer().analyze(ipo, prospectus_info, text)

    sb = signal["signal_breakdown"]
    assert "market_heat" in sb
    assert sb["market_heat"]["label"] in ("极热", "热门")
    assert "sector_flow" in sb
    assert sb["sector_flow"]["label"] in ("放量", "活跃", "平稳", "偏弱", "缺失")
    assert "sector_momentum" in sb
    assert sb["sector_momentum"]["label"] in ("强势", "上行", "盘整", "偏弱", "缺失")
    assert signal["live_market_heat"]["sector_heat_label"] in ("极热", "热门")


def test_manual_live_market_heat_flows_into_mainline_beta():
    ipo = {"market_heat": "热门", "over_sub_ratio": 128.0, "live_market_heat": {
        "sector_heat_label": "热门",
        "sector_flow_label": "活跃",
        "sector_momentum_label": "上行",
        "sector_peer_count": 3,
    }}
    prospectus_info = {
        "sector": "hardtech",
        "peer_comparison": {"subsector": "robotics_factory_automation"},
        "business_breakdown": {"business_model_label": "机器人解决方案为主"},
        "rnd_pipeline": {"hardtech_moat_label": "强"},
    }
    text = "robotic solution automation system"

    signal = SignalComponentAnalyzer().analyze(ipo, prospectus_info, text)
    mainline = signal["components"]["mainline_beta"]
    assert mainline["confidence"] == "market_signal"
    assert "动能:上行" in mainline["detail"]
    assert "资金流:活跃" in mainline["detail"]


def test_board_heat_analyzer_uses_real_board_index():
    BOARD_HEAT_CACHE.clear()
    concept_df = pd.DataFrame([
        {"板块": "机器人概念", "涨跌幅": 3.2, "总成交额": 28651266870, "公司家数": 45},
        {"板块": "创新药", "涨跌幅": -1.0, "总成交额": 56717116184, "公司家数": 100},
    ])
    industry_df = pd.DataFrame([
        {"板块": "电气设备", "涨跌幅": 0.8, "总成交额": 12000000000, "公司家数": 30},
    ])

    with patch("ipo_analyzer.board_heat.ak.stock_sector_spot", side_effect=lambda indicator='概念': concept_df if indicator == '概念' else industry_df):
        snapshot = BoardHeatAnalyzer().analyze(
            {"sector": "hardtech", "peer_comparison": {"subsector": "robotics_factory_automation"}},
            "robotics solution automation system",
        )

    assert snapshot["sector_board_label"] == "机器人概念"
    assert snapshot["sector_board_heat_label"] == "强势"
    assert snapshot["sector_board_flow_label"] in ("放量", "活跃")
    assert "机器人概念" in snapshot["sector_board_detail"]
