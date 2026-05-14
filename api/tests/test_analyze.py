import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


TEST_TOKEN = "test-api-token-12345"


@pytest.fixture
def client(monkeypatch):
    tmpdir = tempfile.mkdtemp()
    os.environ["STORAGE_BASE_PATH"] = tmpdir
    os.environ["HKIPO_API_TOKEN"] = TEST_TOKEN

    calls = []

    def fake_run_upload(job_id, upload_path, stock_code, company_name):
        calls.append(("upload", job_id, upload_path, stock_code, company_name))

    def fake_run_reanalyze(job_id, stock_code, company_name, historical_market_data):
        calls.append(("reanalyze", job_id, stock_code, company_name, historical_market_data))

    # Patch before importing app so routers pick up the fakes
    import api.routers.analyze as analyze_router
    import api.workers.analyze_worker as analyze_worker

    monkeypatch.setattr(analyze_worker, "run_upload_analysis", fake_run_upload)
    monkeypatch.setattr(analyze_worker, "run_reanalyze", fake_run_reanalyze)
    monkeypatch.setattr(analyze_router, "run_upload_analysis", fake_run_upload)
    monkeypatch.setattr(analyze_router, "run_reanalyze", fake_run_reanalyze)

    from api.config import get_config
    from api.main import app
    from api.services.history_service import HistoryService

    config = get_config()
    history_svc = HistoryService(str(config.db_path))
    history_svc.init_db()

    test_client = TestClient(app)
    test_client._worker_calls = calls
    yield test_client


def _auth_headers():
    return {"Authorization": f"Bearer {TEST_TOKEN}"}


class TestUploadAndAnalyze:
    def test_upload_pdf_creates_job(self, client):
        pdf_bytes = b"%PDF-1.4 fake pdf content"
        response = client.post(
            "/api/analyze/upload",
            files={"pdf": ("test.pdf", pdf_bytes, "application/pdf")},
            data={"stock_code": "01234", "company_name": "TestCo"},
            headers=_auth_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "queued"
        assert data["created_at"] is not None

        assert len(client._worker_calls) == 1
        call = client._worker_calls[0]
        assert call[0] == "upload"
        assert call[3] == "01234"
        assert call[4] == "TestCo"

    def test_upload_non_pdf_rejected(self, client):
        response = client.post(
            "/api/analyze/upload",
            files={"pdf": ("test.txt", b"not a pdf", "text/plain")},
            headers=_auth_headers(),
        )
        assert response.status_code == 400
        assert "PDF" in response.json()["detail"]

    def test_upload_empty_pdf_rejected(self, client):
        response = client.post(
            "/api/analyze/upload",
            files={"pdf": ("empty.pdf", b"", "application/pdf")},
            headers=_auth_headers(),
        )
        assert response.status_code == 400
        assert "empty" in response.json()["detail"]

    def test_upload_without_token_returns_401(self, client):
        response = client.post(
            "/api/analyze/upload",
            files={"pdf": ("test.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
        assert response.status_code == 401

    def test_upload_with_wrong_token_returns_401(self, client):
        response = client.post(
            "/api/analyze/upload",
            files={"pdf": ("test.pdf", b"%PDF-1.4 fake", "application/pdf")},
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert response.status_code == 401


class TestReanalyze:
    def test_reanalyze_creates_job(self, client):
        response = client.post(
            "/api/analyze/reanalyze",
            json={"stock_code": "09995", "company_name": "Demo Ltd"},
            headers=_auth_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "queued"

        assert len(client._worker_calls) == 1
        call = client._worker_calls[0]
        assert call[0] == "reanalyze"
        assert call[2] == "09995"
        assert call[3] == "Demo Ltd"

    def test_reanalyze_without_token_returns_401(self, client):
        response = client.post(
            "/api/analyze/reanalyze",
            json={"stock_code": "09995", "company_name": "Demo Ltd"},
        )
        assert response.status_code == 401


class TestJobStatus:
    def test_get_job_status(self, client):
        upload_resp = client.post(
            "/api/analyze/upload",
            files={"pdf": ("test.pdf", b"%PDF-1.4 fake", "application/pdf")},
            headers=_auth_headers(),
        )
        job_id = upload_resp.json()["job_id"]

        response = client.get(f"/api/analyze/jobs/{job_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["status"] == "queued"

    def test_get_nonexistent_job(self, client):
        response = client.get("/api/analyze/jobs/nonexistent-job-id")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


class TestJobResult:
    def test_get_result_before_success(self, client):
        upload_resp = client.post(
            "/api/analyze/upload",
            files={"pdf": ("test.pdf", b"%PDF-1.4 fake", "application/pdf")},
            headers=_auth_headers(),
        )
        job_id = upload_resp.json()["job_id"]

        response = client.get(f"/api/analyze/jobs/{job_id}/result")
        assert response.status_code == 409
        assert "only available" in response.json()["detail"]

    def test_get_result_nonexistent_job(self, client):
        response = client.get("/api/analyze/jobs/nonexistent/result")
        assert response.status_code == 404
