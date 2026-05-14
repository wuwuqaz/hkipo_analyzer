import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class APIConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    storage_base_path: Path = field(default_factory=lambda: Path(os.getenv("STORAGE_BASE_PATH", "storage")))
    max_concurrent_analyses: int = 2
    api_token_env: str = "HKIPO_API_TOKEN"
    cors_origins: list[str] = field(default_factory=lambda: [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ])
    db_path: Path = field(default_factory=lambda: Path(os.getenv("STORAGE_BASE_PATH", "storage")) / "history.db")

    def __post_init__(self):
        if isinstance(self.storage_base_path, str):
            self.storage_base_path = Path(self.storage_base_path)
        if isinstance(self.db_path, str):
            self.db_path = Path(self.db_path)
        self.max_concurrent_analyses = int(os.getenv("MAX_CONCURRENT_ANALYSES", str(self.max_concurrent_analyses)))
        self.host = os.getenv("API_HOST", self.host)
        self.port = int(os.getenv("API_PORT", str(self.port)))
        cors_raw = os.getenv("CORS_ORIGINS")
        if cors_raw:
            self.cors_origins = [origin.strip() for origin in cors_raw.split(",") if origin.strip()]


def get_config() -> APIConfig:
    return APIConfig()
