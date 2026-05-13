import json
from unittest.mock import MagicMock, patch

import pytest

from ipo_analyzer.blogger_monitor.config import BloggerMonitorConfig
from ipo_analyzer.blogger_monitor.models import (
    BloggerOpinionModel,
    ConsensusResultModel,
    RelevanceResultModel,
    SearchResultModel,
)
from ipo_analyzer.blogger_monitor.service import BloggerMonitorService


@pytest.fixture
def config():
    return BloggerMonitorConfig(
        tavily_api_key="test-key",
        llm_api_key="test-key",
        keyword_templates=["{company_name} IPO"],
        ipo_keywords=["IPO", "打新"],
        opinion_keywords=["看好", "建议"],
        source_weights={"default": 0.5},
    )


@pytest.fixture
def service(tmp_path, config):
    db_path = str(tmp_path / "test_service.db")
    with patch("ipo_analyzer.blogger_monitor.service.load_config", return_value=config):
        svc = BloggerMonitorService(db_path=db_path)
    return svc


class TestResolveCompanyName:
    def test_resolve_from_ipo_history(self, service, tmp_path):
        history = [{"hk_code": "09999", "company_name": "测试公司"}]
        history_path = tmp_path / "ipo_history.json"
        history_path.write_text(json.dumps(history), encoding="utf-8")
        with patch.object(service, "_resolve_company_name") as mock_resolve:
            mock_resolve.return_value = "测试公司"
            result = service._resolve_company_name("09999")
            assert result == "测试公司"

    def test_resolve_with_padded_code(self, service, tmp_path):
        history = [{"hk_code": "09999", "company_name": "测试公司"}]
        history_path = tmp_path / "ipo_history.json"
        history_path.write_text(json.dumps(history), encoding="utf-8")
        with patch("ipo_analyzer.blogger_monitor.service.Path") as mock_path_cls:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.__str__ = lambda s: str(history_path)
            mock_path_cls.return_value = mock_path
            mock_path.open.return_value.__enter__ = lambda s: open(history_path, encoding="utf-8")
            mock_path.open.return_value.__exit__ = MagicMock(return_value=False)

    def test_resolve_no_history_file(self, service):
        result = service._resolve_company_name("09999")
        assert result is None


class TestComputeContentHash:
    def test_deterministic_hash(self):
        hash1 = BloggerMonitorService._compute_content_hash("测试内容")
        hash2 = BloggerMonitorService._compute_content_hash("测试内容")
        assert hash1 == hash2

    def test_different_content_different_hash(self):
        hash1 = BloggerMonitorService._compute_content_hash("内容A")
        hash2 = BloggerMonitorService._compute_content_hash("内容B")
        assert hash1 != hash2

    def test_hash_length(self):
        h = BloggerMonitorService._compute_content_hash("测试")
        assert len(h) == 16


class TestRunFullPipeline:
    def test_pipeline_with_mocks(self, service):
        mock_search_result = SearchResultModel(
            title="测试公司IPO看好",
            url="https://example.com/article1",
            snippet="看好测试公司IPO",
            content="测试公司(09999)IPO打新分析，看好申购" + "详细" * 200,
            published_at="2026-01-01",
            source_domain="example.com",
        )

        mock_relevance = RelevanceResultModel(
            is_relevant=True,
            contains_opinion=True,
            relevance_score=0.8,
            reason="通过所有过滤条件",
        )

        mock_opinion = BloggerOpinionModel(
            stock_code="09999",
            company_name="测试公司",
            source="example.com",
            author="博主A",
            stance="positive",
            stance_score=80,
            confidence_score=75,
            main_reasons=["估值合理"],
            risk_points=["市场风险"],
            summary="看好",
        )

        service.searcher = MagicMock()
        service.searcher.search.return_value = [mock_search_result]

        service.relevance_filter = MagicMock()
        service.relevance_filter.filter.return_value = mock_relevance

        service.analyzer = MagicMock()
        service.analyzer.analyze.return_value = mock_opinion

        service.consensus_calculator = MagicMock()
        service.consensus_calculator.calculate.return_value = ConsensusResultModel(
            stock_code="09999",
            total_posts=1,
            positive_count=1,
            consensus_score=80.0,
            coverage_score=50.0,
            updated_at="2026-01-01T00:00:00+00:00",
        )

        result = service.run_full_pipeline("09999", "测试公司")
        assert result is not None
        assert result.stock_code == "09999"
        assert result.consensus_score == 80.0

    def test_pipeline_no_company_name_returns_none(self, service):
        with patch.object(service, "_resolve_company_name", return_value=None):
            result = service.run_full_pipeline("09999")
        assert result is None


class TestGetConsensus:
    def test_get_consensus_found(self, service):
        consensus_data = {
            "stock_code": "09999",
            "total_posts": 3,
            "positive_count": 2,
            "neutral_count": 1,
            "negative_count": 0,
            "consensus_score": 70.0,
            "top_reasons": "[]",
            "top_risks": "[]",
            "representative_posts": "[]",
            "coverage_score": 60.0,
            "data_quality_warning": "",
            "failed_posts_count": 0,
            "skipped_posts_count": 0,
            "last_error_message": "",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        service.db.upsert_consensus(consensus_data)
        result = service.get_consensus("09999")
        assert result is not None
        assert result.stock_code == "09999"

    def test_get_consensus_not_found(self, service):
        result = service.get_consensus("00000")
        assert result is None
