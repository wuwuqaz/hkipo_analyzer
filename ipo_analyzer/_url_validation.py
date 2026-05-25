"""URL 安全校验，防止 SSRF 和路径遍历."""

from __future__ import annotations

import re
from urllib.parse import urlparse

ALLOWED_SCHEMES = {"https", "http"}
ALLOWED_HOSTS = {
    "www1.hkexnews.hk",
    "www.hkex.com.hk",
    "www.hkexnews.hk",
    "hkexnews.hk",
    "aipo.com",
    "www.aipo.com",
    "aipo.com.hk",
}


def validate_download_url(url: str) -> str:
    """校验下载 URL 是否指向允许的域名，防止 SSRF.

    Returns: 校验通过的原 URL
    Raises: ValueError: URL 不合法
    """
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
    """清理上传文件名，防止路径遍历.

    Returns: 仅包含安全字符的文件名
    """
    cleaned = re.sub(r'[^\w\s\-.]', '', filename.strip())
    cleaned = re.sub(r'\.{2,}', '.', cleaned)
    cleaned = cleaned.strip('.')
    if not cleaned:
        cleaned = "upload"
    return cleaned
