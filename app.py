import os
import logging

import streamlit as st

from ui.pages.dashboard_page import DashboardPage
from ui.pages.upload_page import UploadPage
from ui.pages.history_page import HistoryPage
from ui.utils.file_utils import cleanup_temp_files
from ui.renderers.html_renderer import HtmlRenderer
from ui.constants import DISCLAIMER

logging.basicConfig(level=logging.WARNING, format="%(message)s")

TEMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
os.makedirs(TEMP_DIR, exist_ok=True)
CSS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style.css")


@st.cache_data
def _read_css(path: str, mtime: float):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _load_style() -> None:
    css_mtime = os.path.getmtime(CSS_PATH) if os.path.exists(CSS_PATH) else 0
    css = _read_css(CSS_PATH, css_mtime)
    if css is None:
        st.warning("样式文件 style.css 未找到，使用默认样式")
    else:
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def _peer_admin_factory():
    from ui.pages.peer_admin_page import PeerAdminPage
    return PeerAdminPage()


PAGE_REGISTRY = [
    ("🏠 首页 Dashboard", lambda: DashboardPage(TEMP_DIR)),
    ("📤 手动上传分析", lambda: UploadPage(TEMP_DIR)),
    ("📚 历史分析", lambda: HistoryPage(TEMP_DIR)),
    ("🧩 同行库管理", _peer_admin_factory),
]


def main():
    st.set_page_config(
        page_title="港股IPO打新分析", 
        page_icon="📊", 
        layout="wide",
        initial_sidebar_state="expanded"
    )

    if not st.session_state.get("_temp_cleaned"):
        cleanup_temp_files(TEMP_DIR)
        st.session_state["_temp_cleaned"] = True
    _load_style()

    HtmlRenderer.sidebar_header("📊", "港股IPO分析", "IPO Analyzer Pro")

    page_label = st.sidebar.radio("导航", [label for label, _ in PAGE_REGISTRY])
    factory = dict(PAGE_REGISTRY)[page_label]
    try:
        factory().render()
    except Exception as e:
        st.error(f"页面加载失败: {e}")

    st.sidebar.markdown("---")
    st.sidebar.caption(DISCLAIMER)


if __name__ == "__main__":
    main()
