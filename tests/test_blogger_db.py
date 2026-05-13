import pytest

from ipo_analyzer.blogger_monitor.db import BloggerMonitorDB


@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "test_blogger.db")
    instance = BloggerMonitorDB(db_path)
    yield instance
    instance.close()


def _make_post(stock_code="09999", url="https://example.com/post1", **overrides):
    post = {
        "stock_code": stock_code,
        "keyword": "测试公司 IPO",
        "search_source": "tavily",
        "search_rank": 1,
        "url": url,
        "canonical_url": url,
        "domain": "example.com",
        "content_hash": "abc123def456",
        "title": "测试文章",
        "author": "博主A",
        "source": "example.com",
        "published_at": "2026-01-01",
        "raw_content": "文章内容",
        "content_length": 4,
        "fetch_status": "pending",
        "fetched_at": "2026-01-01T00:00:00+00:00",
    }
    post.update(overrides)
    return post


def _make_analysis(post_id=1, stock_code="09999", **overrides):
    analysis = {
        "post_id": post_id,
        "stock_code": stock_code,
        "company_name": "测试公司",
        "source": "example.com",
        "author": "博主A",
        "author_type": "blogger",
        "title": "测试文章",
        "published_at": "2026-01-01",
        "stance": "positive",
        "stance_score": 80,
        "apply_suggestion": "积极申购",
        "suggested_capital_ratio": "20%",
        "main_reasons": ["理由1", "理由2"],
        "risk_points": ["风险1"],
        "valuation_comment": "估值合理",
        "summary": "看好",
        "confidence_score": 75,
        "evidence_quotes": ["引用1"],
        "is_actionable": True,
        "analysis_status": "completed",
        "analyzed_at": "2026-01-01T00:00:00+00:00",
    }
    analysis.update(overrides)
    return analysis


def _make_consensus(stock_code="09999", **overrides):
    consensus = {
        "stock_code": stock_code,
        "total_posts": 3,
        "positive_count": 2,
        "neutral_count": 1,
        "negative_count": 0,
        "consensus_score": 70.0,
        "top_reasons": ["理由1", "理由2"],
        "top_risks": ["风险1"],
        "representative_posts": [],
        "coverage_score": 60.0,
        "data_quality_warning": "",
        "failed_posts_count": 0,
        "skipped_posts_count": 0,
        "last_error_message": "",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    consensus.update(overrides)
    return consensus


class TestInsertPost:
    def test_insert_post_returns_id(self, db):
        post_id = db.insert_post(_make_post())
        assert post_id is not None
        assert isinstance(post_id, int)

    def test_insert_post_duplicate_returns_none(self, db):
        db.insert_post(_make_post())
        result = db.insert_post(_make_post())
        assert result is None

    def test_insert_post_different_url_succeeds(self, db):
        id1 = db.insert_post(_make_post(url="https://example.com/a"))
        id2 = db.insert_post(_make_post(url="https://example.com/b"))
        assert id1 is not None
        assert id2 is not None
        assert id1 != id2


class TestInsertAnalysis:
    def test_insert_analysis_returns_id(self, db):
        post_id = db.insert_post(_make_post())
        analysis_id = db.insert_analysis(_make_analysis(post_id=post_id))
        assert analysis_id is not None
        assert isinstance(analysis_id, int)

    def test_insert_analysis_json_fields(self, db):
        post_id = db.insert_post(_make_post())
        db.insert_analysis(_make_analysis(post_id=post_id))
        analyses = db.get_analyses_by_stock("09999")
        assert len(analyses) == 1
        assert isinstance(analyses[0]["main_reasons"], list)
        assert len(analyses[0]["main_reasons"]) == 2


class TestUpsertConsensus:
    def test_insert_consensus(self, db):
        db.upsert_consensus(_make_consensus())
        result = db.get_consensus("09999")
        assert result is not None
        assert result["consensus_score"] == 70.0

    def test_update_consensus(self, db):
        db.upsert_consensus(_make_consensus())
        db.upsert_consensus(_make_consensus(consensus_score=85.0))
        result = db.get_consensus("09999")
        assert result["consensus_score"] == 85.0


class TestGetConsensus:
    def test_get_consensus_not_found(self, db):
        result = db.get_consensus("00000")
        assert result is None

    def test_get_consensus_json_fields(self, db):
        db.upsert_consensus(_make_consensus())
        result = db.get_consensus("09999")
        assert isinstance(result["top_reasons"], list)
        assert isinstance(result["top_risks"], list)


class TestGetPostsByStock:
    def test_get_posts_empty(self, db):
        posts = db.get_posts_by_stock("09999")
        assert posts == []

    def test_get_posts_returns_inserted(self, db):
        db.insert_post(_make_post())
        posts = db.get_posts_by_stock("09999")
        assert len(posts) == 1
        assert posts[0]["stock_code"] == "09999"


class TestGetAnalysesByStock:
    def test_get_analyses_empty(self, db):
        analyses = db.get_analyses_by_stock("09999")
        assert analyses == []

    def test_get_analyses_returns_inserted(self, db):
        post_id = db.insert_post(_make_post())
        db.insert_analysis(_make_analysis(post_id=post_id))
        analyses = db.get_analyses_by_stock("09999")
        assert len(analyses) == 1
        assert analyses[0]["stance"] == "positive"


class TestPostExists:
    def test_post_exists_true(self, db):
        db.insert_post(_make_post())
        assert db.post_exists("09999", "https://example.com/post1", "abc123def456") is True

    def test_post_exists_false(self, db):
        assert db.post_exists("09999", "https://example.com/post1", "abc123def456") is False


class TestGetPendingPosts:
    def test_no_pending_posts(self, db):
        db.insert_post(_make_post(fetch_status="pending"))
        pending = db.get_pending_posts("09999")
        assert pending == []

    def test_pending_posts_with_fetched_and_no_analysis(self, db):
        post_id = db.insert_post(_make_post(fetch_status="fetched"))
        pending = db.get_pending_posts("09999")
        assert len(pending) == 1
        assert pending[0]["id"] == post_id

    def test_fetched_with_analysis_not_pending(self, db):
        post_id = db.insert_post(_make_post(fetch_status="fetched"))
        db.insert_analysis(_make_analysis(post_id=post_id))
        pending = db.get_pending_posts("09999")
        assert pending == []


class TestUpdatePostRelevance:
    def test_update_relevance(self, db):
        post_id = db.insert_post(_make_post())
        db.update_post_relevance(post_id, 0.85)
        posts = db.get_posts_by_stock("09999")
        assert posts[0]["relevance_score"] == 0.85


class TestUpdatePostFetchStatus:
    def test_update_fetch_status(self, db):
        post_id = db.insert_post(_make_post())
        db.update_post_fetch_status(post_id, "analyzed")
        posts = db.get_posts_by_stock("09999")
        assert posts[0]["fetch_status"] == "analyzed"
