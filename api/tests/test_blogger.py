import os
import tempfile
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

TEST_TOKEN = "test-api-token"


def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_TOKEN}"}


@pytest.fixture
def client(monkeypatch):
    tmpdir = tempfile.mkdtemp()
    os.environ["STORAGE_BASE_PATH"] = tmpdir
    os.environ["HKIPO_API_TOKEN"] = TEST_TOKEN
    os.environ["HKIPO_REQUIRE_API_TOKEN"] = "true"

    import api.routers.analyze as analyze_router
    import api.workers.analyze_worker as analyze_worker
    from ipo_analyzer.blogger_monitor.service import BloggerMonitorService

    monkeypatch.setattr(analyze_worker, "run_upload_analysis", lambda *a, **k: None)
    monkeypatch.setattr(analyze_worker, "run_reanalyze", lambda *a, **k: None)
    monkeypatch.setattr(analyze_router, "run_upload_analysis", lambda *a, **k: None)
    monkeypatch.setattr(analyze_router, "run_reanalyze", lambda *a, **k: None)
    monkeypatch.setattr(
        BloggerMonitorService,
        "run_full_pipeline",
        lambda self, stock_code: SimpleNamespace(
            consensus_score=72.5,
            total_posts=1,
            positive_count=1,
            neutral_count=0,
            negative_count=0,
            top_reasons=["热度较高"],
            top_risks=[],
            representative_posts=[],
        ),
    )

    from api.config import get_config
    from api.main import app
    from api.services.history_service import HistoryService

    config = get_config()
    history_svc = HistoryService(str(config.db_path))
    history_svc.init_db()

    mock_db = MagicMock()
    mock_db.close = MagicMock()
    mock_db.get_consensus.return_value = None

    from api.deps import get_blogger_db
    app.dependency_overrides[get_blogger_db] = lambda: mock_db

    test_client = TestClient(app)
    test_client._mock_db = mock_db
    yield test_client

    app.dependency_overrides.clear()


class TestBloggerConsensus:
    def test_get_consensus_no_data(self, client):
        response = client.get("/api/blogger/09995")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] is not None

    def test_get_consensus_returns_stock_code(self, client):
        response = client.get("/api/blogger/09995")
        assert response.status_code == 200
        data = response.json()
        assert data["stock_code"] == "09995"


class TestBloggerSearch:
    def test_search_without_token_is_rejected(self, client):
        response = client.post("/api/blogger/09995/search")
        assert response.status_code == 401

    def test_search_with_token_returns_consensus(self, client):
        response = client.post("/api/blogger/09995/search", headers=auth_headers())
        assert response.status_code == 200
        data = response.json()
        assert data["stock_code"] == "09995"
        assert data["total_posts"] == 1
