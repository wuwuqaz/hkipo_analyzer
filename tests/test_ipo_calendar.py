"""Tests for IPO calendar/key dates calculator."""
import pytest
from datetime import date
from ipo_analyzer.ipo_calendar import IPOCalendarCalculator


class TestIPOCalendarCalculator:

    def test_basic_timeline(self):
        calc = IPOCalendarCalculator()
        result = calc.calculate(
            listing_date="2026-06-15",
        )
        assert result["listing_date"] == "2026-06-15"
        assert result["grey_market_date"] is not None
        assert result["allotment_date"] is not None

    def test_all_dates_calculated(self):
        calc = IPOCalendarCalculator()
        result = calc.calculate(
            apply_start_date="2026-05-28",
            apply_end_date="2026-06-02",
            listing_date="2026-06-15",
        )
        assert result["apply_start_date"] == "2026-05-28"
        assert result["apply_end_date"] == "2026-06-02"
        assert result["listing_date"] == "2026-06-15"
        assert result["grey_market_date"] is not None
        assert result["allotment_date"] is not None

    def test_grey_market_before_listing(self):
        calc = IPOCalendarCalculator()
        result = calc.calculate(listing_date="2026-06-15")
        assert result["grey_market_date"] < result["listing_date"]

    def test_allotment_before_grey_market(self):
        calc = IPOCalendarCalculator()
        result = calc.calculate(listing_date="2026-06-15")
        assert result["allotment_date"] <= result["grey_market_date"]

    def test_days_remaining_to_apply_end(self):
        calc = IPOCalendarCalculator()
        result = calc.calculate(
            apply_end_date="2026-06-10",
            listing_date="2026-06-15",
            current_date=date(2026, 6, 8),
        )
        assert result["days_to_apply_end"] == 2

    def test_days_remaining_to_listing(self):
        calc = IPOCalendarCalculator()
        result = calc.calculate(
            listing_date="2026-06-20",
            current_date=date(2026, 6, 15),
        )
        assert result["days_to_listing"] == 5

    def test_apply_closed(self):
        calc = IPOCalendarCalculator()
        result = calc.calculate(
            apply_end_date="2026-06-01",
            listing_date="2026-06-15",
            current_date=date(2026, 6, 5),
        )
        assert result["apply_status"] == "已截止"

    def test_apply_open(self):
        calc = IPOCalendarCalculator()
        result = calc.calculate(
            apply_start_date="2026-06-01",
            apply_end_date="2026-06-10",
            listing_date="2026-06-15",
            current_date=date(2026, 6, 5),
        )
        assert result["apply_status"] == "认购中"

    def test_not_started(self):
        calc = IPOCalendarCalculator()
        result = calc.calculate(
            apply_start_date="2026-07-01",
            apply_end_date="2026-07-05",
            listing_date="2026-07-15",
            current_date=date(2026, 6, 15),
        )
        assert result["apply_status"] == "未开始"

    def test_post_listing(self):
        calc = IPOCalendarCalculator()
        result = calc.calculate(
            listing_date="2026-06-01",
            current_date=date(2026, 6, 15),
        )
        assert result["apply_status"] == "已上市"

    def test_stock_connect_eligible_date(self):
        calc = IPOCalendarCalculator()
        result = calc.calculate(
            listing_date="2026-06-15",
        )
        assert result["stock_connect_eligible_date"] is not None
        assert result["stock_connect_eligible_date"] >= result["listing_date"]

    def test_greenshoe_expiry(self):
        calc = IPOCalendarCalculator()
        result = calc.calculate(
            listing_date="2026-06-15",
            has_greenshoe=True,
        )
        assert result["greenshoe_expiry_date"] is not None
        assert result["greenshoe_expiry_date"] > result["listing_date"]

    def test_no_greenshoe(self):
        calc = IPOCalendarCalculator()
        result = calc.calculate(
            listing_date="2026-06-15",
            has_greenshoe=False,
        )
        assert result["greenshoe_expiry_date"] is None
