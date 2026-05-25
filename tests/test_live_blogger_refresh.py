from unittest.mock import MagicMock, call, patch

from ipo_analyzer.core import _refresh_live_blogger_consensus, analyze_live_ipos


def test_refresh_live_blogger_consensus_calls_service_for_each_live_ipo(tmp_path):
    results = [
        {"hk_code": "07688", "company_name": "拓璞数控"},
        {"hk_code": "06871", "company_name": "翼菲科技"},
    ]

    service = MagicMock()
    with patch("ipo_analyzer.core.BloggerMonitorService", return_value=service) as mock_service_cls:
        _refresh_live_blogger_consensus(results, output_dir=str(tmp_path))

    mock_service_cls.assert_called_once_with(db_path=str(tmp_path / "blogger_monitor.db"))
    service.run_full_pipeline.assert_has_calls(
        [
            call("07688", company_name="拓璞数控"),
            call("06871", company_name="翼菲科技"),
        ]
    )


def test_refresh_live_blogger_consensus_tolerates_single_failure(tmp_path):
    results = [
        {"hk_code": "07688", "company_name": "拓璞数控"},
        {"hk_code": "06871", "company_name": "翼菲科技"},
    ]

    service = MagicMock()
    service.run_full_pipeline.side_effect = [RuntimeError("network"), object()]
    with patch("ipo_analyzer.core.BloggerMonitorService", return_value=service):
        _refresh_live_blogger_consensus(results, output_dir=str(tmp_path))

    assert service.run_full_pipeline.call_count == 2


def test_analyze_live_ipos_does_not_block_on_blogger_consensus(tmp_path):
    fake_live_ipos = [
        {"shortname": "拓璞数控", "symbol": "07688"},
        {"shortname": "翼菲科技", "symbol": "06871"},
    ]

    fake_results = [
        {"hk_code": "07688", "company_name": "拓璞数控", "score": 10},
        {"hk_code": "06871", "company_name": "翼菲科技", "score": 20},
    ]

    client = MagicMock()
    client.fetch_live_ipos.return_value = fake_live_ipos

    with patch("ipo_analyzer.core.AiPOMarginClient", return_value=client), \
         patch("ipo_analyzer.core.ProspectusDownloader"), \
         patch("ipo_analyzer.core.ProspectusParser"), \
         patch("ipo_analyzer.core._process_ipo", side_effect=fake_results), \
         patch("ipo_analyzer.core._refresh_live_blogger_consensus") as mock_refresh:
        results = analyze_live_ipos(output_dir=str(tmp_path))

    assert [r["hk_code"] for r in results] == ["06871", "07688"]
    mock_refresh.assert_not_called()
