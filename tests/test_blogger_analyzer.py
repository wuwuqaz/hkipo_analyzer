import pytest

from ipo_analyzer.blogger_monitor.analyzer import BloggerAnalyzer
from ipo_analyzer.blogger_monitor.config import BloggerMonitorConfig
from ipo_analyzer.blogger_monitor.models import SearchResultModel


@pytest.fixture
def config():
    return BloggerMonitorConfig(
        llm_api_key="test-key",
        llm_base_url="https://api.example.com/v1",
        llm_model="test-model",
    )


@pytest.fixture
def analyzer(config):
    return BloggerAnalyzer(config)


def _make_article():
    return SearchResultModel(
        title="测试公司IPO分析",
        url="https://example.com/article",
        snippet="看好测试公司IPO",
        content="测试公司(09999)IPO打新分析，看好申购",
        published_at="2026-01-01",
        source_domain="example.com",
    )


class TestParseJson:
    def test_parse_normal_json(self, analyzer):
        text = '{"stance": "positive", "stance_score": 80}'
        result = analyzer._parse_json(text)
        assert result is not None
        assert result["stance"] == "positive"

    def test_parse_markdown_code_block(self, analyzer):
        text = '```json\n{"stance": "neutral", "stance_score": 50}\n```'
        result = analyzer._parse_json(text)
        assert result is not None
        assert result["stance"] == "neutral"

    def test_parse_markdown_without_language(self, analyzer):
        text = '```\n{"stance": "negative", "stance_score": 20}\n```'
        result = analyzer._parse_json(text)
        assert result is not None
        assert result["stance"] == "negative"

    def test_parse_brace_extraction(self, analyzer):
        text = '分析结果如下：{"stance": "positive", "stance_score": 75} 以上是结果。'
        result = analyzer._parse_json(text)
        assert result is not None
        assert result["stance_score"] == 75

    def test_parse_invalid_returns_none(self, analyzer):
        result = analyzer._parse_json("not json at all")
        assert result is None


class TestRepairJson:
    def test_trailing_comma_repair(self, analyzer):
        text = '{"stance": "positive", "main_reasons": ["a", "b",]}'
        result = analyzer._repair_json(text)
        assert result is not None
        assert result["stance"] == "positive"

    def test_single_quote_repair(self, analyzer):
        text = "{'stance': 'positive', 'stance_score': 80}"
        result = analyzer._repair_json(text)
        assert result is not None
        assert result["stance"] == "positive"

    def test_python_bool_repair(self, analyzer):
        text = '{"is_actionable": True, "stance_score": 50}'
        result = analyzer._repair_json(text)
        assert result is not None
        assert result["is_actionable"] is True

    def test_none_repair(self, analyzer):
        text = '{"value": None}'
        result = analyzer._repair_json(text)
        assert result is not None
        assert result["value"] is None

    def test_unrepairable_returns_none(self, analyzer):
        result = analyzer._repair_json("no braces here")
        assert result is None


class TestValidateWithPydantic:
    def test_valid_data(self, analyzer):
        data = {
            "stock_code": "09999",
            "company_name": "测试公司",
            "stance": "positive",
            "stance_score": 80,
            "confidence_score": 75,
        }
        result = analyzer._validate_with_pydantic(data)
        assert result is not None
        assert result.stance == "positive"

    def test_invalid_data_returns_none(self, analyzer):
        data = {"stance": "invalid_stance", "stance_score": 999}
        result = analyzer._validate_with_pydantic(data)
        assert result is None


class TestAnalyzeNoApiKey:
    def test_analyze_returns_none_without_api_key(self):
        cfg = BloggerMonitorConfig(llm_api_key="")
        a = BloggerAnalyzer(cfg)
        article = _make_article()
        result = a.analyze(article, "09999", "测试公司")
        assert result is not None
        assert result.stance == "positive"

    def test_analyze_returns_neutral_fallback_without_sentiment_keywords(self):
        cfg = BloggerMonitorConfig(llm_api_key="")
        a = BloggerAnalyzer(cfg)
        article = SearchResultModel(
            title="测试公司 IPO 打新分析",
            url="https://example.com/article",
            snippet="测试公司(09999) 新股申购要点",
            content="测试公司(09999) IPO 打新分析，介绍招股、估值、赛道与公开发售情况。",
            published_at="2026-01-01",
            source_domain="example.com",
        )
        result = a.analyze(article, "09999", "测试公司")
        assert result is not None
        assert result.stance == "neutral"
        assert "IPO相关" in result.summary
