"""URL 安全校验测试."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from ipo_analyzer._url_validation import validate_download_url, sanitize_filename


def test_valid_hkex_url():
    url = "https://www1.hkexnews.hk/some/path.pdf"
    assert validate_download_url(url) == url


def test_valid_hkex2_url():
    url = "https://www2.hkexnews.hk/New-Listings?sc_lang=zh-HK"
    assert validate_download_url(url) == url


def test_valid_aipo_url():
    url = "https://aipo.myiqdii.com/api/data"
    assert validate_download_url(url) == url


def test_valid_jyb_url():
    url = "https://jybdata.iqdii.com/api/endpoint"
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


def test_sanitize_normal_filename():
    assert sanitize_filename("report.pdf") == "report.pdf"


def test_sanitize_path_traversal():
    result = sanitize_filename("../../../etc/passwd")
    assert ".." not in result


def test_sanitize_empty():
    assert sanitize_filename("") == "upload"


def test_sanitize_double_dot():
    result = sanitize_filename("file..pdf")
    assert result == "file.pdf"
