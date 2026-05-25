from ipo_analyzer.analyzers import BusinessBreakdownAnalyzer, WorkingCapitalCashFlowAnalyzer, RnDPipelineAnalyzer, ValuationAnalyzer
from ipo_analyzer.peer_comps import PeerComparableAnalyzer
from ipo_analyzer.scoring import SignalComponentAnalyzer
from ipo_analyzer.market_heat import LiveMarketHeatAnalyzer
from ipo_analyzer.board_heat import BoardHeatAnalyzer, _CACHE as BOARD_HEAT_CACHE
from unittest.mock import patch
import pandas as pd
import pytest


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


def test_chinese_3d_printing_revenue_table_extracts_segments():
    text = """
    我們的收入模式
    下表載列於所示年度我們按業務線劃分的收入明細（按絕對金額及佔總收入百分比列示）。
    截至12月31日止年度
    2023年
    2024年
    2025年
    人民幣
    %
    人民幣
    %
    人民幣
    %
    （以千元計，百分比除外）
    3D打印機 . . . . . . . . . .
    1,403,796
    74.6
    1,416,124
    61.9
    1,784,952
    57.1
    3D打印耗材 . . . . . . . .
    136,203
    7.2
    261,534
    11.4
    418,408
    13.4
    3D掃描儀 . . . . . . . . . .
    41,530
    2.2
    207,585
    9.1
    365,701
    11.7
    總計 . . . . . . . . . . . . . .
    1,882,862
    100.0
    2,288,328
    100.0
    3,127,040
    100.0
    """

    result = BusinessBreakdownAnalyzer().analyze({"sector": "hardtech"}, text)

    assert result["main_segment"] == "3D打印機"
    assert len(result["segments"]) >= 3
    assert result["segments"][0]["revenue_latest"] == 1784.952
    assert result["segments"][0]["share_pct"] == 57.1
    assert result["fastest_growing_segment"] == "3D掃描儀"


def test_generic_chinese_business_line_table_extracts_non_3d_segments():
    text = """
    下表載列於所示年度我們按服務線劃分的收入明細（按絕對金額及佔總收入百分比列示）。
    截至12月31日止年度
    2023年
    2024年
    2025年
    人民幣
    %
    人民幣
    %
    人民幣
    %
    （以千元計，百分比除外）
    雲平台訂閱服務 . . . . . . . . . .
    120,000
    40.0
    180,000
    45.0
    300,000
    50.0
    專業實施服務 . . . . . . . . . .
    90,000
    30.0
    130,000
    32.5
    180,000
    30.0
    硬件設備銷售 . . . . . . . . . .
    90,000
    30.0
    90,000
    22.5
    120,000
    20.0
    總計 . . . . . . . . . . . . . .
    300,000
    100.0
    400,000
    100.0
    600,000
    100.0
    競爭格局
    第一名市場份額 45.0%
    """

    result = BusinessBreakdownAnalyzer().analyze({"sector": "hardtech"}, text)

    assert result["main_segment"] == "雲平台訂閱服務"
    assert result["segments"][0]["revenue_latest"] == 300.0
    assert result["segments"][0]["share_pct"] == 50.0
    assert result["fastest_growing_segment"] == "雲平台訂閱服務"
    assert all("市場份額" not in s["name"] for s in result["segments"])


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


def test_chinese_cashflow_extracts_operating_cash_flow_turn_negative():
    text = """
    合併現金流量表概要
    截至12月31日止年度
    2023年
    2024年
    2025年
    （人民幣千元）
    經營活動所得╱（所用）現金淨額 . . .
    161,123
    172,911
    (63,977)
    """

    result = WorkingCapitalCashFlowAnalyzer().analyze(
        {"revenue": 3127.04, "net_profit": -182.42, "financial_currency": "RMB"},
        text,
    )

    assert result["operating_cash_flow"] == -63.977
    assert result["operating_cash_flow_prev"] == 172.911
    assert result["cash_quality_label"] == "弱"
    assert any("经营现金流为负" in item for item in result["working_capital_risks"])


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


def test_peer_comparison_outputs_market_parallel_stats_when_hk_samples_exist():
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
            "hardtech_moat_reasons": ["专利286项", "在手订单约501.6M"],
            "industry_rank": "第4位",
        },
        "_extracted_text": "Industrial robot body and robotic solution automation system",
    }

    result = PeerComparableAnalyzer().analyze(
        prospectus_info,
        prospectus_info["_extracted_text"],
        {"company_name": "拓璞数控", "hk_code": "07688"},
    )

    stats = result["market_peer_stats"]
    assert result["comparison_mode"] == "by_market"
    assert result["primary_comparison_market"] == "composite"
    assert stats["hk"]["peer_count"] >= 2
    assert stats["a_share"]["peer_count"] >= 2
    assert result["quantitative_basis"] == "composite_listed_peers"
    assert result["quantitative_peer_count"] > stats["hk"]["peer_count"]
    assert stats["a_share"]["valuation_position"] != "样本不足，仅作定性参考"
    assert all(p["market"] == "A股" for p in stats["a_share"]["peers"])


