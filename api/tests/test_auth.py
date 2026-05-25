import os
import tempfile

import pytest
from fastapi.testclient import TestClient

TEST_TOKEN = "test-api-token"


def auth_headers(token: str = TEST_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client_with_token(monkeypatch):
    tmpdir = tempfile.mkdtemp()
    os.environ["STORAGE_BASE_PATH"] = tmpdir
    os.environ["HKIPO_API_TOKEN"] = TEST_TOKEN
    os.environ["HKIPO_REQUIRE_API_TOKEN"] = "true"

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
    HistoryService(str(config.db_path)).init_db()
    yield TestClient(app)


@pytest.fixture
def client_without_configured_token(monkeypatch):
    tmpdir = tempfile.mkdtemp()
    os.environ["STORAGE_BASE_PATH"] = tmpdir
    os.environ.pop("HKIPO_API_TOKEN", None)
    os.environ["HKIPO_REQUIRE_API_TOKEN"] = "true"

    from api.config import get_config
    from api.main import app
    from api.services.history_service import HistoryService

    config = get_config()
    HistoryService(str(config.db_path)).init_db()
    yield TestClient(app)


@pytest.fixture
def client_without_required_token(monkeypatch):
    tmpdir = tempfile.mkdtemp()
    os.environ["STORAGE_BASE_PATH"] = tmpdir
    os.environ.pop("HKIPO_REQUIRE_API_TOKEN", None)
    os.environ.pop("HKIPO_API_TOKEN", None)

    import api.routers.analyze as analyze_router
    import api.workers.analyze_worker as analyze_worker

    monkeypatch.setattr(analyze_worker, "run_reanalyze", lambda *a, **k: None)
    monkeypatch.setattr(analyze_router, "run_reanalyze", lambda *a, **k: None)

    from api.config import get_config
    from api.main import app
    from api.services.history_service import HistoryService

    config = get_config()
    HistoryService(str(config.db_path)).init_db()
    yield TestClient(app)


def test_missing_token_returns_401(client_with_token):
    response = client_with_token.post(
        "/api/analyze/upload",
        files={"pdf": ("test.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert response.status_code == 401


def test_invalid_token_returns_401(client_with_token):
    response = client_with_token.post(
        "/api/analyze/upload",
        files={"pdf": ("test.pdf", b"%PDF-1.4 fake", "application/pdf")},
        headers=auth_headers("wrong-token"),
    )
    assert response.status_code == 401


def test_valid_bearer_token_passes(client_with_token):
    response = client_with_token.post(
        "/api/analyze/upload",
        files={"pdf": ("test.pdf", b"%PDF-1.4 fake", "application/pdf")},
        headers=auth_headers(),
    )
    assert response.status_code == 200


def test_unconfigured_token_returns_503(client_without_configured_token):
    response = client_without_configured_token.post(
        "/api/analyze/reanalyze",
        json={"stock_code": "09995"},
        headers=auth_headers(),
    )
    assert response.status_code == 503


def test_token_not_required_by_default(client_without_required_token):
    response = client_without_required_token.post(
        "/api/analyze/reanalyze",
        json={"stock_code": "09995"},
    )
    assert response.status_code == 200
