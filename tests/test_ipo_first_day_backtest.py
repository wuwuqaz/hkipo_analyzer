"""IPO 首日表现回测模块测试"""
import csv
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ipo_analyzer.backtest.ipo_models import (
    IPOBacktestRecord,
    AllotmentExtractionResult,
    ProspectusSignalResult,
)
from ipo_analyzer.backtest.feature_builder import (
    build_ipo_features,
    _classify_bottom_group,
    _classify_wind_group,
    _parse_date,
)
from ipo_analyzer.backtest.ipo_backtester import (
    run_ipo_first_day_backtest,
    write_ipo_backtest_csv,
    write_ipo_backtest_report,
    _group_stats,
)
from ipo_analyzer.extractors.allotment_result_extractor import extract_allotment_result
from ipo_analyzer.extractors.prospectus_signal_extractor import (
    extract_prospectus_signals,
    _detect_greenshoe,
    _assess_independence,
)
from ipo_analyzer.data_sources.hkex_news_crawler import (
    _classify_filename,
    _extract_code_from_filename,
)


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

def test_ipo_backtest_record_derived_values():
    r = IPOBacktestRecord(
        hk_code="09999",
        company_name="测试",
        listing_date="2025-01-15",
        first_day_return=12.5,
    )
    assert r.is_win is True
    assert r.is_break is True or r.is_break is False
    assert r.is_big_meat_50 is False


def test_ipo_backtest_record_negative_return():
    r = IPOBacktestRecord(
        hk_code="08888",
        company_name="亏损",
        listing_date="2025-02-20",
        first_day_return=-8.3,
    )
    assert r.is_win is False
    assert r.is_break is True
    assert r.is_big_meat_50 is False


def test_ipo_backtest_record_big_meat():
    r = IPOBacktestRecord(
        hk_code="07777",
        company_name="大肉",
        listing_date="2025-03-10",
        first_day_return=60.0,
    )
    assert r.is_win is True
    assert r.is_big_meat_50 is True


def test_allotment_extraction_result_is_complete():
    complete = AllotmentExtractionResult(
        final_offer_price=5.5,
        public_subscription_multiple=100.0,
    )
    assert complete.is_complete is True

    incomplete = AllotmentExtractionResult(final_offer_price=5.5)
    assert incomplete.is_complete is False


def test_prospectus_signal_result_defaults():
    r = ProspectusSignalResult()
    assert r.has_greenshoe is None
    assert r.sponsors == []
    assert r.cornerstone_investors == []
    assert r.cornerstone_independence is None
    assert r.has_related_support is False


# ---------------------------------------------------------------------------
# Extractor tests — allotment
# ---------------------------------------------------------------------------

def test_extract_allotment_empty():
    result = extract_allotment_result("")
    assert result.final_offer_price is None
    assert result.public_subscription_multiple is None


def test_extract_allotment_chinese():
    text = (
        "發售價為每股 5.28 港元。\n"
        "公开发售部分获超购 150.5 倍。\n"
        "一手中籤率为 35.0%。\n"
        "回撥比例为 20.0%。"
    )
    result = extract_allotment_result(text)
    assert result.final_offer_price == 5.28
    assert result.public_subscription_multiple == 150.5
    assert result.one_lot_success_rate is not None
    assert result.clawback_ratio is not None


def test_extract_allotment_english():
    text = (
        "The final offer price is HK$ 8.50 per share.\n"
        "The public offering was oversubscribed by approximately 200 times.\n"
        "The one lot success rate is 25%.\n"
        "The clawback percentage is 30%."
    )
    result = extract_allotment_result(text)
    assert result.final_offer_price == 8.50
    assert result.public_subscription_multiple is not None


def test_extract_allotment_short_text():
    result = extract_allotment_result("too short")
    assert result.final_offer_price is None


# ---------------------------------------------------------------------------
# Extractor tests — prospectus signals
# ---------------------------------------------------------------------------

def test_extract_prospectus_greenshoe_yes():
    text = "本次发行设有超额配股权（绿鞋机制），稳价操作人为 XX 证券。"
    result = extract_prospectus_signals(text)
    assert result.has_greenshoe is True


def test_extract_prospectus_greenshoe_no():
    text = "本次发行无超额配股机制。"
    result = extract_prospectus_signals(text)
    assert result.has_greenshoe is False


