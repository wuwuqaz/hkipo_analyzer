from datetime import datetime, date
from typing import Any, Optional

from ipo_analyzer.utils import _is_num, _normalize_gm
from ui.utils.shared_utils import _num, _html, _as_html
from ui.utils.shared_utils import SafeHtml


class DataFormatter:
    """数据格式化器，负责数据格式化和日期解析"""

    @staticmethod
    def format_number(val: Any, suffix: str = "", precision: int = 2) -> str:
        if val is None:
            return "--"
        if _is_num(val):
            return f"{val:.{precision}f}{suffix}"
        return str(val)

    @staticmethod
    def format_percentage(val: Any) -> str:
        if val is None:
            return "--"
        if _is_num(val):
            return f"{val:.1f}%"
        return str(val)

    @staticmethod
    def parse_date(value: Any) -> Optional[date]:
        if not value:
            return None
        text = str(value).strip()
        if "T" in text:
            text = text.split("T", 1)[0]
        elif " " in text:
            text = text.split(" ", 1)[0]
        try:
            return datetime.strptime(text, "%Y-%m-%d").date()
        except Exception:
            return None

    @staticmethod
    def is_live_or_future(ipo: dict) -> bool:
        end_date = DataFormatter.parse_date((ipo or {}).get("apply_end_date"))
        return end_date is not None and end_date >= datetime.now().date()

    @staticmethod
    def is_ended(ipo: dict) -> bool:
        end_date = DataFormatter.parse_date((ipo or {}).get("apply_end_date"))
        return end_date is not None and end_date < datetime.now().date()

    @staticmethod
    def archive_time_display(ipo: dict) -> str:
        archived_at = (ipo or {}).get("_archived_at") or (ipo or {}).get("_cached_at") or ""
        if not archived_at:
            return "--"
        try:
            return datetime.fromisoformat(str(archived_at)).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return str(archived_at)[:16]

    @staticmethod
    def ipo_summary_rows(ipos: list[dict], include_archive_time: bool = False) -> list[dict]:
        rows = []
        for ipo in ipos:
            pi = ipo.get("prospectus_info", {}) or {}
            val = pi.get("valuation", {}) or {}
            score = ipo.get("score", 0)
            row = {
                "股票代码": ipo.get("hk_code", "--"),
                "公司名称": ipo.get("company_name", "--"),
                "总评分": f"{score}/100",
                "_score_num": _num(score),
                "申购热度": ipo.get("subscription_score", 0),
                "基本面": ipo.get("fundamental_score", 0),
                "风险扣分": f"-{ipo.get('risk_penalty', 0)}",
                "市场热度": ipo.get("market_heat", "--"),
                "估值": val.get("valuation_label", "--"),
                "毛利率": DataFormatter.format_percentage(
                    _normalize_gm(pi.get("gross_margin")) if _is_num(pi.get("gross_margin")) else None
                ),
                "净利润(M)": DataFormatter.format_number(pi.get("net_profit")),
                "截止日": ipo.get("apply_end_date", "--"),
            }
            if include_archive_time:
                row["归档时间"] = DataFormatter.archive_time_display(ipo)
            rows.append(row)
        return rows

    @staticmethod
    def sort_ipos(ipos: list[dict], sort_by: str) -> list[dict]:
        if sort_by == "评分从高到低":
            return sorted(ipos, key=lambda item: _num(item.get("score")), reverse=True)
        if sort_by == "评分从低到高":
            return sorted(ipos, key=lambda item: _num(item.get("score")), reverse=False)
        with_dates = [item for item in ipos if DataFormatter.parse_date(item.get("apply_end_date")) is not None]
        without_dates = [item for item in ipos if DataFormatter.parse_date(item.get("apply_end_date")) is None]
        if sort_by == "截止日从远到近":
            return sorted(with_dates, key=lambda item: DataFormatter.parse_date(item.get("apply_end_date")), reverse=True) + without_dates
        return sorted(with_dates, key=lambda item: DataFormatter.parse_date(item.get("apply_end_date"))) + without_dates

    @staticmethod
    def latest_record_time(records: list[dict], field: str = "_cached_at") -> str:
        times = [str(item.get(field) or "") for item in records or [] if item.get(field)]
        return max(times) if times else ""

    @staticmethod
    def format_revenue_with_yoy(pi: dict) -> str:
        rev = pi.get('revenue')
        rev_y1 = pi.get('revenue_y1')
        if rev and rev_y1 and rev_y1 != 0:
            rev_yoy = (rev - rev_y1) / abs(rev_y1) * 100
            rev_str = f"{rev:.1f} M"
            color = '#ef4444' if rev_yoy > 0 else '#22c55e'
            arrow = '↑' if rev_yoy > 0 else '↓'
            return SafeHtml(
                f"{_html(rev_str)} <span style='color:{color};font-size:12px;'>"
                f"({arrow}{abs(rev_yoy):.1f}%)</span>"
            )
        return DataFormatter.format_number(pi.get('revenue'), ' M')

    @staticmethod
    def format_net_profit_with_yoy(pi: dict) -> str:
        np_val = pi.get('net_profit')
        np_y1 = pi.get('net_profit_y1')
        if np_val is not None and np_y1 is not None and np_y1 != 0:
            np_yoy = (np_val - np_y1) / abs(np_y1) * 100
            np_str = f"{np_val:.1f} M"
            color = '#ef4444' if np_yoy > 0 else '#22c55e'
            arrow = '↑' if np_yoy > 0 else '↓'
            return SafeHtml(
                f"{_html(np_str)} <span style='color:{color};font-size:12px;'>"
                f"({arrow}{abs(np_yoy):.1f}%)</span>"
            )
        return DataFormatter.format_number(pi.get('net_profit'), ' M')

    @staticmethod
    def format_gross_margin_with_yoy(pi: dict) -> str:
        gm = pi.get('gross_margin')
        gm_y1 = pi.get('gross_margin_y1')
        if _is_num(gm) and _is_num(gm_y1):
            gm_cur = _normalize_gm(gm)
            gm_delta = gm_cur - _normalize_gm(gm_y1)
            gm_str = f"{gm_cur:.1f}%"
            color = '#ef4444' if gm_delta > 0 else '#22c55e'
            arrow = '↑' if gm_delta > 0 else '↓'
            return SafeHtml(
                f"{_html(gm_str)} <span style='color:{color};font-size:12px;'>"
                f"({arrow}{abs(gm_delta):.1f}pp)</span>"
            )
        return DataFormatter.format_percentage(
            _normalize_gm(pi.get('gross_margin')) if _is_num(pi.get('gross_margin')) else None
        )
