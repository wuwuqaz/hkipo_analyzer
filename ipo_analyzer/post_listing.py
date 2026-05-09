"""Post-listing tracking for ended Hong Kong IPOs.

This module keeps the post-listing workflow separate from the prospectus
analysis pipeline: it finds HKEX allotment announcements, parses allocation
metrics, and adds best-effort price performance data.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime
from html import unescape
from typing import Any, Optional

import httpx

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover - import failure is surfaced at runtime
    fitz = None

try:
    import yfinance as yf
except Exception:  # pragma: no cover - yfinance is optional at import time
    yf = None

from .downloader import ProspectusDownloader, _retry_request
from .utils import _is_num, _normalize_company_name, _normalize_stock_code

logger = logging.getLogger(__name__)


HKEX_HOST = "https://www1.hkexnews.hk"
HKEX_PREFIX_URL = f"{HKEX_HOST}/search/prefix.do"
HKEX_TITLE_SEARCH_URL = f"{HKEX_HOST}/search/titlesearch.xhtml"
HKEX_PREDEFINED_ALLOTMENT_URL = (
    f"{HKEX_HOST}/search/predefineddoc.xhtml?predefineddocuments=4"
)
AASTOCKS_GREY_MARKET_URL = (
    "https://www.aastocks.com/sc/stocks/market/ipo/greymarket.aspx?symbol={code}"
)


def _display_stock_code(stock_code: Any) -> str:
    code = re.sub(r"\D", "", str(stock_code or ""))
    if not code:
        return ""
    return code.zfill(5)


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def _to_int(value: Any) -> Optional[int]:
    if value in (None, "", "--"):
        return None
    try:
        return int(str(value).replace(",", "").strip())
    except Exception:
        return None


def _to_float(value: Any) -> Optional[float]:
    if value in (None, "", "--"):
        return None
    try:
        return float(str(value).replace(",", "").replace("HK$", "").replace("HKD", "").strip())
    except Exception:
        return None


def _pct_change(price: Any, base_price: Any) -> Optional[float]:
    price_val = _to_float(price)
    base_val = _to_float(base_price)
    if price_val is None or base_val in (None, 0):
        return None
    return round((price_val / base_val - 1) * 100, 2)


def _parse_english_date(value: str) -> Optional[str]:
    text = re.sub(r"\s+", " ", value or "").strip().rstrip(".,")
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except Exception:
            continue
    return None


def _extract_pdf_text(pdf_path: Optional[str] = None, pdf_bytes: Optional[bytes] = None) -> str:
    if fitz is None:
        raise RuntimeError("PyMuPDF is not available; cannot parse allotment PDF")
    if pdf_bytes is not None:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    elif pdf_path:
        doc = fitz.open(pdf_path)
    else:
        raise ValueError("pdf_path or pdf_bytes is required")
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def _section(text: str, start_pattern: str, end_pattern: Optional[str] = None) -> str:
    flags = re.IGNORECASE | re.DOTALL
    start = re.search(start_pattern, text, flags)
    if not start:
        return ""
    start_idx = start.end()
    if end_pattern:
        end = re.search(end_pattern, text[start_idx:], flags)
        if end:
            return text[start_idx:start_idx + end.start()]
    return text[start_idx:]


def _extract_labeled_number(text: str, label_pattern: str, max_gap: int = 180) -> Optional[float]:
    pattern = rf"{label_pattern}[\s\S]{{0,{max_gap}}}?([0-9][0-9,]*(?:\.[0-9]+)?)"
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    return _to_float(match.group(1))


def _extract_labeled_text(text: str, label_pattern: str, values: tuple[str, ...]) -> Optional[str]:
    value_pattern = "|".join(re.escape(v) for v in values)
    match = re.search(rf"{label_pattern}\s*({value_pattern})\b", text, re.IGNORECASE)
    if not match:
        return None
    return match.group(1)


def parse_allotment_text(text: str) -> dict[str, Any]:
    """Parse core allocation metrics from an HKEX allotment announcement text."""
    result: dict[str, Any] = {}
    if not text:
        return result

    compact = re.sub(r"[ \t]+", " ", text)
    hk_section = _section(
        compact,
        r"ALLOTMENT RESULTS DETAILS\s+HONG KONG PUBLIC OFFERING|HONG KONG PUBLIC OFFERING",
        r"\n\s*INTERNATIONAL OFFERING\b",
    )
    intl_section = _section(compact, r"\n\s*INTERNATIONAL OFFERING\b")

    offer_price = _extract_labeled_number(compact, r"Final\s+Offer\s+Price")
    if offer_price is not None:
        result["final_offer_price"] = offer_price

    listing_match = re.search(
        r"Dealings\s+commencement\s+date\s*([A-Z][a-z]{2,9}\s+\d{1,2},\s+\d{4})",
        compact,
        re.IGNORECASE,
    )
    if not listing_match:
        listing_match = re.search(
            r"expected\s+to\s+be\s+on\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s*"
            r"([A-Z][a-z]{2,9}\s+\d{1,2},\s+\d{4})",
            compact,
            re.IGNORECASE,
        )
    if listing_match:
        parsed_date = _parse_english_date(listing_match.group(1))
        result["listing_date"] = parsed_date or listing_match.group(1)

    valid = _extract_labeled_number(hk_section or compact, r"No\.\s+of\s+valid\s+applications")
    successful = _extract_labeled_number(
        hk_section or compact, r"No\.\s+of\s+successful\s+applications"
    )
    if valid is not None:
        result["valid_applications"] = int(valid)
    if successful is not None:
        result["successful_applications"] = int(successful)
    if valid and successful is not None:
        result["overall_success_rate_pct"] = round(successful / valid * 100, 2)

    public_sub = _extract_labeled_number(hk_section or compact, r"Subscription\s+level")
    intl_sub = _extract_labeled_number(intl_section, r"Subscription\s+Level")
    placees = _extract_labeled_number(intl_section, r"No\.\s+of\s+placees")
    if public_sub is not None:
        result["public_subscription_level"] = public_sub
    if intl_sub is not None:
        result["international_subscription_level"] = intl_sub
    if placees is not None:
        result["placees_count"] = int(placees)

    reallocation = _extract_labeled_text(hk_section or compact, r"Reallocation", ("Yes", "No"))
    if reallocation:
        result["reallocation"] = reallocation

    share_patterns = {
        "initial_hk_offer_shares": (
            r"No\.\s+of\s+Offer\s+Shares\s+initially\s+available\s+under\s+the\s+Hong\s+Kong\s+Public\s+Offering",
            r"Number\s+of\s+Hong\s+Kong\s+Offer\s+Shares",
        ),
        "final_hk_offer_shares": (
            r"Final\s+(?:no\.|Number)\s+of\s+Offer\s+Shares\s+(?:under|in)\s+(?:the\s+)?Hong\s+Kong\s+Public\s+Offering",
            r"Final\s+Number\s+of\s+Offer\s+Shares\s+in\s+Hong\s+Kong\s+Public\s+Offering",
        ),
        "final_international_offer_shares": (
            r"Final\s+(?:no\.|Number)\s+of\s+Offer\s+Shares\s+(?:under|in)\s+(?:the\s+)?International\s+Offering",
            r"Final\s+Number\s+of\s+Offer\s+Shares\s+in\s+International\s+Offering",
        ),
    }
    for key, patterns in share_patterns.items():
        for pattern in patterns:
            value = _extract_labeled_number(compact, pattern, max_gap=240)
            if value is not None:
                result[key] = int(value)
                break

    pool_a = _section(compact, r"\bPOOL\s+A\b", r"\bPOOL\s+B\b")
    one_lot = re.search(
        r"([0-9][0-9,]*)\s+([0-9][0-9,]*)\s+"
        r"([0-9][0-9,]*)\s+out\s+of\s+([0-9][0-9,]*)\s+applicants"
        r"[\s\S]{0,180}?([0-9]+(?:\.[0-9]+)?)%",
        pool_a,
        re.IGNORECASE,
    )
    if one_lot:
        applied = _to_int(one_lot.group(1))
        valid_apps = _to_int(one_lot.group(2))
        successful_apps = _to_int(one_lot.group(3))
        denominator = _to_int(one_lot.group(4))
        pct = _to_float(one_lot.group(5))
        result["one_lot_applied_shares"] = applied
        result["one_lot_valid_applications"] = valid_apps
        result["one_lot_successful_applications"] = successful_apps
        if successful_apps is not None and denominator:
            result["one_lot_success_rate_pct"] = round(successful_apps / denominator * 100, 2)
        elif pct is not None:
            result["one_lot_success_rate_pct"] = pct

    return result


def parse_allotment_pdf(
    pdf_path: Optional[str] = None,
    pdf_bytes: Optional[bytes] = None,
    text: Optional[str] = None,
) -> dict[str, Any]:
    """Parse an allotment PDF or already-extracted text."""
    extracted_text = text if text is not None else _extract_pdf_text(pdf_path=pdf_path, pdf_bytes=pdf_bytes)
    result = parse_allotment_text(extracted_text)
    result["text_length"] = len(extracted_text or "")
    return result


def _parse_jsonp(text: str) -> dict[str, Any]:
    match = re.search(r"\((\{.*\})\)\s*;?\s*$", text or "", re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except Exception:
        return {}


def _fetch_stock_id(stock_code: str) -> Optional[str]:
    display_code = _display_stock_code(stock_code)
    if not display_code:
        return None
    response = _retry_request(
        httpx.get,
        HKEX_PREFIX_URL,
        params={
            "callback": "callback",
            "lang": "EN",
            "market": "SEHK",
            "type": "A",
            "name": display_code,
        },
        timeout=20,
    )
    data = _parse_jsonp(response.text)
    for item in data.get("stockInfo") or []:
        if _normalize_stock_code(item.get("code")) == _normalize_stock_code(display_code):
            stock_id = item.get("stockId")
            return str(stock_id) if stock_id is not None else None
    return None


def _parse_hkex_rows(html: str) -> list[dict[str, Any]]:
    rows = []
    for row_html in re.findall(r"<tr\b[^>]*>(.*?)</tr>", html or "", re.IGNORECASE | re.DOTALL):
        if ".pdf" not in row_html.lower():
            continue
        href_match = re.search(r'href="([^"]+?\.pdf)"', row_html, re.IGNORECASE)
        if not href_match:
            continue
        href = href_match.group(1)
        if href.startswith("/"):
            href = f"{HKEX_HOST}{href}"
        plain = _clean_text(row_html)
        rows.append(
            {
                "href": href,
                "stock_code": (re.search(r"Stock\s+Code:\s*([0-9]{4,5})", plain, re.IGNORECASE) or [None, None])[1],
                "stock_short_name": (re.search(r"Stock\s+Short\s+Name:\s*([^:]+?)\s+Document:", plain, re.IGNORECASE) or [None, None])[1],
                "release_time": (re.search(r"Release\s+Time:\s*([0-9/:\s]+)", plain, re.IGNORECASE) or [None, None])[1],
                "text": plain,
                "raw_html": row_html,
            }
        )
    return rows


def _is_ipo_allotment_row(row: dict[str, Any], stock_code: str) -> bool:
    row_code = _normalize_stock_code(row.get("stock_code"))
    target_code = _normalize_stock_code(stock_code)
    if row_code and row_code != target_code:
        return False

    text = (row.get("text") or "").lower()
    if "allotment results" not in text:
        return False

    non_ipo_keywords = (
        "rights issue",
        "open offer",
        "completion of the rights",
        "results of the rights",
        "placing / rights issue",
    )
    if any(keyword in text for keyword in non_ipo_keywords):
        return False

    ipo_keywords = (
        "final offer price",
        "global offering",
        "public offering",
        "announcement of allotment results",
    )
    return any(keyword in text for keyword in ipo_keywords)


def _find_from_title_search(stock_code: str) -> Optional[dict[str, Any]]:
    stock_id = _fetch_stock_id(stock_code)
    if not stock_id:
        return None
    response = _retry_request(
        httpx.get,
        HKEX_TITLE_SEARCH_URL,
        params={
            "lang": "EN",
            "market": "SEHK",
            "stockId": stock_id,
            "category": "0",
        },
        timeout=30,
        follow_redirects=True,
    )
    for row in _parse_hkex_rows(response.text):
        if _is_ipo_allotment_row(row, stock_code):
            row["source"] = "hkex_title_search"
            return row
    return None


def _find_from_new_listing_page(stock_code: str, company_name: Optional[str]) -> Optional[dict[str, Any]]:
    downloader = ProspectusDownloader()
    normalized_code = _normalize_stock_code(stock_code)
    normalized_name = _normalize_company_name(company_name or "") if company_name else ""
    pages = [
        "https://www2.hkexnews.hk/New-Listings/New-Listing-Information/Main-Board?sc_lang=en",
        "https://www2.hkexnews.hk/New-Listings/New-Listing-Information/GEM?sc_lang=en",
    ]
    for page_url in pages:
        for row in downloader._fetch_new_listing_rows(page_url):
            row_code = _normalize_stock_code(row.get("stock_code"))
            row_name = _normalize_company_name(row.get("stock_name") or "")
            code_match = row_code == normalized_code
            name_match = bool(normalized_name) and (
                normalized_name in row_name or row_name in normalized_name
            )
            if not (code_match or name_match):
                continue
            for href in row.get("allotment_links") or []:
                if not href:
                    continue
                if href.startswith("/"):
                    href = f"{HKEX_HOST}{href}"
                return {
                    "href": href,
                    "stock_code": _display_stock_code(stock_code),
                    "stock_short_name": row.get("stock_name"),
                    "release_time": None,
                    "text": "New Listing Information allotment link",
                    "source": "hkex_new_listing_page",
                }
    return None


def _find_from_predefined(stock_code: str) -> Optional[dict[str, Any]]:
    response = _retry_request(
        httpx.get,
        HKEX_PREDEFINED_ALLOTMENT_URL,
        timeout=30,
        follow_redirects=True,
    )
    for row in _parse_hkex_rows(response.text):
        if _is_ipo_allotment_row(row, stock_code):
            row["source"] = "hkex_predefined_allotment"
            return row
    return None


def find_allotment_announcement(stock_code: str, company_name: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Find the latest IPO allotment announcement for a stock code."""
    for finder in (
        lambda: _find_from_title_search(stock_code),
        lambda: _find_from_new_listing_page(stock_code, company_name),
        lambda: _find_from_predefined(stock_code),
    ):
        try:
            found = finder()
            if found:
                return found
        except Exception as exc:
            logger.warning("Allotment announcement finder failed: %s", exc)
    return None


