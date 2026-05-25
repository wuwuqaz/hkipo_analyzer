"""Tests for A/B group strategy analyzer."""
import pytest
from ipo_analyzer.a_b_group_strategy import ABGroupStrategyAnalyzer


class TestABGroupStrategyAnalyzer:

    def test_small_capital_strategy(self):
        analyzer = ABGroupStrategyAnalyzer()
        result = analyzer.analyze(
            over_sub_ratio=80.0,
            public_offer_shares=1000000,
            lot_size=200,
        )
        optimal = result["optimal_strategy"]
        assert optimal["small_capital"]["strategy"] == "甲头（一手党）"

    def test_medium_capital_strategy(self):
        analyzer = ABGroupStrategyAnalyzer()
        result = analyzer.analyze(
            over_sub_ratio=80.0,
            public_offer_shares=1000000,
            lot_size=200,
        )
        optimal = result["optimal_strategy"]
        assert optimal["medium_capital"]["strategy"] == "甲尾（接近500万）"

    def test_large_capital_strategy(self):
        analyzer = ABGroupStrategyAnalyzer()
        result = analyzer.analyze(
            over_sub_ratio=80.0,
            public_offer_shares=1000000,
            lot_size=200,
        )
        optimal = result["optimal_strategy"]
        assert optimal["large_capital"]["strategy"] == "乙头（刚超500万）"

    def test_cold_market_strategy(self):
        analyzer = ABGroupStrategyAnalyzer()
        result = analyzer.analyze(
            over_sub_ratio=8.0,
            public_offer_shares=1000000,
            lot_size=200,
        )
        optimal = result["optimal_strategy"]
        assert optimal["small_capital"]["strategy"] == "甲头（一手党）"

    def test_extreme_hot_strategy(self):
        analyzer = ABGroupStrategyAnalyzer()
        result = analyzer.analyze(
            over_sub_ratio=5000.0,
            public_offer_shares=1000000,
            lot_size=200,
        )
        optimal = result["optimal_strategy"]
        assert "乙头" in optimal["large_capital"]["strategy"] or "顶头槌" in optimal["large_capital"]["strategy"]

    def test_missing_data(self):
        analyzer = ABGroupStrategyAnalyzer()
        result = analyzer.analyze(
            over_sub_ratio=None,
            public_offer_shares=None,
            lot_size=200,
        )
        assert result["data_sufficient"] is False

    def test_data_sufficient_when_over_sub_provided(self):
        analyzer = ABGroupStrategyAnalyzer()
        result = analyzer.analyze(
            over_sub_ratio=50.0,
            public_offer_shares=1000000,
            lot_size=200,
        )
        assert result["data_sufficient"] is True
        assert "group_a_analysis" in result
        assert "group_b_analysis" in result
        assert "optimal_strategy" in result
