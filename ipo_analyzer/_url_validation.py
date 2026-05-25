"""URL 安全校验，防止 SSRF 和路径遍历."""

from __future__ import annotations

import re
from urllib.parse import urlparse

ALLOWED_SCHEMES = {"https", "http"}
ALLOWED_HOSTS = {
    "www1.hkexnews.hk",
    "www2.hkexnews.hk",
    "www.hkex.com.hk",
    "www.hkexnews.hk",
    "aipo.myiqdii.com",
    "jybdata.iqdii.com",
}


def validate_download_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError(f"不允许的 URL scheme: {parsed.scheme}")
    if not parsed.hostname:
        raise ValueError(f"URL 缺少 hostname: {url}")
    host_lower = parsed.hostname.lower()
    host_ok = any(
        host_lower == allowed or host_lower.endswith("." + allowed)
        for allowed in ALLOWED_HOSTS
    )
    if not host_ok:
        raise ValueError(f"不允许的下载域名: {parsed.hostname}")
    return url


def sanitize_filename(filename: str) -> str:
    cleaned = re.sub(r'[^\w\s\-.]', '', filename.strip())
    cleaned = re.sub(r'\.{2,}', '.', cleaned)
    if not cleaned:
        cleaned = "upload"
    return cleaned
