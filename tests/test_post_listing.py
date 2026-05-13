#!/usr/bin/env python3
"""Post-listing tracking regression tests."""

import os
import shutil
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd

from ipo_analyzer.history import HistoryStore
from ipo_analyzer import post_listing as pl


def test_parse_allotment_text_core_metrics():
    text = """
    SUMMARY
    Final Offer Price
    HKD26.36
    Dealings commencement date
    May 11, 2026

    ALLOTMENT RESULTS DETAILS
    HONG KONG PUBLIC OFFERING
    No. of valid applications
    296,740
    No. of successful applications
    16,667
    Subscription level
    6,707.66 times
    Reallocation
    No
    No. of Offer Shares initially available under the Hong Kong Public Offering
    3,333,400
    Final no. of Offer Shares under the Hong Kong Public Offering
    3,333,400

    INTERNATIONAL OFFERING
    No. of placees
    111
    Subscription Level
    9.54 times
    Final no. of Offer Shares under the International Offering
    30,000,000

    BASIS OF ALLOCATION UNDER THE HONG KONG PUBLIC OFFERING
    Number of H Shares applied for
    Number of valid applications
    Basis of allocation/ballot
    Approximate % allotted
    POOL A
    200
    80,907
    648 out of 80,907 applicants to receive 200 H Shares
    0.80%
    400
    15,128
    162 out of 15,128 applicants to receive 200 H Shares
    0.54%
    POOL B
    200,000
    15,279
    1,528 out of 15,279 applicants to receive 200 H Shares
    0.01%
    300,000
    5,720
    832 out of 5,720 applicants to receive 200 H Shares
    0.01%
    """

    parsed = pl.parse_allotment_text(text)
    assert parsed["final_offer_price"] == 26.36
    assert parsed["listing_date"] == "2026-05-11"
    assert parsed["valid_applications"] == 296740
    assert parsed["successful_applications"] == 16667
    assert parsed["overall_success_rate_pct"] == 5.62
    assert parsed["public_subscription_level"] == 6707.66
    assert parsed["international_subscription_level"] == 9.54
    assert parsed["placees_count"] == 111
    assert parsed["reallocation"] == "No"
    assert parsed["initial_hk_offer_shares"] == 3333400
    assert parsed["final_hk_offer_shares"] == 3333400
    assert parsed["final_international_offer_shares"] == 30000000
    assert parsed["one_lot_success_rate_pct"] == 0.8
    assert parsed["one_lot_valid_applications"] == 80907
    assert parsed["allocation_pools"]["A"]["valid_applications"] == 96035
    assert parsed["allocation_pools"]["A"]["successful_applications"] == 810
    assert parsed["allocation_pools"]["A"]["rows"][1]["applied_shares"] == 400
    assert parsed["allocation_pools"]["A"]["rows"][1]["allotment_pct"] == 0.54
    assert parsed["allocation_pools"]["A"]["rows"][1]["success_rate_pct"] == 1.07
    assert parsed["allocation_pools"]["B"]["valid_applications"] == 20999
    assert parsed["allocation_pools"]["B"]["successful_applications"] == 2360
    assert parsed["allocation_pools"]["B"]["rows"][1]["success_rate_pct"] == 14.55


def test_find_allotment_announcement_filters_non_ipo(monkeypatch):
    html = """
    <table>
      <tr>
        <td>Release Time: 08/05/2026 22:38</td>
        <td>Stock Code: 01236</td>
        <td>Stock Short Name: LDROBOT</td>
        <td>Document: Announcements and Notices - [Allotment Results]
          <a href="/listedco/listconews/sehk/2026/0508/ipo.pdf">ANNOUNCEMENT OF FINAL OFFER PRICE AND ALLOTMENT RESULTS</a>
        </td>
      </tr>
      <tr>
        <td>Release Time: 08/05/2026 16:49</td>
        <td>Stock Code: 01236</td>
        <td>Stock Short Name: LDROBOT</td>
        <td>Document: Announcements and Notices - [Allotment Results / Rights Issue]
          <a href="/listedco/listconews/sehk/2026/0508/rights.pdf">RESULTS OF THE RIGHTS ISSUE</a>
        </td>
      </tr>
    </table>
    """

    monkeypatch.setattr(pl, "_fetch_stock_id", lambda stock_code, lang="EN": "1000301498")
    monkeypatch.setattr(pl, "_retry_request", lambda *args, **kwargs: SimpleNamespace(text=html))

    found = pl.find_allotment_announcement("01236")
    assert found is not None
    assert found["href"].endswith("/ipo.pdf")
    assert "hkex_title_search" in found["source"]


