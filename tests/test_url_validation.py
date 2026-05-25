"""URL 安全校验测试."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from ipo_analyzer._url_validation import validate_download_url, sanitize_filename


def test_valid_hkex_url():
    url = "https://www1.hkexnews.hk/some/path.pdf"
    assert validate_download_url(url) == url


def test_valid_hkexnews_url():
    url = "https://hkexnews.hk/some/path.pdf"
    assert validate_download_url(url) == url


def test_valid_aipo_url():
    url = "https://aipo.com/api/data"
    assert validate_download_url(url) == url


def test_reject_ftp_scheme():
    with pytest.raises(ValueError, match="scheme"):
        validate_download_url("ftp://evil.com/file")


def test_reject_unknown_host():
    with pytest.raises(ValueError, match="域名"):
        validate_download_url("https://evil.com/file.pdf")


def test_reject_no_hostname():
    with pytest.raises(ValueError, match="hostname"):
        validate_download_url("https:///path.pdf")


def test_reject_http_to_unknown():
    with pytest.raises(ValueError):
        validate_download_url("http://malicious-site.com/foo")


def test_sanitize_normal_filename():
    assert sanitize_filename("report.pdf") == "report.pdf"


def test_sanitize_path_traversal():
    assert sanitize_filename("../../../etc/passwd") == "etcpasswd"


def test_sanitize_empty():
    assert sanitize_filename("") == "upload"


def test_sanitize_double_dot():
    assert sanitize_filename("file..pdf") == "file.pdf"


def test_sanitize_spaces():
    result = sanitize_filename("  my file  .pdf  ")
    assert result == "my file.pdf" or "my file.pdf"


def test_sanitize_special_chars():
    result = sanitize_filename("foo<bar>.pdf")
    assert "<" not in result
    assert ">" not in result
