from datetime import datetime, date
from typing import Any, Optional

from ipo_analyzer.utils import _is_num, _normalize_gm
from ui.utils.shared_utils import _num, _html
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
    def format_change_pct(val: Any) -> str:
        if val is None:
            return "--"
        if _is_num(val):
            sign = "+" if val > 0 else ""
            return f"{sign}{val:.1f}%"
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
        if end_date is not None:
            return end_date <= datetime.now().date()
        # 没有截止日时，从上市日期回退判断
        # 招股通常在上市前 1-2 天已结束，所以 listing_date <= 明天 即认为已结束
        from datetime import timedelta
        listing_date = DataFormatter.parse_date((ipo or {}).get("listing_date"))
        if listing_date is None:
            pi = (ipo or {}).get("prospectus_info", {}) or {}
            listing_date = DataFormatter.parse_date(pi.get("listing_date"))
        if listing_date is not None:
            return listing_date <= datetime.now().date() + timedelta(days=1)
        return False

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
            biz = pi.get("business_breakdown", {}) or {}
            rnd = pi.get("rnd_pipeline", {}) or {}
            post = ipo.get("post_listing", {}) or {}
            status_map = {
                "ok": "已完成",
                "pending_allotment": "待公告",
                "partial": "部分",
                "error": "异常",
            }
            score = ipo.get("score", 0)
            trade_score = ipo.get("ipo_trade_score", ipo.get("trade_score", ipo.get("subscription_score", 0)))
            long_term_score = ipo.get("long_term_score", ipo.get("fundamental_score", 0))
            row = {
                "股票代码": ipo.get("hk_code", "--"),
                "公司名称": ipo.get("company_name", "--"),
                "打新交易分": f"{trade_score}/100",
                "_score_num": _num(trade_score),
                "长期投资分": f"{long_term_score}/100",
                "申购建议": ipo.get("subscription_recommendation", "--"),
                "估值压力": ipo.get("valuation_pressure_label", "--"),
                "重大红旗扣分": f"-{ipo.get('risk_penalty', 0)}",
                "市场热度": ipo.get("market_heat", "--"),
                "实时热度": (ipo.get("live_market_heat") or {}).get("sector_heat_label", ipo.get("market_heat", "--")),
                "实时超购倍数": DataFormatter.format_number(
                    ipo.get("actual_over_sub_ratio") if ipo.get("actual_over_sub_ratio") is not None
                    else ipo.get("forecast_over_sub_ratio") if ipo.get("forecast_over_sub_ratio") is not None
                    else ipo.get("over_sub_ratio"),
                    "x"
                ),
                "孖展资金总计": DataFormatter.format_number(ipo.get("margin_total"), "亿"),
                "板块指数": (ipo.get("live_market_heat") or {}).get("sector_board_label", "--"),
                "板块资金流": (ipo.get("live_market_heat") or {}).get("sector_flow_label", "--"),
                "估值": val.get("valuation_label", "--"),
                "Fisher": (pi.get("stock_quality") or {}).get("fisher_label", "--"),
                "Lynch": (pi.get("stock_quality") or {}).get("lynch_label", "--"),
                "业务模型": biz.get("business_model_label", "--"),
                "护城河": rnd.get("hardtech_moat_label", rnd.get("pipeline_quality_label", "--")),
                "EV/Sales": "PS失真" if val.get("revenue_too_small_for_ps") else DataFormatter.format_number(val.get("ev_sales_ratio"), "x"),
                "毛利率": DataFormatter.format_percentage(
                    _normalize_gm(pi.get("gross_margin")) if _is_num(pi.get("gross_margin")) else None
                ),
                "净利润(M)": DataFormatter.format_number(pi.get("net_profit")),
                "库存(M)": DataFormatter.format_number((pi.get("cashflow") or {}).get("inventory_amount")),
                "应收(M)": DataFormatter.format_number((pi.get("cashflow") or {}).get("receivables_amount")),
                "截止日": ipo.get("apply_end_date", "--"),
                "跟踪": status_map.get(post.get("status"), "未跟踪"),
                "一手中签率": DataFormatter.format_percentage(post.get("one_lot_success_rate_pct")),
                "首日涨跌": DataFormatter.format_change_pct((post.get("first_day") or {}).get("change_pct")),
                "至今涨跌": DataFormatter.format_change_pct((post.get("latest") or {}).get("change_pct")),
            }
            if include_archive_time:
                row["归档时间"] = DataFormatter.archive_time_display(ipo)
            rows.append(row)
        return rows

    @staticmethod
    def sort_ipos(ipos: list[dict], sort_by: str) -> list[dict]:
        if sort_by in ("评分从高到低", "打新分从高到低"):
            return sorted(ipos, key=lambda item: _num(item.get("ipo_trade_score", item.get("trade_score", item.get("score")))), reverse=True)
        if sort_by in ("评分从低到高", "打新分从低到高"):
            return sorted(ipos, key=lambda item: _num(item.get("ipo_trade_score", item.get("trade_score", item.get("score")))), reverse=False)
        if sort_by == "长期分从高到低":
            return sorted(ipos, key=lambda item: _num(item.get("long_term_score", item.get("fundamental_score"))), reverse=True)
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
        if rev is not None and rev_y1 is not None and rev_y1 != 0:
            rev_yoy = (rev - rev_y1) / abs(rev_y1) * 100
            rev_str = f"{rev:.1f} M"
            color = '#059669' if rev_yoy > 0 else '#DC2626'
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
            color = '#059669' if np_yoy > 0 else '#DC2626'
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
            color = '#059669' if gm_delta > 0 else '#DC2626'
            arrow = '↑' if gm_delta > 0 else '↓'
            return SafeHtml(
                f"{_html(gm_str)} <span style='color:{color};font-size:12px;'>"
                f"({arrow}{abs(gm_delta):.1f}pp)</span>"
            )
        return DataFormatter.format_percentage(
            _normalize_gm(pi.get('gross_margin')) if _is_num(pi.get('gross_margin')) else None
        )
