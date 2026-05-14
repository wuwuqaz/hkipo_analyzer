import os
import tempfile

import pytest
from fastapi.testclient import TestClient


TEST_TOKEN = "test-api-token-12345"


@pytest.fixture
def client_with_token(monkeypatch):
    tmpdir = tempfile.mkdtemp()
    os.environ["STORAGE_BASE_PATH"] = tmpdir
    os.environ["HKIPO_API_TOKEN"] = TEST_TOKEN

    # Patch worker before importing app
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


@pytest.fixture
def client_no_token(monkeypatch):
    tmpdir = tempfile.mkdtemp()
    os.environ["STORAGE_BASE_PATH"] = tmpdir
    os.environ.pop("HKIPO_API_TOKEN", None)

    # Patch worker before importing app
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


def _auth_headers(token: str = TEST_TOKEN):
    return {"Authorization": f"Bearer {token}"}


class TestTokenNotConfigured:
    def test_upload_returns_503_when_token_not_set(self, client_no_token):
        response = client_no_token.post(
            "/api/analyze/upload",
            files={"pdf": ("test.pdf", b"%PDF-1.4 fake", "application/pdf")},
            headers=_auth_headers(),
        )
        assert response.status_code == 503
        assert "not configured" in response.json()["detail"]

    def test_reanalyze_returns_503_when_token_not_set(self, client_no_token):
        response = client_no_token.post(
            "/api/analyze/reanalyze",
            json={"stock_code": "09995"},
            headers=_auth_headers(),
        )
        assert response.status_code == 503


class TestMissingToken:
    def test_upload_without_header_returns_401(self, client_with_token):
        response = client_with_token.post(
            "/api/analyze/upload",
            files={"pdf": ("test.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
        assert response.status_code == 401
        assert "Missing" in response.json()["detail"]

    def test_reanalyze_without_header_returns_401(self, client_with_token):
        response = client_with_token.post(
            "/api/analyze/reanalyze",
            json={"stock_code": "09995"},
        )
        assert response.status_code == 401


class TestInvalidToken:
    def test_upload_with_wrong_token_returns_401(self, client_with_token):
        response = client_with_token.post(
            "/api/analyze/upload",
            files={"pdf": ("test.pdf", b"%PDF-1.4 fake", "application/pdf")},
            headers=_auth_headers("wrong-token"),
        )
        assert response.status_code == 401
        assert "Invalid" in response.json()["detail"]

    def test_reanalyze_with_wrong_token_returns_401(self, client_with_token):
        response = client_with_token.post(
            "/api/analyze/reanalyze",
            json={"stock_code": "09995"},
            headers=_auth_headers("wrong-token"),
        )
        assert response.status_code == 401


class TestValidToken:
    def test_upload_with_correct_token_succeeds(self, client_with_token):
        response = client_with_token.post(
            "/api/analyze/upload",
            files={"pdf": ("test.pdf", b"%PDF-1.4 fake", "application/pdf")},
            headers=_auth_headers(),
        )
        assert response.status_code == 200
        assert "job_id" in response.json()

    def test_reanalyze_with_correct_token_succeeds(self, client_with_token):
        response = client_with_token.post(
            "/api/analyze/reanalyze",
            json={"stock_code": "09995", "company_name": "Demo"},
            headers=_auth_headers(),
        )
        assert response.status_code == 200
        assert "job_id" in response.json()


class TestPublicEndpointsNoAuthRequired:
    def test_health_no_token(self, client_with_token):
        response = client_with_token.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_version_no_token(self, client_with_token):
        response = client_with_token.get("/api/version")
        assert response.status_code == 200
        assert "app_version" in response.json()

    def test_get_job_status_no_token(self, client_with_token):
        # First create a job with token
        upload_resp = client_with_token.post(
            "/api/analyze/upload",
            files={"pdf": ("test.pdf", b"%PDF-1.4 fake", "application/pdf")},
            headers=_auth_headers(),
        )
        job_id = upload_resp.json()["job_id"]

        # Then query without token
        response = client_with_token.get(f"/api/analyze/jobs/{job_id}")
        assert response.status_code == 200
        assert response.json()["job_id"] == job_id

    def test_get_job_result_no_token(self, client_with_token):
        # First create a job with token
        upload_resp = client_with_token.post(
            "/api/analyze/upload",
            files={"pdf": ("test.pdf", b"%PDF-1.4 fake", "application/pdf")},
            headers=_auth_headers(),
        )
        job_id = upload_resp.json()["job_id"]

        # Query result without token (will be 409 since job is queued, not 401)
        response = client_with_token.get(f"/api/analyze/jobs/{job_id}/result")
        assert response.status_code == 409
        assert "only available" in response.json()["detail"]
