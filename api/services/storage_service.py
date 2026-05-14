from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from api.config import APIConfig, get_config


class StorageService:
    def __init__(self, config: Optional[APIConfig] = None):
        self.config = config or get_config()
        self.base = self.config.storage_base_path
        self.uploads_dir = self.base / "uploads"
        self.results_dir = self.base / "results"
        self.tmp_dir = self.base / "tmp"

    def ensure_dirs(self):
        self.base.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def upload_path(self, file_uuid: str) -> Path:
        return self.uploads_dir / f"{file_uuid}.pdf"

    def result_path(self, stock_code: str, timestamp: str) -> Path:
        safe_code = stock_code.replace("/", "_").replace("\\", "_")
        safe_ts = timestamp.replace(":", "-").replace(" ", "_")
        return self.results_dir / f"{safe_code}_{safe_ts}.json"

    def save_upload(self, file_bytes: bytes, filename: str) -> Path:
        self.ensure_dirs()
        file_uuid = str(uuid.uuid4())
        dest = self.upload_path(file_uuid)
        dest.write_bytes(file_bytes)
        return dest

    def save_result(self, stock_code: str, data: dict) -> Path:
        self.ensure_dirs()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.result_path(stock_code, ts)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def read_result(self, result_path: str) -> dict:
        p = Path(result_path)
        if not p.exists():
            raise FileNotFoundError(f"Result file not found: {p}")
        return json.loads(p.read_text(encoding="utf-8"))

    def cleanup_tmp(self):
        if self.tmp_dir.exists():
            for item in self.tmp_dir.iterdir():
                if item.name == ".gitkeep":
                    continue
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
