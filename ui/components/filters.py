from typing import Any

import streamlit as st


class IpoFilters:
    """IPO 过滤器组件"""

    @staticmethod
    def _has_effective_cornerstone_v2(ipo: dict) -> bool:
        ca = (ipo or {}).get("prospectus_info", {}).get("cornerstone_analysis", {}) or {}
        if ca.get("cornerstone_investors") or ca.get("cornerstone_pct") is not None:
            return True
        try:
            return float(ca.get("score", 0)) > 0
        except Exception:
            return False

    @staticmethod
    def render_dashboard_filters() -> tuple[bool, bool, bool, bool]:
        filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
        with filter_col1:
            filter_high_score = st.checkbox("🏆 高分（≥60）")
        with filter_col2:
            filter_low_risk = st.checkbox("🛡️ 低风险")
        with filter_col3:
            filter_has_cornerstone = st.checkbox("🏛️ 有基石")
        with filter_col4:
            filter_valuation_ok = st.checkbox("💰 估值合理")
        return filter_high_score, filter_low_risk, filter_has_cornerstone, filter_valuation_ok

    @staticmethod
    def apply_filters(ipos: list[dict], filter_high_score: bool, filter_low_risk: bool,
                      filter_has_cornerstone: bool, filter_valuation_ok: bool) -> list[dict]:
        filtered = list(ipos)
        if filter_high_score:
            filtered = [r for r in filtered if r.get("score", 0) >= 60]
        if filter_low_risk:
            filtered = [r for r in filtered if r.get("risk_penalty", 0) <= 3]
        if filter_has_cornerstone:
            filtered = [r for r in filtered if IpoFilters._has_effective_cornerstone_v2(r)]
        if filter_valuation_ok:
            filtered = [r for r in filtered if r.get("prospectus_info", {}).get("valuation", {}).get("valuation_label") in ("合理", "低估")]
        return filtered

    @staticmethod
    def render_history_filters(query: str = "") -> tuple[str, bool, str]:
        filter_col1, filter_col2, filter_col3 = st.columns([2, 1, 1])
        with filter_col1:
            query = st.text_input("搜索股票代码或公司名", query, placeholder="如 01236 / 乐动", label_visibility="collapsed")
        with filter_col2:
            show_live = st.checkbox("显示仍在招股", value=False)
        with filter_col3:
            sort_by = st.selectbox("排序", ["截止日从近到远", "截止日从远到近", "评分从高到低", "评分从低到高"], label_visibility="collapsed")
        return query, show_live, sort_by

    @staticmethod
    def apply_history_filters(ipos: list[dict], query: str, show_live: bool,
                              is_live_fn) -> list[dict]:
        visible = list(ipos)
        if not show_live:
            visible = [item for item in visible if not is_live_fn(item)]
        query_text = query.strip().lower()
        if query_text:
            visible = [
                item for item in visible
                if query_text in str(item.get("hk_code", "")).lower()
                or query_text in str(item.get("company_name", "")).lower()
            ]
        return visible