def test_extract_prospectus_sponsors():
    text = "保薦人：中金公司、海通证券"
    result = extract_prospectus_signals(text)
    assert len(result.sponsors) >= 1


def test_extract_prospectus_cornerstones():
    text = (
        "基石投资者包括：ABC Capital、XYZ Fund、DEF Investments，"
        "认购总额为 500 百万港元。"
    )
    result = extract_prospectus_signals(text)
    assert len(result.cornerstone_investors) >= 1
    assert result.cornerstone_amount_hkd_million is not None


def test_extract_prospectus_short_text():
    result = extract_prospectus_signals("short")
    assert result.has_greenshoe is None
    assert result.sponsors == []


# ---------------------------------------------------------------------------
# Independence tests
# ---------------------------------------------------------------------------

def test_independence_related():
    text = "基石投资者中包括关联方认购，为控股股东附属公司。"
    result = _assess_independence(text, ["ABC Corp"])
    assert result == "related"


def test_independence_independent():
    text = "所有基石投资者均为独立第三方 (independent third party)。"
    result = _assess_independence(text, ["ABC Corp"])
    assert result == "independent"


def test_independence_mixed():
    text = (
        "部分基石为关联方认购，同时引入独立第三方投资者。"
        "independent third party and related party"
    )
    result = _assess_independence(text, ["ABC Corp"])
    assert result == "mixed"


def test_independence_unknown():
    text = "基石投资者已确认参与本次认购。"
    result = _assess_independence(text, ["ABC Corp"])
    assert result == "unknown"


def test_independence_no_cornerstones():
    result = _assess_independence("some text", [])
    assert result is None


# ---------------------------------------------------------------------------
# Data source tests
# ---------------------------------------------------------------------------

def test_classify_filename_prospectus():
    assert _classify_filename("prospectus_09999.pdf") == "prospectus"
    assert _classify_filename("09999_招股书.pdf") == "prospectus"


def test_classify_filename_allotment():
    assert _classify_filename("allotment_result_09999.pdf") == "allotment_result"
    assert _classify_filename("配发结果_09999.pdf") == "allotment_result"


def test_classify_filename_offer_price():
    assert _classify_filename("offer_price_09999.pdf") == "offer_price"
    assert _classify_filename("发售价_09999.pdf") == "offer_price"


def test_classify_filename_unknown():
    assert _classify_filename("random_file.pdf") == "unknown"


def test_extract_code_from_filename():
    assert _extract_code_from_filename("09999_prospectus.pdf") == "09999"
    assert _extract_code_from_filename("company_2580.pdf") == "2580"
    assert _extract_code_from_filename("no_code.pdf") is None


# ---------------------------------------------------------------------------
# Feature builder tests
# ---------------------------------------------------------------------------

def test_parse_date_valid():
    d = _parse_date("2025-01-15")
    assert d is not None
    assert d.year == 2025
    assert d.month == 1


def test_parse_date_invalid():
    assert _parse_date("") is None
    assert _parse_date("not-a-date") is None


def test_build_features_sorts_by_date():
    records = [
        IPOBacktestRecord(hk_code="00003", listing_date="2025-03-01", first_day_return=5.0),
        IPOBacktestRecord(hk_code="00001", listing_date="2025-01-01", first_day_return=10.0),
        IPOBacktestRecord(hk_code="00002", listing_date="2025-02-01", first_day_return=-3.0),
    ]
    result = build_ipo_features(records)
    assert result[0].hk_code == "00001"
    assert result[1].hk_code == "00002"
    assert result[2].hk_code == "00003"


def test_build_features_no_future_function():
    """构造 3 只 IPO，确认第 2 只的市场风向和保荐人弹性不读取第 3 只结果。"""
    records = [
        IPOBacktestRecord(
            hk_code="00001", listing_date="2025-01-01",
            first_day_return=20.0, over_sub_ratio=500.0,
        ),
        IPOBacktestRecord(
            hk_code="00002", listing_date="2025-02-01",
            first_day_return=-5.0, over_sub_ratio=10.0,
            sponsors=["Test Sponsor"],
        ),
        IPOBacktestRecord(
            hk_code="00003", listing_date="2025-03-01",
            first_day_return=100.0, over_sub_ratio=1000.0,
            sponsors=["Test Sponsor"],
        ),
    ]
    result = build_ipo_features(records)

    second = result[1]
    assert second.market_wind_score is not None
    assert second.market_wind_score == 20.0

    third = result[2]
    assert third.market_wind_score is not None
    assert third.market_wind_score == 7.5