def test_fetch_price_performance_with_mock_yfinance(monkeypatch):
    dates = pd.to_datetime(["2026-05-11", "2026-05-12", "2026-05-13"])
    history = pd.DataFrame({"Close": [26.36, 31.0, 20.0]}, index=dates)

    class FakeYF:
        @staticmethod
        def download(*args, **kwargs):
            return history

    monkeypatch.setattr(pl, "yf", FakeYF)

    perf = pl.fetch_price_performance("01236", final_offer_price=26.36, listing_date="2026-05-11")
    assert perf["status"] == "ok"
    assert perf["symbol"] == "1236.HK"
    assert perf["first_day"]["price"] == 26.36
    assert perf["first_day"]["change_pct"] == 0.0
    assert perf["first_day"]["date"] == "2026-05-11"
    assert perf["latest"]["price"] == 20.0
    assert perf["latest"]["change_pct"] == -24.13
    assert perf["latest"]["date"] == "2026-05-13"


def test_history_store_update_post_listing_preserves_analysis_fields():
    temp_dir = tempfile.mkdtemp()
    try:
        store = HistoryStore(temp_dir)
        original = {
            "hk_code": "01236",
            "company_name": "LDROBOT",
            "apply_end_date": "2026-05-06",
            "score": 49,
            "parse_success": True,
            "prospectus_info": {"revenue": 100},
            "_reanalysis": {"analysis_mode": "reanalysis"},
        }
        assert store.archive_one(original, source="live")

        updated = store.update_post_listing(
            "1236",
            {
                "status": "ok",
                "final_offer_price": 26.36,
                "one_lot_success_rate_pct": 0.8,
            },
        )
        assert updated["score"] == 49
        assert updated["prospectus_info"]["revenue"] == 100
        assert updated["_reanalysis"]["analysis_mode"] == "reanalysis"
        assert updated["post_listing"]["final_offer_price"] == 26.36

        reanalysis = {
            "hk_code": "01236",
            "company_name": "LDROBOT",
            "score": 55,
            "parse_success": True,
            "_reanalysis": {"analysis_mode": "reanalysis"},
        }
        assert store.merge_analysis_result(reanalysis, source="reanalysis")
        latest = store.load(include_live=True)[0]
        assert latest["score"] == 55
        assert latest["apply_end_date"] == "2026-05-06"
        assert latest["post_listing"]["one_lot_success_rate_pct"] == 0.8
    finally:
        shutil.rmtree(temp_dir)


def test_update_post_listing_fills_actual_over_sub_ratio():
    """Test that public_subscription_level from post_listing fills actual_over_sub_ratio."""
    temp_dir = tempfile.mkdtemp()
    try:
        store = HistoryStore(temp_dir)
        # Create initial record without actual_over_sub_ratio
        initial = {
            "hk_code": "01236",
            "company_name": "LDROBOT",
            "score": 50,
            "actual_over_sub_ratio": None,
        }
        store.merge_analysis_result(initial)
        
        # Update with post_listing containing public_subscription_level
        post_listing_data = {
            "status": "ok",
            "stock_code": "01236",
            "company_name": "LDROBOT",
            "final_offer_price": 26.36,
            "public_subscription_level": 6707.66,
            "international_subscription_level": 9.54,
            "overall_success_rate_pct": 5.62,
        }
        updated = store.update_post_listing("01236", post_listing_data)
        
        assert updated is not None
        assert updated["actual_over_sub_ratio"] == 6707.66
        assert updated["over_sub_ratio_source"] == "post_listing_actual"
        
        # Verify it persists
        latest = store.load(include_live=True)[0]
        assert latest["actual_over_sub_ratio"] == 6707.66
        assert latest["over_sub_ratio_source"] == "post_listing_actual"
    finally:
        shutil.rmtree(temp_dir)


