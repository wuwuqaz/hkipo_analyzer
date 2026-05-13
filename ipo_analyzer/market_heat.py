"""外部市场热度增强器.

基于东方财富实时行情与可比公司涨跌，给出可选的赛道热度判断。
失败时静默降级，不影响主流程。
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from statistics import median
from typing import Any, Iterable

import httpx

from .downloader import _retry_request
from .board_heat import BoardHeatAnalyzer
from .settings import SETTINGS
from .utils import _is_num

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None


_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


@dataclass
class MarketHeatSnapshot:
    sector_heat_label: str = "缺失"
    sector_heat_score: int = 0
    sector_heat_detail: str = ""
    sector_heat_confidence: str = "missing"
    sector_flow_label: str = "缺失"
    sector_flow_score: int = 0
    sector_flow_detail: str = ""
    sector_momentum_label: str = "缺失"
    sector_momentum_score: int = 0
    sector_momentum_detail: str = ""
    sector_board_label: str = "缺失"
    sector_board_type: str = "缺失"
    sector_board_change_pct: float | None = None
    sector_board_turnover: float | None = None
    sector_board_company_count: int | None = None
    sector_board_heat_label: str = "缺失"
    sector_board_flow_label: str = "缺失"
    sector_board_detail: str = ""
    sector_board_source: str = "none"
    sector_board_confidence: str = "missing"
    sector_peer_count: int = 0
    sector_peer_avg_change_pct: float | None = None
    sector_peer_median_change_pct: float | None = None
    sector_peer_median_turnover: float | None = None
    sector_index_change_pct: float | None = None
    sector_samples: list[dict[str, Any]] = field(default_factory=list)
    sector_heat_source: str = "none"
    sector_heat_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sector_heat_label": self.sector_heat_label,
            "sector_heat_score": self.sector_heat_score,
            "sector_heat_detail": self.sector_heat_detail,
            "sector_heat_confidence": self.sector_heat_confidence,
            "sector_flow_label": self.sector_flow_label,
            "sector_flow_score": self.sector_flow_score,
            "sector_flow_detail": self.sector_flow_detail,
            "sector_momentum_label": self.sector_momentum_label,
            "sector_momentum_score": self.sector_momentum_score,
            "sector_momentum_detail": self.sector_momentum_detail,
            "sector_board_label": self.sector_board_label,
            "sector_board_type": self.sector_board_type,
            "sector_board_change_pct": self.sector_board_change_pct,
            "sector_board_turnover": self.sector_board_turnover,
            "sector_board_company_count": self.sector_board_company_count,
            "sector_board_heat_label": self.sector_board_heat_label,
            "sector_board_flow_label": self.sector_board_flow_label,
            "sector_board_detail": self.sector_board_detail,
            "sector_board_source": self.sector_board_source,
            "sector_board_confidence": self.sector_board_confidence,
            "sector_peer_count": self.sector_peer_count,
            "sector_peer_avg_change_pct": self.sector_peer_avg_change_pct,
            "sector_peer_median_change_pct": self.sector_peer_median_change_pct,
            "sector_peer_median_turnover": self.sector_peer_median_turnover,
            "sector_index_change_pct": self.sector_index_change_pct,
            "sector_samples": self.sector_samples,
            "sector_heat_source": self.sector_heat_source,
            "sector_heat_error": self.sector_heat_error,
        }


def _cache_get(key: str, ttl_seconds: int) -> dict[str, Any] | None:
    item = _CACHE.get(key)
    if not item:
        return None
    ts, payload = item
    if time.monotonic() - ts > ttl_seconds:
        _CACHE.pop(key, None)
        return None
    return payload


def _cache_set(key: str, payload: dict[str, Any]) -> None:
    _CACHE[key] = (time.monotonic(), payload)


def _normalize_ticker(ticker: str) -> tuple[str, str] | None:
    t = str(ticker or "").strip().upper()
    if not t or t in {"PRIVATE", "N/A", "--"}:
        return None
    if t.endswith(".HK"):
        code = re.sub(r"\D", "", t[:-3]).zfill(5)
        return ("116", code)
    if t.endswith(".SH"):
        code = re.sub(r"\D", "", t[:-3]).zfill(6)
        return ("1", code)
    if t.endswith(".SZ"):
        code = re.sub(r"\D", "", t[:-3]).zfill(6)
        return ("0", code)
    if re.fullmatch(r"[A-Z.0-9-]+", t) and any(ch.isalpha() for ch in t):
        return None
    return None


def _build_secid(ticker: str) -> str | None:
    parsed = _normalize_ticker(ticker)
    if not parsed:
        return None
    market, code = parsed
    return f"{market}.{code}"


def _pct_from_quote(row: dict[str, Any]) -> float | None:
    for key in ("f3", "pct_change", "change_pct", "changePercent"):
        val = row.get(key)
        if _is_num(val):
            return round(float(val), 2)
    current = row.get("f2")
    prev_close = row.get("f18")
    if _is_num(current) and _is_num(prev_close) and prev_close:
        return round((float(current) / float(prev_close) - 1) * 100, 2)
    return None


def _fetch_eastmoney_quotes(secids: list[str]) -> list[dict[str, Any]]:
    if not secids:
        return []
    requested = {str(secid).strip().upper() for secid in secids if str(secid).strip()}
    url = (
        "https://push2.eastmoney.com/api/qt/ulist.np/get"
        "?fltt=2&invt=2&ut=fa5fd1943c7b386f172d6893dbfba10b"
        "&fields=f1,f2,f3,f4,f12,f13,f14,f15,f16,f17,f18,f20,f21,f62,f100"
        f"&secids={','.join(secids)}"
    )
    response = _retry_request(httpx.get, url, headers={"User-Agent": "Mozilla/5.0"}, timeout=SETTINGS.network.default_timeout)
    if response.status_code != 200:
        return []
    try:
        data = response.json().get("data", {}) or {}
    except Exception:
        return []
    items = data.get("diff") or []
    result: list[dict[str, Any]] = []
    for row in items:
        pct = _pct_from_quote(row)
        if pct is None:
            continue
        secid = f"{row.get('f13', '')}.{row.get('f12', '')}".upper()
        if requested and secid not in requested:
            continue
        result.append(
            {
                "ticker": secid,
                "name": row.get("f14", ""),
                "change_pct": pct,
                "market_cap_hkd_million": row.get("f20"),
                "turnover": row.get("f62"),
                "source": "eastmoney",
            }
        )
    return result


def _fetch_yfinance_quotes(tickers: list[str]) -> list[dict[str, Any]]:
    if yf is None or not tickers:
        return []
    result: list[dict[str, Any]] = []
    for ticker in tickers:
        try:
            hist = yf.download(
                ticker,
                period="5d",
                interval="1d",
                progress=False,
                auto_adjust=False,
                threads=False,
            )
        except Exception as e:  # pragma: no cover - network dependent
            logger.debug("yfinance 获取 %s 失败: %s", ticker, e)
            continue
        if hist is None or hist.empty:
            continue
        close = hist.get("Close")
        if close is None or len(close) < 2:
            continue
        try:
            prev = float(close.iloc[-2])
            curr = float(close.iloc[-1])
        except Exception:
            continue
        if not prev:
            continue
        result.append(
            {
                "ticker": ticker,
                "name": ticker,
                "change_pct": round((curr / prev - 1) * 100, 2),
                "source": "yfinance",
            }
        )
    return result


def _fetch_index_change() -> dict[str, Any]:
    try:
        quotes = _fetch_eastmoney_quotes(["100.HSI", "100.HSCEI"])
    except Exception as e:  # pragma: no cover - network dependent
        return {"label": "缺失", "change_pct": None, "source": "none", "error": str(e)}
    if not quotes:
        return {"label": "缺失", "change_pct": None, "source": "none"}
    hsi = next((q for q in quotes if str(q.get("ticker", "")).startswith("100.")), quotes[0])
    return {
        "label": "恒指",
        "change_pct": hsi.get("change_pct"),
        "source": hsi.get("source", "eastmoney"),
    }


def _label_from_change(change_pct: float | None, peer_count: int = 0) -> str:
    if change_pct is None or peer_count <= 0:
        return "缺失"
    if change_pct >= 3.0:
        return "极热"
    if change_pct >= 1.2:
        return "热门"
    if change_pct >= -0.5:
        return "温和"
    return "冷清"


def _label_from_flow(change_pct: float | None, median_turnover: float | None, peer_count: int = 0) -> str:
    if peer_count <= 0:
        return "缺失"
    if _is_num(median_turnover) and median_turnover > 0:
        if median_turnover >= 200000000:
            return "放量"
        if median_turnover >= 50000000:
            return "活跃"
        if median_turnover >= 10000000:
            return "平稳"
        return "偏弱"
    if change_pct is None:
        return "缺失"
    if change_pct >= 1.2:
        return "活跃"
    if change_pct >= -0.5:
        return "平稳"
    return "偏弱"


def _score_from_flow_label(label: str) -> int:
    return {
        "放量": 5,
        "活跃": 4,
        "平稳": 2,
        "偏弱": 1,
        "缺失": 0,
    }.get(label, 0)


def _label_from_momentum(change_pct: float | None, median_turnover: float | None, peer_count: int = 0) -> str:
    if peer_count <= 0 or not _is_num(change_pct):
        return "缺失"
    if change_pct >= 2.0 and _is_num(median_turnover) and median_turnover >= 100000000:
        return "强势"
    if change_pct >= 1.0 and _is_num(median_turnover) and median_turnover >= 50000000:
        return "上行"
    if change_pct >= -0.5:
        return "盘整"
    return "偏弱"


def _score_from_momentum_label(label: str) -> int:
    return {
        "强势": 6,
        "上行": 4,
        "盘整": 2,
        "偏弱": 1,
        "缺失": 0,
    }.get(label, 0)


def _score_from_label(label: str) -> int:
    return {
        "极热": 4,
        "热门": 3,
        "温和": 1,
        "冷清": 0,
        "缺失": 0,
    }.get(label, 0)


class LiveMarketHeatAnalyzer:
    """把可比公司实时涨跌折算成赛道热度。"""

    def analyze(self, prospectus_info: dict[str, Any], text: str = "", peer_comparison: dict[str, Any] | None = None) -> dict[str, Any]:
        peer_comparison = peer_comparison or prospectus_info.get("peer_comparison") or {}
        peers = peer_comparison.get("quantitative_peers") or peer_comparison.get("matched_peers") or []
        cache_key = self._build_cache_key(peers)
        cached = _cache_get(cache_key, ttl_seconds=300)
        if cached is not None:
            return cached

        snapshot = MarketHeatSnapshot()
        if not peers:
            board_info = BoardHeatAnalyzer().analyze(prospectus_info, text, peer_comparison=peer_comparison)
            snapshot.sector_board_label = board_info.get("sector_board_label", "缺失")
            snapshot.sector_board_type = board_info.get("sector_board_type", "缺失")
            snapshot.sector_board_change_pct = board_info.get("sector_board_change_pct")
            snapshot.sector_board_turnover = board_info.get("sector_board_turnover")
            snapshot.sector_board_company_count = board_info.get("sector_board_company_count")
            snapshot.sector_board_heat_label = board_info.get("sector_board_heat_label", "缺失")
            snapshot.sector_board_flow_label = board_info.get("sector_board_flow_label", "缺失")
            snapshot.sector_board_detail = board_info.get("sector_board_detail", "")
            snapshot.sector_board_source = board_info.get("sector_board_source", "none")
            snapshot.sector_board_confidence = board_info.get("sector_board_confidence", "missing")
            snapshot.sector_heat_detail = snapshot.sector_board_detail or "未获取到可比公司行情"
            payload = snapshot.to_dict()
            _cache_set(cache_key, payload)
            return payload

        quotes = self._collect_peer_quotes(peers)
        change_pcts = [q["change_pct"] for q in quotes if _is_num(q.get("change_pct"))]
        board_info = BoardHeatAnalyzer().analyze(prospectus_info, text, peer_comparison=peer_comparison)
        if change_pcts:
            peer_avg = round(sum(change_pcts) / len(change_pcts), 2)
            peer_med = round(median(change_pcts), 2)
            turnover_values = [q.get("turnover") for q in quotes if _is_num(q.get("turnover"))]
            peer_turnover_med = round(median(turnover_values), 2) if turnover_values else None
            index_info = _fetch_index_change()
            index_change = index_info.get("change_pct")
            board_change = board_info.get("sector_board_change_pct")

            blended = peer_med * 1.5
            if _is_num(index_change):
                blended += float(index_change) * 0.5
            if _is_num(board_change):
                blended += float(board_change) * 0.6

            label = _label_from_change(blended, len(change_pcts))
            flow_label = _label_from_flow(peer_med, peer_turnover_med, len(change_pcts))
            momentum_label = _label_from_momentum(peer_med, peer_turnover_med, len(change_pcts))
            snapshot = MarketHeatSnapshot(
                sector_heat_label=label,
                sector_heat_score=max(0, min(15, round((blended + 3) * 2))),
                sector_heat_detail=self._build_detail(peer_avg, peer_med, index_info, len(change_pcts))
                + (f"；板块{board_info.get('sector_board_label')} {board_info.get('sector_board_change_pct', 0):+.2f}%" if board_info.get("sector_board_label") and board_info.get("sector_board_label") != "缺失" and _is_num(board_info.get("sector_board_change_pct")) else ""),
                sector_heat_confidence="market",
                sector_flow_label=flow_label,
                sector_flow_score=_score_from_flow_label(flow_label),
                sector_flow_detail=self._build_flow_detail(peer_med, peer_turnover_med, len(change_pcts)),
                sector_momentum_label=momentum_label,
                sector_momentum_score=_score_from_momentum_label(momentum_label),
                sector_momentum_detail=self._build_momentum_detail(peer_med, peer_turnover_med, len(change_pcts)),
                sector_board_label=board_info.get("sector_board_label", "缺失"),
                sector_board_type=board_info.get("sector_board_type", "缺失"),
                sector_board_change_pct=board_info.get("sector_board_change_pct"),
                sector_board_turnover=board_info.get("sector_board_turnover"),
                sector_board_company_count=board_info.get("sector_board_company_count"),
                sector_board_heat_label=board_info.get("sector_board_heat_label", "缺失"),
                sector_board_flow_label=board_info.get("sector_board_flow_label", "缺失"),
                sector_board_detail=board_info.get("sector_board_detail", ""),
                sector_board_source=board_info.get("sector_board_source", "none"),
                sector_board_confidence=board_info.get("sector_board_confidence", "missing"),
                sector_peer_count=len(change_pcts),
                sector_peer_avg_change_pct=peer_avg,
                sector_peer_median_change_pct=peer_med,
                sector_peer_median_turnover=peer_turnover_med,
                sector_index_change_pct=index_change if _is_num(index_change) else None,
                sector_samples=quotes[:6],
                sector_heat_source="eastmoney_push2" if any(q.get("source") == "eastmoney" for q in quotes) else "yfinance",
            )
        else:
            snapshot = MarketHeatSnapshot(
                sector_heat_label="缺失",
                sector_heat_score=0,
                sector_heat_detail=board_info.get("sector_board_detail") or "未获取到可比公司行情",
                sector_heat_confidence="missing",
                sector_board_label=board_info.get("sector_board_label", "缺失"),
                sector_board_type=board_info.get("sector_board_type", "缺失"),
                sector_board_change_pct=board_info.get("sector_board_change_pct"),
                sector_board_turnover=board_info.get("sector_board_turnover"),
                sector_board_company_count=board_info.get("sector_board_company_count"),
                sector_board_heat_label=board_info.get("sector_board_heat_label", "缺失"),
                sector_board_flow_label=board_info.get("sector_board_flow_label", "缺失"),
                sector_board_detail=board_info.get("sector_board_detail", ""),
                sector_board_source=board_info.get("sector_board_source", "none"),
                sector_board_confidence=board_info.get("sector_board_confidence", "missing"),
                sector_peer_count=0,
                sector_samples=quotes[:6],
                sector_heat_source="none",
            )

        payload = snapshot.to_dict()
        _cache_set(cache_key, payload)
        return payload

    def _collect_peer_quotes(self, peers: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        eastmoney_secids: list[str] = []
        yfinance_tickers: list[str] = []
        ticker_meta: dict[str, dict[str, Any]] = {}

        for peer in peers:
            ticker = str(peer.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            if ticker == "PRIVATE":
                continue
            secid = _build_secid(ticker)
            if secid:
                eastmoney_secids.append(secid)
                ticker_meta[secid] = {
                    "ticker": ticker,
                    "name": peer.get("name") or ticker,
                }
            else:
                yfinance_tickers.append(ticker)

        quotes: list[dict[str, Any]] = []
        if eastmoney_secids:
            try:
                quotes.extend(_fetch_eastmoney_quotes(list(dict.fromkeys(eastmoney_secids))))
            except Exception as e:  # pragma: no cover - network dependent
                logger.debug("东财行情获取失败: %s", e)
                quotes = []

        if yfinance_tickers:
            try:
                quotes.extend(_fetch_yfinance_quotes(list(dict.fromkeys(yfinance_tickers))))
            except Exception as e:  # pragma: no cover - network dependent
                logger.debug("yfinance 行情获取失败: %s", e)

        normalized: list[dict[str, Any]] = []
        for row in quotes:
            ticker = str(row.get("ticker") or "").upper()
            if ticker in ticker_meta:
                row = {**row, **ticker_meta[ticker]}
            normalized.append(row)
        return normalized

    @staticmethod
    def _build_cache_key(peers: Iterable[dict[str, Any]]) -> str:
        tickers = sorted(
            {
                str(peer.get("ticker") or "").strip().upper()
                for peer in peers
                if str(peer.get("ticker") or "").strip() and str(peer.get("ticker") or "").strip().upper() != "PRIVATE"
            }
        )
        return "sector_heat:" + "|".join(tickers[:30])

    @staticmethod
    def _build_detail(peer_avg: float, peer_med: float, index_info: dict[str, Any], peer_count: int) -> str:
        index_change = index_info.get("change_pct")
        index_part = f"恒指{index_change:+.2f}%" if _is_num(index_change) else "恒指--"
        return f"可比公司{peer_count}家，均值{peer_avg:+.2f}% ，中位数{peer_med:+.2f}% ，{index_part}"

    @staticmethod
    def _build_flow_detail(peer_med: float, median_turnover: float | None, peer_count: int) -> str:
        turnover_part = f"中位成交额{median_turnover:,.0f}" if _is_num(median_turnover) else "成交额--"
        return f"可比公司{peer_count}家，{turnover_part}，涨跌中位数{peer_med:+.2f}%"

    @staticmethod
    def _build_momentum_detail(peer_med: float, median_turnover: float | None, peer_count: int) -> str:
        turnover_part = f"中位成交额{median_turnover:,.0f}" if _is_num(median_turnover) else "成交额--"
        return f"可比公司{peer_count}家，{turnover_part}，板块动能{peer_med:+.2f}%"