def _download_allotment_pdf(url: str, stock_code: str, output_dir: str, force_refresh: bool = False) -> str:
    allotment_dir = os.path.join(output_dir, "allotment")
    os.makedirs(allotment_dir, exist_ok=True)
    pdf_path = os.path.join(allotment_dir, f"{_display_stock_code(stock_code)}_allotment.pdf")
    if os.path.exists(pdf_path) and not force_refresh:
        return pdf_path
    response, _ = ProspectusDownloader(cache_dir=allotment_dir)._download_pdf_with_fallback(url)
    with open(pdf_path, "wb") as f:
        f.write(response.content)
    return pdf_path


def fetch_grey_market_performance(stock_code: str, final_offer_price: Any = None) -> dict[str, Any]:
    """Best-effort grey-market parser.

    The page is not an official source and may be dynamically rendered, so
    failures are intentionally represented as missing data.
    """
    display_code = _display_stock_code(stock_code)
    url = AASTOCKS_GREY_MARKET_URL.format(code=display_code)
    payload: dict[str, Any] = {
        "status": "missing",
        "source": "aastocks_grey_market",
        "source_url": url,
        "fetched_at": datetime.now().isoformat(),
    }
    try:
        response = httpx.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            timeout=httpx.Timeout(12.0, connect=5.0, read=12.0),
            follow_redirects=True,
        )
        if response.status_code != 200:
            payload["error"] = f"HTTP {response.status_code}"
            return payload
        text = _clean_text(response.text)
        if "暗盘" not in text and "grey" not in text.lower():
            payload["error"] = "grey market section not found"
            return payload

        # Conservative parsing: only accept prices close to explicit grey-market wording.
        match = re.search(
            r"(?:暗盘|Grey\s*Market)[^0-9]{0,120}([0-9]+(?:\.[0-9]+)?)\s*(?:港元|HKD|HK\$)?",
            text,
            re.IGNORECASE,
        )
        if not match:
            payload["error"] = "grey market price not found"
            return payload
        price = _to_float(match.group(1))
        if price is None:
            return payload
        payload.update(
            {
                "status": "ok",
                "price": price,
                "change_pct": _pct_change(price, final_offer_price),
            }
        )
    except Exception as exc:
        payload["error"] = str(exc)
    return payload