def test_build_features_sets_market_wind_group_without_future_data():
    records = [
        IPOBacktestRecord(hk_code="00001", listing_date="2025-01-01", first_day_return=20.0),
        IPOBacktestRecord(hk_code="00002", listing_date="2025-02-01", first_day_return=10.0),
        IPOBacktestRecord(hk_code="00003", listing_date="2025-03-01", first_day_return=-5.0),
        IPOBacktestRecord(hk_code="00004", listing_date="2025-04-01", first_day_return=3.0),
    ]

    result = build_ipo_features(records)

    assert result[0].market_wind_group is None
    assert result[3].market_wind_score == 10.0
    assert result[3].market_wind_group == "strong"


def test_build_features_sponsor_elasticity_uses_sponsors_field():
    records = [
        IPOBacktestRecord(
            hk_code="00001", listing_date="2025-01-01",
            first_day_return=20.0, sponsors=["Test Sponsor"],
        ),
        IPOBacktestRecord(
            hk_code="00002", listing_date="2025-02-01",
            first_day_return=10.0, sponsors=["Test Sponsor"],
        ),
        IPOBacktestRecord(
            hk_code="00003", listing_date="2025-03-01",
            first_day_return=0.0, sponsors=["Test Sponsor"],
        ),
    ]

    result = build_ipo_features(records)

    assert result[2].sponsor_elastic_group == "high"


def test_build_features_empty_list():
    assert build_ipo_features([]) == []


def test_classify_bottom_group_good():
    r = IPOBacktestRecord(
        sponsor_elastic_group="high",
        cornerstone_pct=15.0,
        cornerstone_independence="independent",
        has_related_support=False,
        fundamental_score=60.0,
    )
    assert _classify_bottom_group(r) == "good"


def test_classify_bottom_group_weak():
    r = IPOBacktestRecord(
        sponsor_elastic_group="low",
        cornerstone_pct=5.0,
        cornerstone_independence="related",
        has_related_support=True,
        fundamental_score=30.0,
    )
    assert _classify_bottom_group(r) == "weak"


def test_classify_wind_group_strong():
    r = IPOBacktestRecord(
        subscription_heat_group="strong",
        market_wind_score=10.0,
        extra={"market_wind_group": "strong"},
    )
    assert _classify_wind_group(r) == "strong"


def test_classify_wind_group_weak():
    r = IPOBacktestRecord(
        subscription_heat_group="weak",
        market_wind_score=-5.0,
    )
    assert _classify_wind_group(r) == "weak"


# ---------------------------------------------------------------------------
# Backtest engine tests
# ---------------------------------------------------------------------------

def _make_sample_records() -> list[IPOBacktestRecord]:
    return [
        IPOBacktestRecord(
            hk_code="00001", company_name="A", listing_date="2025-01-10",
            first_day_return=15.0, over_sub_ratio=500.0,
            has_greenshoe=True, fundamental_score=65.0,
            cornerstone_pct=12.0, cornerstone_independence="independent",
        ),
        IPOBacktestRecord(
            hk_code="00002", company_name="B", listing_date="2025-02-10",
            first_day_return=-8.0, over_sub_ratio=10.0,
            has_greenshoe=False, fundamental_score=30.0,
            cornerstone_pct=3.0, cornerstone_independence="related",
            has_related_support=True,
        ),
        IPOBacktestRecord(
            hk_code="00003", company_name="C", listing_date="2025-03-10",
            first_day_return=55.0, over_sub_ratio=800.0,
            has_greenshoe=True, fundamental_score=70.0,
            cornerstone_pct=20.0, cornerstone_independence="independent",
        ),
        IPOBacktestRecord(
            hk_code="00004", company_name="D", listing_date="2025-04-10",
            first_day_return=2.0, over_sub_ratio=50.0,
            has_greenshoe=None, fundamental_score=50.0,
        ),
        IPOBacktestRecord(
            hk_code="00005", company_name="E", listing_date="2025-05-10",
            first_day_return=-15.0, over_sub_ratio=5.0,
            has_greenshoe=False, fundamental_score=20.0,
            has_related_support=True,
        ),
    ]


