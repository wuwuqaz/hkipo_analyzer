import os

import streamlit as st

from ipo_analyzer.core import generate_pdf_report, save_json_report
from ipo_analyzer.utils import _is_num
from ui.renderers.html_renderer import HtmlRenderer
from ui.renderers.data_formatter import DataFormatter
from ui.utils.shared_utils import SafeHtml, score_class, score_color_hex
from ui.utils.file_utils import read_file_bytes_and_remove, TEMP_DIR
from ui.constants import DISCLAIMER


class DetailView:
    """IPO 详情展示组件"""

    def __init__(self, html_renderer: HtmlRenderer = None, data_formatter: DataFormatter = None):
        self.html = html_renderer or HtmlRenderer()
        self.fmt = data_formatter or DataFormatter()

    @staticmethod
    def _format_public_offer_lots(pi: dict) -> str:
        """计算公开发售手数 = hk_offer_shares / lot_size"""
        lot_size = pi.get('lot_size')
        hk_offer = pi.get('hk_offer_shares')
        if _is_num(lot_size) and _is_num(hk_offer) and lot_size > 0:
            lots = int(hk_offer / lot_size)
            text = f"{lots:,}"
            clawback_pct = pi.get('public_offer_clawback_max_pct') if pi.get('is_chapter_18c') else None
            global_offer = pi.get('global_offer_shares')
            if _is_num(clawback_pct):
                text += f"（可回拨至{clawback_pct:g}%"
                if _is_num(global_offer):
                    max_lots = int(global_offer * clawback_pct / 100 / lot_size)
                    text += f"：{max_lots:,}手"
                text += "）"
            return text
        return "--"

    def render(self, ipo: dict) -> None:
        pi = ipo.get("prospectus_info", {}) or {}
        has_prospectus = bool(pi) and ipo.get("parse_success", False)
        key_financials_empty = all([
            pi.get("revenue") is None,
            pi.get("net_profit") is None,
            pi.get("gross_margin") is None,
            pi.get("market_cap_hkd_million") is None,
            pi.get("offer_price") is None,
        ])

        self._render_header(ipo)
        self._render_prospectus_warning(has_prospectus, key_financials_empty)
        self._render_metrics(ipo)
        self._render_post_listing(ipo)
        self._render_score_waterfall(ipo)
        self._render_signal_breakdown(ipo)
        self._render_score_reasons(ipo)
        self._render_diagnosis(ipo)
        self._render_warnings(ipo, key_financials_empty)
        self._render_info_and_financials(ipo)
        self._render_cornerstone(ipo)
        self._render_peer_comparison(ipo)
        self._render_downloads(ipo)
        st.caption(DISCLAIMER)

    def _render_header(self, ipo: dict) -> None:
        pi = ipo.get("prospectus_info", {}) or {}
        val = pi.get("valuation", {}) or {}
        company_name = ipo.get('company_name', '--')
        stock_code = ipo.get('hk_code', '--')
        score = ipo.get('ipo_trade_score', ipo.get('trade_score', ipo.get('score', 0)))
        long_score = ipo.get('long_term_score', ipo.get('fundamental_score', 0))
        recommendation = ipo.get('subscription_recommendation') or '--'

        st.markdown(f"""
        <div class="glass-card glass-card-glow" style="padding:24px 28px;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <div>
                    <div style="font-size:26px;font-weight:700;color:#0F172A;font-family:var(--font-sans);letter-spacing:0.01em;">{self.html.escape(company_name)}</div>
                    <div style="font-size:15px;color:#475569;margin-top:4px;font-weight:500;">
                        {self.html.escape(stock_code)} ·
                        {self.html.escape(pi.get('sector', '--'))} ·
                        {self.html.escape(val.get('valuation_label', '--'))}
                    </div>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:44px;font-weight:800;font-family:var(--font-mono);color:{score_color_hex(score)};">
                        {self.html.escape(str(score))}
                    </div>
                    <div style="font-size:13px;color:#64748B;letter-spacing:0.05em;font-weight:600;">打新交易分</div>
                    <div style="font-size:13px;color:#64748B;margin-top:4px;font-weight:500;">长期 {self.html.escape(str(long_score))}/100</div>
                </div>
            </div>
            <div style="font-size:15px;color:#475569;margin-top:12px;font-weight:500;line-height:1.5;">{self.html.escape(recommendation)}</div>
            {self.html.progress_bar(score, score_color_hex(score))}
        </div>
        """, unsafe_allow_html=True)

    def _render_prospectus_warning(self, has_prospectus: bool, key_financials_empty: bool) -> None:
        if not has_prospectus or key_financials_empty:
            st.warning("⚠️ 未成功解析招股书，当前评分仅基于孖展/默认值，不能用于判断基本面。")

    def _render_metrics(self, ipo: dict) -> None:
        score = ipo.get('score', 0)
        trade_score = ipo.get('ipo_trade_score', ipo.get('trade_score', ipo.get('subscription_score', 0)))
        long_score = ipo.get('long_term_score', ipo.get('fundamental_score', 0))

        cols = st.columns(5)
        metrics = [
            ("打新交易分", f"{trade_score}/100", ipo.get('ipo_trade_label', ''), score_class(trade_score)),
            ("长期投资分", f"{long_score}/100", ipo.get('long_term_label', ''), score_class(long_score)),
            ("估值压力", ipo.get('valuation_pressure_label', '--'), "", score_class(ipo.get('valuation_score', 0))),
            ("旧综合分", f"{score}/100", "兼容/调试", score_class(score)),
            ("重大红旗扣分", f"-{ipo.get('risk_penalty', 0)}", "", "score-poor" if ipo.get('risk_penalty', 0) > 5 else ""),
        ]
        self.html.metric_card_st(cols, metrics)



    def _render_post_listing(self, ipo: dict) -> None:
        post = ipo.get("post_listing") or {}
        if not post:
            return

        status = post.get("status", "")
        status_label = {
            "ok": "已完成",
            "pending_allotment": "待公告",
            "partial": "部分完成",
            "error": "异常",
        }.get(status, status or "--")

        allotment_kpis = [
            ("跟踪状态", status_label),
            ("最终发售价", self.fmt.format_number(post.get("final_offer_price"), " HKD")),
            ("上市日期", post.get("listing_date") or "--"),
            ("一手中签率", self.fmt.format_percentage(post.get("one_lot_success_rate_pct"))),
            ("整体中签率", self.fmt.format_percentage(post.get("overall_success_rate_pct"))),
            ("有效申请", self._format_int(post.get("valid_applications"))),
            ("成功申请", self._format_int(post.get("successful_applications"))),
            ("公配倍数", self.fmt.format_number(post.get("public_subscription_level"), "x")),
            ("国配倍数", self.fmt.format_number(post.get("international_subscription_level"), "x")),
            ("承配人数", self._format_int(post.get("placees_count"))),
        ]

        price_kpis = [
            ("暗盘", self._format_price_perf(post.get("grey_market"))),
            ("首日", self._format_price_perf(post.get("first_day"))),
            ("至今", self._format_price_perf(post.get("latest"))),
        ]
        allocation_review = self._render_allocation_review(post)

        pdf = post.get("allotment_pdf") or {}
        source_url = pdf.get("source_url") or post.get("source_url")
        pdf_link = ""
        if source_url:
            pdf_link = (
                f'<div style="font-size:12px;color:#475569;margin-top:8px;">'
                f'配发公告：<a href="{self.html.escape(source_url)}" target="_blank">HKEX PDF</a>'
                f'</div>'
            )
        message = post.get("message") or post.get("error")
        message_html = ""
        if message:
            message_html = (
                f'<div style="font-size:12px;color:#D97706;margin-top:8px;">'
                f'{self.html.escape(message)}</div>'
            )

        st.markdown(
            '<div class="section-card">\n'
            '<div class="section-title">📌 上市后跟踪</div>\n'
            f'{self.html.kpi_row(allotment_kpis)}\n'
            '<div style="border-top:1px solid rgba(148,163,184,0.15);margin:12px 0;"></div>\n'
            f'{self.html.kpi_row(price_kpis)}\n'
            f'{allocation_review}\n'
            f'{pdf_link}\n'
            f'{message_html}\n'
            '</div>',
            unsafe_allow_html=True,
        )

    def _format_int(self, value) -> str:
        if value is None:
            return "--"
        try:
            return f"{int(value):,}"
        except Exception:
            return str(value)

    def _format_price_perf(self, payload) -> SafeHtml:
        payload = payload or {}
        if payload.get("status") == "missing":
            return SafeHtml('<span style="color:#475569;">缺失</span>')
        price = payload.get("price")
        change = payload.get("change_pct")
        date = payload.get("date")
        if price is None and change is None:
            return SafeHtml('<span style="color:#475569;">--</span>')
        change_html = ""
        if _is_num(change):
            color = "#DC2626" if change > 0 else ("#059669" if change < 0 else "#475569")
            sign = "+" if change > 0 else ""
            change_html = f' <span style="color:{color};font-size:12px;">({sign}{change:.1f}%)</span>'
        date_html = f'<div style="font-size:11px;color:#475569;">{self.html.escape(date)}</div>' if date else ""
        price_html = self.html.escape(self.fmt.format_number(price, " HKD")) if price is not None else "--"
        return SafeHtml(f'{price_html}{change_html}{date_html}')

    def _render_allocation_review(self, post: dict) -> str:
        pools = post.get("allocation_pools") or {}
        if not pools:
            return ""

        pool_labels = {"A": "甲组", "B": "乙组"}
        pool_html = ""
        trend_rows = []
        for key in ("A", "B"):
            pool = pools.get(key) or {}
            if not pool.get("rows"):
                continue
            pool_html += self._render_allocation_pool(pool, pool_labels.get(key, key))
            for row in pool.get("rows") or []:
                trend_row = dict(row)
                trend_row["pool"] = key
                trend_rows.append(trend_row)

        if not pool_html:
            return ""

        trend_html = self._render_allocation_trend(trend_rows)
        return SafeHtml(
            '<div style="border-top:1px solid rgba(148,163,184,0.1);margin:14px 0 0;padding-top:14px;">'
            '<div class="section-title">中签复盘</div>'
            '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px;">'
            f'{pool_html}'
            '</div>'
            f'{trend_html}'
            '</div>'
        )

    def _render_allocation_pool(self, pool: dict, label: str) -> str:
        rows_html = ""
        for row in pool.get("rows") or []:
            rows_html += (
                "<tr>"
                f"<td>{self._format_int(row.get('applied_shares'))}</td>"
                f"<td>{self._format_int(row.get('valid_applications'))}</td>"
                f"<td>{self._format_int(row.get('successful_applications'))}</td>"
                f"<td>{self._format_pct(row.get('allotment_pct'))}</td>"
                f"<td><b>{self._format_pct(row.get('success_rate_pct'))}</b></td>"
                "</tr>"
            )

        summary = (
            f"有效申请人数：{self._format_int(pool.get('valid_applications'))}"
            f" | 中签总数：{self._format_int(pool.get('successful_applications'))}"
            f" | 中签率：{self._format_pct(pool.get('success_rate_pct'))}"
        )
        return (
            '<div style="border:1px solid rgba(148,163,184,0.18);border-radius:12px;overflow:hidden;'
            'background:rgba(241,245,249,0.6);">'
            '<div style="display:flex;align-items:center;gap:10px;padding:10px 12px;'
            'border-bottom:1px solid rgba(148,163,184,0.14);">'
            '<span style="display:inline-flex;align-items:center;justify-content:center;min-width:44px;'
            'padding:5px 10px;border-radius:8px;background:#F1F5F9;color:#475569;font-weight:800;">'
            f'{self.html.escape(label)}</span>'
            f'<span style="font-size:12px;color:#475569;">{self.html.escape(summary)}</span>'
            '</div>'
            '<div style="max-height:360px;overflow:auto;">'
            '<table style="width:100%;border-collapse:collapse;font-size:12px;color:#475569;">'
            '<thead style="position:sticky;top:0;background:#F1F5F9;color:#64748B;">'
            '<tr>'
            '<th style="padding:8px;text-align:right;">申请股数</th>'
            '<th style="padding:8px;text-align:right;">有效申请人</th>'
            '<th style="padding:8px;text-align:right;">中签人</th>'
            '<th style="padding:8px;text-align:right;">一手中签率</th>'
            '<th style="padding:8px;text-align:right;">中签率</th>'
            '</tr>'
            '</thead>'
            f'<tbody>{rows_html}</tbody>'
            '</table>'
            '</div>'
            '</div>'
        )

    def _render_allocation_trend(self, rows: list[dict]) -> str:
        trend_rows = [
            row for row in rows
            if _is_num(row.get("success_rate_pct")) and _is_num(row.get("applied_shares"))
        ]
        if len(trend_rows) < 2:
            return ""

        width = 920
        height = 260
        left = 48
        right = 22
        top = 32
        bottom = 42
        plot_w = width - left - right
        plot_h = height - top - bottom
        max_rate = max(row["success_rate_pct"] for row in trend_rows)
        y_max = max(100, ((int(max_rate) // 10) + 1) * 10)

        points = []
        points_a = []
        points_b = []
        labels = []
        for idx, row in enumerate(trend_rows):
            x = left + (plot_w * idx / max(1, len(trend_rows) - 1))
            y = top + plot_h - (plot_h * row["success_rate_pct"] / y_max)
            pt = f"{x:.1f},{y:.1f}"
            points.append(pt)
            if row.get("pool") == "B":
                points_b.append(pt)
            else:
                points_a.append(pt)
            if idx == 0 or idx == len(trend_rows) - 1 or idx % 3 == 0:
                labels.append(
                    f'<text x="{x:.1f}" y="{height - 12}" text-anchor="middle" '
                    f'font-size="9" fill="#64748B">{self._compact_shares(row.get("applied_shares"))}</text>'
                )

        grid = ""
        for pct in range(0, int(y_max) + 1, 20):
            y = top + plot_h - (plot_h * pct / y_max)
            grid += (
                f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" '
                'stroke="rgba(148,163,184,0.18)" stroke-dasharray="4 4"/>'
                f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" font-size="10" fill="#64748B">{pct}%</text>'
            )

        split_idx = next((idx for idx, row in enumerate(trend_rows) if row.get("pool") == "B"), None)
        split_html = ""
        if split_idx:
            x = left + (plot_w * split_idx / max(1, len(trend_rows) - 1))
            split_html = (
                f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_h}" '
                'stroke="rgba(148,163,184,0.35)" stroke-dasharray="5 5"/>'
                f'<rect x="{x - 58:.1f}" y="{top + 6}" width="116" height="22" rx="6" fill="#F1F5F9" '
                'stroke="rgba(148,163,184,0.35)"/>'
                f'<text x="{x:.1f}" y="{top + 21}" text-anchor="middle" font-size="11" fill="#475569">甲组结束 / 乙组开始</text>'
            )

        color_a = "#3B82F6"
        color_b = "#D97706"
        dots = ""
        for point, row in zip(points, trend_rows):
            x, y = point.split(",")
            fill = color_b if row.get("pool") == "B" else color_a
            dots += (
                f'<circle cx="{x}" cy="{y}" r="3.2" fill="{fill}" stroke="#F1F5F9" stroke-width="1.5">'
                f'<title>{self._format_int(row.get("applied_shares"))}股: {self._format_pct(row.get("success_rate_pct"))}</title>'
                '</circle>'
            )

        polylines = ""
        if len(points_a) >= 2:
            polylines += f'<polyline points="{" ".join(points_a)}" fill="none" stroke="{color_a}" stroke-width="2.4"/>'
        if len(points_b) >= 2:
            polylines += f'<polyline points="{" ".join(points_b)}" fill="none" stroke="{color_b}" stroke-width="2.4"/>'
        if len(points_a) >= 1 and len(points_b) >= 1:
            # 连接甲组最后一点到乙组第一点，颜色与甲组一致
            bridge = [points_a[-1], points_b[0]]
            polylines += f'<polyline points="{" ".join(bridge)}" fill="none" stroke="{color_a}" stroke-width="2.4"/>'

        legend = (
            f'<g transform="translate({width - right - 120}, 10)">'
            f'<circle cx="0" cy="0" r="3" fill="{color_a}"/>'
            f'<text x="8" y="3" font-size="10" fill="#64748B">甲组</text>'
            f'<circle cx="50" cy="0" r="3" fill="{color_b}"/>'
            f'<text x="58" y="3" font-size="10" fill="#64748B">乙组</text>'
            '</g>'
        )

        return (
            '<div style="margin-top:14px;border:1px solid rgba(148,163,184,0.18);border-radius:12px;'
            'padding:12px;background:rgba(241,245,249,0.5);overflow-x:auto;">'
            '<div style="font-size:13px;font-weight:800;color:#0F172A;text-align:center;margin-bottom:6px;">'
            '甲乙组中签率趋势</div>'
            f'<svg viewBox="0 0 {width} {height}" width="100%" style="min-width:720px;display:block;">'
            f'{legend}'
            f'{grid}'
            f'{split_html}'
            f'{polylines}'
            f'{dots}'
            f'{"".join(labels)}'
            f'<text x="{width / 2:.1f}" y="{height - 2}" text-anchor="middle" font-size="11" fill="#64748B">申请股数</text>'
            '</svg>'
            '</div>'
        )

    def _format_pct(self, value) -> str:
        if value is None:
            return "--"
        try:
            return f"{float(value):.2f}%"
        except Exception:
            return str(value)

    def _compact_shares(self, value) -> str:
        try:
            num = int(value)
        except Exception:
            return "--"
        if num >= 1_000_000:
            return f"{num / 1_000_000:.1f}M"
        if num >= 1000:
            return f"{num // 1000}K"
        return str(num)


    def _render_score_waterfall(self, ipo: dict) -> None:
        """展示五维评分的 waterfall 拆解：各维度分数 × 权重 = 贡献值。"""
        wp = ipo.get('weight_profile', {}) or {}
        weights = wp.get('weights', {})
        if not weights:
            return

        dimensions = [
            ("交易面", ipo.get('trade_score', 0), weights.get('trade', 0)),
            ("基本面", ipo.get('fundamental_score', 0), weights.get('fundamental', 0)),
            ("估值面", ipo.get('valuation_score', 0), weights.get('valuation', 0)),
            ("主题面", ipo.get('theme_score', 0), weights.get('theme', 0)),
            ("数据质量", ipo.get('data_quality_score', 0), weights.get('data_quality', 0)),
        ]

        rows_html = ""
        raw_total = 0
        for title, score, weight in dimensions:
            contribution = round(score * weight)
            raw_total += contribution
            rows_html += (
                '<div style="display:flex;justify-content:space-between;'
                'align-items:center;padding:7px 0;border-bottom:1px solid rgba(148,163,184,0.08);">'
                '<div style="display:flex;align-items:center;gap:8px;flex:1;">'
                '<div style="width:4px;height:24px;border-radius:2px;background:rgba(6,182,212,0.3);"></div>'
                '<div><div style="font-size:14px;color:#0F172A;">' + str(title) +
                ' <span style="color:#64748B;">(' + str(round(weight * 100)) + '%)</span></div>'
                '<div style="font-size:12px;color:#475569;margin-top:2px;">贡献 ' + str(contribution) + ' 分</div></div></div>'
                '<div style="font-size:13px;font-weight:600;color:#0F172A;font-family:JetBrains Mono,monospace;">'
                + str(score) + ' &times; ' + str(round(weight * 100)) + '% = ' + str(contribution) + '</div>'
                '</div>'
            )

        penalty = ipo.get('risk_penalty', 0)
        penalty_html = ""
        if penalty > 0:
            penalty_html = (
                '<div style="display:flex;justify-content:space-between;'
                'align-items:center;padding:7px 0;border-bottom:1px solid rgba(148,163,184,0.08);">'
                '<div style="font-size:13px;color:#DC2626;">风险惩罚</div>'
                '<div style="font-size:13px;font-weight:600;color:#DC2626;">&minus;' + str(penalty) + '</div>'
                '</div>'
            )

        final = ipo.get('score', 0)
        cap_reason = ipo.get('debug_info', {}).get('cap_reason', '')
        cap_html = ('<div style="font-size:11px;color:#475569;margin-top:4px;">'
                    + self.html.escape(str(cap_reason)) + '</div>') if cap_reason else ""

        html = (
            '<div class="section-card">'
            '<div class="section-title">⚖️ 旧综合分拆解 (Waterfall)</div>'
            + rows_html
            + penalty_html
            + '<div style="display:flex;justify-content:space-between;'
               'align-items:center;padding:8px 0;margin-top:4px;">'
               '<div style="font-size:14px;font-weight:700;color:#64748B;">加权原始分</div>'
               '<div style="font-size:14px;font-weight:700;color:#64748B;font-family:JetBrains Mono,monospace;">' + str(raw_total) + '</div>'
               '</div>'
            + '<div style="display:flex;justify-content:space-between;'
               'align-items:center;padding:8px 0;border-top:2px solid rgba(148,163,184,0.2);">'
               '<div style="font-size:16px;font-weight:800;color:#0F172A;">旧综合分</div>'
               '<div style="font-size:16px;font-weight:800;font-family:JetBrains Mono,monospace;color:'
               + score_color_hex(final) + ';">' + str(final) + '/100</div>'
               '</div>'
            + cap_html
            + '</div>'
        )

        try:
            st.html(html)
        except AttributeError:
            st.markdown(html, unsafe_allow_html=True)

    def _render_score_reasons(self, ipo: dict) -> None:
        reasons = []
        if ipo.get("subscription_recommendation"):
            reasons.append(f"申购建议: {ipo.get('subscription_recommendation')}")
        reasons.extend(ipo.get("recommendation_reasons", []) or [])
        reasons.extend(ipo.get("score_reasons", []) or [])
        chips_html = self.html.reason_chips(reasons) if reasons else ""
        st.markdown(
            '<div class="section-card">\n'
            '<div class="section-title">📝 评分理由</div>\n'
            f'{chips_html}\n'
            '</div>',
            unsafe_allow_html=True,
        )

    def _render_signal_breakdown(self, ipo: dict) -> None:
        sb = ipo.get("signal_breakdown") or {}
        if not sb:
            # 尝试从旧结构回退
            pi = ipo.get("prospectus_info", {}) or {}
            af = pi.get("advanced_framework") or {}
            sb = af.get("signal_breakdown", {})
        if not sb:
            return

        items = [
            ("real_money", "资金热度", "🔥"),
            ("float_structure", "筹码弹性", "📊"),
            ("cornerstone_quality", "基石质量", "🏛️"),
            ("valuation_reading", "估值解释", "📈"),
            ("theme_bonus", "主题催化", "🚀"),
            ("liquidity_bonus", "港股通路径", "🌐"),
            ("data_confidence", "数据置信度", "🛡️"),
        ]

        rows_html = ""
        for key, title, emoji in items:
            item = sb.get(key, {})
            strength = item.get("strength", "缺失")
            detail = item.get("detail", "")
            color = "#475569"
            if strength in ("强", "高"):
                color = "#059669"
            elif strength == "中":
                color = "#D97706"
            elif strength in ("弱", "低"):
                color = "#DC2626"
            signal_dot = {'强': '#059669', '高': '#059669', '中': '#D97706', '弱': '#DC2626', '低': '#DC2626'}.get(strength, '#475569')
            rows_html += (
                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                f'padding:8px 0;border-bottom:1px solid rgba(148,163,184,0.08);">'
                f'<div style="display:flex;align-items:center;gap:8px;">'
                f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{signal_dot};'
                f'box-shadow:0 0 6px {signal_dot}60;"></span>'
                f'<div><div style="font-size:14px;color:#0F172A;">{emoji} {title}</div>'
                f'<div style="font-size:13px;color:#475569;max-width:320px;overflow:hidden;text-overflow:ellipsis;">'
                f'{self.html.escape(detail)}</div></div></div>'
                f'<div style="font-size:14px;font-weight:700;color:{color};">{strength}</div>'
                f'</div>'
            )

        st.markdown(
            '<div class="section-card">\n'
            '<div class="section-title">📡 交易信号拆解</div>\n'
            f'{rows_html}\n'
            '</div>',
            unsafe_allow_html=True,
        )

    def _render_diagnosis(self, ipo: dict) -> None:
        identity_conf = ipo.get("pdf_identity_confidence", "low")
        if identity_conf == "high":
            identity_html = self.html.tag("✅ 高", "green")
        elif identity_conf == "medium":
            identity_html = self.html.tag("⚠️ 中", "yellow")
        else:
            identity_html = self.html.tag("❌ 低", "red")

        fin_conf = ipo.get("financial_extract_confidence", "--")
        if fin_conf == "consolidated_statement":
            fin_conf_html = self.html.tag("🟢 财务主表已识别", "green")
        else:
            fin_conf_html = self.html.tag(str(fin_conf), "gray")

        diag_items = [
            ("PDF下载", "✅ 成功" if ipo.get("pdf_downloaded") else "❌ 未下载"),
            ("PDF大小", f"{ipo.get('pdf_file_size_mb', '--')} MB"),
            ("文本长度", f"{ipo.get('prospectus_text_length', 0):,} 字符"),
            ("身份确认", identity_html),
            ("股票代码", "✅ 匹配" if ipo.get("pdf_stock_code_match") else "❌ 未匹配"),
            ("财务置信度", fin_conf_html),
        ]
        extracted_cn = ipo.get("extracted_company_name")
        if extracted_cn:
            diag_items.append(("PDF公司名", extracted_cn))
        extracted_en = ipo.get("extracted_english_name")
        if extracted_en and len(extracted_en) < 80:
            diag_items.append(("PDF英文名", extracted_en))

        st.markdown(
            '<div class="section-card">\n'
            '<div class="section-title">🔍 解析诊断</div>\n'
            f'{self.html.diag_grid(diag_items)}\n'
            '</div>',
            unsafe_allow_html=True,
        )

    def _render_warnings(self, ipo: dict, key_financials_empty: bool) -> None:
        validation_warning = ipo.get("pdf_validation_warning")
        if validation_warning:
            st.warning(f"⚠️ {validation_warning}")
        parse_error = ipo.get("parse_error")
        if parse_error:
            st.error(f"❌ 解析错误: {parse_error}")
        if key_financials_empty:
            st.error("🔴 关键财务数据全空，招股书可能未成功解析。可能原因：PDF为扫描件（需OCR识别）、招股书格式不标准、或提取规则未覆盖当前招股书内容。可尝试重新上传PDF。")

    def _render_info_and_financials(self, ipo: dict) -> None:
        pi = ipo.get("prospectus_info", {}) or {}
        val = pi.get("valuation", {}) or {}
        rnd = pi.get("rnd_pipeline", {}) or {}
        geo = pi.get("geographic", {}) or {}
        biz = pi.get("business_breakdown", {}) or {}
        cs = pi.get("customer_supplier", {}) or {}
        cf = pi.get("cashflow", {}) or {}
        cap = pi.get("capacity", {}) or {}
        risk = pi.get("risk_factors", {}) or {}
        pc = pi.get("peer_comparison", {}) or {}

        info_kpis = [
            ("招股期", f"{ipo.get('apply_start_date', '--')} ~ {ipo.get('apply_end_date', '--')}"),
            ("估值口径", "最终价" if pi.get('valuation_price_basis') == 'final_price' else "招股价"),
            ("发行价", self.fmt.format_number(pi.get('offer_price'), ' HKD')),
            ("原招股价", self.fmt.format_number(pi.get('indicative_offer_price'), ' HKD') if pi.get('indicative_offer_price') else "--"),
            ("每手股数", str(pi.get('lot_size', '--'))),
            ("公开发售手数", self._format_public_offer_lots(pi)),
            ("入场费", self.fmt.format_number(pi.get('entry_fee_hkd'), ' HKD')),
            ("市值", self.fmt.format_number(pi.get('market_cap_hkd_million'), ' M HKD')),
            ("发行比例", self.fmt.format_percentage(pi.get('issuance_ratio_pct'))),
            ("孖展资金", self.fmt.format_number(ipo.get('margin_total'), ' 亿')),
            ("超购倍数", self.fmt.format_number(ipo.get('over_sub_ratio'), 'x')),
            ("市场热度", ipo.get('market_heat', '--')),
            ("行业", pi.get('sector', '--')),
        ]

        # 亏损/未盈利公司 PE 显示 "PE不适用"
        pe_display = self.fmt.format_number(val.get('pe_ratio'), 'x')
        if val.get('valuation_profitability_type') == 'loss_making':
            pe_display = "PE不适用"
        elif val.get('pe_ratio') is None and val.get('valuation_framework_type') == '18A_biotech':
            pe_display = "PE不适用"

        fin_kpis = [
            ("收入", self.fmt.format_revenue_with_yoy(pi)),
            ("净利润", self.fmt.format_net_profit_with_yoy(pi)),
            ("毛利率", self.fmt.format_gross_margin_with_yoy(pi)),
            ("PE", pe_display),
            ("PS", self.fmt.format_number(val.get('ps_ratio'), 'x')),
            ("最终价PS", self.fmt.format_number(val.get('final_ps_ratio') or pi.get('final_ps_ratio'), 'x')),
            ("PB", self.fmt.format_number(val.get('pb_ratio'), 'x')),
            ("研发费率", self._render_rd_ratio(rnd)),
            ("海外占比", self._render_overseas_pct(geo)),
            ("增长来源", biz.get('growth_source', '--')),
            ("海外扩张", geo.get('overseas_growth_label', '--')),
        ]

        # 估值框架、市值/R&D、现金runway、临床阶段
        detail_kpis = [
            ("客户集中度", cs.get('concentration_risk_label', '--')),
            ("客户质量", f"{cs.get('customer_quality_label', '--')} ({cs.get('customer_quality_score', 0)}/100)"),
            ("客户留存率", self.fmt.format_percentage(cs.get('customer_retention_rate_pct'))),
            ("NDR", self.fmt.format_percentage(cs.get('net_dollar_retention_rate_pct'))),
            ("Top5客户占比", self.fmt.format_percentage(cs.get('top5_customer_revenue_pct'))),
            ("最大客户占比", self.fmt.format_percentage(cs.get('largest_customer_revenue_pct'))),
            ("现金流质量", cf.get('cash_quality_label', '--')),
            ("OCF/收入", self.fmt.format_percentage(cf.get('ocf_to_revenue') * 100) if _is_num(cf.get('ocf_to_revenue')) else "--"),
            ("现金余额", self.fmt.format_number(cf.get('cash_and_cash_equivalents'), ' M')),
            ("募资后runway", f"{cf.get('post_ipo_cash_runway_years', '--')}年" if cf.get('post_ipo_cash_runway_years') is not None else "--"),
            ("技术壁垒", f"{rnd.get('pipeline_quality_label', '--')} ({rnd.get('technology_moat_score', 0)}/10)"),
            ("产能利用率", self.fmt.format_percentage(cap.get('utilization_rate'))),
            ("招股书风险因子", str(risk.get('total_penalty', 0))),
            ("估值框架", self._render_valuation_framework_label(ipo, val)),
            ("市值/R&D", self.fmt.format_number(val.get('market_cap_to_rd_ratio'), 'x')),
            ("现金runway", f"{val.get('cash_runway_years', '--')}年" if val.get('cash_runway_years') is not None else '--'),
            ("临床阶段", val.get('latest_clinical_stage') or '--'),
        ]

        biz_seg_html = self._render_biz_segments(biz)
        risk_expanded_html = self._render_risk_details(risk)

        st.markdown(
            '<div class="section-card">\n'
            '<div class="section-title">📈 基本信息</div>\n'
            f'{self.html.kpi_row(info_kpis)}\n'
            '<div style="border-top:1px solid rgba(148,163,184,0.15);margin:14px 0;"></div>\n'
            '<div class="section-title">💰 核心财务</div>\n'
            f'{self.html.kpi_row(fin_kpis)}\n'
            '<div style="border-top:1px solid rgba(148,163,184,0.15);margin:14px 0;"></div>\n'
            '<div class="section-title">🔬 深度分析</div>\n'
            f'{self.html.kpi_row(detail_kpis)}\n'
            f'{biz_seg_html}\n'
            f'{risk_expanded_html}\n'
            '</div>',
            unsafe_allow_html=True,
        )

        if biz.get("business_breakdown_warning"):
            st.warning(f"⚠️ {biz['business_breakdown_warning']}")
        if biz.get("vbp_risk_score", 0) > 0:
            st.warning(f"⚠️ 集采/VBP风险: {biz.get('vbp_summary', '')}")
        if val.get("revenue_too_small_for_ps"):
            st.warning("⚠️ 收入基数极小，PS严重失真，仅作参考，需结合管线/技术阶段/平台价值判断")
        if pc.get("peer_sample_warning"):
            st.info(f"ℹ️ {pc['peer_sample_warning']}")

    def _render_valuation_framework_label(self, ipo: dict, val: dict) -> str:
        """未盈利 biotech 显示更友好的估值框架标签"""
        # 优先使用 signal_breakdown 中的估值解释
        sb = ipo.get('signal_breakdown') or {}
        if not sb:
            pi = ipo.get('prospectus_info', {}) or {}
            af = pi.get('advanced_framework') or {}
            sb = af.get('signal_breakdown', {})
        val_reading = sb.get('valuation_reading', {})
        if val_reading.get('label'):
            return val_reading['label']
        # 回退到 valuation 标签
        vtype = val.get('valuation_framework_type')
        if vtype == '18A_biotech':
            return val.get('valuation_label') or '18A biotech'
        return vtype or val.get('valuation_label') or '--'

    def _render_rd_ratio(self, rnd: dict) -> str:
        rd_ratio = rnd.get('rd_expense_ratio')
        if rd_ratio is not None and rd_ratio > 100:
            if rnd.get('rd_ratio_biotech'):
                return f"{rd_ratio:.1f}%"
            return "单位异常"
        elif rd_ratio is not None:
            return f"{rd_ratio:.1f}%"
        if rnd.get('rd_ratio_warning'):
            return "单位异常"
        return "--"

    def _render_overseas_pct(self, geo: dict) -> str:
        overseas_pct = geo.get('overseas_revenue_pct')
        return f"{overseas_pct:.1f}%" if overseas_pct is not None else "--"

    def _render_biz_segments(self, biz: dict) -> str:
        if not biz.get("segments"):
            return ""
        seg_items = ""
        for seg in biz["segments"][:6]:
            name = seg.get("name", "--")
            share = seg.get("share_pct")
            growth = seg.get("growth_pct")
            share_str = f"{share:.1f}%" if share is not None else "--"
            growth_str = f"↑{growth:.1f}%" if growth and growth > 0 else (f"↓{abs(growth):.1f}%" if growth else "--")
            seg_items += (
                f'<div class="kpi-item"><div class="kpi-label">{self.html.escape(name)}</div>'
                f'<div class="kpi-value">{self.html.escape(share_str)}</div>'
                f'<div style="font-size:12px;color:#475569;">{self.html.escape(growth_str)}</div></div>'
            )
        return SafeHtml(
            f'<div style="border-top:1px solid rgba(148,163,184,0.1);margin:12px 0;"></div>'
            f'<div class="section-title">📊 业务分部</div>'
            f'<div class="kpi-row">{seg_items}</div>'
        )

    def _render_risk_details(self, risk: dict) -> str:
        risk_items = risk.get('risks', {})
        if not risk_items:
            return ""
        risk_chips = []
        for cat, data in risk_items.items():
            level = data.get('risk_level', '--')
            penalty = data.get('score_penalty', 0)
            if penalty > 0:
                color = '#DC2626' if level == '高' else ('#D97706' if level == '中' else '#475569')
                cat_label = cat.replace('_risk', '').replace('_', ' ')
                risk_chips.append(
                    f'<span style="display:inline-block;padding:3px 8px;margin:2px;border-radius:12px;'
                    f'font-size:12px;background:rgba(251,113,133,0.1);color:{color};border:1px solid rgba(251,113,133,0.2);">'
                    f'{cat_label} {level}(-{penalty})</span>'
                )
        if not risk_chips:
            return ""
        risk_detail_html = f'<div style="margin-top:6px;">{" ".join(risk_chips)}</div>'
        return SafeHtml(
            f'<div style="border-top:1px solid rgba(148,163,184,0.1);margin:12px 0;"></div>'
            f'<div class="section-title">⚠️ 风险明细</div>{risk_detail_html}'
        )

    def _render_cornerstone(self, ipo: dict) -> None:
        pi = ipo.get("prospectus_info", {}) or {}
        ca = pi.get("cornerstone_analysis", {}) or {}

        has_cornerstone_signal = bool(
            ca.get("cornerstone_investors")
            or ca.get("cornerstone_pct") is not None
            or ca.get("dimension_scores")
            or ca.get("reasons")
            or ca.get("score")
        )
        if not has_cornerstone_signal:
            return

        ca_score = ca.get('score', 0)
        ca_label = ca.get('label', '--')
        ca_band = ca.get('grade_band') or ca_label
        ca_rec = ca.get('recommendation', '--')
        cornerstone_amount = pi.get('cornerstone_investment_hkd_million') or ca.get('cornerstone_investment_hkd_million')
        cornerstone_offer_ratio = pi.get('cornerstone_offer_ratio_pct') or ca.get('cornerstone_offer_ratio_pct')
        total_fund_m = pi.get('total_fund') or pi.get('final_total_fund')
        amount_to_gross_pct = None
        if _is_num(cornerstone_amount) and _is_num(total_fund_m) and total_fund_m:
            amount_to_gross_pct = cornerstone_amount / (total_fund_m * 100) * 100
        combo = ca.get('combination_summary') or '--'

        ca_kpi_html = SafeHtml(
            f'<div class="kpi-row">'
            f'<div class="kpi-item"><div class="kpi-label">基石评级</div><div class="kpi-value">{self.html.escape(ca_label)} · {self.html.escape(ca_band)}</div></div>'
            f'<div class="kpi-item"><div class="kpi-label">基石评分</div><div class="kpi-value">{self.html.escape(str(ca_score))}/100</div></div>'
            f'<div class="kpi-item"><div class="kpi-label">认购金额</div><div class="kpi-value">{self.html.escape(self.fmt.format_number(cornerstone_amount, " M HKD"))}</div></div>'
            f'<div class="kpi-item"><div class="kpi-label">占全球发售</div><div class="kpi-value">{self.html.escape(self.fmt.format_percentage(cornerstone_offer_ratio))}</div></div>'
            f'<div class="kpi-item"><div class="kpi-label">占总募资</div><div class="kpi-value">{self.html.escape(self.fmt.format_percentage(amount_to_gross_pct))}</div></div>'
            f'<div class="kpi-item"><div class="kpi-label">模型判断</div><div class="kpi-value">{self.html.escape(ca_rec)}</div></div>'
            f'</div>'
        )

        summary_html = SafeHtml(
            f'<div style="font-size:15px;color:#475569;margin:12px 0 10px;padding:14px 16px;'
                f'background:rgba(30,64,175,0.04);border:1px solid rgba(148,163,184,0.12);border-radius:12px;line-height:1.5;">'
            f'<b style="color:#1E40AF;">组合画像：</b>{self.html.escape(combo)}</div>'
        )
        dimension_html = self._render_cornerstone_dimensions(ca)
        ca_rows_html = self._render_cornerstone_rows(ca)
        ca_signal_html = self._render_cornerstone_signals(ca)
        source_html = self._render_cornerstone_source(ca)

        st.markdown(
            '<div class="section-card">\n'
            '<div class="section-title">🏛️ 基石评分</div>\n'
            f'{ca_kpi_html}\n'
            f'{summary_html}\n'
            f'{dimension_html}\n'
            f'{ca_rows_html}\n'
            f'{ca_signal_html}\n'
            f'{source_html}\n'
            '</div>',
            unsafe_allow_html=True,
        )

    def _render_cornerstone_source(self, ca: dict) -> str:
        excerpt = ca.get("source_excerpt") or ca.get("raw_pdf_excerpt") or ""
        if not excerpt:
            return ""
        escaped_excerpt = self.html.escape(excerpt)
        return (
            '<details style="margin-top:14px;border-top:1px solid rgba(148,163,184,0.14);padding-top:12px;">'
            '<summary style="cursor:pointer;font-size:13px;font-weight:800;color:#1E40AF;">'
            '查看基石章节 PDF 原文摘录</summary>'
            '<div style="font-size:12px;color:#64748B;margin:8px 0 6px;">'
            '以下为 PDF 文本提取结果中的基石章节附近原文，用于人工核对投资者名称、认购金额和占比。</div>'
            '<pre style="white-space:pre-wrap;word-break:break-word;max-height:360px;overflow:auto;'
            'font-size:12px;line-height:1.5;color:#0F172A;background:#F8FAFC;'
            'border:1px solid rgba(148,163,184,0.18);border-radius:8px;padding:12px;">'
            f'{escaped_excerpt}</pre>'
            '</details>'
        )

    def _render_cornerstone_dimensions(self, ca: dict) -> str:
        dims = ca.get("dimension_scores") or {}
        if not dims:
            return ""
        rows = ""
        for item in dims.values():
            label = item.get("label", "--")
            score = item.get("score", 0)
            max_score = item.get("max_score", 0) or 1
            detail = item.get("detail", "")
            try:
                pct = max(0, min(100, float(score) / float(max_score) * 100))
            except Exception:
                pct = 0
            rows += (
                f'<div style="margin:8px 0;">'
                f'<div style="display:flex;justify-content:space-between;font-size:13px;color:#64748B;">'
                f'<span>{self.html.escape(label)} · {self.html.escape(detail)}</span>'
                f'<b style="color:#0F172A;">{self.html.escape(str(score))}/{self.html.escape(str(max_score))}</b>'
                f'</div>'
                f'<div class="progress-bar" style="height:7px;margin-top:4px;">'
                f'<div class="fill" style="width:{pct:.0f}%;background:#D97706;"></div>'
                f'</div>'
                f'</div>'
            )
        return f'<div style="margin:8px 0 12px;">{rows}</div>'

    def _render_cornerstone_rows(self, ca: dict) -> str:
        ca_rows_html = ""
        for row in ca.get("cornerstone_investors") or []:
            name = row.get('short_name') or row.get('name', '--')
            full_name = row.get('name', '')
            match_note = row.get("match_note", "")
            offer_pct = self.fmt.format_percentage(row.get("offer_shares_pct"))
            amount = row.get('investment_amount_hkd_m') or row.get('total_investment_amount_hkd_m')
            amount_text = self.fmt.format_number(amount, " M HKD") if amount is not None else "--"
            tier = row.get("tier", "")
            category = row.get("category", "未知")
            role_note = row.get("role_note", "")
            tier_score = row.get("tier_score", "--")
            fit_label = row.get("sector_fit_label", "--")
            tier_color = "green" if tier == "S" else ("blue" if tier == "A" else ("yellow" if tier == "B" else "gray"))
            tier_tag = self.html.tag(tier or "未知", tier_color)
            full_name_html = ""
            if full_name and full_name != name:
                full_name_html = f'<div style="font-size:11px;color:#475569;margin-top:2px;">{self.html.escape(full_name)}</div>'
            ca_rows_html += (
                f'<div class="cornerstone-row" style="grid-template-columns:1.25fr 1.75fr;">'
                f'<div><b>{self.html.escape(name)}</b> {tier_tag}{full_name_html}'
                f'<div style="font-size:12px;color:#475569;margin-top:4px;">{self.html.escape(category)} · {self.html.escape(str(tier_score))}分 · {self.html.escape(amount_text)} · 占全球发售 {self.html.escape(offer_pct)}</div></div>'
                f'<div style="color:#475569;font-size:13px;">{self.html.escape(role_note or match_note)}'
                f'<div style="font-size:12px;color:#475569;margin-top:4px;">{self.html.escape(match_note)} · {self.html.escape(fit_label)}</div></div>'
                f'</div>'
            )

        if not ca_rows_html:
            matched = ca.get("matched_investors") or []
            if matched:
                for item in matched:
                    name = item.get("name", "--")
                    tier = item.get("tier", "")
                    tier_tag = self.html.tag(tier, "blue" if tier == "S" else "gray")
                    ca_rows_html += (
                        f'<div class="cornerstone-row"><div><b>{self.html.escape(name)}</b> {tier_tag}</div>'
                        f'<div style="color:#475569;font-size:14px;">V2重点基石 · 明细表未完整提取</div></div>'
                    )
            else:
                ca_rows_html = (
                    '<div style="font-size:13px;color:#475569;padding:8px 2px;">'
                    '基石投资者明细表未完整提取，以下评级基于已识别到的基石占比、赛道匹配和风险信号。</div>'
                )
        return ca_rows_html

    def _render_cornerstone_signals(self, ca: dict) -> str:
        strengths = ca.get("strengths") or []
        concerns = ca.get("concerns") or []
        red_flags = ca.get("red_flags") or []
        if not strengths and not concerns and not red_flags:
            return ""
        blocks = []
        if strengths:
            chips = " ".join(f'<span class="reason-chip">{self.html.escape(item)}</span>' for item in strengths[:5])
            blocks.append(f'<div style="margin-top:10px;"><b style="font-size:13px;color:#059669;">亮点</b><div style="margin-top:6px;">{chips}</div></div>')
        if concerns:
            chips = " ".join(f'<span class="reason-chip" style="background:rgba(217,119,6,0.08);color:#D97706;border-color:rgba(217,119,6,0.16);">{self.html.escape(item)}</span>' for item in concerns[:5])
            blocks.append(f'<div style="margin-top:10px;"><b style="font-size:13px;color:#D97706;">隐忧</b><div style="margin-top:6px;">{chips}</div></div>')
        if red_flags:
            chips = " ".join(f'<span class="reason-chip" style="background:rgba(220,38,38,0.08);color:#DC2626;border-color:rgba(220,38,38,0.16);">{self.html.escape(item)}</span>' for item in red_flags[:5])
            blocks.append(f'<div style="margin-top:10px;"><b style="font-size:13px;color:#DC2626;">红旗</b><div style="margin-top:6px;">{chips}</div></div>')
        return "".join(blocks)

    def _render_peer_comparison(self, ipo: dict) -> None:
        pi = ipo.get("prospectus_info", {}) or {}
        pc = pi.get("peer_comparison", {}) or {}

        pc_subsector = pc.get("subsector")
        pc_peers = pc.get("matched_peers", [])
        extracted_comps = pc.get("extracted_competitors", [])
        unmatched_candidates = pc.get("unmatched_peer_candidates", [])
        if not pc_subsector or (not pc_peers and not extracted_comps and not unmatched_candidates):
            return

        pc_company_ps = pc.get("company_ps")
        pc_company_pe = pc.get("company_pe")
        pc_peer_median_ps = pc.get("peer_median_ps")
        pc_peer_median_pe = pc.get("peer_median_pe")
        pc_premium_ps = pc.get("relative_ps_premium_pct")
        weighted_peer_ps = pc.get("weighted_peer_ps")
        weighted_premium_ps = pc.get("relative_weighted_ps_premium_pct")
        pc_scarcity = pc.get("scarcity_score", 0)
        pc_score = pc.get("peer_score", 0)
        pc_position = pc.get("valuation_position", "缺失")
        pc_summary = pc.get("summary", "")
        pc_warnings = pc.get("warnings", [])
        quantitative_peers = pc.get("quantitative_peers", [])
        qualitative_peers = pc.get("qualitative_peers", [])

        pc_html_parts = [
            f'<div style="margin-bottom:10px;font-size:15px;color:#0F172A;"><b>细分赛道:</b> {self.html.escape(str(pc_subsector).replace("_", " / "))}</div>'
        ]

        if pc_summary:
            pc_html_parts.append(
                f'<div style="font-size:14px;color:#475569;margin-bottom:12px;line-height:1.6;">{self.html.escape(pc_summary)}</div>'
            )

        if _is_num(pc_company_ps) and _is_num(pc_peer_median_ps):
            premium_str = f"{pc_premium_ps:+.1f}%" if _is_num(pc_premium_ps) else "--"
            pc_html_parts.append(
                f'<div class="kpi-row" style="margin-bottom:8px;">'
                f'<div class="kpi-item"><div class="kpi-label">公司PS</div><div class="kpi-value">{self.fmt.format_number(pc_company_ps)}x</div></div>'
                f'<div class="kpi-item"><div class="kpi-label">同行PS中位数({pc.get("peer_ps_count", 0)}家)</div><div class="kpi-value">{self.fmt.format_number(pc_peer_median_ps)}x</div></div>'
                f'<div class="kpi-item"><div class="kpi-label">业务加权同行PS</div><div class="kpi-value">{self.fmt.format_number(weighted_peer_ps, "x")}</div></div>'
                f'<div class="kpi-item"><div class="kpi-label">相对溢价</div><div class="kpi-value">{self.html.escape(premium_str)}</div></div>'
                f'<div class="kpi-item"><div class="kpi-label">赛道稀缺性</div><div class="kpi-value">{self.html.escape(str(pc_scarcity))}/10</div></div>'
                f'</div>'
            )
            if _is_num(weighted_peer_ps) and _is_num(weighted_premium_ps):
                pc_html_parts.append(
                    f'<div style="font-size:12px;color:#475569;margin:-2px 0 8px;">'
                    f'混合业务按分部收入占比重估：加权同行PS {weighted_peer_ps:.1f}x，相对溢价 {weighted_premium_ps:+.1f}%'
                    f'</div>'
                )

        if _is_num(pc_company_pe) and _is_num(pc_peer_median_pe):
            premium_pe_str = f"{pc.get('relative_pe_premium_pct', 0):+.1f}%" if _is_num(pc.get('relative_pe_premium_pct')) else "--"
            pc_html_parts.append(
                f'<div class="kpi-row" style="margin-bottom:8px;">'
                f'<div class="kpi-item"><div class="kpi-label">公司PE</div><div class="kpi-value">{self.fmt.format_number(pc_company_pe)}x</div></div>'
                f'<div class="kpi-item"><div class="kpi-label">同行PE中位数</div><div class="kpi-value">{self.fmt.format_number(pc_peer_median_pe)}x</div></div>'
                f'<div class="kpi-item"><div class="kpi-label">PE相对溢价</div><div class="kpi-value">{self.html.escape(premium_pe_str)}</div></div>'
                f'<div class="kpi-item"><div class="kpi-label">估值定位</div><div class="kpi-value">{self.html.escape(pc_position)}</div></div>'
                f'</div>'
            )

        position_map = {
            "明显偏贵": ("明显偏贵", "red"),
            "偏贵": ("偏贵", "yellow"),
            "偏贵但可解释": ("偏贵但有稀缺性支撑", "yellow"),
            "合理": ("估值合理或偏低", "green"),
            "相对低估": ("相对低估", "green"),
            "赛道合理": ("赛道合理", "green"),
            "偏高但稀缺赛道": ("偏高但赛道稀缺", "yellow"),
            "PS辅助(明显偏贵)": ("PS辅助(偏贵，收入基数小)", "yellow"),
            "PS辅助（明显偏贵）": ("PS辅助(偏贵，收入基数小)", "yellow"),
            "PS辅助(偏高但稀缺赛道)": ("PS辅助(偏高但赛道稀缺)", "yellow"),
            "PS辅助（偏高但稀缺赛道）": ("PS辅助(偏高但赛道稀缺)", "yellow"),
            "样本不足，仅作定性参考": ("样本不足，仅作定性参考", "gray"),
            "PS辅助估值": ("PS辅助估值", "yellow"),
            "PS失真，仅作参考": ("PS失真，仅作参考", "yellow"),
            "管线阶段估值": ("管线阶段估值", "yellow"),
            "数据不足，需人工核对": ("数据不足，需人工核对", "gray"),
        }
        pos_label, pos_color = position_map.get(pc_position, (pc_position, "gray"))
        pc_html_parts.append(
            f'<div style="margin:10px 0;display:flex;align-items:center;gap:8px;">'
            f'<b>综合估值:</b> {self.html.tag(pos_label, pos_color)} '
            f'<b>同行对比评分:</b> {self.fmt.format_number(pc_score, precision=0)}/15'
            f'</div>'
        )

        if pc.get("peer_sample_warning"):
            pc_html_parts.append(
                f'<div style="font-size:12px;color:#475569;margin:6px 0;padding:6px 10px;background:rgba(30,64,175,0.04);border-radius:8px;">'
                f'ℹ️ {self.html.escape(pc["peer_sample_warning"])}'
                f'</div>'
            )

        if pc_peers:
            pc_peers_short = pc_peers[:8]
            peer_rows = ""
            for p in pc_peers_short:
                p_name = self.html.escape(p.get("name", ""))
                p_ticker = self.html.escape(p.get("ticker", ""))
                p_type = p.get("type", "")
                p_ps = f"{self.fmt.format_number(p.get('ps'))}x" if p.get("ps") else "--"
                p_pe = f"{self.fmt.format_number(p.get('pe'))}x" if p.get("pe") else "--"
                p_gm = self.fmt.format_percentage(p.get("gross_margin_pct")) if p.get("gross_margin_pct") else "--"
                p_growth = self.fmt.format_number(p.get("revenue_growth_pct"), "%") if p.get("revenue_growth_pct") else "--"
                p_match = self.html.escape(p.get("matched_by", ""))
                p_note = self.html.escape(p.get("notes", "")) if p.get("notes") else ""
                type_tag = self.html.tag("已上市", "green") if p_type == "listed" else self.html.tag("未上市", "gray")
                peer_rows += (
                    f'<div class="cornerstone-row" style="grid-template-columns:auto;">'
                    f'<div style="display:flex;justify-content:space-between;width:100%;align-items:center;">'
                    f'<div><b>{p_name}</b> {p_ticker} {type_tag}</div>'
                    f'<div style="font-size:12px;color:#475569;">PS {p_ps} | PE {p_pe} | 毛利率 {p_gm} | 收入增 {p_growth}</div>'
                    f'</div>'
                    f'<div style="font-size:12px;color:#475569;width:100%;">{p_match}{(" | " + p_note) if p_note else ""}</div>'
                    f'</div>'
                )
            pc_html_parts.append(
                f'<div style="margin-top:8px;"><b>可比公司 ({len(pc_peers_short)}家):</b></div>{peer_rows}'
            )

        # quantitative / qualitative 区分展示
        if quantitative_peers or qualitative_peers:
            q_rows = ""
            for p in quantitative_peers[:6]:
                q_rows += f'<div style="font-size:12px;color:#475569;">• {self.html.escape(p.get("name", ""))} (quantitative)</div>'
            for p in qualitative_peers[:4]:
                q_rows += f'<div style="font-size:12px;color:#475569;">• {self.html.escape(p.get("name", ""))} (qualitative)</div>'
            if q_rows:
                pc_html_parts.append(
                    f'<div style="margin-top:8px;font-size:12px;color:#475569;">'
                    f'<b>quantitative peers:</b> 参与估值中位数计算；<b>qualitative peers:</b> 仅作定性参考'
                    f'</div>{q_rows}'
                )

        for w in pc_warnings:
            pc_html_parts.append(
                f'<div style="font-size:12px;color:#DC2626;margin-top:4px;">⚠️ {self.html.escape(w)}</div>'
            )

        # 招股书提及的同行候选
        if extracted_comps:
            names = "、".join(self.html.escape(n) for n in extracted_comps[:10])
            pc_html_parts.append(
                f'<div style="font-size:12px;color:#475569;margin-top:8px;">'
                f'📖 招股书明确提及的已收录同行: {names}'
                f'</div>'
            )
        if unmatched_candidates:
            names = "、".join(self.html.escape(n) for n in unmatched_candidates[:8])
            pc_html_parts.append(
                f'<div style="font-size:12px;color:#D97706;margin-top:4px;">'
                f'🔍 招股书提及但本地同行库未收录: {names}'
                f'<div style="font-size:11px;color:#475569;margin-top:2px;">'
                f'（不参与估值中位数，仅供人工维护同行库）'
                f'</div></div>'
            )

        st.markdown(
            f'<div class="section-card"><div class="section-title">🏷️ 同行对比与相对估值</div>{"".join(pc_html_parts)}</div>',
            unsafe_allow_html=True,
        )

    def _render_downloads(self, ipo: dict) -> None:
        st.markdown("""
        <div class="section-card">
            <div class="section-title">📥 下载报告</div>
        """, unsafe_allow_html=True)

        dl_col1, dl_col2 = st.columns(2)
        with dl_col1:
            if st.button("📄 下载PDF报告", key=f"pdf_{ipo.get('hk_code', 'x')}", width="stretch"):
                try:
                    pdf_path = generate_pdf_report([ipo], TEMP_DIR)
                    pdf_name = os.path.basename(pdf_path)
                    pdf_data = read_file_bytes_and_remove(pdf_path)
                    st.download_button("⬇️ 点击下载PDF", pdf_data, pdf_name, "application/pdf", width="stretch")
                except Exception as e:
                    st.error(f"PDF生成失败: {e}")
        with dl_col2:
            if st.button("📋 下载JSON数据", key=f"json_{ipo.get('hk_code', 'x')}", width="stretch"):
                try:
                    json_path = save_json_report([ipo], TEMP_DIR)
                    json_name = os.path.basename(json_path)
                    json_data = read_file_bytes_and_remove(json_path)
                    st.download_button("⬇️ 点击下载JSON", json_data, json_name, "application/json", width="stretch")
                except Exception as e:
                    st.error(f"JSON保存失败: {e}")

        st.markdown("</div>", unsafe_allow_html=True)