def _series_from_history(history: Any):
    if history is None or getattr(history, "empty", True):
        return None
    columns = getattr(history, "columns", None)
    if columns is None:
        return None
    try:
        if getattr(columns, "nlevels", 1) > 1:
            level0 = list(columns.get_level_values(0))
            if "Close" in level0:
                close = history["Close"]
            elif "Adj Close" in level0:
                close = history["Adj Close"]
            else:
                return None
            if hasattr(close, "columns"):
                close = close.iloc[:, 0]
            return close.dropna()
        if "Close" in columns:
            return history["Close"].dropna()
        if "Adj Close" in columns:
            return history["Adj Close"].dropna()
    except Exception:
        return None
    return None


def fetch_price_performance(stock_code: str, final_offer_price: Any = None, listing_date: Optional[str] = None) -> dict[str, Any]:
    source_symbol = f"{_normalize_stock_code(stock_code)}.HK"
    result: dict[str, Any] = {
        "status": "missing",
        "source": "yfinance",
        "symbol": source_symbol,
        "fetched_at": datetime.now().isoformat(),
    }
    if yf is None:
        result["error"] = "yfinance is not available"
        return result
    try:
        history = yf.download(
            source_symbol,
            period="max",
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        close = _series_from_history(history)
        if close is None or getattr(close, "empty", True):
            result["error"] = "no price history"
            return result
        if listing_date:
            try:
                close = close[close.index >= listing_date]
            except Exception:
                pass
        if getattr(close, "empty", True):
            result["error"] = "no price history after listing date"
            return result

        first_idx = close.index[0]
        latest_idx = close.index[-1]
        first_price = float(close.iloc[0])
        latest_price = float(close.iloc[-1])

        result.update(
            {
                "status": "ok",
                "first_day": {
                    "price": round(first_price, 3),
                    "change_pct": _pct_change(first_price, final_offer_price),
                    "date": first_idx.strftime("%Y-%m-%d") if hasattr(first_idx, "strftime") else str(first_idx)[:10],
                    "source": "yfinance",
                    "source_url": f"https://finance.yahoo.com/quote/{source_symbol}",
                },
                "latest": {
                    "price": round(latest_price, 3),
                    "change_pct": _pct_change(latest_price, final_offer_price),
                    "date": latest_idx.strftime("%Y-%m-%d") if hasattr(latest_idx, "strftime") else str(latest_idx)[:10],
                    "source": "yfinance",
                    "source_url": f"https://finance.yahoo.com/quote/{source_symbol}",
                },
            }
        )
    except Exception as exc:
        result["error"] = str(exc)
    return result


def track_post_listing(
    stock_code: str,
    company_name: Optional[str] = None,
    base_record: Optional[dict[str, Any]] = None,
    output_dir: str = "temp",
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Fetch and parse post-listing data for one ended IPO."""
    display_code = _display_stock_code(stock_code)
    post_listing: dict[str, Any] = {
        "status": "pending_allotment",
        "stock_code": display_code,
        "company_name": company_name or (base_record or {}).get("company_name"),
        "tracked_at": datetime.now().isoformat(),
    }

    announcement = find_allotment_announcement(display_code, company_name)
    if not announcement:
        post_listing["message"] = "HKEX allotment announcement not found yet"
        return post_listing

    source_url = announcement.get("href")
    try:
        pdf_path = _download_allotment_pdf(source_url, display_code, output_dir, force_refresh=force_refresh)
        parsed = parse_allotment_pdf(pdf_path=pdf_path)
    except Exception as exc:
        post_listing.update(
            {
                "status": "error",
                "source_url": source_url,
                "error": str(exc),
            }
        )
        return post_listing

    fetched_at = datetime.now().isoformat()
    post_listing.update(parsed)
    post_listing.update(
        {
            "status": "ok" if parsed else "partial",
            "allotment_pdf": {
                "path": pdf_path,
                "source_url": source_url,
                "release_time": announcement.get("release_time"),
                "source": announcement.get("source"),
                "fetched_at": fetched_at,
            },
            "source_url": source_url,
            "release_time": announcement.get("release_time"),
        }
    )

    final_offer_price = post_listing.get("final_offer_price")
    post_listing["grey_market"] = fetch_grey_market_performance(display_code, final_offer_price)
    price_perf = fetch_price_performance(display_code, final_offer_price, post_listing.get("listing_date"))
    if price_perf.get("status") == "ok":
        post_listing["first_day"] = price_perf.get("first_day")
        post_listing["latest"] = price_perf.get("latest")
    else:
        post_listing["first_day"] = {"status": "missing", "source": "yfinance", "error": price_perf.get("error")}
        post_listing["latest"] = {"status": "missing", "source": "yfinance", "error": price_perf.get("error")}
    post_listing["price_performance"] = price_perf
    return post_listing


def _is_ended_record(record: dict[str, Any]) -> bool:
    value = (record or {}).get("apply_end_date")
    if not value:
        return False
    text = str(value).split("T", 1)[0].split(" ", 1)[0]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date() < date.today()
    except Exception:
        return False


def track_ended_ipos(
    output_dir: str = "temp",
    stock_codes: Optional[list[str]] = None,
    only_missing: bool = True,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Track all ended IPOs in HistoryStore, optionally narrowed by stock code."""
    from .history import HistoryStore

    store = HistoryStore(output_dir)
    selected_codes = {_normalize_stock_code(code) for code in stock_codes or [] if code}
    records = store.load(include_live=True)
    summary = {"processed": 0, "updated": 0, "skipped": 0, "failed": 0, "details": []}

    for record in records:
        code = record.get("hk_code")
        if not code:
            continue
        if selected_codes and _normalize_stock_code(code) not in selected_codes:
            continue
        if not _is_ended_record(record):
            summary["skipped"] += 1
            continue
        existing_status = (record.get("post_listing") or {}).get("status")
        if only_missing and existing_status == "ok" and not force_refresh:
            summary["skipped"] += 1
            continue

        summary["processed"] += 1
        try:
            post_listing = track_post_listing(
                code,
                company_name=record.get("company_name"),
                base_record=record,
                output_dir=output_dir,
                force_refresh=force_refresh,
            )
            store.update_post_listing(code, post_listing)
            summary["updated"] += 1
            summary["details"].append(
                {
                    "stock_code": _display_stock_code(code),
                    "company_name": record.get("company_name"),
                    "status": post_listing.get("status"),
                    "message": post_listing.get("message") or post_listing.get("error"),
                }
            )
        except Exception as exc:
            summary["failed"] += 1
            summary["details"].append(
                {
                    "stock_code": _display_stock_code(code),
                    "company_name": record.get("company_name"),
                    "status": "error",
                    "message": str(exc),
                }
            )
    return summary
