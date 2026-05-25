import os
import tempfile

import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client(monkeypatch):
    tmpdir = tempfile.mkdtemp()
    os.environ["STORAGE_BASE_PATH"] = tmpdir

    import api.routers.analyze as analyze_router
    import api.workers.analyze_worker as analyze_worker

    monkeypatch.setattr(analyze_worker, "run_upload_analysis", lambda *a, **k: None)
    monkeypatch.setattr(analyze_worker, "run_reanalyze", lambda *a, **k: None)
    monkeypatch.setattr(analyze_router, "run_upload_analysis", lambda *a, **k: None)
    monkeypatch.setattr(analyze_router, "run_reanalyze", lambda *a, **k: None)

    from api.config import get_config
    from api.main import app
    from api.services.history_service import HistoryService

    config = get_config()
    history_svc = HistoryService(str(config.db_path))
    history_svc.init_db()

    yield TestClient(app)


class TestHistoryRecords:
    def test_list_history_records_empty(self, client):
        response = client.get("/api/history/records")
        assert response.status_code == 200
        data = response.json()
        assert data["records"] == []
        assert data["total"] == 0

    def test_list_history_records_structure(self, client):
        response = client.get("/api/history/records")
        assert response.status_code == 200
        data = response.json()
        assert "records" in data
        assert "total" in data
        assert isinstance(data["records"], list)
        assert isinstance(data["total"], int)


class TestHistoryRecordDetail:
    def test_get_nonexistent_record_returns_404(self, client):
        response = client.get("/api/history/records/00000")
        assert response.status_code == 404


class TestHistoryExport:
    def test_export_without_token_returns_200(self, client):
        response = client.get("/api/history/export")
        assert response.status_code == 200
