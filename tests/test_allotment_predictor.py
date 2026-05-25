"""Tests for allotment predictor."""
import pytest
from ipo_analyzer.allotment_predictor import AllotmentPredictor


class TestAllotmentPredictor:

    def test_very_cold_over_sub(self):
        predictor = AllotmentPredictor()
        result = predictor.predict_one_lot_allotment(over_sub_ratio=3.0)
        assert result["one_lot_rate_min"] >= 80
        assert result["one_lot_rate_max"] <= 100
        assert result["heat_label"] == "冷门"

    def test_cold_over_sub(self):
        predictor = AllotmentPredictor()
        result = predictor.predict_one_lot_allotment(over_sub_ratio=10.0)
        assert result["one_lot_rate_min"] >= 50
        assert result["one_lot_rate_max"] <= 80
        assert result["heat_label"] == "温和"

    def test_normal_over_sub(self):
        predictor = AllotmentPredictor()
        result = predictor.predict_one_lot_allotment(over_sub_ratio=30.0)
        assert result["one_lot_rate_min"] >= 20
        assert result["one_lot_rate_max"] <= 50
        assert result["heat_label"] == "一般"

    def test_hot_over_sub(self):
        predictor = AllotmentPredictor()
        result = predictor.predict_one_lot_allotment(over_sub_ratio=80.0)
        assert result["one_lot_rate_min"] >= 6
        assert result["one_lot_rate_max"] <= 20
        assert result["heat_label"] == "热门"

    def test_very_hot_over_sub(self):
        predictor = AllotmentPredictor()
        result = predictor.predict_one_lot_allotment(over_sub_ratio=200.0)
        assert result["one_lot_rate_min"] >= 2
        assert result["one_lot_rate_max"] <= 10
        assert result["heat_label"] == "极热"

    def test_crazy_over_sub(self):
        predictor = AllotmentPredictor()
        result = predictor.predict_one_lot_allotment(over_sub_ratio=800.0)
        assert result["one_lot_rate_min"] >= 0.5
        assert result["one_lot_rate_max"] <= 3
        assert result["heat_label"] == "疯狂"

    def test_extreme_over_sub(self):
        predictor = AllotmentPredictor()
        result = predictor.predict_one_lot_allotment(over_sub_ratio=5000.0)
        assert result["one_lot_rate_min"] >= 0.03
        assert result["one_lot_rate_max"] <= 1
        assert result["heat_label"] == "极端"

    def test_missing_over_sub(self):
        predictor = AllotmentPredictor()
        result = predictor.predict_one_lot_allotment(over_sub_ratio=None)
        assert result["one_lot_rate_min"] is None
        assert result["heat_label"] == "数据不足"

    def test_predict_group_allotment(self):
        predictor = AllotmentPredictor()
        result = predictor.predict_group_allotment(over_sub_ratio=100.0)
        assert result["group_a_one_lot_rate_min"] is not None
        assert result["group_b_one_lot_rate_min"] is not None
        assert result["group_b_one_lot_rate_min"] >= result["group_a_one_lot_rate_min"]

    def test_steady_one_lot_capital(self):
        predictor = AllotmentPredictor()
        result = predictor.predict_steady_one_lot_capital(over_sub_ratio=80.0)
        assert result["steady_capital_hkd"] > 0
        assert result["capital_label"] is not None

    def test_extreme_steady_one_lot_capital(self):
        predictor = AllotmentPredictor()
        result = predictor.predict_steady_one_lot_capital(over_sub_ratio=5000.0)
        assert result["steady_capital_hkd"] >= 10000000

    def test_zero_over_sub(self):
        predictor = AllotmentPredictor()
        result = predictor.predict_one_lot_allotment(over_sub_ratio=0)
        assert result["one_lot_rate_min"] is None
        assert result["heat_label"] == "数据不足"

    def test_negative_over_sub(self):
        predictor = AllotmentPredictor()
        result = predictor.predict_one_lot_allotment(over_sub_ratio=-5)
        assert result["one_lot_rate_min"] is None
        assert result["heat_label"] == "数据不足"
