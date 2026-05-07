import os
import time
import logging

from ipo_analyzer.settings import SETTINGS


TEMP_FILE_TTL_SECONDS = SETTINGS.file.temp_file_ttl_days * 86400
MAX_UPLOAD_SIZE_MB = SETTINGS.file.max_upload_size_mb
TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "temp")


def cleanup_temp_files(temp_dir: str, ttl_seconds: float = TEMP_FILE_TTL_SECONDS) -> None:
    prefixes = ("upload_", "IPO分析报告_", "ipo_live_data_")
    now = time.time()
    try:
        for filename in os.listdir(temp_dir):
            if not filename.startswith(prefixes):
                continue
            path = os.path.join(temp_dir, filename)
            if os.path.isfile(path) and now - os.path.getmtime(path) > ttl_seconds:
                os.remove(path)
    except Exception as e:
        logging.getLogger(__name__).warning("临时文件清理失败: %s", e)


def read_file_bytes_and_remove(path: str) -> bytes:
    with open(path, "rb") as f:
        data = f.read()
    try:
        os.remove(path)
    except Exception:
        pass
    return data
