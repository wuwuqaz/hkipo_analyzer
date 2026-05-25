"""本地 HKEX 数据源 — 扫描本地 PDF 目录并按关键词分类"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Optional

from ipo_analyzer.text_extractor import extract_pdf_text

logger = __import__("logging").getLogger(__name__)

PROSPECTUS_KEYWORDS = re.compile(
    r"prospectus|招股|招股書|prospectus", re.IGNORECASE
)
ALLOTMENT_KEYWORDS = re.compile(
    r"allotment|配發|配发|allotment.results|results.of.allotment", re.IGNORECASE
)
OFFER_PRICE_KEYWORDS = re.compile(
    r"offer.price|發售價|发售价|pricing|定價|定价", re.IGNORECASE
)


@dataclass
class LocalPDFFile:
    path: str
    filename: str
    category: str
    stock_code: Optional[str] = None
    company_name: Optional[str] = None


def _classify_filename(filename: str) -> str:
    lower = filename.lower()
    if ALLOTMENT_KEYWORDS.search(lower):
        return "allotment_result"
    if OFFER_PRICE_KEYWORDS.search(lower):
        return "offer_price"
    if PROSPECTUS_KEYWORDS.search(lower):
        return "prospectus"
    return "unknown"


def _extract_code_from_filename(filename: str) -> Optional[str]:
    match = re.search(r"(\d{4,6})", filename)
    return match.group(1) if match else None


def scan_local_pdfs(directory: str) -> list[LocalPDFFile]:
    """扫描目录下所有 PDF，按文件名关键词分类。"""
    results: list[LocalPDFFile] = []
    if not os.path.isdir(directory):
        logger.warning("PDF 目录不存在: %s", directory)
        return results

    for root, _dirs, files in os.walk(directory):
        for fname in sorted(files):
            if not fname.lower().endswith(".pdf"):
                continue
            fpath = os.path.join(root, fname)
            category = _classify_filename(fname)
            code = _extract_code_from_filename(fname)
            results.append(LocalPDFFile(
                path=fpath,
                filename=fname,
                category=category,
                stock_code=code,
            ))
    return results


def read_pdf_text(path: str, max_pages: int = 500) -> str:
    """复用现有 extract_pdf_text，增加异常保护。"""
    try:
        return extract_pdf_text(path, max_pages=max_pages)
    except Exception as e:
        logger.error("PDF 文本提取失败 %s: %s", path, e)
        return ""


def find_pdfs_for_code(
    directory: str, stock_code: str
) -> dict[str, list[LocalPDFFile]]:
    """按股票代码分组查找本地 PDF。"""
    all_files = scan_local_pdfs(directory)
    grouped: dict[str, list[LocalPDFFile]] = {
        "prospectus": [],
        "allotment_result": [],
        "offer_price": [],
        "unknown": [],
    }
    for f in all_files:
        if f.stock_code and f.stock_code.lstrip("0") == stock_code.lstrip("0"):
            grouped.setdefault(f.category, []).append(f)
        elif stock_code.lower() in f.filename.lower():
            grouped.setdefault(f.category, []).append(f)
    return grouped
