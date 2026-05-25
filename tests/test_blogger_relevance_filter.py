from datetime import datetime, timezone, timedelta

import pytest

from ipo_analyzer.blogger_monitor.config import BloggerMonitorConfig
from ipo_analyzer.blogger_monitor.models import SearchResultModel
from ipo_analyzer.blogger_monitor.relevance_filter import RelevanceFilter


@pytest.fixture
def config():
    return BloggerMonitorConfig(
        ipo_keywords=["IPO", "打新", "申购", "新股"],
        opinion_keywords=["看好", "看空", "建议", "观点"],
        max_article_age_months=6,
        min_content_length=200,
    )


@pytest.fixture
def relevance_filter(config):
    return RelevanceFilter(config)


def _make_article(
    title="测试公司IPO打新分析",
    snippet="测试公司(09999)IPO申购建议看好",
    content="",
    published_at=None,
    source_domain="example.com",
):
    full_content = content or f"{title} {snippet} " + "详细内容" * 100
    return SearchResultModel(
        title=title,
        url="https://example.com/article",
        snippet=snippet,
        content=full_content,
        published_at=published_at,
        source_domain=source_domain,
    )


class TestRelevantArticlePasses:
    def test_relevant_article(self, relevance_filter):
        article = _make_article()
        result = relevance_filter.filter(article, "09999", "测试公司")
        assert result.is_relevant is True
        assert result.relevance_score > 0.0


class TestSameNameCompanyFiltered:
    def test_company_name_without_ipo_keywords(self, relevance_filter):
        article = _make_article(
            title="测试公司年度报告",
            snippet="测试公司发布了年度报告",
            content="测试公司发布了年度报告" + "详细内容" * 100,
        )
        result = relevance_filter.filter(article, "09999", "测试公司")
        assert result.is_relevant is False
        assert "同名公司" in result.reason or "IPO关键词" in result.reason


class TestPureAnnouncementFiltered:
    def test_no_opinion_keywords(self, relevance_filter):
        article = _make_article(
            title="测试公司IPO公告",
            snippet="测试公司(09999)IPO招股书已发布",
            content="测试公司(09999)IPO招股书已发布" + "详细内容" * 100,
        )
        result = relevance_filter.filter(article, "09999", "测试公司")
        assert result.contains_opinion is False


class TestOldArticleFiltered:
    def test_old_article_filtered(self, relevance_filter):
        old_date = (datetime.now(tz=timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%d")
        article = _make_article(published_at=old_date)
        result = relevance_filter.filter(article, "09999", "测试公司")
        assert result.is_relevant is False
        assert "过旧" in result.reason


class TestShortContentFiltered:
    def test_short_content_filtered(self):
        cfg = BloggerMonitorConfig(
            ipo_keywords=["IPO"],
            opinion_keywords=["看好"],
            min_content_length=500,
        )
        f = RelevanceFilter(cfg)
        article = SearchResultModel(
            title="测试公司IPO看好",
            snippet="测试公司(09999)IPO看好",
            content="短内容",
            published_at=None,
        )
        result = f.filter(article, "09999", "测试公司")
        assert result.is_relevant is False
        assert "长度不足" in result.reason

    def test_short_but_strong_ipo_context_can_pass(self):
        cfg = BloggerMonitorConfig(
            ipo_keywords=["IPO", "打新", "申购", "新股"],
            opinion_keywords=["看好", "建议", "分析"],
            min_content_length=500,
        )
        f = RelevanceFilter(cfg)
        article = SearchResultModel(
            title="测试公司 IPO 打新分析",
            url="https://example.com/article",
            snippet="测试公司(09999) IPO 申购建议",
            content="测试公司(09999) IPO 打新分析，建议申购，核心看点是估值和赛道。",
            published_at=None,
            source_domain="example.com",
        )
        result = f.filter(article, "09999", "测试公司")
        assert result.is_relevant is True
        assert result.relevance_score > 0.0


class TestRelevanceScore:
    def test_score_increases_with_opinion(self, relevance_filter):
        article_with_opinion = _make_article(
            snippet="测试公司(09999)IPO看好建议申购",
        )
        article_without_opinion = _make_article(
            snippet="测试公司(09999)IPO招股书发布",
        )
        r_with = relevance_filter.filter(article_with_opinion, "09999", "测试公司")
        r_without = relevance_filter.filter(article_without_opinion, "09999", "测试公司")
        assert r_with.relevance_score >= r_without.relevance_score

    def test_score_within_range(self, relevance_filter):
        article = _make_article()
        result = relevance_filter.filter(article, "09999", "测试公司")
        assert 0.0 <= result.relevance_score <= 1.0

    def test_no_company_no_stock_code(self, relevance_filter):
        article = _make_article(
            title="市场综述",
            snippet="今日市场整体上涨",
            content="今日市场整体上涨" + "详细内容" * 100,
        )
        result = relevance_filter.filter(article, "09999", "测试公司")
        assert result.is_relevant is False
