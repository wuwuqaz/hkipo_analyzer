from html import escape as html_escape
from typing import Any, Optional

from ui.utils.shared_utils import SafeHtml, _num


class HtmlRenderer:
    """HTML 渲染器，负责生成安全的 HTML 片段"""

    allowed_score_classes = {"score-excellent", "score-good", "score-medium", "score-poor", ""}
    allowed_colors = {"#4ade80", "#a3e635", "#facc15", "#f87171"}
    allowed_tag_colors = {"green", "yellow", "red", "blue", "gray"}

    @staticmethod
    def metric_card(label: str, value: str, sub: str = "", score_class: str = "") -> SafeHtml:
        safe_class = score_class if score_class in HtmlRenderer.allowed_score_classes else ""
        sub_html = f'<div class="sub">{HtmlRenderer.escape(sub)}</div>' if sub else ""
        return SafeHtml(
            f'<div class="metric-card {safe_class}">'
            f'<div class="label">{HtmlRenderer.escape(label)}</div>'
            f'<div class="value">{HtmlRenderer.escape(value)}</div>'
            f'{sub_html}</div>'
        )

    @staticmethod
    def progress_bar(pct: float, color: str) -> SafeHtml:
        try:
            safe_pct = max(0, min(100, float(pct)))
        except Exception:
            safe_pct = 0
        safe_color = color if color in HtmlRenderer.allowed_colors else "#64748b"
        return SafeHtml(
            f'<div class="progress-bar"><div class="fill" style="width:{safe_pct}%;background:{safe_color}"></div></div>'
        )

    @staticmethod
    def kpi_row(kpis: list[tuple[str, Any]]) -> SafeHtml:
        items = "".join(
            f'<div class="kpi-item"><div class="kpi-label">{HtmlRenderer.escape(label)}</div>'
            f'<div class="kpi-value">{HtmlRenderer.as_html(value)}</div></div>'
            for label, value in kpis
        )
        return SafeHtml(f'<div class="kpi-row">{items}</div>')

    @staticmethod
    def tag(text: str, color: str = "gray") -> SafeHtml:
        safe_color = color if color in HtmlRenderer.allowed_tag_colors else "gray"
        return SafeHtml(f'<span class="tag tag-{safe_color}">{HtmlRenderer.escape(text)}</span>')

    @staticmethod
    def escape(value: Any) -> str:
        if value is None:
            return "--"
        return html_escape(str(value), quote=True)

    @staticmethod
    def as_html(value: Any) -> str:
        if isinstance(value, SafeHtml):
            return str(value)
        return HtmlRenderer.escape(value)

    @staticmethod
    def hero_section(title: str, subtitle: str) -> None:
        import streamlit as st
        st.markdown(f"""
        <div class="hero-gradient">
            <h1>{title}</h1>
            <p>{HtmlRenderer.escape(subtitle)}</p>
        </div>
        """, unsafe_allow_html=True)

    @staticmethod
    def sidebar_header(icon: str, title: str, subtitle: str) -> None:
        import streamlit as st
        st.sidebar.markdown(f"""
        <div style="text-align:center;padding:20px 0 16px;">
            <div style="font-size:28px;">{HtmlRenderer.escape(icon)}</div>
            <div style="font-size:18px;font-weight:700;color:#f1f5f9;">{HtmlRenderer.escape(title)}</div>
            <div style="font-size:12px;color:#64748b;margin-top:4px;">{HtmlRenderer.escape(subtitle)}</div>
        </div>
        """, unsafe_allow_html=True)

    @staticmethod
    def empty_state(icon: str, title: str, description: str, extra: str = "") -> None:
        import streamlit as st
        extra_html = f"<div style='font-size:14px;color:#94a3b8;margin-top:8px;'>{extra}</div>" if extra else ""
        st.markdown(f"""
        <div class="section-card" style="text-align:center;padding:60px 24px;">
            <div style="font-size:48px;margin-bottom:16px;">{icon}</div>
            <div style="font-size:18px;color:#475569;font-weight:500;">{HtmlRenderer.escape(title)}</div>
            {extra_html}
        </div>
        """, unsafe_allow_html=True)

    @staticmethod
    def metric_card_st(columns, metrics: list[tuple[str, str, str, str]]) -> None:
        import streamlit as st
        for col, (label, value, sub, cls) in zip(columns, metrics):
            with col:
                st.markdown(HtmlRenderer.metric_card(label, value, sub, cls), unsafe_allow_html=True)

    @staticmethod
    def reason_chips(reasons: list[str]) -> str:
        if not reasons:
            return ""
        return " ".join(
            f'<span class="reason-chip">{HtmlRenderer.escape(r)}</span>' for r in reasons
        )

    @staticmethod
    def diag_grid(items: list[tuple[str, Any]]) -> str:
        rows = "".join(
            f'<div class="diag-item"><span class="diag-label">{HtmlRenderer.escape(label)}</span>'
            f'<span class="diag-value">{HtmlRenderer.as_html(value)}</span></div>'
            for label, value in items
        )
        return f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:0 32px;">{rows}</div>'

    @staticmethod
    def section_title(title: str) -> str:
        return f'<div class="section-title">{title}</div>'

    @staticmethod
    def section_card_start() -> str:
        return '<div class="section-card">'

    @staticmethod
    def section_card_end() -> str:
        return '</div>'
