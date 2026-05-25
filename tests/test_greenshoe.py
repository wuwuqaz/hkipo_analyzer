"""Tests for greenshoe analyzer."""
import pytest
from ipo_analyzer.greenshoe_analyzer import GreenshoeAnalyzer


class TestGreenshoeAnalyzer:

    def test_has_greenshoe(self):
        analyzer = GreenshoeAnalyzer()
        result = analyzer.analyze({
            "_extracted_text": "公司授予承销商超额配股权，可额外发售15%股份",
            "global_offer_shares": 10000000,
        })
        assert result["has_greenshoe"] is True
        assert result["greenshoe_ratio"] == pytest.approx(0.15, abs=0.01)
        assert result["impact_score"] > 0

    def test_no_greenshoe(self):
        analyzer = GreenshoeAnalyzer()
        result = analyzer.analyze({
            "_extracted_text": "本次全球发售无超额配股权",
            "global_offer_shares": 10000000,
        })
        assert result["has_greenshoe"] is False
        assert result["impact_score"] == 0

    def test_missing_text(self):
        analyzer = GreenshoeAnalyzer()
        result = analyzer.analyze({
            "_extracted_text": None,
            "global_offer_shares": 10000000,
        })
        assert result["has_greenshoe"] is None
        assert result["impact_score"] == 0

    def test_greenshoe_shares_calculation(self):
        analyzer = GreenshoeAnalyzer()
        result = analyzer.analyze({
            "_extracted_text": "超额配股权可发售额外股份",
            "global_offer_shares": 10000000,
        })
        assert result["greenshoe_shares"] == 1500000

    def test_stabilizer_detection(self):
        analyzer = GreenshoeAnalyzer()
        result = analyzer.analyze({
            "_extracted_text": "中金公司担任稳价操作人，行使超额配股权",
            "global_offer_shares": 10000000,
        })
        assert "中金" in result.get("stabilizer", "")

    def test_impact_score_positive(self):
        analyzer = GreenshoeAnalyzer()
        result = analyzer.analyze({
            "_extracted_text": "公司授予承销商超额配股权",
            "global_offer_shares": 50000000,
        })
        assert result["impact_score"] >= 2

    def test_top_tier_stabilizer_bonus(self):
        analyzer = GreenshoeAnalyzer()
        result = analyzer.analyze({
            "_extracted_text": "中金公司稳价操作",
            "global_offer_shares": 10000000,
        })
        assert result["impact_score"] >= 3

    def test_empty_text(self):
        analyzer = GreenshoeAnalyzer()
        result = analyzer.analyze({
            "_extracted_text": "",
            "global_offer_shares": 10000000,
        })
        assert result["has_greenshoe"] is None
        assert result["impact_score"] == 0
