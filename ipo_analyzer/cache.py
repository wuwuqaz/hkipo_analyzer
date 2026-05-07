import os
import json
import logging
import tempfile
from datetime import datetime, timedelta

from .utils import strip_runtime_fields
from .settings import SETTINGS

logger = logging.getLogger(__name__)


class ResultCache:
    CACHE_VERSION = SETTINGS.cache.version

    def __init__(self, cache_dir='temp'):
        self.cache_dir = cache_dir
        self.cache_file = os.path.join(cache_dir, 'results_cache.json')
        os.makedirs(cache_dir, exist_ok=True)

    def load(self):
        if not os.path.exists(self.cache_file):
            return []
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            cutoff = (datetime.now() - timedelta(days=SETTINGS.cache.ttl_days)).isoformat()
            data = [item for item in data if item.get('_cached_at', '') >= cutoff]
            return strip_runtime_fields(data)
        except Exception as e:
            logger.warning(f"缓存加载失败: {e}")
            return []

    def save(self, results):
        try:
            cached_results = strip_runtime_fields(results)
            cached_at = datetime.now().isoformat()
            for item in cached_results:
                item['_cached_at'] = cached_at
                item['_cache_version'] = self.CACHE_VERSION

            fd, tmp_file = tempfile.mkstemp(prefix='results_cache_', suffix='.tmp', dir=self.cache_dir)
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(cached_results, f, ensure_ascii=False, indent=2, default=str)
            os.replace(tmp_file, self.cache_file)
            logger.info(f"缓存已保存: {len(results)} 条记录")
        except Exception as e:
            tmp_file = locals().get('tmp_file')
            if tmp_file and os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except Exception:
                    pass
            logger.warning(f"缓存保存失败: {e}")

    def get_by_code(self, stock_code):
        for item in self.load():
            if item.get('hk_code') == stock_code:
                return item
        return None

    def clear(self):
        if os.path.exists(self.cache_file):
            os.remove(self.cache_file)
