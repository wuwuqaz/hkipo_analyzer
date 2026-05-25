"""Tests for sell timing advisor."""
import pytest
from ipo_analyzer.sell_timing_advisor import SellTimingAdvisor


class TestSellTimingAdvisor:

    def test_hot_biotech_hold_longer(self):
        advisor = SellTimingAdvisor()
        result = advisor.analyze(
            sector="healthcare",
            subsector="biotech",
            grey_market_change_pct=15.0,
            over_sub_ratio=200.0,
            cornerstone_quality="A",
        )
        assert result["recommended_hold_days"] >= 14
        assert result["confidence"] in ("高", "中高")

    def test_cold_traditional_sell_early(self):
        advisor = SellTimingAdvisor()
        result = advisor.analyze(
            sector="traditional",
            grey_market_change_pct=-5.0,
            over_sub_ratio=3.0,
        )
        assert result["recommended_hold_days"] <= 1
        assert "首日" in result["sell_timing_label"] or "尽早" in result["sell_timing_label"]

    def test_consumer_hold_for_peak(self):
        advisor = SellTimingAdvisor()
        result = advisor.analyze(
            sector="consumer",
            grey_market_change_pct=8.0,
            over_sub_ratio=50.0,
        )
        assert result["recommended_hold_days"] >= 7

    def test_moderate_heat_sell_partial(self):
        advisor = SellTimingAdvisor()
        result = advisor.analyze(
            sector="tech",
            grey_market_change_pct=3.0,
            over_sub_ratio=30.0,
        )
        assert 1 <= result["recommended_hold_days"] <= 10

    def test_missing_data_default(self):
        advisor = SellTimingAdvisor()
        result = advisor.analyze(
            sector=None,
            grey_market_change_pct=None,
            over_sub_ratio=None,
        )
        assert result["recommended_hold_days"] == 1
        assert "默认" in result.get("reasoning", "")

    def test_detail_message(self):
        advisor = SellTimingAdvisor()
        result = advisor.analyze(
            sector="healthcare",
            grey_market_change_pct=10.0,
            over_sub_ratio=100.0,
        )
        assert result["detail"] is not None
        assert len(result["detail"]) > 20