def test_update_post_listing_overwrites_with_real_data():
    """Test that public_subscription_level from allotment overwrites estimated values."""
    temp_dir = tempfile.mkdtemp()
    try:
        store = HistoryStore(temp_dir)
        # Create initial record with estimated actual_over_sub_ratio
        initial = {
            "hk_code": "01236",
            "company_name": "LDROBOT",
            "score": 50,
            "actual_over_sub_ratio": 4322.0,
            "over_sub_ratio_source": "historical_actual",
        }
        store.merge_analysis_result(initial)
        
        # Update with post_listing containing real public_subscription_level
        post_listing_data = {
            "status": "ok",
            "stock_code": "01236",
            "public_subscription_level": 6707.66,
        }
        updated = store.update_post_listing("01236", post_listing_data)
        
        assert updated is not None
        assert updated["actual_over_sub_ratio"] == 6707.66
        assert updated["over_sub_ratio"] == 6707.66
        assert updated["over_sub_ratio_source"] == "post_listing_actual"
    finally:
        shutil.rmtree(temp_dir)


def test_strip_script_style():
    html = """
    <html>
      <script>var x = 123;</script>
      <style>.cls{color:red}</style>
      <div>暗盘收报49.8元</div>
    </html>
    """
    result = pl._strip_script_style(html)
    assert "var x = 123" not in result
    assert ".cls{color:red}" not in result
    assert "暗盘收报49.8元" in result


def test_is_price_reasonable():
    assert pl._is_price_reasonable(49.8, 26.36) is True
    assert pl._is_price_reasonable(26.36, 26.36) is True
    assert pl._is_price_reasonable(980.0, 26.36) is False
    assert pl._is_price_reasonable(2.0, 26.36) is False
    assert pl._is_price_reasonable(49.8, None) is True
    assert pl._is_price_reasonable(49.8, 0) is True


def test_fetch_grey_market_performance_news_headline(monkeypatch):
    html = """
    <html>
    <script>
    var is980Mode = $(".div980").is(":visible");
    var x = "暗盘";
    </script>
    <div class="newsBox">
      <a href="/sc/stocks/news/aafn-con/NOW.1523652/ipo-news/AAFN"
         title="《新股》乐动机器人暗盘收报49.8元 高上市价88.9%">
        <div class="news-content-text">《新股》乐动机器人暗盘收报49.8元 高上市价88.9%</div>
      </a>
    </div>
    <div class="ns1">
      <div class="title">今日新股暗盘</div>
    </div>
    <table class="ns1 GMList-Container">
      <tbody><tr><td class="txt_c msg" colspan="8">供应商是日没有新股暗盘</td></tr></tbody>
    </table>
    </html>
    """

    class FakeResponse:
        status_code = 200
        text = html

    monkeypatch.setattr(pl.httpx, "get", lambda *args, **kwargs: FakeResponse())

    result = pl.fetch_grey_market_performance("01236", final_offer_price=26.36)
    assert result["status"] == "ok"
    assert result["price"] == 49.8
    assert abs(result["change_pct"] - 88.9) < 0.5


def test_fetch_grey_market_performance_rejects_js_noise(monkeypatch):
    """Regression test: JS code containing '暗盘' followed by '980' should not be matched."""
    html = """
    <html>
    <body>
      <script>
        var is980Mode = $(".div980").is(":visible");
        OA_show('Crazy_iPad_popup');
      </script>
      <div class="title">新股频道 IPO - 新股暗盘</div>
      <div>暗盘收报49.8元</div>
    </body>
    </html>
    """

    class FakeResponse:
        status_code = 200
        text = html

    monkeypatch.setattr(pl.httpx, "get", lambda *args, **kwargs: FakeResponse())

    result = pl.fetch_grey_market_performance("01236", final_offer_price=26.36)
    assert result["status"] == "ok"
    assert result["price"] == 49.8


def test_fetch_grey_market_performance_missing(monkeypatch):
    html = "<html><body><div>普通页面</div></body></html>"

    class FakeResponse:
        status_code = 200
        text = html

    monkeypatch.setattr(pl.httpx, "get", lambda *args, **kwargs: FakeResponse())

    result = pl.fetch_grey_market_performance("01236", final_offer_price=26.36)
    assert result["status"] == "missing"
