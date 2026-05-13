import streamlit as st

from ipo_analyzer.core import reanalyze_ipo
from ui.renderers.html_renderer import HtmlRenderer
from ui.renderers.data_formatter import DataFormatter
from ui.components.detail_view import DetailView
from ui.constants import DISCLAIMER


class ReanalyzePage:
    """历史IPO重新分析页面"""

    def __init__(self, temp_dir: str):
        self.temp_dir = temp_dir
        self.html = HtmlRenderer()
        self.fmt = DataFormatter()
        self.detail_view = DetailView(self.html, self.fmt)

    def render(self) -> None:
        self.html.hero_section(
            "🔁 历史IPO重新分析",
            "输入股票代码或上传招股书PDF，对已经结束招股的IPO进行回溯分析"
        )

        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">🔁 重新分析参数</div>', unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            stock_code = st.text_input("股票代码", "", placeholder="如 09995")
            company_name = st.text_input("公司名称", "", placeholder="如 荣昌生物")
            uploaded_file = st.file_uploader("上传招股书PDF（可选）", type=["pdf"], label_visibility="collapsed")
        with col2:
            force_refresh = st.checkbox("强制刷新缓存", value=False)
            st.markdown("<div style='margin-top:8px;'><b>历史热度数据（可选）</b></div>", unsafe_allow_html=True)
            margin_total = st.number_input("孖展资金总计（亿）", value=None, format="%.2f")
            public_offer = st.number_input("公开集资额（亿）", value=None, format="%.2f")
            actual_over_sub_ratio = st.number_input("实际超购倍数", value=None, format="%.1f")
            forecast_over_sub_ratio = st.number_input("预测超购倍数", value=None, format="%.1f")
            market_heat = st.selectbox("市场热度", ["", "极热", "热门", "温和", "冷清"], index=0)
            sector_heat_label = st.selectbox("实时热度", ["", "极热", "热门", "温和", "冷清"], index=0)
            sector_flow_label = st.selectbox("板块资金流", ["", "放量", "活跃", "平稳", "偏弱"], index=0)
            sector_momentum_label = st.selectbox("板块动能", ["", "强势", "上行", "盘整", "偏弱"], index=0)

        st.markdown('</div>', unsafe_allow_html=True)

        if st.button("🔍 开始重新分析", type="primary", width="stretch"):
            historical_market_data = None
            if any(v is not None for v in [margin_total, public_offer, actual_over_sub_ratio, forecast_over_sub_ratio]) or market_heat:
                historical_market_data = {}
                if margin_total is not None:
                    historical_market_data["margin_total"] = margin_total
                if public_offer is not None:
                    historical_market_data["public_offer"] = public_offer
                if actual_over_sub_ratio is not None:
                    historical_market_data["actual_over_sub_ratio"] = actual_over_sub_ratio
                if forecast_over_sub_ratio is not None:
                    historical_market_data["forecast_over_sub_ratio"] = forecast_over_sub_ratio
                if market_heat and market_heat.strip():
                    historical_market_data["market_heat"] = market_heat
                live_market_heat = {}
                if sector_heat_label.strip():
                    live_market_heat["sector_heat_label"] = sector_heat_label
                if sector_flow_label.strip():
                    live_market_heat["sector_flow_label"] = sector_flow_label
                if sector_momentum_label.strip():
                    live_market_heat["sector_momentum_label"] = sector_momentum_label
                if live_market_heat:
                    historical_market_data["live_market_heat"] = live_market_heat

            with st.spinner("正在重新分析..."):
                try:
                    response = reanalyze_ipo(
                        stock_code=stock_code or None,
                        company_name=company_name or None,
                        pdf_path=None,
                        uploaded_file=uploaded_file,
                        historical_market_data=historical_market_data,
                        force_refresh=force_refresh,
                        output_dir=self.temp_dir,
                    )
                    st.session_state["reanalyze_response"] = response
                    if response.get("status") == "error":
                        st.error(f"分析失败: {response.get('message', '')}")
                        if response.get("suggestion"):
                            st.info(f"建议: {response['suggestion']}")
                    elif response.get("status") == "warning":
                        st.warning(f"分析完成（有警告）: {response.get('message', '')}")
                    else:
                        st.success("✅ 重新分析完成！")
                        if response.get("message"):
                            st.info(response["message"])
                except Exception as e:
                    st.error(f"分析异常: {e}")

        response = st.session_state.get("reanalyze_response")
        if response and response.get("status") != "error":
            result = response.get("result", {})
            version_delta = result.get("version_delta")
            if version_delta:
                self._render_version_delta(version_delta)
            if result:
                self.detail_view.render(result)

        st.caption(DISCLAIMER)

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

        st.markdown(f"""
        <div class="glass-card glass-card-glow" style="padding:18px 22px;">
            <div class="section-title">📊 版本对比</div>
            <div style="display:flex;gap:20px;align-items:center;margin:12px 0;">
                <div style="text-align:center;flex:1;">
                    <div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:1px;">上次评分</div>
                    <div style="font-size:28px;font-weight:800;color:#475569;font-family:JetBrains Mono,monospace;">{prev_score}</div>
                </div>
                <div style="font-size:24px;color:#64748b;font-weight:300;">→</div>
                <div style="text-align:center;flex:1;">
                    <div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:1px;">本次评分</div>
                    <div style="font-size:28px;font-weight:800;color:#0F172A;font-family:JetBrains Mono,monospace;">{curr_score}</div>
                </div>
                <div style="text-align:center;flex:1;">
                    <div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:1px;">变化</div>
                    <div style="font-size:28px;font-weight:800;font-family:JetBrains Mono,monospace;color:{delta_color};text-shadow:0 0 12px {delta_color}40;">{delta_sign}{score_delta}</div>
                </div>
            </div>
            {f'<div style="font-size:13px;color:#475569;margin-bottom:8px;padding:8px 10px;background:rgba(30,64,175,0.04);border-radius:8px;">{changed_reason}</div>' if changed_reason else ''}
            <div style="display:flex;flex-wrap:wrap;gap:4px;">{dim_rows}</div>
        </div>
        """, unsafe_allow_html=True)
