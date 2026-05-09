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
    POOL B
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

    monkeypatch.setattr(pl, "_fetch_stock_id", lambda stock_code: "1000301498")
    monkeypatch.setattr(pl, "_retry_request", lambda *args, **kwargs: SimpleNamespace(text=html))

    found = pl.find_allotment_announcement("01236")
    assert found is not None
    assert found["href"].endswith("/ipo.pdf")
    assert found["source"] == "hkex_title_search"


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