def test_peer_comparison_marks_single_market_sample_as_reference_only():
    prospectus_info = {
        "sector": "hardtech",
        "revenue": 748.0,
        "revenue_y1": 467.5,
        "market_cap_hkd_million": 8786.68,
        "financial_currency": "RMB",
        "business_breakdown": {
            "segments": [
                {"name": "Visual Perception Products", "share_pct": 81.1},
                {"name": "Robot lawn mowers", "share_pct": 18.3},
            ],
            "growth_source": "主业增长 + 新业务贡献",
        },
    }
    text = "visual perception products sensors algorithm modules robot lawn mowers"

    result = PeerComparableAnalyzer().analyze(
        prospectus_info,
        text,
        {"company_name": "LDROBOT", "hk_code": "01236"},
    )

    stats = result["market_peer_stats"]
    assert stats["hk"]["peer_count"] == 1
    assert stats["hk"]["valuation_position"] == "单一样本参考"
    assert stats["a_share"]["peer_count"] >= 2
    assert stats["a_share"]["valuation_position"] != "单一样本参考"


def test_consumer_3d_printing_peer_matching_uses_additive_manufacturing_peers():
    prospectus_info = {
        "sector": "hardtech",
        "revenue": 3127.04,
        "revenue_y1": 2288.33,
        "market_cap_hkd_million": 8776.6,
        "gross_margin": 31.2,
        "business_breakdown": {
            "segments": [
                {"name": "3D printers", "share_pct": 57.1},
                {"name": "3D printing filaments", "share_pct": 13.4},
                {"name": "3D scanners", "share_pct": 11.7},
            ],
        },
        "_extracted_text": (
            "global consumer-grade 3D printing products and services, additive manufacturing, "
            "3D printers, 3D printing filaments, 3D scanners, Creality Cloud"
        ),
    }

    result = PeerComparableAnalyzer().analyze(
        prospectus_info,
        prospectus_info["_extracted_text"],
        {"company_name": "创想三维", "hk_code": "03388"},
    )

    assert result["subsector"] == "consumer_3d_printing"
    assert result["peer_median_ps"] <= 1.5
    assert result["relative_ps_premium_pct"] > 50
    assert result["valuation_position"] in ("明显偏贵", "偏贵")


def test_hardtech_relative_overvaluation_overrides_low_absolute_ps_label():
    prospectus_info = {
        "sector": "hardtech",
        "financial_currency": "RMB",
        "revenue": 3127.04,
        "revenue_y1": 2288.33,
        "net_profit": -182.42,
        "market_cap_hkd_million": 8776.6,
        "gross_margin": 31.2,
        "peer_comparison": {
            "peer_median_ps": 1.1,
            "relative_ps_premium_pct": 136.4,
            "valuation_position": "明显偏贵",
            "scarcity_score": 1,
        },
    }

    result = ValuationAnalyzer().analyze(prospectus_info, "")

    assert result["ps_ratio"] > 2
    assert result["relative_valuation_label"] == "明显偏贵"
    assert result["valuation_label"] in ("偏贵", "很贵")


def test_financial_company_uses_pb_framework_not_ps_primary_label():
    prospectus_info = {
        "sector": "financial",
        "financial_currency": "RMB",
        "revenue": 1500.0,
        "net_profit": 320.0,
        "offer_price": 5.0,
        "pro_forma_NTA_per_share_HKD": 3.0,
        "market_cap_hkd_million": 5000.0,
    }

    result = ValuationAnalyzer().analyze(prospectus_info, "banking wealth management insurance brokerage")

    assert result["valuation_framework_type"] == "financial_pb_roe"
    assert result["primary_valuation_metric"] == "PB"
    assert result["valuation_label"] in ("合理", "偏贵")
    assert any("金融" in r or "P/B" in r for r in result["valuation_reasons"])


def test_saas_company_uses_growth_ps_framework():
    prospectus_info = {
        "sector": "hardtech",
        "financial_currency": "RMB",
        "revenue": 600.0,
        "revenue_y1": 360.0,
        "net_profit": -80.0,
        "market_cap_hkd_million": 7200.0,
        "_extracted_text": "cloud SaaS platform subscription recurring revenue ARR NRR",
    }

    result = ValuationAnalyzer().analyze(prospectus_info, prospectus_info["_extracted_text"])

    assert result["valuation_framework_type"] == "tech_saas"
    assert result["primary_valuation_metric"] == "PS/Growth"
    assert any("SaaS" in r or "订阅" in r for r in result["valuation_reasons"])


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


def test_live_market_heat_degrades_to_local_peer_library_when_quotes_fail():
    peers = [
        {"name": "Stratasys", "ticker": "SSYS"},
        {"name": "3D Systems", "ticker": "DDD"},
    ]
    board = {
        "sector_board_label": "科技硬件",
        "sector_board_type": "theme",
        "sector_board_change_pct": 1.2,
        "sector_board_turnover": 20_000_000,
        "sector_board_company_count": 12,
        "sector_board_heat_label": "热门",
        "sector_board_flow_label": "活跃",
        "sector_board_detail": "本地板块热度可用",
        "sector_board_source": "local",
        "sector_board_confidence": "fallback",
    }

    with patch.object(LiveMarketHeatAnalyzer, "_collect_peer_quotes", return_value=[]), \
         patch.object(BoardHeatAnalyzer, "analyze", return_value=board):
        snapshot = LiveMarketHeatAnalyzer().analyze(
            {"peer_comparison": {"quantitative_peers": peers}},
            "",
        )

    assert snapshot["sector_heat_source"] == "local_peer_library_fallback"
    assert snapshot["sector_flow_label"] == "活跃"
    assert snapshot["sector_samples"][0]["source"] == "local_peer_library"


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
    pytest.importorskip("akshare", reason="akshare not installed")
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
