import os
import uuid

import streamlit as st

from datetime import datetime
from ipo_analyzer.core import analyze_uploaded_pdf
from ipo_analyzer.history import HistoryStore
from ui.renderers.html_renderer import HtmlRenderer
from ui.renderers.data_formatter import DataFormatter
from ui.components.detail_view import DetailView
from ui.constants import DISCLAIMER


class UploadPage:
    """手动上传分析页面"""

    def __init__(self, temp_dir: str):
        self.temp_dir = temp_dir
        self.html = HtmlRenderer()
        self.fmt = DataFormatter()
        self.detail_view = DetailView(self.html, self.fmt)

    def render(self) -> None:
        self.html.hero_section(
            "📤 手动上传招股书",
            "上传PDF招股书，输入股票代码和公司名称，一键获取分析结果"
        )

        st.markdown('<div class="section-card">', unsafe_allow_html=True)

        upload_col1, upload_col2 = st.columns([2, 1])
        with upload_col1:
            uploaded_file = st.file_uploader("上传招股书PDF", type=["pdf"], label_visibility="collapsed")
        with upload_col2:
            stock_code = st.text_input("股票代码（可选）", "", placeholder="如 01236")
            company_name = st.text_input("公司名称（可选）", "", placeholder="如 乐动机器人")

        if uploaded_file and st.button("🔍 开始分析", type="primary", use_container_width=True):
            from ui.utils.file_utils import MAX_UPLOAD_SIZE_MB

            if uploaded_file.size > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
                st.error(f"上传文件过大，请控制在 {MAX_UPLOAD_SIZE_MB} MB 以内。")
            else:
                temp_path = os.path.join(
                    self.temp_dir,
                    f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex}.pdf"
                )
                with open(temp_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                with st.spinner("正在分析招股书..."):
                    try:
                        result = analyze_uploaded_pdf(temp_path, stock_code or None, company_name or None)
                        if "error" in result:
                            st.error(f"分析失败: {result['error']}")
                        else:
                            HistoryStore(self.temp_dir).archive_one(result, source='upload')
                            st.session_state["upload_result"] = result
                            st.success("✅ 分析完成！")
                    except Exception as e:
                        st.error(f"分析异常: {e}")

        st.markdown('</div>', unsafe_allow_html=True)

        result = st.session_state.get("upload_result")
        if result and "error" not in result:
            self.detail_view.render(result)

        st.caption(DISCLAIMER)
