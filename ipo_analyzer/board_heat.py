"""板块指数/资金流热度增强器.

优先使用新浪板块行情数据，输出板块名称、涨跌幅、成交额与热度分层。
失败时静默降级，不影响主流程。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from statistics import median
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    import akshare as ak
except Exception:  # pragma: no cover
    ak = None


_CACHE: dict[str, tuple[float, pd.DataFrame]] = {}


@dataclass
class BoardHeatSnapshot:
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

    def to_dict(self) -> dict[str, Any]:
        return {
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
        }


def _cache_get(key: str, ttl_seconds: int) -> pd.DataFrame | None:
    item = _CACHE.get(key)
    if not item:
        return None
    ts, payload = item
    if time.monotonic() - ts > ttl_seconds:
        _CACHE.pop(key, None)
        return None
    return payload


def _cache_set(key: str, payload: pd.DataFrame) -> None:
    _CACHE[key] = (time.monotonic(), payload)


def _label_from_change(change_pct: float | None) -> str:
    if change_pct is None:
        return "缺失"
    if change_pct >= 3:
        return "强势"
    if change_pct >= 1.2:
        return "热门"
    if change_pct >= -0.5:
        return "温和"
    return "冷清"


def _label_from_flow(turnover: float | None) -> str:
    if turnover is None:
        return "缺失"
    if turnover >= 50000000000:
        return "放量"
    if turnover >= 10000000000:
        return "活跃"
    if turnover >= 3000000000:
        return "平稳"
    return "偏弱"


def _score_from_heat(label: str) -> int:
    return {"强势": 6, "热门": 4, "温和": 2, "冷清": 0, "缺失": 0}.get(label, 0)


def _score_from_flow(label: str) -> int:
    return {"放量": 4, "活跃": 3, "平稳": 2, "偏弱": 1, "缺失": 0}.get(label, 0)


class BoardHeatAnalyzer:
    """从板块指数层面给出热度/资金流判断。"""

    _BOARD_MAP = {
        "hardtech": {
            "robotics_factory_automation": ["机器人概念", "智能机器", "智能制造", "人工智能", "工业母机", "自动化"],
            "robotics_visual_perception": ["人工智能", "智能机器", "机器视觉", "视觉", "智能制造"],
            "default": ["人工智能", "半导体", "芯片", "机器人概念", "智能制造", "自动化"],
        },
        "healthcare": {
            "ai_drug_delivery_nanomedicine": ["创新药", "医药", "生物医药", "医疗"],
            "default": ["创新药", "医药", "生物医药", "医疗"],
        },
        "consumer": {
            "default": ["消费电子", "食品饮料", "零售", "家用电器", "白酒"],
        },
    }

    def analyze(self, prospectus_info: dict[str, Any], text: str = "", peer_comparison: dict[str, Any] | None = None) -> dict[str, Any]:
        peer_comparison = peer_comparison or prospectus_info.get("peer_comparison") or {}
        sector = prospectus_info.get("sector", "unknown")
        subsector = peer_comparison.get("subsector") or ""
        candidates = self._candidate_keywords(sector, subsector, text)

        concept_df = self._load_board_df("concept")
        industry_df = self._load_board_df("industry")
        best = self._pick_best_board(concept_df, "概念", candidates)
        alt = self._pick_best_board(industry_df, "行业", candidates)
        chosen = self._choose_board(best, alt)
        if not chosen:
            return BoardHeatSnapshot().to_dict()

        heat_label = _label_from_change(chosen.get("涨跌幅"))
        flow_label = _label_from_flow(chosen.get("总成交额"))
        detail = (
            f"{chosen.get('板块', '--')} · 涨跌{chosen.get('涨跌幅', 0):+.2f}% · "
            f"成交额{self._fmt_money(chosen.get('总成交额'))} · {chosen.get('公司家数', '--')}家公司"
        )
        return BoardHeatSnapshot(
            sector_board_label=str(chosen.get("板块", "--")),
            sector_board_type=str(chosen.get("_source_type", "--")),
            sector_board_change_pct=chosen.get("涨跌幅"),
            sector_board_turnover=chosen.get("总成交额"),
            sector_board_company_count=int(chosen.get("公司家数")) if chosen.get("公司家数") is not None else None,
            sector_board_heat_label=heat_label,
            sector_board_flow_label=flow_label,
            sector_board_detail=detail,
            sector_board_source="sina_sector_spot",
            sector_board_confidence="matched" if chosen.get("_match_score", 0) > 0 else "fallback",
        ).to_dict()

    @staticmethod
    def _fmt_money(value: Any) -> str:
        if value is None:
            return "--"
        try:
            v = float(value)
        except Exception:
            return "--"
        if v >= 1e8:
            return f"{v / 1e8:.1f}亿"
        if v >= 1e4:
            return f"{v / 1e4:.1f}万"
        return f"{v:.0f}"

    def _candidate_keywords(self, sector: str, subsector: str, text: str) -> list[str]:
        text_lower = (text or "").lower()
        candidates = []
        sector_map = self._BOARD_MAP.get(sector, {})
        if subsector in sector_map:
            candidates.extend(sector_map[subsector])
        candidates.extend(sector_map.get("default", []))

        if "robot" in text_lower or "机器人" in text_lower:
            candidates.extend(["机器人概念", "智能机器", "智能制造"])
        if "drug" in text_lower or "biotech" in text_lower or "18a" in text_lower or "创新药" in text_lower:
            candidates.extend(["创新药", "医药", "生物医药"])
        if "vision" in text_lower or "视觉" in text_lower:
            candidates.extend(["人工智能", "智能机器"])

        seen = set()
        ordered = []
        for item in candidates:
            if item not in seen and item:
                seen.add(item)
                ordered.append(item)
        return ordered

    def _load_board_df(self, indicator: str) -> pd.DataFrame | None:
        cache_key = f"board:{indicator}"
        cached = _cache_get(cache_key, ttl_seconds=600)
        if cached is not None:
            return cached
        if ak is None:
            return None
        try:
            df = ak.stock_sector_spot(indicator={"concept": "概念", "industry": "行业", "region": "地域"}.get(indicator, "概念"))
        except Exception as e:
            logger.debug("板块行情获取失败[%s]: %s", indicator, e)
            return None
        if df is not None and not df.empty:
            df = df.copy()
            _cache_set(cache_key, df)
            return df
        return None

    def _pick_best_board(self, df: pd.DataFrame | None, source_type: str, candidates: list[str]) -> dict[str, Any] | None:
        if df is None or df.empty:
            return None
        best_row = None
        best_score = 0
        for _, row in df.iterrows():
            name = str(row.get("板块", "") or "")
            score = sum(2 for kw in candidates if kw and kw in name)
            if source_type == "概念" and any(k in name for k in ("机器人", "创新药", "人工智能", "智能机器", "智能制造")):
                score += 1
            if score > best_score:
                best_score = score
                best_row = row.to_dict()
                best_row["_match_score"] = score
                best_row["_source_type"] = source_type
        return best_row if best_score > 0 else None

    @staticmethod
    def _choose_board(best: dict[str, Any] | None, alt: dict[str, Any] | None) -> dict[str, Any] | None:
        if best and alt:
            best_score = best.get("_match_score", 0)
            alt_score = alt.get("_match_score", 0)
            return best if best_score >= alt_score else alt
        return best or alt
