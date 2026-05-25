from api.config import get_config
from api import config as config_module
from ipo_analyzer.db_pool import SQLiteConnectionPool
from api.services.history_service import HistoryService
from api.services.storage_service import StorageService
from api.config import APIConfig


def test_get_config_returns_cached_instance(monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_BASE_PATH", str(tmp_path))
    config_module._build_config.cache_clear()

    first = get_config()
    second = get_config()

    assert first is second
    assert first.storage_base_path == tmp_path


def test_history_service_reuses_connection_pool(monkeypatch, tmp_path):
    db_path = tmp_path / "history.db"
    from api.services import history_service as history_service_module

    history_service_module._get_shared_pool.cache_clear()
    service_a = HistoryService(str(db_path))
    service_b = HistoryService(str(db_path))

    pool_a = service_a._get_pool()
    pool_b = service_b._get_pool()

    assert isinstance(pool_a, SQLiteConnectionPool)
    assert pool_a is pool_b


def test_storage_path_validation_rejects_prefix_sibling(tmp_path):
    service = StorageService(APIConfig(storage_base_path=tmp_path / "storage"))
    outside = tmp_path / "storage_evil" / "result.json"
    outside.parent.mkdir()
    outside.write_text("{}", encoding="utf-8")

    try:
        service.validate_path(str(outside))
    except ValueError:
        pass
    else:
        raise AssertionError("Expected prefix sibling path to be rejected")
