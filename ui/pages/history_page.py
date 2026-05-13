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
        self.html.hero_section("📚 历史 IPO 分析", "历史归档 · 回溯重分析 · 配发结果与上市后表现跟踪")

        self._migrate_cache()

        with st.spinner("正在加载历史数据..."):
            all_history = self.history_store.load(include_live=True)

        if not all_history:
            self._render_empty_history()
            return

        self._render_stats(all_history)
        all_history = self._render_tracking_actions(all_history)

        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">🔎 筛选历史记录</div>', unsafe_allow_html=True)
        query, show_live, sort_by, tracking_status = IpoFilters.render_history_filters()
        st.markdown("</div>", unsafe_allow_html=True)

        visible = IpoFilters.apply_history_filters(all_history, query, show_live, self.fmt.is_live_or_future, tracking_status)
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
                f"(打新 {item.get('ipo_trade_score', item.get('trade_score', item.get('score', 0)))}/100 · 截止 {item.get('apply_end_date', '--')})"
                for item in visible
            ]
            selected = st.selectbox("选择历史IPO", options, label_visibility="collapsed")
            st.markdown("</div>", unsafe_allow_html=True)

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
                        item = self._render_selected_tools(item)
                        self.detail_view.render(item)
                        break

        st.caption(DISCLAIMER)

    def _migrate_cache(self) -> None:
        migrated_count = self.history_store.migrate_from_cache(self.cache.load())
        if migrated_count:
            st.success(f"已从当前缓存迁移 {migrated_count} 条记录到历史库")

    def _render_empty_history(self) -> None:
        self.html.empty_state(
            "🗂️", "暂无历史分析记录", "", extra=("点击首页「更新IPO」或在「手动上传分析」完成一次分析后，系统会自动归档到这里。")
        )
        st.caption(DISCLAIMER)

    def _render_stats(self, all_history: list) -> None:
        live_count = sum(1 for item in all_history if self.fmt.is_live_or_future(item))
        ended_count = sum(1 for item in all_history if self.fmt.is_ended(item))
        tracked_count = sum(1 for item in all_history if (item.get("post_listing") or {}).get("status") == "ok")
        latest_archive = max((item.get("_archived_at") or "" for item in all_history), default="")
        latest_archive_display = "--"
        if latest_archive:
            try:
                latest_archive_display = datetime.fromisoformat(latest_archive).strftime("%Y-%m-%d %H:%M")
            except Exception:
                latest_archive_display = latest_archive[:16]

        stats_cols = st.columns(5)
        stat_values = [
            ("历史股票数", len(all_history)),
            ("已结束", ended_count),
            ("招股中", live_count),
            ("已跟踪", tracked_count),
            ("最后归档", latest_archive_display),
        ]
        for col, (label, value) in zip(stats_cols, stat_values):
            with col:
                st.markdown(self.html.metric_card(label, str(value)), unsafe_allow_html=True)

    def _render_tracking_actions(self, all_history: list) -> list:
        ended_pending = [item for item in all_history if self.fmt.is_ended(item) and (item.get("post_listing") or {}).get("status") != "ok"]

        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">📡 上市后跟踪</div>', unsafe_allow_html=True)
        col1, col2 = st.columns([2, 1])
        with col1:
            st.caption(f"待跟踪/待补全已结束 IPO：{len(ended_pending)} 只。配发公告未发布时会标记为待公告。")
        with col2:
            force_refresh = st.checkbox("强制刷新跟踪", value=False, key="history_track_force_refresh")

        if st.button("📡 跟踪全部已结束待更新", width="stretch", disabled=not ended_pending and not force_refresh):
            with st.spinner("正在抓取配发公告与上市后表现..."):
                try:
                    from ipo_analyzer.post_listing import track_ended_ipos

                    summary = track_ended_ipos(
                        output_dir=self.temp_dir,
                        only_missing=not force_refresh,
                        force_refresh=force_refresh,
                    )
                    st.session_state["post_listing_summary"] = summary
                    st.success(
                        f"跟踪完成：处理 {summary.get('processed', 0)}，更新 {summary.get('updated', 0)}，失败 {summary.get('failed', 0)}"
                    )
                    all_history = self.history_store.load(include_live=True)
                except Exception as e:
                    st.error(f"跟踪失败: {e}")

        summary = st.session_state.get("post_listing_summary")
        if summary and summary.get("details"):
            with st.expander("查看最近一次跟踪明细", expanded=False):
                st.dataframe(pd.DataFrame(summary["details"]), width="stretch", hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)
        return all_history

    def _render_selected_tools(self, item: dict) -> dict:
        stock_code = item.get("hk_code", "")
        company_name = item.get("company_name")
        current_item = item

        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">🛠️ 历史操作</div>', unsafe_allow_html=True)
        action_col1, action_col2 = st.columns(2)
        with action_col1:
            can_track = self.fmt.is_ended(item)
            if st.button("📡 跟踪选中 IPO", key=f"track_{stock_code}", width="stretch", disabled=not can_track):
                with st.spinner("正在跟踪配发公告与上市后表现..."):
                    try:
                        from ipo_analyzer.post_listing import track_post_listing

                        post_listing = track_post_listing(
                            stock_code,
                            company_name=company_name,
                            base_record=item,
                            output_dir=self.temp_dir,
                            force_refresh=True,
                        )
                        current_item = self.history_store.update_post_listing(stock_code, post_listing) or item
                        if post_listing.get("status") == "error":
                            st.error(f"跟踪异常: {post_listing.get('error', '')}")
                        elif post_listing.get("status") == "pending_allotment":
                            st.info("配发结果公告暂未找到，已记录为待公告。")
                        else:
                            st.success("✅ 上市后跟踪完成！")
                    except Exception as e:
                        st.error(f"跟踪异常: {e}")
            if not can_track:
                st.caption("仍在招股或缺少截止日，暂不进行上市后跟踪。")
        with action_col2:
            allotment_pdf = st.file_uploader("上传配发公告PDF", type=["pdf"], key=f"allotment_pdf_{stock_code}")
            if allotment_pdf is not None and st.button("📋 解析配发公告", key=f"parse_allotment_{stock_code}", width="stretch"):
                with st.spinner("正在解析配发公告..."):
                    try:
                        from ipo_analyzer.post_listing import parse_allotment_pdf, track_post_listing

                        pdf_bytes = allotment_pdf.read()
                        parsed = parse_allotment_pdf(pdf_bytes=pdf_bytes)
                        if not parsed or not parsed.get("final_offer_price"):
                            st.warning("解析结果不完整，请确认上传的是配发结果公告PDF。")
                        post_listing = track_post_listing(
                            stock_code,
                            company_name=company_name,
                            base_record=item,
                            output_dir=self.temp_dir,
                            force_refresh=True,
                        )
                        if parsed:
                            post_listing.update(parsed)
                            post_listing["status"] = "ok"
                        current_item = self.history_store.update_post_listing(stock_code, post_listing) or item
                        st.success("✅ 配发公告解析完成！")
                    except Exception as e:
                        st.error(f"解析异常: {e}")
            st.caption("自动搜索未找到公告时，可手动上传配发结果PDF。")

        if st.button("🔍 搜索博主观点", key=f"blogger_{stock_code}", width="stretch"):
            with st.spinner("正在搜索博主观点..."):
                try:
                    from ipo_analyzer.blogger_monitor.service import BloggerMonitorService

                    service = BloggerMonitorService()
                    consensus = service.run_full_pipeline(stock_code, company_name=company_name)
                    if consensus is None:
                        st.warning("无法获取博主观点，请确认公司名称。")
                    elif consensus.total_posts == 0:
                        st.warning("未搜索到相关博主观点文章。")
                    else:
                        valid = consensus.positive_count + consensus.neutral_count + consensus.negative_count
                        st.success(
                            f"✅ 搜索完成：共 {consensus.total_posts} 篇，有效分析 {valid} 篇，共识分 {consensus.consensus_score:.1f}"
                        )
                except Exception as e:
                    st.error(f"搜索失败: {e}")
        st.markdown("</div>", unsafe_allow_html=True)

        with st.expander("🔁 重新分析参数", expanded=False):
            r_col1, r_col2 = st.columns(2)
            with r_col1:
                uploaded_file = st.file_uploader("上传招股书PDF（可选）", type=["pdf"], key=f"reanalyze_pdf_{stock_code}")
                force_refresh = st.checkbox("强制刷新招股书", value=False, key=f"reanalyze_force_{stock_code}")
            with r_col2:
                margin_total = st.number_input("孖展资金总计（亿）", value=None, format="%.2f", key=f"margin_{stock_code}")
                public_offer = st.number_input("公开集资额（亿）", value=None, format="%.2f", key=f"public_offer_{stock_code}")
                actual_over_sub_ratio = st.number_input("实际超购倍数", value=None, format="%.1f", key=f"actual_over_{stock_code}")
                forecast_over_sub_ratio = st.number_input("预测超购倍数", value=None, format="%.1f", key=f"forecast_over_{stock_code}")
                market_heat = st.selectbox("市场热度", ["", "极热", "热门", "温和", "冷清"], index=0, key=f"market_heat_{stock_code}")
                sector_heat_label = st.selectbox("实时热度", ["", "极热", "热门", "温和", "冷清"], index=0, key=f"sector_heat_{stock_code}")
                sector_flow_label = st.selectbox(
                    "板块资金流", ["", "放量", "活跃", "平稳", "偏弱"], index=0, key=f"sector_flow_{stock_code}"
                )
                sector_momentum_label = st.selectbox(
                    "板块动能", ["", "强势", "上行", "盘整", "偏弱"], index=0, key=f"sector_momentum_{stock_code}"
                )

            if st.button("🔁 开始重新分析", key=f"reanalyze_{stock_code}", width="stretch"):
                historical_market_data = self._build_historical_market_data(
                    margin_total,
                    public_offer,
                    actual_over_sub_ratio,
                    forecast_over_sub_ratio,
                    market_heat,
                    sector_heat_label,
                    sector_flow_label,
                    sector_momentum_label,
                )
                with st.spinner("正在重新分析..."):
                    try:
                        from ipo_analyzer.core import reanalyze_ipo

                        response = reanalyze_ipo(
                            stock_code=stock_code,
                            company_name=company_name,
                            uploaded_file=uploaded_file,
                            historical_market_data=historical_market_data,
                            force_refresh=force_refresh,
                            output_dir=self.temp_dir,
                        )
                        if response.get("status") == "error":
                            st.error(f"重新分析失败: {response.get('message', '')}")
                        else:
                            st.success("✅ 重新分析完成！")
                            result = response.get("result", {})
                            version_delta = result.get("version_delta")
                            if version_delta:
                                self._render_version_delta(version_delta)
                            if result:
                                current_item = self._merge_display_result(current_item, result)
                    except Exception as e:
                        st.error(f"重新分析异常: {e}")

        return current_item

    def _build_historical_market_data(
        self,
        margin_total,
        public_offer,
        actual_over,
        forecast_over,
        market_heat,
        sector_heat_label,
        sector_flow_label,
        sector_momentum_label,
    ):
        if not any(v is not None for v in [margin_total, public_offer, actual_over, forecast_over]) and not any(
            [market_heat, sector_heat_label, sector_flow_label, sector_momentum_label]
        ):
            return None
        data = {}
        if margin_total is not None:
            data["margin_total"] = margin_total
        if public_offer is not None:
            data["public_offer"] = public_offer
        if actual_over is not None:
            data["actual_over_sub_ratio"] = actual_over
        if forecast_over is not None:
            data["forecast_over_sub_ratio"] = forecast_over
        if market_heat:
            data["market_heat"] = market_heat
        live_market_heat = {}
        if sector_heat_label:
            live_market_heat["sector_heat_label"] = sector_heat_label
        if sector_flow_label:
            live_market_heat["sector_flow_label"] = sector_flow_label
        if sector_momentum_label:
            live_market_heat["sector_momentum_label"] = sector_momentum_label
        if live_market_heat:
            data["live_market_heat"] = live_market_heat
        return data

    def _merge_display_result(self, current_item: dict, result: dict) -> dict:
        merged = dict(current_item or {})
        for key, value in (result or {}).items():
            if key == "post_listing":
                continue
            if value is None or value == "":
                continue
            merged[key] = value
        if current_item.get("post_listing"):
            merged["post_listing"] = current_item["post_listing"]
        elif result.get("post_listing"):
            merged["post_listing"] = result["post_listing"]
        return merged

    def _render_version_delta(self, version_delta: dict) -> None:
        prev_score = version_delta.get("previous_score")
        curr_score = version_delta.get("current_score")
        score_delta = version_delta.get("score_delta")
        changed_reason = version_delta.get("changed_reason")

        if prev_score is None or curr_score is None:
            return

        delta_color = "#059669" if score_delta and score_delta > 0 else ("#DC2626" if score_delta and score_delta < 0 else "#64748b")
        delta_sign = "+" if score_delta and score_delta > 0 else ""

        dim_rows = ""
        for dim, delta in version_delta.get("dimension_deltas", {}).items():
            dim_label = {
                "ipo_trade_score": "打新",
                "long_term_score": "长期",
                "trade_score": "交易",
                "fundamental_score": "基本面",
                "valuation_score": "估值",
                "theme_score": "主题",
            }.get(dim, dim)
            dim_color = "#059669" if delta > 0 else ("#DC2626" if delta < 0 else "#64748b")
            dim_sign = "+" if delta > 0 else ""
            dim_rows += (
                f'<div style="display:inline-block;margin:2px 4px;padding:4px 10px;border-radius:8px;'
                f'background:rgba(30,64,175,0.04);border:1px solid rgba(148,163,184,0.12);font-size:12px;color:#475569;">'
                f'{dim_label}: <b style="color:{dim_color};">{dim_sign}{delta}</b></div>'
            )

        st.markdown(
            f"""
        <div class="glass-card glass-card-glow" style="padding:18px 22px;">
            <div class="section-title">📊 版本对比</div>
            <div style="display:flex;gap:20px;align-items:center;margin:12px 0;">
                <div style="text-align:center;flex:1;">
                    <div style="font-size:11px;color:#64748b;font-weight:600;letter-spacing:0.05em;">上次评分</div>
                    <div style="font-size:28px;font-weight:800;color:#475569;font-family:JetBrains Mono,monospace;">{prev_score}</div>
                </div>
                <div style="font-size:24px;color:#64748b;font-weight:300;">→</div>
                <div style="text-align:center;flex:1;">
                    <div style="font-size:11px;color:#64748b;font-weight:600;letter-spacing:0.05em;">本次评分</div>
                    <div style="font-size:28px;font-weight:800;color:#0F172A;font-family:JetBrains Mono,monospace;">{curr_score}</div>
                </div>
                <div style="text-align:center;flex:1;">
                    <div style="font-size:11px;color:#64748b;font-weight:600;letter-spacing:0.05em;">变化</div>
                    <div style="font-size:28px;font-weight:800;font-family:JetBrains Mono,monospace;color:{delta_color};text-shadow:0 0 12px {delta_color}40;">{delta_sign}{score_delta}</div>
                </div>
            </div>
            {f'<div style="font-size:13px;color:#475569;margin-bottom:8px;padding:8px 10px;background:rgba(30,64,175,0.04);border-radius:8px;">{changed_reason}</div>' if changed_reason else ""}
            <div style="display:flex;flex-wrap:wrap;gap:4px;">{dim_rows}</div>
        </div>
        """,
            unsafe_allow_html=True,
        )
