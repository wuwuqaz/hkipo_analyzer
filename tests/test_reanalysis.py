#!/usr/bin/env python3
"""重新分析功能回归测试

运行:
    python3 -m pytest tests/test_reanalysis.py -v
    # 或
    python3 tests/test_reanalysis.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import copy
import tempfile
import shutil

from ipo_analyzer.models import IPOData
from ipo_analyzer.history import HistoryStore
from ipo_analyzer.scoring import ScoringSystem
from ipo_analyzer.cornerstone import CornerstoneAnalyzer


def test_ipodata_from_dict_preserves_new_fields():
    """IPOData.from_dict 不丢失 weight_profile / risk_penalty_breakdown / _reanalysis"""
    raw = {
        "company_name": "TestCo",
        "hk_code": "1234",
        "weight_profile": {"name": "live_heat", "weights": {"trade": 0.35}},
        "score_weights_note": "权重: trade=35% fundamental=30%",
        "data_confidence_gate_warning": "数据质量中等",
        "risk_penalty_breakdown": [
            {"type": "cash_runway", "penalty": 3, "reason": "现金紧张"}
        ],
        "_reanalysis": {
            "analysis_mode": "reanalysis",
            "source_type": "stock_code_download",
            "heat_data_source": "historical_actual",
        },
    }
    obj = IPOData.from_dict(raw)
    assert obj is not None
    assert obj.weight_profile == raw["weight_profile"]
    assert obj.score_weights_note == raw["score_weights_note"]
    assert obj.data_confidence_gate_warning == raw["data_confidence_gate_warning"]
    assert obj.risk_penalty_breakdown == raw["risk_penalty_breakdown"]
    assert obj._reanalysis == raw["_reanalysis"]

    # to_dict(drop_runtime=False) 保留 _reanalysis
    d_full = obj.to_dict(drop_runtime=False)
    assert d_full["_reanalysis"] == raw["_reanalysis"]
    assert d_full["weight_profile"] == raw["weight_profile"]
    assert d_full["risk_penalty_breakdown"] == raw["risk_penalty_breakdown"]

    # to_dict(drop_runtime=True) 剔除 _reanalysis（以下划线开头）
    d_dropped = obj.to_dict(drop_runtime=True)
    assert "_reanalysis" not in d_dropped
    assert d_dropped["weight_profile"] == raw["weight_profile"]
    assert d_dropped["risk_penalty_breakdown"] == raw["risk_penalty_breakdown"]
    print("✅ test_ipodata_from_dict_preserves_new_fields passed")


def test_no_historical_market_data_uses_prospectus_only():
    """无 historical_market_data 时 weight_profile.name == 'prospectus_only'"""
    ipo = {
        "over_sub_ratio": None,
        "over_sub_ratio_source": "missing",
        "forecast_over_sub_ratio": None,
        "market_heat": "",
    }
    prospectus_info = {
        "gross_margin": 40,
        "profitable": True,
        "revenue": 500,
        "sector": "hardtech",
        "cornerstone_analysis": {"score": 70, "label": "A级", "has_cornerstone_section": True},
        "valuation": {"pe_ratio": 25.0, "ps_ratio": 3.0},
        "peer_comparison": {"peer_score": 10, "scarcity_score": 6, "valuation_position": "合理"},
    }
    result = ScoringSystem().calculate(ipo, prospectus_info, signal_components={})
    wp = result.get("weight_profile", {})
    assert wp.get("name") == "prospectus_only", f"期望 prospectus_only，实际: {wp.get('name')}"
    print("✅ test_no_historical_market_data_uses_prospectus_only passed")


def test_historical_actual_uses_live_heat():
    """有 actual_over_sub_ratio 时 over_sub_ratio_source == 'historical_actual'，weight_profile.name == 'live_heat'"""
    ipo = {
        "over_sub_ratio": 150.0,
        "over_sub_ratio_source": "historical_actual",
    }
    prospectus_info = {
        "gross_margin": 40,
        "profitable": True,
        "revenue": 500,
        "sector": "hardtech",
        "cornerstone_analysis": {"score": 70, "label": "A级", "has_cornerstone_section": True},
        "valuation": {"pe_ratio": 25.0, "ps_ratio": 3.0},
        "peer_comparison": {"peer_score": 10, "scarcity_score": 6, "valuation_position": "合理"},
    }
    result = ScoringSystem().calculate(ipo, prospectus_info, signal_components={})
    wp = result.get("weight_profile", {})
    assert wp.get("name") == "live_heat", f"期望 live_heat，实际: {wp.get('name')}"
    print("✅ test_historical_actual_uses_live_heat passed")


def test_history_store_saves_timestamp_and_latest():
    """HistoryStore 保存 timestamp 文件和 latest 文件"""
    temp_dir = tempfile.mkdtemp()
    try:
        store = HistoryStore(temp_dir)

        result = {
            "hk_code": "09995",
            "company_name": "TestCo",
            "score": 65,
            "weight_profile": {"name": "live_heat"},
            "_reanalysis": {
                "analysis_mode": "reanalysis",
                "heat_data_source": "historical_actual",
                "source_type": "local_pdf",
            },
        }

        record, delta = store.save_reanalysis(result)
        assert record is not None
        assert delta is None  # 第一次无 delta

        # 检查 latest 文件存在
        latest = store.load_reanalysis_latest("09995")
        assert latest is not None
        assert latest.get("score") == 65

        # 检查时间戳文件存在
        history = store.load_reanalysis_history("09995")
        assert len(history) >= 1

        # 第二次保存，验证 delta
        result2 = copy.deepcopy(result)
        result2["score"] = 72
        record2, delta2 = store.save_reanalysis(result2)
        assert delta2 is not None
        assert delta2.get("previous_score") == 65
        assert delta2.get("current_score") == 72
        assert delta2.get("score_delta") == 7

        latest2 = store.load_reanalysis_latest("09995")
        assert latest2.get("score") == 72

        print("✅ test_history_store_saves_timestamp_and_latest passed")
    finally:
        shutil.rmtree(temp_dir)


def test_version_delta_correct():
    """version_delta 正确生成"""
    temp_dir = tempfile.mkdtemp()
    try:
        store = HistoryStore(temp_dir)

        first = {
            "hk_code": "09995",
            "company_name": "TestCo",
            "score": 60,
            "trade_score": 50,
            "fundamental_score": 55,
            "valuation_score": 60,
            "theme_score": 65,
            "data_quality_score": 70,
            "weight_profile": {"name": "prospectus_only"},
            "_reanalysis": {
                "analysis_mode": "reanalysis",
                "heat_data_source": "missing",
                "source_type": "stock_code_download",
            },
        }
        store.save_reanalysis(first)

        second = {
            "hk_code": "09995",
            "company_name": "TestCo",
            "score": 75,
            "trade_score": 70,
            "fundamental_score": 60,
            "valuation_score": 65,
            "theme_score": 70,
            "data_quality_score": 70,
            "weight_profile": {"name": "live_heat"},
            "_reanalysis": {
                "analysis_mode": "reanalysis",
                "heat_data_source": "historical_actual",
                "source_type": "stock_code_download",
            },
        }
        _, delta = store.save_reanalysis(second)

        assert delta is not None
        assert delta["previous_score"] == 60
        assert delta["current_score"] == 75
        assert delta["score_delta"] == 15
        assert delta["dimension_deltas"]["trade_score"] == 20
        assert delta["dimension_deltas"]["fundamental_score"] == 5
        assert "权重配置变化" in (delta.get("changed_reason") or "")

        print("✅ test_version_delta_correct passed")
    finally:
        shutil.rmtree(temp_dir)


def test_no_cornerstone_section_no_cap():
    """无基石章节时不产生 cornerstone_score，也不因 label='未披露' 直接封顶 55"""
    ipo = {
        "over_sub_ratio": None,
        "over_sub_ratio_source": "missing",
        "total_fund": 5.0,
    }
    prospectus_info = {
        "gross_margin": 40,
        "profitable": True,
        "revenue": 500,
        "sector": "hardtech",
        "cornerstone_analysis": {
            "score": 0,
            "label": "未披露",
            "has_cornerstone_section": False,
        },
        "valuation": {"pe_ratio": 25.0, "ps_ratio": 3.0},
        "peer_comparison": {"peer_score": 10, "scarcity_score": 6, "valuation_position": "合理"},
    }
    result = ScoringSystem().calculate(ipo, prospectus_info, signal_components={})
    # 无基石章节时，不应因 label="未披露" 封顶 55；但由于无热度数据权重不同，
    # 且基本面/估值等维度分数可能较低，总分本身就可能低于55，所以重点检查：
    # 1. 没有因为 has_cornerstone_section=False 而被额外封顶
    # 2. cornerstone 组件分数为 0
    components = result.get("components", {})
    assert components.get("cornerstone", {}).get("score") == 0, \
        f"无基石时 cornerstone score 应为0，实际: {components.get('cornerstone', {})}"
    # 用有较好基本面+估值数据但无基石的情况，验证分数不被封顶55
    # 提供 signal_components 中的 valuation_framework 以拉高 valuation_score
    ipo2 = {
        "over_sub_ratio": 100.0,
        "over_sub_ratio_source": "actual",
        "total_fund": 5.0,
    }
    prospectus_info2 = {
        "gross_margin": 40,
        "profitable": True,
        "revenue": 500,
        "sector": "hardtech",
        "stock_quality": {
            "score": 65,
            "label": "中",
            "reasons": ["盈利"],
            "dimensions": {
                "growth": {"detail": "增长稳健"},
                "profitability": {"detail": "盈利"},
            },
        },
        "cornerstone_analysis": {
            "score": 0,
            "label": "未披露",
            "has_cornerstone_section": False,
        },
        "valuation": {"pe_ratio": 25.0, "ps_ratio": 3.0, "valuation_label": "合理", "relative_valuation_label": "合理"},
        "peer_comparison": {"peer_score": 10, "scarcity_score": 6, "valuation_position": "合理"},
    }
    signal_components = {
        "valuation_framework": {"score": 15},
        "mainline_beta": {"score": 10},
        "stock_connect_path": {"score": 8},
        "data_quality": {"score": 5},
    }
    result2 = ScoringSystem().calculate(ipo2, prospectus_info2, signal_components=signal_components)
    # 无基石章节 + score<50 封顶55 这条在旧代码里只对 has_cornerstone_section=True 生效
    # 所以这里 score 应该能超过 55
    assert result2["score"] > 55, \
        f"有热度数据+好基本面但无基石时不应封顶55，实际 score={result2['score']}"
    print("✅ test_no_cornerstone_section_no_cap passed")


def test_yifei_pre_ipo_not_cornerstone():
    """翼菲科技文本含 pre-ipo investors / 春华资本，但无 cornerstone anchors 时，不识别为基石"""
    text = """
    Our Company has received investments from a number of sophisticated independent investors.
    The pathfinder sophisticated independent investors include Primavera Capital,
    China Broadband Capital, Tsinghua Holdings Capital, and other previous investors.
    These pre-ipo investors have supported our growth since Series A.
    """
    result = CornerstoneAnalyzer().analyze(text)
    assert result.get("has_cornerstone_section") is False, \
        f"应判定为无基石章节，实际: {result.get('has_cornerstone_section')}"
    assert result.get("score") == 0, f"无基石时 score 应为 0，实际: {result.get('score')}"
    assert result.get("label") == "未披露", f"无基石时 label 应为'未披露'，实际: {result.get('label')}"
    print("✅ test_yifei_pre_ipo_not_cornerstone passed")


def test_jitai_cornerstone_detected():
    """剂泰科技文本含 cornerstone investors / BlackRock / UBS / HHLR 时，正常识别强基石"""
    text = """
    Cornerstone Investors
    The following cornerstone investors have agreed to subscribe for the Offer Shares:
    BlackRock, Inc. has agreed to subscribe for 5,000,000 Offer Shares.
    UBS Asset Management has agreed to subscribe for 3,000,000 Offer Shares.
    HHLR Fund, L.P. has agreed to subscribe for 2,000,000 Offer Shares.
    RTW Investments, LP has agreed to subscribe for 1,500,000 Offer Shares.
    """
    result = CornerstoneAnalyzer().analyze(text)
    assert result.get("has_cornerstone_section") is True, \
        f"应判定为有基石章节，实际: {result.get('has_cornerstone_section')}"
    assert result.get("score", 0) > 0, f"有强基石时 score 应>0，实际: {result.get('score')}"
    matched_names = [m["name"] for m in result.get("matched_investors", [])]
    assert "BlackRock" in matched_names, f"应识别 BlackRock，实际: {matched_names}"
    assert "Hillhouse/HHLR" in matched_names, f"应识别 Hillhouse/HHLR，实际: {matched_names}"
    assert "UBS Asset Management" in matched_names, f"应识别 UBS，实际: {matched_names}"
    print("✅ test_jitai_cornerstone_detected passed")


if __name__ == "__main__":
    test_ipodata_from_dict_preserves_new_fields()
    test_no_historical_market_data_uses_prospectus_only()
    test_historical_actual_uses_live_heat()
    test_history_store_saves_timestamp_and_latest()
    test_version_delta_correct()
    test_no_cornerstone_section_no_cap()
    test_yifei_pre_ipo_not_cornerstone()
    test_jitai_cornerstone_detected()
    print("\n" + "=" * 60)
    print("✅ 所有重新分析回归测试通过")
    print("=" * 60)
