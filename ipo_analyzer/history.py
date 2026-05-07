import copy
import json
import logging
import os
import tempfile
from datetime import date, datetime

from .utils import strip_runtime_fields
from .settings import SETTINGS

logger = logging.getLogger(__name__)


class HistoryStore:
    HISTORY_VERSION = SETTINGS.history.version

    def __init__(self, history_dir='temp'):
        self.history_dir = history_dir
        self.history_file = os.path.join(history_dir, 'ipo_history.json')
        os.makedirs(history_dir, exist_ok=True)

    @staticmethod
    def _stock_code(item):
        code = str((item or {}).get('hk_code') or '').strip()
        if not code or code in ('--', '未知', 'None'):
            return None
        return code

    @classmethod
    def _is_valid_record(cls, item):
        return isinstance(item, dict) and item.get('parse_success', False) and cls._stock_code(item) is not None

    @staticmethod
    def _parse_date(value):
        if not value:
            return None
        text = str(value).strip()
        if 'T' in text:
            text = text.split('T', 1)[0]
        elif ' ' in text:
            text = text.split(' ', 1)[0]
        try:
            return datetime.strptime(text, '%Y-%m-%d').date()
        except Exception:
            return None

    @classmethod
    def _is_live_or_future(cls, item):
        end_date = cls._parse_date((item or {}).get('apply_end_date'))
        return end_date is not None and end_date >= date.today()

    def _read_all(self):
        if not os.path.exists(self.history_file):
            return []
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, list):
                return []
            return [strip_runtime_fields(item) for item in data if isinstance(item, dict)]
        except Exception as e:
            logger.warning("历史库加载失败: %s", e)
            return []

    def _write_all(self, records):
        fd, tmp_file = tempfile.mkstemp(prefix='ipo_history_', suffix='.tmp', dir=self.history_dir)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(records, f, ensure_ascii=False, indent=2, default=str)
            os.replace(tmp_file, self.history_file)
        except Exception:
            if os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except Exception:
                    pass
            raise

    def load(self, include_live=True):
        records = self._read_all()
        if include_live:
            return records
        return [item for item in records if not self._is_live_or_future(item)]

    def archive_many(self, results, source='live'):
        if not results:
            return 0

        existing = {
            self._stock_code(item): item
            for item in self._read_all()
            if self._stock_code(item)
        }
        archived_at = datetime.now().isoformat()
        count = 0

        for item in results:
            if not self._is_valid_record(item):
                continue

            record = strip_runtime_fields(copy.deepcopy(item))
            code = self._stock_code(record)
            record['_archived_at'] = archived_at
            record['_archive_source'] = source
            record['_history_version'] = self.HISTORY_VERSION
            existing[code] = record
            count += 1

        if count:
            records = sorted(
                existing.values(),
                key=lambda item: (
                    self._parse_date(item.get('apply_end_date')) or date.min,
                    str(item.get('_archived_at') or ''),
                    str(item.get('hk_code') or ''),
                ),
                reverse=True,
            )
            self._write_all(records)
            logger.info("历史库已归档: %d 条记录", count)

        return count

    def archive_one(self, result, source='upload'):
        return self.archive_many([result], source=source) > 0

    def migrate_from_cache(self, cache_results):
        """增量同步缓存中的新记录到历史库（去重）"""
        if not cache_results:
            return 0

        existing = {
            self._stock_code(item): item
            for item in self._read_all()
            if self._stock_code(item)
        }
        existing_codes = set(existing.keys())

        new_records = []
        for item in cache_results:
            if not self._is_valid_record(item):
                continue
            code = self._stock_code(item)
            if code and code not in existing_codes:
                new_records.append(item)

        if not new_records:
            return 0

        return self.archive_many(new_records, source='live')
