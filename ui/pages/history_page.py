import json

import streamlit as st
import pandas as pd

from datetime import datetime
from ipo_analyzer.cache import ResultCache
from ipo_analyzer.history import HistoryStore
from ui.renderers.html_renderer import HtmlRenderer
from ui.renderers.data_formatter import DataFormatter
from ui.components.detail_view import DetailView
from ui.components.filters import IpoFilters
from ui.constants import DISCLAIMER


class HistoryPage:
    """历史记录页面"""

    def __init__(self, temp_dir: str):
        self.temp_dir = temp_dir
        self.cache = ResultCache(temp_dir)
        self.history_store = HistoryStore(temp_dir)
        self.html = HtmlRenderer()
        self.fmt = DataFormatter()
        self.detail_view = DetailView(self.html, self.fmt)

    def render(self) -> None:
        self.html.hero_section(
            "📚 历史 IPO 分析",
            "沉淀已分析过的新股 · 回看招股结束标的 · 用同一口径辅助对比"
        )

        self._migrate_cache()
        all_history = self.history_store.load(include_live=True)

        if not all_history:
            self._render_empty_history()
            return

        self._render_stats(all_history)

        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">🔎 筛选历史记录</div>', unsafe_allow_html=True)
        query, show_live, sort_by = IpoFilters.render_history_filters()
        st.markdown('</div>', unsafe_allow_html=True)

        visible = IpoFilters.apply_history_filters(all_history, query, show_live, self.fmt.is_live_or_future)
        visible = self.fmt.sort_ipos(visible, sort_by)

        rows = self.fmt.ipo_summary_rows(visible, include_archive_time=True)

        if not rows:
            st.info("没有匹配的历史记录。若要查看仍在招股的历史归档，请勾选「显示仍在招股」。")
        else:
            df = pd.DataFrame(rows)
            df = df.drop(columns=["_score_num"])
            st.dataframe(df, width="stretch", hide_index=True, height=min(420, len(df) * 40 + 50))

            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">📋 选择历史IPO查看详情</div>', unsafe_allow_html=True)
            options = [
                f"{item.get('hk_code', '--')} - {item.get('company_name', '--')} "
                f"({item.get('score', 0)}/100 · 截止 {item.get('apply_end_date', '--')})"
                for item in visible
            ]
            selected = st.selectbox("选择历史IPO", options, label_visibility="collapsed")
            st.markdown('</div>', unsafe_allow_html=True)

            export_payload = json.dumps(all_history, ensure_ascii=False, indent=2, default=str).encode("utf-8")
            st.download_button(
                "📦 导出历史JSON",
                export_payload,
                "ipo_history.json",
                "application/json",
                width="stretch",
            )

            if selected:
                stock_code = selected.split(" - ", 1)[0].strip()
                for item in visible:
                    if item.get("hk_code") == stock_code:
                        self.detail_view.render(item)
                        break

        st.caption(DISCLAIMER)

    def _migrate_cache(self) -> None:
        migrated_count = self.history_store.migrate_from_cache(self.cache.load())
        if migrated_count:
            st.success(f"已从当前缓存迁移 {migrated_count} 条记录到历史库")

    def _render_empty_history(self) -> None:
        self.html.empty_state(
            "🗂️",
            "暂无历史分析记录",
            "",
            extra=(
                "点击首页「更新IPO」或在「手动上传分析」完成一次分析后，"
                "系统会自动归档到这里。"
            )
        )
        st.caption(DISCLAIMER)

    def _render_stats(self, all_history: list) -> None:
        live_count = sum(1 for item in all_history if self.fmt.is_live_or_future(item))
        ended_count = sum(1 for item in all_history if self.fmt.is_ended(item))
        latest_archive = max((item.get("_archived_at") or "" for item in all_history), default="")
        latest_archive_display = "--"
        if latest_archive:
            try:
                latest_archive_display = datetime.fromisoformat(latest_archive).strftime("%Y-%m-%d %H:%M")
            except Exception:
                latest_archive_display = latest_archive[:16]

        stats_cols = st.columns(4)
        stat_values = [
            ("历史股票数", len(all_history)),
            ("已结束", ended_count),
            ("招股中", live_count),
            ("最后归档", latest_archive_display),
        ]
        for col, (label, value) in zip(stats_cols, stat_values):
            with col:
                st.markdown(self.html.metric_card(label, str(value)), unsafe_allow_html=True)
