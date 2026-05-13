import pytest
from pydantic import ValidationError

from ipo_analyzer.blogger_monitor.models import (
    BloggerOpinionModel,
    ConsensusResultModel,
    RelevanceResultModel,
    SearchResultModel,
)


class TestSearchResultModel:
    def test_create_with_defaults(self):
        m = SearchResultModel()
        assert m.title == ""
        assert m.url == ""
        assert m.snippet == ""
        assert m.content == ""
        assert m.published_at is None
        assert m.source_domain == ""

    def test_create_with_values(self):
        m = SearchResultModel(
            title="测试标题",
            url="https://example.com",
            snippet="摘要",
            content="正文",
            published_at="2026-01-01",
            source_domain="example.com",
        )
        assert m.title == "测试标题"
        assert m.url == "https://example.com"
        assert m.published_at == "2026-01-01"


class TestRelevanceResultModel:
    def test_default_values(self):
        m = RelevanceResultModel()
        assert m.is_relevant is False
        assert m.contains_opinion is False
        assert m.relevance_score == 0.0
        assert m.reason == ""

    def test_valid_score_range(self):
        m = RelevanceResultModel(relevance_score=0.0)
        assert m.relevance_score == 0.0
        m = RelevanceResultModel(relevance_score=1.0)
        assert m.relevance_score == 1.0
        m = RelevanceResultModel(relevance_score=0.5)
        assert m.relevance_score == 0.5

    def test_score_below_zero_raises(self):
        with pytest.raises(ValidationError):
            RelevanceResultModel(relevance_score=-0.1)

    def test_score_above_one_raises(self):
        with pytest.raises(ValidationError):
            RelevanceResultModel(relevance_score=1.1)


class TestBloggerOpinionModel:
    def test_default_values(self):
        m = BloggerOpinionModel()
        assert m.stance == "neutral"
        assert m.stance_score == 50
        assert m.confidence_score == 50
        assert m.main_reasons == []
        assert m.risk_points == []
        assert m.evidence_quotes == []
        assert m.is_actionable is False

    def test_valid_stances(self):
        for stance in ("positive", "neutral", "negative"):
            m = BloggerOpinionModel(stance=stance)
            assert m.stance == stance

    def test_invalid_stance_raises(self):
        with pytest.raises(ValidationError):
            BloggerOpinionModel(stance="bullish")

    def test_stance_score_range(self):
        BloggerOpinionModel(stance_score=0)
        BloggerOpinionModel(stance_score=100)
        with pytest.raises(ValidationError):
            BloggerOpinionModel(stance_score=-1)
        with pytest.raises(ValidationError):
            BloggerOpinionModel(stance_score=101)

    def test_confidence_score_range(self):
        BloggerOpinionModel(confidence_score=0)
        BloggerOpinionModel(confidence_score=100)
        with pytest.raises(ValidationError):
            BloggerOpinionModel(confidence_score=-1)
        with pytest.raises(ValidationError):
            BloggerOpinionModel(confidence_score=101)

    def test_list_fields(self):
        m = BloggerOpinionModel(
            main_reasons=["理由1", "理由2"],
            risk_points=["风险1"],
            evidence_quotes=["引用1"],
        )
        assert len(m.main_reasons) == 2
        assert len(m.risk_points) == 1
        assert len(m.evidence_quotes) == 1


class TestConsensusResultModel:
    def test_default_values(self):
        m = ConsensusResultModel()
        assert m.stock_code == ""
        assert m.total_posts == 0
        assert m.consensus_score == 0.0
        assert m.coverage_score == 0.0
        assert m.top_reasons == []
        assert m.top_risks == []

    def test_consensus_score_range(self):
        ConsensusResultModel(consensus_score=0.0)
        ConsensusResultModel(consensus_score=100.0)
        with pytest.raises(ValidationError):
            ConsensusResultModel(consensus_score=-0.1)
        with pytest.raises(ValidationError):
            ConsensusResultModel(consensus_score=100.1)

    def test_coverage_score_range(self):
        ConsensusResultModel(coverage_score=0.0)
        ConsensusResultModel(coverage_score=100.0)
        with pytest.raises(ValidationError):
            ConsensusResultModel(coverage_score=-1.0)
        with pytest.raises(ValidationError):
            ConsensusResultModel(coverage_score=101.0)
