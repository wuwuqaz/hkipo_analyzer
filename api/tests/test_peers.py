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
    import api.workers.analyze_worker as analyze_worker
    from ipo_analyzer.peer_data import PeerMetricsUpdater

    monkeypatch.setattr(analyze_worker, "run_upload_analysis", lambda *a, **k: None)
    monkeypatch.setattr(analyze_worker, "run_reanalyze", lambda *a, **k: None)
    monkeypatch.setattr(analyze_router, "run_upload_analysis", lambda *a, **k: None)
    monkeypatch.setattr(analyze_router, "run_reanalyze", lambda *a, **k: None)
    monkeypatch.setattr(
        PeerMetricsUpdater,
        "update_all",
        lambda self, stale_only=True, dry_run=True: {
            "total": 0,
            "processed": 0,
            "updated": 0,
            "skipped": 0,
            "failed": 0,
            "details": [],
        },
    )

    from api.config import get_config
    from api.main import app
    from api.services.history_service import HistoryService

    config = get_config()
    history_svc = HistoryService(str(config.db_path))
    history_svc.init_db()

    yield TestClient(app)


class TestPeersList:
    def test_list_peers_returns_200(self, client):
        response = client.get("/api/peers/")
        assert response.status_code == 200

    def test_list_peers_structure(self, client):
        response = client.get("/api/peers/")
        data = response.json()
        assert "peers" in data
        assert "total" in data
        assert "sectors" in data
        assert "subsectors" in data
        assert isinstance(data["peers"], list)
        assert isinstance(data["total"], int)
        assert isinstance(data["sectors"], list)
        assert isinstance(data["subsectors"], list)

    def test_list_peers_with_sector_filter(self, client):
        response = client.get("/api/peers/?sector=Technology")
        assert response.status_code == 200


class TestPeersRefresh:
    def test_refresh_without_token_is_rejected(self, client):
        response = client.post(
            "/api/peers/refresh",
            json={"dry_run": True, "stale_only": True},
        )
        assert response.status_code == 401

    def test_refresh_with_token_returns_200(self, client):
        response = client.post(
            "/api/peers/refresh",
            json={"dry_run": True, "stale_only": True},
            headers=auth_headers(),
        )
        assert response.status_code == 200
        assert response.json()["dry_run"] is True
