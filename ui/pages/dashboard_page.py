from typing import Any

import streamlit as st
import pandas as pd

from ipo_analyzer.core import analyze_live_ipos
from ipo_analyzer.cache import ResultCache
from ipo_analyzer.history import HistoryStore
from ui.renderers.html_renderer import HtmlRenderer
from ui.renderers.data_formatter import DataFormatter
from ui.components.detail_view import DetailView
from ui.components.filters import IpoFilters


class DashboardPage:
    """首页 Dashboard"""

    def __init__(self, temp_dir: str):
        self.temp_dir = temp_dir
        self.cache = ResultCache(temp_dir)
        self.html = HtmlRenderer()
        self.fmt = DataFormatter()
        self.detail_view = DetailView(self.html, self.fmt)
        self.filters = IpoFilters()

    def render(self) -> None:
        self._render_hero()
        self._render_update_buttons()
        results = self._get_results()

        if not results:
            self._render_empty_state()
            return

        st.markdown(
            f'<div style="font-size:14px;color:#64748b;margin-bottom:12px;">共 <b>{len(results)}</b> 只正在招股</div>',
            unsafe_allow_html=True
        )

        filter_high_score, filter_low_risk, filter_has_cornerstone, filter_valuation_ok = (
            IpoFilters.render_dashboard_filters()
        )
        filtered = IpoFilters.apply_filters(
            results, filter_high_score, filter_low_risk, filter_has_cornerstone, filter_valuation_ok
        )

        rows = self.fmt.ipo_summary_rows(filtered)
        if not rows:
            st.info("没有匹配的IPO")
            return

        df = pd.DataFrame(rows)
        df = df.sort_values("_score_num", ascending=False)
        df = df.drop(columns=["_score_num"])
        st.dataframe(df, use_container_width=True, hide_index=True, height=min(400, len(df) * 40 + 50))

        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">📋 选择查看详情</div>', unsafe_allow_html=True)

        if not rows:
            st.info("没有可查看详情的IPO")
        else:
            codes = [f"{r['股票代码']} - {r['公司名称']} (打新 {r['打新交易分']})" for r in rows]

            selected = st.radio(
                "选择IPO查看详情",
                ["（不选择）"] + codes,
                index=0,
                format_func=lambda x: x if x != "（不选择）" else "请选择一只IPO...",
                label_visibility="collapsed",
                horizontal=True
            )

            if selected and selected != "（不选择）":
                stock_code = selected.split(" - ", 1)[0].strip()
                for ipo in filtered:
                    if ipo.get("hk_code") == stock_code:
                        self.detail_view.render(ipo)
                        break

        st.markdown('</div>', unsafe_allow_html=True)

    def _render_hero(self) -> None:
        self.html.hero_section(
            "📊 港股 IPO 打新分析",
            "智能招股书解析 · 多维评分体系 · 一键生成报告"
        )

    def _render_update_buttons(self) -> None:
        cached = self.cache.load()
        session_results = st.session_state.get("results")
        if cached and (not session_results or
                       self.fmt.latest_record_time(cached) > self.fmt.latest_record_time(session_results)):
            st.session_state["results"] = cached

        cache_time_str = self._get_cache_time_str(cached)

        col1, col2, col3 = st.columns([2, 2, 3])
        with col1:
            if st.button("🔄 更新IPO（使用缓存）", type="primary", use_container_width=True):
                with st.spinner("正在获取和分析IPO数据..."):
                    self._execute_ipo_update(force_refresh=False)
        with col2:
            if st.button("⚡ 强制刷新（重新下载）", use_container_width=True):
                with st.spinner("正在重新下载和分析..."):
                    self._execute_ipo_update(force_refresh=True)
        with col3:
            st.markdown(
                f'<div style="text-align:right;color:#64748b;font-size:13px;padding-top:8px;">'
                f'最新缓存时间: {self.html.escape(cache_time_str)}</div>',
                unsafe_allow_html=True
            )

    def _get_cache_time_str(self, cached: list = None) -> str:
        if cached is None:
            cached = self.cache.load()
        if not cached:
            return "暂无缓存"
        cache_times = [item.get("_cached_at", "") for item in cached if item.get("_cached_at")]
        if not cache_times:
            return "暂无缓存"
        latest_cache = max(cache_times)
        try:
            dt_obj = type(latest_cache)(latest_cache) if not isinstance(latest_cache, str) else latest_cache
            from datetime import datetime
            dt_obj = datetime.fromisoformat(latest_cache)
            return dt_obj.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return latest_cache[:16] if len(latest_cache) >= 16 else latest_cache

    def _get_results(self) -> list:
        cached = self.cache.load()
        session_results = st.session_state.get("results")
        if cached and (not session_results or
                       self.fmt.latest_record_time(cached) > self.fmt.latest_record_time(session_results)):
            st.session_state["results"] = cached
        return st.session_state.get("results", cached or [])

    def _execute_ipo_update(self, force_refresh: bool = False) -> None:
        try:
            payload = analyze_live_ipos(output_dir=self.temp_dir, force_refresh=force_refresh, return_status=True)
            self._handle_analysis_result(payload, force_refresh)
        except Exception as e:
            err_lower = str(e).lower()
            if "connect" in err_lower or "timeout" in err_lower:
                st.error("⚠️ 网络连接失败，请检查网络后重试。如果问题持续，可能是接口暂不可用。")
            else:
                st.error(f"⚠️ 获取失败: {e}")

    def _handle_analysis_result(self, payload: Any, force_refresh: bool) -> None:
        if isinstance(payload, dict):
            status = payload.get("status", "ok")
            results = payload.get("results", [])
            message = payload.get("message") or ""
        else:
            results = payload or []
            status = "ok" if results else "no_data"
            message = ""

        if status == "error":
            st.error(f"⚠️ 获取失败: {message or '接口或网络异常，请稍后重试。'}")
            st.session_state["results"] = []
            return

        if results:
            self.cache.save(results)
            HistoryStore(self.temp_dir).archive_many(results, source='live')
            st.session_state["results"] = results
            success_msg = "✓ 强制刷新完成，获取到 {count} 个IPO" if force_refresh else "✓ 获取到 {count} 个IPO"
            st.success(success_msg.format(count=len(results)))
        else:
            st.warning(message or "当前没有正在招股的IPO")
            st.session_state["results"] = []

    def _render_empty_state(self) -> None:
        self.html.empty_state(
            "📭",
            "暂无正在招股的新股",
            "",
            extra="当前没有处于招股期的 IPO。<br>您可以点击上方「🔄 更新IPO」按钮重新获取最新数据。"
        )
        st.caption("💡 如需分析已下载的招股书PDF，请使用左侧边栏切换到「手动上传分析」。")
