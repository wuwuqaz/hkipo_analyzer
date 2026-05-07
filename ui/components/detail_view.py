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
        score = ipo.get('score', 0)

        st.markdown(f"""
        <div class="section-card" style="background:linear-gradient(135deg,#1e293b 0%,#334155 100%);color:white;padding:20px 24px;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <div>
                    <div style="font-size:24px;font-weight:700;color:#f1f5f9;">{self.html.escape(company_name)}</div>
                    <div style="font-size:14px;color:#94a3b8;margin-top:2px;">
                        股票代码 {self.html.escape(stock_code)} ·
                        {self.html.escape(pi.get('sector', '--'))} ·
                        {self.html.escape(val.get('valuation_label', '--'))}
                    </div>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:38px;font-weight:800;color:{score_color_hex(score)};">
                        {self.html.escape(str(score))}
                    </div>
                    <div style="font-size:13px;color:#94a3b8;">综合评分</div>
                </div>
            </div>
            {self.html.progress_bar(score, score_color_hex(score))}
        </div>
        """, unsafe_allow_html=True)

    def _render_prospectus_warning(self, has_prospectus: bool, key_financials_empty: bool) -> None:
        if not has_prospectus or key_financials_empty:
            st.warning("⚠️ 未成功解析招股书，当前评分仅基于孖展/默认值，不能用于判断基本面。")

    def _render_metrics(self, ipo: dict) -> None:
        pi = ipo.get("prospectus_info", {}) or {}
        af = pi.get("advanced_framework", {}) or {}
        score = ipo.get('score', 0)

        cols = st.columns(5)
        metrics = [
            ("总评分", f"{score}/100", "", score_class(score)),
            ("申购热度", f"{ipo.get('subscription_score', 0)}/100", "", score_class(ipo.get('subscription_score', 0))),
            ("基本面", f"{ipo.get('fundamental_score', 0)}/100", "", score_class(ipo.get('fundamental_score', 0))),
            ("风险扣分", f"-{ipo.get('risk_penalty', 0)}", "", "score-poor" if ipo.get('risk_penalty', 0) > 5 else ""),
            ("进阶框架", f"{af.get('score', 0)}/100", "", score_class(af.get('score', 0))),
        ]
        self.html.metric_card_st(cols, metrics)

    def _render_score_reasons(self, ipo: dict) -> None:
        reasons = ipo.get("score_reasons", [])
        chips_html = self.html.reason_chips(reasons) if reasons else ""
        st.markdown(f"""
        <div class="section-card">
            <div class="section-title">📝 评分理由</div>
            {chips_html}
        </div>
        """, unsafe_allow_html=True)

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

        st.markdown(f"""
        <div class="section-card">
            <div class="section-title">🔍 解析诊断</div>
            {self.html.diag_grid(diag_items)}
        </div>
        """, unsafe_allow_html=True)

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

        info_kpis = [
            ("招股期", f"{ipo.get('apply_start_date', '--')} ~ {ipo.get('apply_end_date', '--')}"),
            ("发行价", self.fmt.format_number(pi.get('offer_price'), ' HKD')),
            ("每手股数", str(pi.get('lot_size', '--'))),
            ("入场费", self.fmt.format_number(pi.get('entry_fee_hkd'), ' HKD')),
            ("市值", self.fmt.format_number(pi.get('market_cap_hkd_million'), ' M HKD')),
            ("发行比例", self.fmt.format_percentage(pi.get('issuance_ratio_pct'))),
            ("孖展资金", self.fmt.format_number(ipo.get('margin_total'), ' 亿')),
            ("超购倍数", self.fmt.format_number(ipo.get('over_sub_ratio'), 'x')),
            ("市场热度", ipo.get('market_heat', '--')),
            ("行业", pi.get('sector', '--')),
        ]

        fin_kpis = [
            ("收入", self.fmt.format_revenue_with_yoy(pi)),
            ("净利润", self.fmt.format_net_profit_with_yoy(pi)),
            ("毛利率", self.fmt.format_gross_margin_with_yoy(pi)),
            ("PE", self.fmt.format_number(val.get('pe_ratio'), 'x')),
            ("PS", self.fmt.format_number(val.get('ps_ratio'), 'x')),
            ("PB", self.fmt.format_number(val.get('pb_ratio'), 'x')),
            ("研发费率", self._render_rd_ratio(rnd)),
            ("海外占比", self._render_overseas_pct(geo)),
            ("增长来源", biz.get('growth_source', '--')),
            ("海外扩张", geo.get('overseas_growth_label', '--')),
        ]

        detail_kpis = [
            ("客户集中度", cs.get('concentration_risk_label', '--')),
            ("Top5客户占比", self.fmt.format_percentage(cs.get('top5_customer_revenue_pct'))),
            ("最大客户占比", self.fmt.format_percentage(cs.get('largest_customer_revenue_pct'))),
            ("现金流质量", cf.get('cash_quality_label', '--')),
            ("技术壁垒", f"{rnd.get('pipeline_quality_label', '--')} ({rnd.get('technology_moat_score', 0)}/10)"),
            ("产能利用率", self.fmt.format_percentage(cap.get('utilization_rate'))),
            ("风险扣分", str(risk.get('total_penalty', 0))),
        ]

        biz_seg_html = self._render_biz_segments(biz)
        risk_expanded_html = self._render_risk_details(risk)

        st.markdown(f"""
        <div class="section-card">
            <div class="section-title">📈 基本信息</div>
            {self.html.kpi_row(info_kpis)}
            <div style="border-top:1px solid #f1f5f9;margin:10px 0;"></div>
            <div class="section-title">💰 核心财务</div>
            {self.html.kpi_row(fin_kpis)}
            <div style="border-top:1px solid #f1f5f9;margin:10px 0;"></div>
            <div class="section-title">🔬 深度分析</div>
            {self.html.kpi_row(detail_kpis)}
            {biz_seg_html}
            {risk_expanded_html}
        </div>
        """, unsafe_allow_html=True)

        if biz.get("business_breakdown_warning"):
            st.warning(f"⚠️ {biz['business_breakdown_warning']}")
        if biz.get("vbp_risk_score", 0) > 0:
            st.warning(f"⚠️ 集采/VBP风险: {biz.get('vbp_summary', '')}")

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
                f'<div style="font-size:12px;color:#94a3b8;">{self.html.escape(growth_str)}</div></div>'
            )
        return SafeHtml(
            f'<div style="border-top:1px solid #f1f5f9;margin:10px 0;"></div>'
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
                color = '#ef4444' if level == '高' else ('#f59e0b' if level == '中' else '#94a3b8')
                cat_label = cat.replace('_risk', '').replace('_', ' ')
                risk_chips.append(
                    f'<span style="display:inline-block;padding:3px 8px;margin:2px;border-radius:12px;'
                    f'font-size:12px;background:#fee2e2;color:{color};border:1px solid #fecaca;">'
                    f'{cat_label} {level}(-{penalty})</span>'
                )
        if not risk_chips:
            return ""
        risk_detail_html = f'<div style="margin-top:6px;">{" ".join(risk_chips)}</div>'
        return SafeHtml(
            f'<div style="border-top:1px solid #f1f5f9;margin:10px 0;"></div>'
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
        ca_pct = self.fmt.format_percentage(ca.get('cornerstone_pct'))
        combo = ca.get('combination_summary') or '--'

        ca_kpi_html = SafeHtml(
            f'<div class="kpi-row">'
            f'<div class="kpi-item"><div class="kpi-label">基石评级</div><div class="kpi-value">{self.html.escape(ca_label)} · {self.html.escape(ca_band)}</div></div>'
            f'<div class="kpi-item"><div class="kpi-label">基石评分</div><div class="kpi-value">{self.html.escape(str(ca_score))}/100</div></div>'
            f'<div class="kpi-item"><div class="kpi-label">基石占比</div><div class="kpi-value">{self.html.escape(ca_pct)}</div></div>'
            f'<div class="kpi-item"><div class="kpi-label">模型判断</div><div class="kpi-value">{self.html.escape(ca_rec)}</div></div>'
            f'</div>'
        )

        summary_html = SafeHtml(
            f'<div style="font-size:14px;color:#334155;margin:10px 0 8px;padding:10px 12px;'
            f'background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;">'
            f'<b>组合画像：</b>{self.html.escape(combo)}</div>'
        )
        dimension_html = self._render_cornerstone_dimensions(ca)
        ca_rows_html = self._render_cornerstone_rows(ca)
        ca_signal_html = self._render_cornerstone_signals(ca)

        st.markdown(f"""
        <div class="section-card">
            <div class="section-title">🏛️ 基石评分</div>
            {ca_kpi_html}
            {summary_html}
            {dimension_html}
            {ca_rows_html}
            {ca_signal_html}
        </div>
        """, unsafe_allow_html=True)

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
                f'<div style="display:flex;justify-content:space-between;font-size:12px;color:#64748b;">'
                f'<span>{self.html.escape(label)} · {self.html.escape(detail)}</span>'
                f'<b>{self.html.escape(str(score))}/{self.html.escape(str(max_score))}</b>'
                f'</div>'
                f'<div class="progress-bar" style="height:7px;margin-top:4px;">'
                f'<div class="fill" style="width:{pct:.0f}%;background:#f59e0b;"></div>'
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
            tier = row.get("tier", "")
            category = row.get("category", "未知")
            role_note = row.get("role_note", "")
            tier_score = row.get("tier_score", "--")
            fit_label = row.get("sector_fit_label", "--")
            tier_color = "green" if tier == "S" else ("blue" if tier == "A" else ("yellow" if tier == "B" else "gray"))
            tier_tag = self.html.tag(tier or "未知", tier_color)
            full_name_html = ""
            if full_name and full_name != name:
                full_name_html = f'<div style="font-size:11px;color:#94a3b8;margin-top:2px;">{self.html.escape(full_name)}</div>'
            ca_rows_html += (
                f'<div class="cornerstone-row" style="grid-template-columns:1.25fr 1.75fr;">'
                f'<div><b>{self.html.escape(name)}</b> {tier_tag}{full_name_html}'
                f'<div style="font-size:12px;color:#64748b;margin-top:4px;">{self.html.escape(category)} · {self.html.escape(str(tier_score))}分 · 占发售 {self.html.escape(offer_pct)}</div></div>'
                f'<div style="color:#64748b;font-size:13px;">{self.html.escape(role_note or match_note)}'
                f'<div style="font-size:12px;color:#94a3b8;margin-top:4px;">{self.html.escape(match_note)} · {self.html.escape(fit_label)}</div></div>'
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
                        f'<div style="color:#64748b;font-size:14px;">V2重点基石 · 明细表未完整提取</div></div>'
                    )
            else:
                ca_rows_html = (
                    '<div style="font-size:13px;color:#64748b;padding:8px 2px;">'
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
            blocks.append(f'<div style="margin-top:10px;"><b style="font-size:13px;color:#166534;">亮点</b><div style="margin-top:6px;">{chips}</div></div>')
        if concerns:
            chips = " ".join(f'<span class="reason-chip" style="background:#fff7ed;color:#9a3412;">{self.html.escape(item)}</span>' for item in concerns[:5])
            blocks.append(f'<div style="margin-top:10px;"><b style="font-size:13px;color:#9a3412;">隐忧</b><div style="margin-top:6px;">{chips}</div></div>')
        if red_flags:
            chips = " ".join(f'<span class="reason-chip" style="background:#fee2e2;color:#991b1b;">{self.html.escape(item)}</span>' for item in red_flags[:5])
            blocks.append(f'<div style="margin-top:10px;"><b style="font-size:13px;color:#991b1b;">红旗</b><div style="margin-top:6px;">{chips}</div></div>')
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
        pc_scarcity = pc.get("scarcity_score", 0)
        pc_score = pc.get("peer_score", 0)
        pc_position = pc.get("valuation_position", "缺失")
        pc_summary = pc.get("summary", "")
        pc_warnings = pc.get("warnings", [])
        quantitative_peers = pc.get("quantitative_peers", [])
        qualitative_peers = pc.get("qualitative_peers", [])

        pc_html_parts = [
            f'<div style="margin-bottom:8px;"><b>细分赛道:</b> {self.html.escape(str(pc_subsector).replace("_", " / "))}</div>'
        ]

        if pc_summary:
            pc_html_parts.append(
                f'<div style="font-size:13px;color:#475569;margin-bottom:10px;">{self.html.escape(pc_summary)}</div>'
            )

        if _is_num(pc_company_ps) and _is_num(pc_peer_median_ps):
            premium_str = f"{pc_premium_ps:+.1f}%" if _is_num(pc_premium_ps) else "--"
            pc_html_parts.append(
                f'<div class="kpi-row" style="margin-bottom:8px;">'
                f'<div class="kpi-item"><div class="kpi-label">公司PS</div><div class="kpi-value">{self.fmt.format_number(pc_company_ps)}x</div></div>'
                f'<div class="kpi-item"><div class="kpi-label">同行PS中位数({pc.get("peer_ps_count", 0)}家)</div><div class="kpi-value">{self.fmt.format_number(pc_peer_median_ps)}x</div></div>'
                f'<div class="kpi-item"><div class="kpi-label">相对溢价</div><div class="kpi-value">{self.html.escape(premium_str)}</div></div>'
                f'<div class="kpi-item"><div class="kpi-label">赛道稀缺性</div><div class="kpi-value">{self.html.escape(str(pc_scarcity))}/10</div></div>'
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
                    f'<div style="font-size:12px;color:#64748b;">PS {p_ps} | PE {p_pe} | 毛利率 {p_gm} | 收入增 {p_growth}</div>'
                    f'</div>'
                    f'<div style="font-size:12px;color:#94a3b8;width:100%;">{p_match}{(" | " + p_note) if p_note else ""}</div>'
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
                q_rows += f'<div style="font-size:12px;color:#94a3b8;">• {self.html.escape(p.get("name", ""))} (qualitative)</div>'
            if q_rows:
                pc_html_parts.append(
                    f'<div style="margin-top:8px;font-size:12px;color:#64748b;">'
                    f'<b>quantitative peers:</b> 参与估值中位数计算；<b>qualitative peers:</b> 仅作定性参考'
                    f'</div>{q_rows}'
                )

        for w in pc_warnings:
            pc_html_parts.append(
                f'<div style="font-size:12px;color:#f87171;margin-top:4px;">⚠️ {self.html.escape(w)}</div>'
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
                f'<div style="font-size:12px;color:#b45309;margin-top:4px;">'
                f'🔍 招股书提及但本地同行库未收录: {names}'
                f'<div style="font-size:11px;color:#94a3b8;margin-top:2px;">'
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
            if st.button("📄 下载PDF报告", key=f"pdf_{ipo.get('hk_code', 'x')}", use_container_width=True):
                try:
                    pdf_path = generate_pdf_report([ipo], TEMP_DIR)
                    pdf_name = os.path.basename(pdf_path)
                    pdf_data = read_file_bytes_and_remove(pdf_path)
                    st.download_button("⬇️ 点击下载PDF", pdf_data, pdf_name, "application/pdf", use_container_width=True)
                except Exception as e:
                    st.error(f"PDF生成失败: {e}")
        with dl_col2:
            if st.button("📋 下载JSON数据", key=f"json_{ipo.get('hk_code', 'x')}", use_container_width=True):
                try:
                    json_path = save_json_report([ipo], TEMP_DIR)
                    json_name = os.path.basename(json_path)
                    json_data = read_file_bytes_and_remove(json_path)
                    st.download_button("⬇️ 点击下载JSON", json_data, json_name, "application/json", use_container_width=True)
                except Exception as e:
                    st.error(f"JSON保存失败: {e}")

        st.markdown("</div>", unsafe_allow_html=True)