def test_run_backtest_returns_summary():
    records = _make_sample_records()
    summary = run_ipo_first_day_backtest(records)

    assert "total" in summary
    assert "greenshoe" in summary
    assert "sponsor_elastic" in summary
    assert "cornerstone_pct" in summary
    assert "cornerstone_independence" in summary
    assert "subscription_heat" in summary
    assert "market_wind" in summary
    assert "bottom_x_wind" in summary
    assert "records" in summary
    assert "run_at" in summary


def test_run_backtest_cornerstone_groups_use_40pct_threshold():
    records = [
        IPOBacktestRecord(hk_code="00001", first_day_return=1.0, cornerstone_pct=None),
        IPOBacktestRecord(hk_code="00002", first_day_return=1.0, cornerstone_pct=20.0),
        IPOBacktestRecord(hk_code="00003", first_day_return=1.0, cornerstone_pct=40.0),
    ]

    summary = run_ipo_first_day_backtest(records)

    assert summary["cornerstone_pct"]["no_cornerstone"]["count"] == 1
    assert summary["cornerstone_pct"]["below_40pct"]["count"] == 1
    assert summary["cornerstone_pct"]["high_40pct"]["count"] == 1


def test_run_backtest_total_stats():
    records = _make_sample_records()
    summary = run_ipo_first_day_backtest(records)
    total = summary["total"]

    assert total["count"] == 5
    assert total["win_rate"] == 0.6
    assert total["break_rate"] == 0.4


def test_run_backtest_empty():
    summary = run_ipo_first_day_backtest([])
    assert summary["total"]["count"] == 0


def test_group_stats_empty():
    stats = _group_stats([])
    assert stats["count"] == 0
    assert stats["win_rate"] == 0.0


def test_group_stats_single():
    r = IPOBacktestRecord(first_day_return=10.0)
    stats = _group_stats([r])
    assert stats["count"] == 1
    assert stats["win_rate"] == 1.0
    assert stats["median_return"] == 10.0


# ---------------------------------------------------------------------------
# Output tests
# ---------------------------------------------------------------------------

def test_write_csv():
    records = _make_sample_records()
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "test_backtest.csv")
        write_ipo_backtest_csv(records, path)

        assert os.path.exists(path)
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 5
        assert "hk_code" in reader.fieldnames
        assert "first_day_return" in reader.fieldnames
        assert "bottom_group" in reader.fieldnames
        assert "wind_group" in reader.fieldnames
        assert "has_greenshoe" in reader.fieldnames
        assert "cornerstone_pct" in reader.fieldnames
        assert "fundamental_score" in reader.fieldnames


def test_write_report():
    records = _make_sample_records()
    summary = run_ipo_first_day_backtest(records)

    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "test_report.md")
        write_ipo_backtest_report(summary, path)

        assert os.path.exists(path)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "# IPO 首日表现回测报告" in content
        assert "## 总览" in content
        assert "## 绿鞋分组" in content
        assert "## ## 绿鞋分组" not in content
        assert "## 保荐人弹性分组" in content
        assert "## 基石比例分组" in content
        assert "## 基石独立性分组" in content
        assert "## 认购热度分组" in content
        assert "## 市场风向分组" in content
        assert "## 底色 × 风向 矩阵" in content


def test_csv_and_report_with_enriched_records():
    """使用 build_ipo_features 后的记录写入 CSV 和报告。"""
    records = _make_sample_records()
    enriched = build_ipo_features(records)
    summary = run_ipo_first_day_backtest(records)

    with tempfile.TemporaryDirectory() as td:
        csv_path = os.path.join(td, "enriched.csv")
        md_path = os.path.join(td, "enriched.md")

        write_ipo_backtest_csv(enriched, csv_path)
        write_ipo_backtest_report(summary, md_path)

        assert os.path.getsize(csv_path) > 0
        assert os.path.getsize(md_path) > 0


def test_bottom_x_wind_matrix_has_all_combinations():
    records = _make_sample_records()
    summary = run_ipo_first_day_backtest(records)

    matrix = summary["bottom_x_wind"]
    expected_keys = {"good_x_strong", "good_x_weak", "weak_x_strong", "weak_x_weak"}
    assert expected_keys.issubset(set(matrix.keys()))

    for key, stats in matrix.items():
        assert "count" in stats
        assert "win_rate" in stats
        assert "median_return" in stats
