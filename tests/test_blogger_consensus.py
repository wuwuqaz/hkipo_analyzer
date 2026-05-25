from datetime import datetime, timezone, timedelta

import pytest

from ipo_analyzer.blogger_monitor.config import BloggerMonitorConfig
from ipo_analyzer.blogger_monitor.consensus import ConsensusCalculator


@pytest.fixture
def config():
    return BloggerMonitorConfig(
        source_weights={"xueqiu.com": 0.8, "eastmoney.com": 0.7, "default": 0.5},
    )


@pytest.fixture
def calculator(config):
    return ConsensusCalculator(config)


def _make_analysis(stance="positive", stance_score=80, **overrides):
    data = {
        "post_id": 1,
        "stance": stance,
        "stance_score": stance_score,
        "main_reasons": ["理由1", "理由2"],
        "risk_points": ["风险1"],
        "evidence_quotes": ["引用1", "引用2"],
        "title": "测试文章",
        "author": "博主A",
        "source": "xueqiu.com",
        "summary": "看好这只新股",
        "apply_suggestion": "积极申购",
    }
    data.update(overrides)
    return data


def _make_post(
    post_id=1,
    domain="example.com",
    fetched_at=None,
    relevance_score=0.8,
    content_length=1000,
):
    if fetched_at is None:
        fetched_at = datetime.now(tz=timezone.utc).isoformat()
    return {
        "id": post_id,
        "domain": domain,
        "fetched_at": fetched_at,
        "relevance_score": relevance_score,
        "content_length": content_length,
        "url": f"https://example.com/post{post_id}",
    }


class TestCountStances:
    def test_count_stances(self, calculator):
        analyses = [
            _make_analysis(stance="positive"),
            _make_analysis(stance="positive"),
            _make_analysis(stance="neutral"),
            _make_analysis(stance="negative"),
        ]
        pos, neu, neg = calculator._count_stances(analyses)
        assert pos == 2
        assert neu == 1
        assert neg == 1

    def test_empty_analyses(self, calculator):
        pos, neu, neg = calculator._count_stances([])
        assert pos == 0
        assert neu == 0
        assert neg == 0


class TestCalculateConsensusScore:
    def test_weighted_calculation(self, calculator):
        analyses = [
            _make_analysis(stance="positive", stance_score=80, post_id=1),
            _make_analysis(stance="negative", stance_score=20, post_id=2),
        ]
        posts = [
            _make_post(post_id=1, domain="xueqiu.com", relevance_score=0.9, content_length=1000),
            _make_post(post_id=2, domain="eastmoney.com", relevance_score=0.7, content_length=500),
        ]
        score = calculator._calculate_consensus_score(analyses, posts)
        assert 0.0 <= score <= 100.0

    def test_empty_analyses_returns_zero(self, calculator):
        score = calculator._calculate_consensus_score([], [])
        assert score == 0.0


class TestGetRecencyWeight:
    def test_recent_within_7_days(self, calculator):
        recent = (datetime.now(tz=timezone.utc) - timedelta(days=3)).isoformat()
        assert calculator._get_recency_weight(recent) == 1.0

    def test_within_30_days(self, calculator):
        mid = (datetime.now(tz=timezone.utc) - timedelta(days=15)).isoformat()
        assert calculator._get_recency_weight(mid) == 0.7

    def test_older_than_30_days(self, calculator):
        old = (datetime.now(tz=timezone.utc) - timedelta(days=60)).isoformat()
        assert calculator._get_recency_weight(old) == 0.4

    def test_empty_fetched_at(self, calculator):
        assert calculator._get_recency_weight("") == 0.4


class TestGetSourceWeight:
    def test_known_domain(self, calculator):
        assert calculator._get_source_weight("xueqiu.com") == 0.8

    def test_unknown_domain_uses_default(self, calculator):
        assert calculator._get_source_weight("unknown.com") == 0.5


