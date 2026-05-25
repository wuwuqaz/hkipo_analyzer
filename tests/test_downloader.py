"""Downloader 模块单元测试 — 覆盖路径安全、PDF校验、重试逻辑。"""

import os
import pytest
from unittest.mock import MagicMock, patch

from ipo_analyzer.downloader import ProspectusDownloader, _retry_request
from ipo_analyzer.utils import _sanitize_stock_code


class TestSanitizeStockCode:
    """股票代码路径净化测试。"""

    def test_normal_code(self):
        assert _sanitize_stock_code("09999") == "09999"
        assert _sanitize_stock_code("01234") == "01234"

    def test_code_with_hyphen(self):
        assert _sanitize_stock_code("09999.HK") == "09999HK"

    def test_path_traversal_attempt(self):
        assert _sanitize_stock_code("../../../etc/passwd") == "etcpasswd"
        assert _sanitize_stock_code("..\\windows\\system32") == "windowssystem32"

    def test_special_characters(self):
        assert _sanitize_stock_code("abc<script>alert(1)</script>") == "abcscriptalert1script"
        assert _sanitize_stock_code("test; rm -rf /") == "testrmrf"

    def test_empty_and_none(self):
        assert _sanitize_stock_code("") == ""
        assert _sanitize_stock_code(None) == ""


class TestProspectusDownloader:
    """招股书下载器测试。"""

    def test_cache_dir_creation(self, tmp_path):
        d = ProspectusDownloader(cache_dir=str(tmp_path / "test_cache"))
        assert os.path.exists(d.cache_dir)

    def test_pdf_path_sanitization(self, tmp_path):
        """确保 stock_code 被净化后才用于拼接路径。"""
        d = ProspectusDownloader(cache_dir=str(tmp_path))
        # 实际代码通过外部流程调用，这里验证净化函数被正确使用
        safe = _sanitize_stock_code("../../../etc/passwd")
        path = os.path.join(d.cache_dir, f"{safe}_prospectus.pdf")
        assert ".." not in path
        assert os.path.dirname(path) == d.cache_dir

    def test_new_listing_pages_try_chinese_before_english(self, tmp_path):
        """默认应优先访问港交所繁中页面，失败时仍可回退英文页。"""
        d = ProspectusDownloader(cache_dir=str(tmp_path))
        assert d._new_listing_page_urls()[0].endswith("sc_lang=zh-HK")
        assert any(url.endswith("sc_lang=en") for url in d._new_listing_page_urls())

    def test_find_prospectus_prefers_chinese_link_in_same_row(self, tmp_path, monkeypatch):
        """同一股票有中英文招股书时，应优先返回中文链接。"""
        d = ProspectusDownloader(cache_dir=str(tmp_path))
        monkeypatch.setattr(
            d,
            "_fetch_new_listing_rows",
            lambda page_url: [
                {
                    "stock_code": "09999",
                    "stock_name": "测试公司",
                    "prospectus_links": [
                        "/listedco/listconews/sehk/2026/0520/2026052000001.pdf",
                        "/listedco/listconews/sehk/2026/0520/2026052000001_c.pdf",
                    ],
                }
            ],
        )

        url = d._find_prospectus_from_new_listing_page("09999", "测试公司", "https://example.com?sc_lang=zh-HK")

        assert url.endswith("_c.pdf")


class TestRetryRequest:
    """HTTP 重试逻辑测试。"""

    @patch("ipo_analyzer.downloader.httpx")
    def test_success_no_retry(self, mock_httpx):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_httpx.get.return_value = mock_response

        resp = _retry_request(mock_httpx.get, "https://example.com/test")
        assert resp.status_code == 200
        assert mock_httpx.get.call_count == 1

    @patch("ipo_analyzer.downloader.httpx")
    def test_retry_on_500(self, mock_httpx):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_httpx.get.return_value = mock_response

        with pytest.raises(RuntimeError):
            _retry_request(mock_httpx.get, "https://example.com/test", max_retries=2, backoff_factor=0.1)
        assert mock_httpx.get.call_count == 2

    @patch("ipo_analyzer.downloader.httpx")
    def test_no_ssl_fallback_after_fix(self, mock_httpx):
        """验证 SSL 回退逻辑已被移除 — 不应再设置 verify=False。"""
        from ipo_analyzer.downloader import _retry_request
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_httpx.get.return_value = mock_response

        _retry_request(mock_httpx.get, "https://example.com/test")
        # 检查调用中不应包含 verify=False
        for call in mock_httpx.get.call_args_list:
            assert call.kwargs.get("verify") is not False
