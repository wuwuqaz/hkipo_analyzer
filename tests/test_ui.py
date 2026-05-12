"""UI 层测试 — 渲染器、格式化器、共享工具。"""

import sys
import os


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestHtmlRenderer:
    """测试 HtmlRenderer HTML 转义和标签生成。"""

    def test_escape_none(self):
        from ui.renderers.html_renderer import HtmlRenderer
        assert HtmlRenderer.escape(None) == "--"

    def test_escape_html_chars(self):
        from ui.renderers.html_renderer import HtmlRenderer
        assert "&lt;" in HtmlRenderer.escape("<script>")
        assert "&gt;" in HtmlRenderer.escape("<script>")
        assert "&amp;" in HtmlRenderer.escape("a & b")
        assert "&quot;" in HtmlRenderer.escape('say "hello"')

    def test_escape_int(self):
        from ui.renderers.html_renderer import HtmlRenderer
        assert HtmlRenderer.escape(42) == "42"

    def test_escape_chinese(self):
        from ui.renderers.html_renderer import HtmlRenderer
        result = HtmlRenderer.escape("基石投资者")
        assert "基石投资者" in result

    def test_tag(self):
        from ui.renderers.html_renderer import HtmlRenderer
        result = HtmlRenderer.tag("S级", "green")
        assert "S级" in result
        assert "green" in result

    def test_sidebar_header_exists(self):
        from ui.renderers.html_renderer import HtmlRenderer
        assert callable(HtmlRenderer.sidebar_header)


class TestDataFormatter:
    """测试 DataFormatter 数据格式化。"""

    def test_format_number_int(self):
        from ui.renderers.data_formatter import DataFormatter
        fmt = DataFormatter()
        assert fmt.format_number(1234.56) == "1234.56"

    def test_format_number_with_suffix(self):
        from ui.renderers.data_formatter import DataFormatter
        fmt = DataFormatter()
        assert "HKD" in fmt.format_number(100, " HKD")

    def test_format_number_none(self):
        from ui.renderers.data_formatter import DataFormatter
        fmt = DataFormatter()
        assert fmt.format_number(None) == "--"

    def test_format_percentage(self):
        from ui.renderers.data_formatter import DataFormatter
        fmt = DataFormatter()
        assert "%" in fmt.format_percentage(35.5)

    def test_format_percentage_none(self):
        from ui.renderers.data_formatter import DataFormatter
        fmt = DataFormatter()
        assert fmt.format_percentage(None) == "--"

    def test_format_revenue_with_yoy(self):
        from ui.renderers.data_formatter import DataFormatter
        fmt = DataFormatter()
        pi = {"revenue": 500, "revenue_y1": 400, "revenue_year": "2025", "revenue_y1_year": "2024"}
        result = fmt.format_revenue_with_yoy(pi)
        assert "500" in result

    def test_format_net_profit_with_yoy(self):
        from ui.renderers.data_formatter import DataFormatter
        fmt = DataFormatter()
        pi = {"net_profit": 50, "net_profit_y1": 40, "net_profit_year": "2025", "net_profit_y1_year": "2024"}
        result = fmt.format_net_profit_with_yoy(pi)
        assert "50" in result


class TestSafeHtml:
    """测试 SafeHtml 标记类型。"""

    def test_safe_html_is_string(self):
        from ui.utils.shared_utils import SafeHtml
        s = SafeHtml("<b>safe</b>")
        assert isinstance(s, str)
        assert s == "<b>safe</b>"

    def test_safe_html_escape_non_safe(self):
        from ui.utils.shared_utils import SafeHtml
        result = SafeHtml("<b>").__class__.__name__
        assert result == "SafeHtml"


class TestScoreUtils:
    """测试评分颜色和分类工具。"""

    def test_score_color_hex(self):
        from ui.utils.shared_utils import score_color_hex
        colors = [score_color_hex(s) for s in [0, 30, 50, 70, 90, 100]]
        assert all(c.startswith("#") for c in colors)
        assert len(set(colors)) >= 3  # different scores should have different colors

    def test_score_class(self):
        from ui.utils.shared_utils import score_class
        classes = [score_class(s) for s in [0, 30, 50, 70, 90, 100]]
        assert all(isinstance(c, str) for c in classes)


class TestDetailView:
    """测试详情页局部渲染辅助。"""

    def test_cornerstone_source_excerpt_is_escaped(self):
        from ui.components.detail_view import DetailView

        html = DetailView()._render_cornerstone_source({
            "source_excerpt": "Cornerstone Investors\nA < B & C",
        })

        assert "查看基石章节 PDF 原文摘录" in html
        assert "Cornerstone Investors" in html
        assert "A &lt; B &amp; C" in html