class TestGetContentQualityWeight:
    def test_high_quality(self, calculator):
        assert calculator._get_content_quality_weight(1000, ["q1", "q2"]) == 1.0

    def test_medium_quality(self, calculator):
        assert calculator._get_content_quality_weight(500, ["q1"]) == 0.8

    def test_low_quality(self, calculator):
        assert calculator._get_content_quality_weight(200, []) == 0.6

    def test_very_low_quality(self, calculator):
        assert calculator._get_content_quality_weight(50, []) == 0.4


class TestExtractTopItems:
    def test_extract_top_reasons(self, calculator):
        analyses = [
            _make_analysis(main_reasons=["估值合理", "行业前景好"]),
            _make_analysis(main_reasons=["估值合理", "基石投资者强"]),
            _make_analysis(main_reasons=["行业前景好"]),
        ]
        top = calculator._extract_top_items(analyses, "main_reasons")
        assert top[0] == "估值合理"
        assert len(top) <= 5

    def test_empty_analyses(self, calculator):
        assert calculator._extract_top_items([], "main_reasons") == []

    def test_json_string_field(self, calculator):
        analyses = [{"main_reasons": '["理由1", "理由2"]'}]
        top = calculator._extract_top_items(analyses, "main_reasons")
        assert "理由1" in top


class TestCalculateCoverageScore:
    def test_zero_posts(self, calculator):
        assert calculator._calculate_coverage_score(0, [], []) == 0.0

    def test_few_posts(self, calculator):
        posts = [_make_post(post_id=i, domain=f"domain{i}.com") for i in range(2)]
        score = calculator._calculate_coverage_score(2, [], posts)
        assert 0.0 < score < 100.0

    def test_many_posts_with_diversity(self, calculator):
        posts = [_make_post(post_id=i, domain=f"domain{i}.com") for i in range(10)]
        score = calculator._calculate_coverage_score(10, [], posts)
        assert score > 60.0

    def test_score_capped_at_100(self, calculator):
        posts = [_make_post(post_id=i, domain=f"domain{i}.com") for i in range(50)]
        score = calculator._calculate_coverage_score(50, [], posts)
        assert score <= 100.0


class TestGenerateQualityWarning:
    def test_no_posts(self, calculator):
        assert calculator._generate_quality_warning(0.0, 0) == "暂无博主观点数据"

    def test_low_coverage(self, calculator):
        assert "不可靠" in calculator._generate_quality_warning(20.0, 2)

    def test_medium_coverage(self, calculator):
        assert "仅供参考" in calculator._generate_quality_warning(40.0, 3)

    def test_good_coverage(self, calculator):
        assert calculator._generate_quality_warning(70.0, 5) == ""


class TestCalculateFullFlow:
    def test_full_calculate(self, calculator):
        analyses = [
            _make_analysis(stance="positive", stance_score=80, post_id=1),
            _make_analysis(stance="neutral", stance_score=50, post_id=2),
        ]
        posts = [
            _make_post(post_id=1, domain="xueqiu.com"),
            _make_post(post_id=2, domain="eastmoney.com"),
        ]
        result = calculator.calculate("09999", analyses, posts)
        assert result.stock_code == "09999"
        assert result.total_posts == 2
        assert result.positive_count == 1
        assert result.neutral_count == 1
        assert result.negative_count == 0
        assert 0.0 <= result.consensus_score <= 100.0
        assert 0.0 <= result.coverage_score <= 100.0
        assert len(result.top_reasons) > 0
        assert result.representative_posts
        rep = result.representative_posts[0]
        assert rep["source"] == "xueqiu.com"
        assert rep["summary"] == "看好这只新股"
        assert rep["apply_suggestion"] == "积极申购"

    def test_empty_analyses_and_posts(self, calculator):
        result = calculator.calculate("09999", [], [])
        assert result.total_posts == 0
        assert result.consensus_score == 0.0
        assert result.data_quality_warning == "暂无博主观点数据"
