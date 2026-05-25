"""Tests for pricing gap analyzer."""
import pytest
from ipo_analyzer.analyzers._pricing_gap import PricingGapAnalyzer


class TestPricingGapAnalyzer:

    def test_upper_pricing(self):
        analyzer = PricingGapAnalyzer()
        result = analyzer.analyze({
            "min_price": 1.0,
            "max_price": 1.5,
            "offer_price": 1.5,
        })
        assert result["pricing_position"] == "上限定价"
        assert result["pricing_pct"] == pytest.approx(100.0, abs=0.01)
        assert result["score_adjustment"] == 3

    def test_mid_upper_pricing(self):
        analyzer = PricingGapAnalyzer()
        result = analyzer.analyze({
            "min_price": 1.0,
            "max_price": 2.0,
            "offer_price": 1.75,
        })
        assert result["pricing_position"] == "中上限"
        assert result["score_adjustment"] == 1

    def test_mid_pricing(self):
        analyzer = PricingGapAnalyzer()
        result = analyzer.analyze({
            "min_price": 1.0,
            "max_price": 2.0,
            "offer_price": 1.5,
        })
        assert result["pricing_position"] == "中间价"
        assert result["score_adjustment"] == 0

    def test_mid_lower_pricing(self):
        analyzer = PricingGapAnalyzer()
        result = analyzer.analyze({
            "min_price": 1.0,
            "max_price": 2.0,
            "offer_price": 1.25,
        })
        assert result["pricing_position"] == "中下限"
        assert result["score_adjustment"] == -2

    def test_lower_pricing(self):
        analyzer = PricingGapAnalyzer()
        result = analyzer.analyze({
            "min_price": 1.0,
            "max_price": 2.0,
            "offer_price": 1.0,
        })
        assert result["pricing_position"] == "下限定价"
        assert result["score_adjustment"] == -5

    def test_missing_prices(self):
        analyzer = PricingGapAnalyzer()
        result = analyzer.analyze({
            "min_price": None,
            "max_price": None,
            "offer_price": None,
        })
        assert result["pricing_position"] == "缺失"
        assert result["score_adjustment"] == 0

    def test_fixed_price_uses_max(self):
        analyzer = PricingGapAnalyzer()
        result = analyzer.analyze({
            "min_price": 1.5,
            "max_price": 1.5,
            "offer_price": 1.5,
        })
        assert result["pricing_position"] == "固定定价"
        assert result["score_adjustment"] == 0

    def test_boundary_95_percent(self):
        analyzer = PricingGapAnalyzer()
        result = analyzer.analyze({
            "min_price": 1.0,
            "max_price": 2.0,
            "offer_price": 1.95,
        })
        assert result["pricing_position"] == "上限定价"
        assert result["score_adjustment"] == 3

    def test_boundary_70_percent(self):
        analyzer = PricingGapAnalyzer()
        result = analyzer.analyze({
            "min_price": 1.0,
            "max_price": 2.0,
            "offer_price": 1.70,
        })
        assert result["pricing_position"] == "中上限"
        assert result["score_adjustment"] == 1

    def test_boundary_40_percent(self):
        analyzer = PricingGapAnalyzer()
        result = analyzer.analyze({
            "min_price": 1.0,
            "max_price": 2.0,
            "offer_price": 1.40,
        })
        assert result["pricing_position"] == "中间价"
        assert result["score_adjustment"] == 0

    def test_boundary_15_percent(self):
        analyzer = PricingGapAnalyzer()
        result = analyzer.analyze({
            "min_price": 1.0,
            "max_price": 2.0,
            "offer_price": 1.15,
        })
        assert result["pricing_position"] == "中下限"
        assert result["score_adjustment"] == -2

    def test_partial_missing(self):
        analyzer = PricingGapAnalyzer()
        result = analyzer.analyze({
            "min_price": 1.0,
            "max_price": None,
            "offer_price": 1.5,
        })
        assert result["pricing_position"] == "缺失"
        assert result["score_adjustment"] == 0

    def test_detail_message(self):
        analyzer = PricingGapAnalyzer()
        result = analyzer.analyze({
            "min_price": 1.0,
            "max_price": 2.0,
            "offer_price": 1.8,
        })
        assert "80%" in result["detail"]
        assert "中上限" in result["detail"]
