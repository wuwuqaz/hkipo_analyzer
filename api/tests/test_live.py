import os
import tempfile

import pytest
from fastapi.testclient import TestClient

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
    import api.routers.live as live_router
    import api.workers.analyze_worker as analyze_worker

    monkeypatch.setattr(analyze_worker, "run_upload_analysis", lambda *a, **k: None)
    monkeypatch.setattr(analyze_worker, "run_reanalyze", lambda *a, **k: None)
    monkeypatch.setattr(analyze_router, "run_upload_analysis", lambda *a, **k: None)
    monkeypatch.setattr(analyze_router, "run_reanalyze", lambda *a, **k: None)

    def fake_run_live_analysis(job_id, force_refresh=False, output_dir="temp"):
        pass

    monkeypatch.setattr(analyze_worker, "run_live_analysis", fake_run_live_analysis)
    monkeypatch.setattr(live_router, "run_live_analysis", fake_run_live_analysis)
    monkeypatch.setattr(live_router, "_load_cached_results", lambda output_dir="temp": ([], None))

    from api.config import get_config
    from api.main import app
    from api.services.history_service import HistoryService

    config = get_config()
    history_svc = HistoryService(str(config.db_path))
    history_svc.init_db()

    yield TestClient(app)


class TestLiveResults:
    def test_get_live_results_empty(self, client):
        response = client.get("/api/live/results")
        assert response.status_code == 200
        data = response.json()
        assert data["results"] == []
        assert data["total"] == 0

    def test_get_live_results_structure(self, client):
        response = client.get("/api/live/results")
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "cache_time" in data
        assert "total" in data


class TestLiveStatus:
    def test_get_live_status_no_running_jobs(self, client):
        response = client.get("/api/live/status")
        assert response.status_code == 200
        data = response.json()
        assert data["has_running_job"] is False


class TestLiveAnalyze:
    def test_trigger_live_analyze_without_token_is_rejected(self, client):
        response = client.post("/api/live/analyze", json={})
        assert response.status_code == 401

    def test_trigger_live_analyze_with_token_creates_job(self, client):
        response = client.post("/api/live/analyze", json={}, headers=auth_headers())
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert "status" in data
