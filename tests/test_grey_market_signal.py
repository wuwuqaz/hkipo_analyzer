"""Tests for grey market signal analyzer."""
import pytest
from ipo_analyzer.grey_market_signal import GreyMarketSignalAnalyzer


class TestGreyMarketSignalAnalyzer:

    def test_strong_positive_signal(self):
        analyzer = GreyMarketSignalAnalyzer()
        result = analyzer.analyze(
            grey_price=5.5,
            offer_price=5.0,
            grey_volume=5000000,
            public_offer_shares=10000000,
        )
        assert result["change_pct"] == pytest.approx(10.0, abs=0.1)
        assert result["signal_strength"] == "强看多"
        assert result["score_adjustment"] > 0

    def test_moderate_positive_signal(self):
        analyzer = GreyMarketSignalAnalyzer()
        result = analyzer.analyze(
            grey_price=5.2,
            offer_price=5.0,
            grey_volume=2000000,
            public_offer_shares=10000000,
        )
        assert result["change_pct"] == pytest.approx(4.0, abs=0.1)
        assert result["signal_strength"] == "温和看多"
        assert result["score_adjustment"] > 0

    def test_neutral_signal(self):
        analyzer = GreyMarketSignalAnalyzer()
        result = analyzer.analyze(
            grey_price=5.0,
            offer_price=5.0,
            grey_volume=1000000,
            public_offer_shares=10000000,
        )
        assert result["change_pct"] == pytest.approx(0.0, abs=0.1)
        assert result["signal_strength"] == "中性"
        assert result["score_adjustment"] == 0

    def test_moderate_negative_signal(self):
        analyzer = GreyMarketSignalAnalyzer()
        result = analyzer.analyze(
            grey_price=4.8,
            offer_price=5.0,
            grey_volume=2000000,
            public_offer_shares=10000000,
        )
        assert result["change_pct"] == pytest.approx(-4.0, abs=0.1)
        assert result["signal_strength"] == "温和看空"
        assert result["score_adjustment"] < 0

    def test_strong_negative_signal(self):
        analyzer = GreyMarketSignalAnalyzer()
        result = analyzer.analyze(
            grey_price=4.4,
            offer_price=5.0,
            grey_volume=5000000,
            public_offer_shares=10000000,
        )
        assert result["change_pct"] == pytest.approx(-12.0, abs=0.1)
        assert result["signal_strength"] == "强看空"
        assert result["score_adjustment"] < 0

    def test_missing_grey_price(self):
        analyzer = GreyMarketSignalAnalyzer()
        result = analyzer.analyze(
            grey_price=None,
            offer_price=5.0,
        )
        assert result["signal_strength"] == "数据不足"
        assert result["score_adjustment"] == 0

    def test_high_volume_confirmation(self):
        analyzer = GreyMarketSignalAnalyzer()
        result = analyzer.analyze(
            grey_price=5.5,
            offer_price=5.0,
            grey_volume=8000000,
            public_offer_shares=10000000,
        )
        assert result["volume_ratio_pct"] > 50
        assert "活跃" in result.get("volume_label", "")

    def test_low_volume_warning(self):
        analyzer = GreyMarketSignalAnalyzer()
        result = analyzer.analyze(
            grey_price=5.5,
            offer_price=5.0,
            grey_volume=500000,
            public_offer_shares=10000000,
        )
        assert "冷淡" in result.get("volume_label", "") or "不足" in result.get("volume_label", "")

    def test_detail_message(self):
        analyzer = GreyMarketSignalAnalyzer()
        result = analyzer.analyze(
            grey_price=5.5,
            offer_price=5.0,
        )
        assert "+10.0%" in result["detail"]
        assert "强看多" in result["detail"]
