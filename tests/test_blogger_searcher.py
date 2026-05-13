from unittest.mock import MagicMock, patch

import pytest

from ipo_analyzer.blogger_monitor.config import BloggerMonitorConfig
from ipo_analyzer.blogger_monitor.searcher import BloggerSearcher


@pytest.fixture
def config():
    return BloggerMonitorConfig(
        tavily_api_key="test-key",
        keyword_templates=[
            "{company_name} IPO 打新",
            "{stock_code} 港股 新股",
        ],
        max_results_per_keyword=5,
    )


@pytest.fixture
def searcher(config):
    return BloggerSearcher(config)


class TestGenerateKeywords:
    def test_generate_keywords(self, searcher):
        keywords = searcher.generate_keywords("测试公司", "09999")
        assert len(keywords) == 2
        assert "测试公司 IPO 打新" in keywords
        assert "09999 港股 新股" in keywords

    def test_generate_keywords_empty_templates(self):
        cfg = BloggerMonitorConfig(tavily_api_key="test-key", keyword_templates=[])
        s = BloggerSearcher(cfg)
        assert s.generate_keywords("公司", "09999") == []


class TestCanonicalizeUrl:
    def test_removes_tracking_params(self):
        url = "https://www.example.com/path?utm_source=twitter&id=123"
        result = BloggerSearcher.canonicalize_url(url)
        assert "utm_source" not in result
        assert "id=123" in result

    def test_removes_www_prefix(self):
        url = "https://www.example.com/path"
        result = BloggerSearcher.canonicalize_url(url)
        assert result.startswith("https://example.com")

    def test_removes_trailing_slash(self):
        url = "https://example.com/path/"
        result = BloggerSearcher.canonicalize_url(url)
        assert not result.rstrip("/").endswith("//")

    def test_lowercases_scheme_and_host(self):
        url = "HTTPS://EXAMPLE.COM/Path"
        result = BloggerSearcher.canonicalize_url(url)
        assert result.startswith("https://example.com")

    def test_sorts_query_params(self):
        url = "https://example.com/path?b=2&a=1"
        result = BloggerSearcher.canonicalize_url(url)
        assert result.index("a=1") < result.index("b=2")

    def test_removes_fbclid(self):
        url = "https://example.com/path?fbclid=abc123&page=1"
        result = BloggerSearcher.canonicalize_url(url)
        assert "fbclid" not in result
        assert "page=1" in result


class TestExtractDomain:
    def test_extracts_domain(self):
        assert BloggerSearcher.extract_domain("https://www.example.com/path") == "example.com"

    def test_removes_www(self):
        assert BloggerSearcher.extract_domain("https://www.blog.example.com/path") == "blog.example.com"

    def test_no_www(self):
        assert BloggerSearcher.extract_domain("https://example.com/path") == "example.com"

    def test_empty_url(self):
        assert BloggerSearcher.extract_domain("") == ""


class TestSearchNoApiKey:
    def test_search_returns_empty_without_api_key(self):
        cfg = BloggerMonitorConfig(tavily_api_key="", keyword_templates=["{company_name}"])
        s = BloggerSearcher(cfg)
        results = s.search("公司", "09999")
        assert results == []


class TestSearchSingleKeyword:
    def test_search_single_keyword_mock(self, searcher):
        mock_client = MagicMock()
        mock_client.search.return_value = {
            "results": [
                {
                    "title": "测试文章",
                    "url": "https://example.com/article1",
                    "content": "摘要内容",
                    "raw_content": "完整内容",
                    "published_date": "2026-01-01",
                }
            ]
        }
        with patch.object(searcher, "_get_client", return_value=mock_client):
            results = searcher._search_single_keyword("测试公司 IPO")
        assert len(results) == 1
        assert results[0].title == "测试文章"
        assert results[0].source_domain == "example.com"

    def test_search_single_keyword_exception(self, searcher):
        mock_client = MagicMock()
        mock_client.search.side_effect = Exception("API error")
        with patch.object(searcher, "_get_client", return_value=mock_client):
            results = searcher._search_single_keyword("测试公司 IPO")
        assert results == []
