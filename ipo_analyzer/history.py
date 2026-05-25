import copy
import json
import logging
import os
import sqlite3
from functools import lru_cache
from datetime import date, datetime

from .utils import strip_runtime_fields, classify_market_heat, _sanitize_stock_code
from .settings import SETTINGS
from .json_utils import fast_dump_file, fast_dumps

logger = logging.getLogger(__name__)


@lru_cache(maxsize=16)
def _load_json_snapshot(path: str, mtime: float, size: int):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _json_to_db_record(item: dict) -> tuple:
    """将 dict 转为 SQLite 行数据 (code, data_json, updated_at, has_post_listing, score)。"""
    code = str((item or {}).get('hk_code') or (item or {}).get('stock_code') or '').strip()
    if code.isdigit():
        code = code.zfill(5)
    updated_at = item.get('_archived_at') or item.get('_post_listing_updated_at') or datetime.now().isoformat()
    has_post = 1 if item.get('post_listing') else 0
    score = item.get('score')
    try:
        score = float(score) if score is not None else None
    except (ValueError, TypeError):
        score = None
    return (code, fast_dumps(item, compact=False), updated_at, has_post, score)


def _is_dict_effectively_empty(d: dict) -> bool:
    """Return True if a dict has no non-None scalar values (all values are None or empty)."""
    if not isinstance(d, dict):
        return False
    for v in d.values():
        if v is None or v == "":
            continue
        if isinstance(v, (list, tuple)) and len(v) == 0:
            continue
        if isinstance(v, dict):
            if not _is_dict_effectively_empty(v):
                return False
            continue
        return False
    return True


class HistoryStore:
    HISTORY_VERSION = SETTINGS.history.version

    def __init__(self, history_dir='temp'):
        self.history_dir = history_dir
        self.history_file = os.path.join(history_dir, 'ipo_history.json')
        self.reanalysis_dir = os.path.join(history_dir, 'reanalysis')
        self.db_path = os.path.join(history_dir, 'history.db')
        os.makedirs(history_dir, exist_ok=True)
        os.makedirs(self.reanalysis_dir, exist_ok=True)
        self._init_db()
        self._migrate_from_json_if_needed()

    # ------------------------------------------------------------------
    # SQLite 存储层
    # ------------------------------------------------------------------

    def _init_db(self):
        """初始化 SQLite 表结构。"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS local_ipo_history (
                    code TEXT PRIMARY KEY,
                    data_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    has_post_listing INTEGER DEFAULT 0,
                    score REAL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_updated_at ON local_ipo_history(updated_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_has_post_listing ON local_ipo_history(has_post_listing)
            """)
            conn.commit()

    def _migrate_from_json_if_needed(self):
        """如果 SQLite 为空且 JSON 文件存在，执行一次性迁移。"""
        if not os.path.exists(self.history_file):
            return
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM local_ipo_history")
            if cursor.fetchone()[0] > 0:
                return
        try:
            stat = os.stat(self.history_file)
            records = copy.deepcopy(_load_json_snapshot(self.history_file, stat.st_mtime, stat.st_size))
            if not isinstance(records, list):
                return
            with sqlite3.connect(self.db_path) as conn:
                for item in records:
                    if not isinstance(item, dict):
                        continue
                    code = str((item or {}).get('hk_code') or (item or {}).get('stock_code') or '').strip()
                    if not code:
                        continue
                    if code.isdigit():
                        code = code.zfill(5)
                    row = _json_to_db_record(item)
                    conn.execute(
                        "INSERT OR REPLACE INTO local_ipo_history (code, data_json, updated_at, has_post_listing, score) VALUES (?, ?, ?, ?, ?)",
                        row,
                    )
                conn.commit()
            logger.info("历史库迁移完成: %d 条记录从 JSON 迁移到 SQLite", len(records))
        except Exception as e:
            logger.warning("JSON 到 SQLite 迁移失败: %s", e)

    def _db_read_all(self):
        """从 SQLite 读取所有记录。"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT data_json FROM local_ipo_history ORDER BY updated_at DESC")
            rows = cursor.fetchall()
        records = []
        for (data_json,) in rows:
            try:
                item = json.loads(data_json)
                if isinstance(item, dict):
                    records.append(strip_runtime_fields(item))
            except Exception:
                continue
        return records

    def _db_write_all(self, records):
        """批量写入 SQLite，同时保留 JSON 备份。"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM local_ipo_history")
            for item in records:
                if not isinstance(item, dict):
                    continue
                code = str((item or {}).get('hk_code') or (item or {}).get('stock_code') or '').strip()
                if not code:
                    continue
                row = _json_to_db_record(item)
                conn.execute(
                    "INSERT OR REPLACE INTO local_ipo_history (code, data_json, updated_at, has_post_listing, score) VALUES (?, ?, ?, ?, ?)",
                    row,
                )
            conn.commit()
        # 保留 JSON 作为备份
        fast_dump_file(self.history_file, records)

    def _get_reanalysis_latest_path(self, stock_code):
        """获取重新分析最新版本文件路径"""
        safe_code = _sanitize_stock_code(stock_code)
        return os.path.join(self.reanalysis_dir, f"{safe_code}_latest.json")

    def _get_reanalysis_timestamp_path(self, stock_code, timestamp):
        """获取重新分析时间戳版本文件路径"""
        safe_code = _sanitize_stock_code(stock_code)
        return os.path.join(self.reanalysis_dir, f"{safe_code}_{timestamp}.json")

    def _read_reanalysis_latest(self, stock_code):
        """读取上次重新分析结果"""
        latest_path = self._get_reanalysis_latest_path(stock_code)
        if not os.path.exists(latest_path):
            return None
        try:
            stat = os.stat(latest_path)
            return copy.deepcopy(_load_json_snapshot(latest_path, stat.st_mtime, stat.st_size))
        except Exception as e:
            logger.warning(f"读取reanalysis latest失败: {e}")
            return None

    def _save_reanalysis_record(self, stock_code, record, timestamp):
        """保存重新分析记录（时间戳版本）"""
        timestamp_path = self._get_reanalysis_timestamp_path(stock_code, timestamp)
        fast_dump_file(timestamp_path, record)
        return timestamp_path

    def _save_reanalysis_latest(self, stock_code, record):
        """保存重新分析最新版本"""
        latest_path = self._get_reanalysis_latest_path(stock_code)
        fast_dump_file(latest_path, record)
        return latest_path

    def _calculate_version_delta(self, previous_result, current_result):
        """计算版本对比delta"""
        if not previous_result:
            return None
        
        delta = {
            'previous_score': previous_result.get('score'),
            'current_score': current_result.get('score'),
            'score_delta': None,
            'dimension_deltas': {},
            'changed_reason': None,
        }
        
        prev_score = previous_result.get('score')
        curr_score = current_result.get('score')
        
        if prev_score is not None and curr_score is not None:
            delta['score_delta'] = curr_score - prev_score
        
        # 计算各维度delta（支持从顶层或score_breakdown中获取）
        dimensions = ['ipo_trade_score', 'long_term_score', 'trade_score', 'fundamental_score', 'valuation_score', 'theme_score']
        for dim in dimensions:
            prev_val = previous_result.get(dim)
            if prev_val is None:
                prev_val = (previous_result.get('score_breakdown') or {}).get(dim)
            curr_val = current_result.get(dim)
            if curr_val is None:
                curr_val = (current_result.get('score_breakdown') or {}).get(dim)
            if prev_val is not None and curr_val is not None:
                delta['dimension_deltas'][dim] = curr_val - prev_val
        
        # 生成变化原因
        reasons = []
        if delta['score_delta'] is not None:
            if delta['score_delta'] > 5:
                reasons.append(f"评分上升{delta['score_delta']}分")
            elif delta['score_delta'] < -5:
                reasons.append(f"评分下降{abs(delta['score_delta'])}分")
        
        # 检查权重配置变化
        prev_wp = previous_result.get('weight_profile', {}).get('name')
        curr_wp = current_result.get('weight_profile', {}).get('name')
        if prev_wp != curr_wp:
            reasons.append(f"权重配置变化: {prev_wp} -> {curr_wp}")
        
        delta['changed_reason'] = '; '.join(reasons) if reasons else None
        
        return delta

    def save_reanalysis(self, result):
        """保存重新分析结果，包含版本对比"""
        stock_code = self._stock_code(result)
        if not stock_code:
            logger.warning("无法保存reanalysis记录：缺少股票代码")
            return None, None
        
        now = datetime.now()
        timestamp = now.strftime('%Y%m%d_%H%M%S')
        
        # 1. 先读取旧latest
        previous_result = self._read_reanalysis_latest(stock_code)
        
        # 2. 计算delta
        version_delta = self._calculate_version_delta(previous_result, result)
        
        # 3. 构建完整记录
        reanalysis_info = result.get('_reanalysis', {})
        record = {
            'stock_code': stock_code,
            'company_name': result.get('company_name'),
            'analysis_mode': reanalysis_info.get('analysis_mode', 'reanalysis'),
            'reanalyzed_at': now.isoformat(),
            'analyzer_version': self.HISTORY_VERSION,
            'source_version': SETTINGS.version if hasattr(SETTINGS, 'version') else 'unknown',
            'weight_profile': result.get('weight_profile'),
            'score': result.get('score'),
            'score_breakdown': {
                'ipo_trade_score': result.get('ipo_trade_score'),
                'strict_ipo_score': result.get('strict_ipo_score'),
                'raw_trade_signal_score': result.get('raw_trade_signal_score'),
                'long_term_score': result.get('long_term_score'),
                'trade_score': result.get('trade_score'),
                'fundamental_score': result.get('fundamental_score'),
                'valuation_score': result.get('valuation_score'),
                'theme_score': result.get('theme_score'),
            },
            'risk_penalty': result.get('risk_penalty'),
            'risk_penalty_breakdown': result.get('risk_penalty_breakdown'),
            'historical_market_data': reanalysis_info.get('historical_market_data'),
            'heat_data_source': reanalysis_info.get('heat_data_source', 'missing'),
            'source_type': reanalysis_info.get('source_type'),
            'pdf_path': result.get('pdf_path'),
            'pdf_identity_confidence': reanalysis_info.get('pdf_identity_confidence'),
            'warning_messages': reanalysis_info.get('warning_messages', []),
            'error_messages': reanalysis_info.get('error_messages', []),
            'version_delta': version_delta,
            '_full_result': result,  # 保存完整结果供后续对比
        }

        # 将 prospectus_info 中的关键日期提升到顶层，确保 _is_ended_record 等函数可访问
        pi = result.get('prospectus_info') or {}
        if not record.get('apply_end_date') and result.get('apply_end_date'):
            record['apply_end_date'] = result.get('apply_end_date')
        if not record.get('listing_date') and pi.get('listing_date'):
            record['listing_date'] = pi.get('listing_date')

        # 4. 保存时间戳版本
        self._save_reanalysis_record(stock_code, record, timestamp)
        
        # 5. 覆盖latest
        self._save_reanalysis_latest(stock_code, record)
        self.merge_analysis_result(result, source='reanalysis')
        
        logger.info(f"重新分析记录已保存: {stock_code}")
        return record, version_delta

    def _recalculate_scores(self, record):
        """当 post_listing 数据更新后，使用已有的招股书数据重新计算评分。"""
        prospectus_info = record.get('prospectus_info')
        if not prospectus_info or not prospectus_info.get('parse_success'):
            return
        prospectus_text = prospectus_info.get('_extracted_text', '') or ''
        if not prospectus_text:
            pdf_path = record.get('pdf_path')
            if pdf_path and os.path.exists(pdf_path):
                try:
                    import fitz
                    doc = fitz.open(pdf_path)
                    prospectus_text = "\n".join(page.get_text() for page in doc)
                    doc.close()
                except Exception as e:
                    logger.warning("PDF回退读取失败 %s: %s", pdf_path, e)
                    return
            else:
                logger.warning("评分重算跳过: 无招股书文本且PDF不存在 (%s)", record.get('hk_code'))
                return
        try:
            from .core import _run_scoring_pipeline
            ipo_data = {k: v for k, v in record.items()
                        if k not in ('prospectus_info', 'post_listing', '_full_result')}
            result = _run_scoring_pipeline(ipo_data, prospectus_info, prospectus_text)
            score_fields = (
                'score', 'subscription_score', 'fundamental_score',
                'stock_quality_score', 'score_reasons', 'score_breakdown',
                'risk_penalty', 'risk_penalty_breakdown',
                'trade_score', 'valuation_score', 'theme_score',
                'strict_ipo_score', 'raw_trade_signal_score', 'strict_scoring_profile',
                'weight_profile', 'debug_info', 'score_trace', 'penalty_reason',
                'analysis_mode', 'over_sub_ratio', 'over_sub_ratio_source',
                'market_heat', 'stock_quality', 'signal_breakdown',
                'advanced_framework_score', 'advanced_score_adjustment',
                'data_confidence_gate_warning', 'score_weights_note',
                'total_fund', 'public_offer', 'margin_total',
                'actual_over_sub_ratio', 'forecast_over_sub_ratio',
                'estimated_subscription_ratio', 'over_sub_ratio_estimated',
                # 策略引擎字段（申购建议相关）
                'ipo_trade_score', 'ipo_trade_label',
                'long_term_score', 'long_term_label',
                'fisher_label', 'lynch_label',
                'valuation_pressure_label', 'subscription_recommendation',
                'recommendation_reasons',
                # 新增的硬科技/估值字段
                'business_model_label', 'business_model_reasons',
                'segment_concentration_label', 'segment_moat_label',
                'ev_sales_ratio', 'net_cash_hkd_million',
                'pre_ipo_valuation_million', 'ipo_valuation_premium_pct',
                'inventory_amount', 'receivables_amount', 'monthly_cash_burn',
                'patent_count', 'software_copyright_count',
                'rd_staff_count', 'rd_staff_ratio',
                'backlog_amount', 'industry_rank', 'market_size_notes',
                'hardtech_moat_label', 'hardtech_moat_reasons', 'hardtech_moat_score',
            )
            for key in score_fields:
                if key in result:
                    record[key] = result[key]
            logger.info("评分重算完成: %s score=%s", record.get('hk_code'), record.get('score'))
        except Exception as e:
            logger.warning("评分重算失败 %s: %s", record.get('hk_code'), e)

    def load_reanalysis_history(self, stock_code):
        """加载某股票的所有重新分析历史记录"""
        records = []
        for filename in os.listdir(self.reanalysis_dir):
            if filename.startswith(f"{stock_code}_") and filename != f"{stock_code}_latest.json":
                filepath = os.path.join(self.reanalysis_dir, filename)
                try:
                    stat = os.stat(filepath)
                    records.append(copy.deepcopy(_load_json_snapshot(filepath, stat.st_mtime, stat.st_size)))
                except Exception as e:
                    logger.warning(f"读取reanalysis记录失败 {filepath}: {e}")
        
        # 按时间戳排序（最新的在前）
        records.sort(key=lambda x: x.get('reanalyzed_at', ''), reverse=True)
        return records

    def load_reanalysis_latest(self, stock_code):
        """加载某股票的最新重新分析记录"""
        return self._read_reanalysis_latest(stock_code)

    @staticmethod
    def _stock_code(item):
        code = str((item or {}).get('hk_code') or (item or {}).get('stock_code') or '').strip()
        if not code or code in ('--', '未知', 'None'):
            return None
        if code.isdigit():
            return code.zfill(5)
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
        """优先从 SQLite 读取，失败时回退到 JSON。"""
        try:
            return self._db_read_all()
        except Exception as e:
            logger.warning("SQLite 读取失败，回退到 JSON: %s", e)
        if not os.path.exists(self.history_file):
            return []
        try:
            stat = os.stat(self.history_file)
            data = copy.deepcopy(_load_json_snapshot(self.history_file, stat.st_mtime, stat.st_size))
            if not isinstance(data, list):
                return []
            return [strip_runtime_fields(item) for item in data if isinstance(item, dict)]
        except Exception as e:
            logger.warning("历史库加载失败: %s", e)
            return []

    def _write_all(self, records):
        """写入 SQLite（主存储）并保留 JSON 备份。"""
        try:
            self._db_write_all(records)
        except Exception as e:
            logger.warning("SQLite 写入失败，仅保留 JSON: %s", e)
            fast_dump_file(self.history_file, records)

    def _sort_records(self, records):
        return sorted(
            records,
            key=lambda item: (
                self._parse_date(item.get('apply_end_date')) or date.min,
                str(item.get('_archived_at') or item.get('_post_listing_updated_at') or ''),
                str(item.get('hk_code') or item.get('stock_code') or ''),
            ),
            reverse=True,
        )

    def load(self, include_live=True):
        records = self._read_all()
        records = self._deduplicate_stocks(records)
        if include_live:
            return records
        return [item for item in records if not self._is_live_or_future(item)]

    @staticmethod
    def _deduplicate_stocks(records):
        """合并同一股票的多条记录：reanalysis 的市场数据覆盖原始记录。

        原始记录保留财务数据（revenue, gross_margin 等），
        reanalysis 记录的市场热度数据（over_sub_ratio, market_heat 等）覆盖原始。
        同时从 _full_result 中提取缺失的顶层字段。
        """
        if not records:
            return records

        # 先补全每条记录：从 _full_result 提取市场数据到顶层
        _MARKET_FIELDS = ('over_sub_ratio', 'over_sub_ratio_source',
                          'actual_over_sub_ratio', 'forecast_over_sub_ratio',
                          'market_heat', 'margin_total', 'public_offer')
        for item in records:
            fr = item.get('_full_result') or {}
            for field in _MARKET_FIELDS:
                cur = item.get(field)
                if (cur is None or cur == '' or cur == 'missing') and fr.get(field) is not None and fr.get(field) != '' and fr.get(field) != 'missing':
                    item[field] = fr.get(field)
            if not item.get('post_listing') and fr.get('post_listing'):
                item['post_listing'] = copy.deepcopy(fr['post_listing'])
            # 恢复 _extracted_text：strip_runtime_fields 已剥离顶层文本，从 _full_result 恢复
            if not item.get('prospectus_info', {}).get('_extracted_text'):
                fr_pi = fr.get('prospectus_info', {})
                extracted = fr_pi.get('_extracted_text', '') if isinstance(fr_pi, dict) else ''
                if extracted and isinstance(item.get('prospectus_info'), dict):
                    item['prospectus_info']['_extracted_text'] = extracted

        groups = {}
        for item in records:
            code = (item.get('hk_code') or item.get('stock_code') or '').strip()
            if not code:
                continue
            groups.setdefault(code, []).append(item)

        merged = []
        seen_codes = set()
        for item in records:
            code = (item.get('hk_code') or item.get('stock_code') or '').strip()
            if not code:
                merged.append(item)
                continue
            if code in seen_codes:
                continue
            seen_codes.add(code)

            group = groups.get(code, [item])
            if len(group) == 1:
                merged.append(group[0])
                continue

            reanalysis_items = [r for r in group if r.get('analysis_mode') == 'reanalysis']
            original_items = [r for r in group if r.get('analysis_mode') != 'reanalysis']

            base = copy.deepcopy(original_items[0]) if original_items else copy.deepcopy(group[0])

            if reanalysis_items:
                # 按 reanalyzed_at 降序排序，取最新的记录
                reanalysis_items.sort(key=lambda x: x.get('reanalyzed_at', ''), reverse=True)
                ra = reanalysis_items[0]
                # 总是合并市场数据
                for field in _MARKET_FIELDS:
                    ra_val = ra.get(field)
                    if ra_val is not None and ra_val != '' and ra_val != 'missing':
                        base[field] = ra_val
                if ra.get('post_listing'):
                    base['post_listing'] = copy.deepcopy(ra['post_listing'])
                if ra.get('historical_market_data'):
                    base['historical_market_data'] = copy.deepcopy(ra['historical_market_data'])
                # 质量检查: 只有当重分析成功解析了招股书时才覆盖评分
                ra_full = ra.get('_full_result', {})
                ra_prospectus = ra_full.get('prospectus_info', {})
                ra_parse_ok = ra_prospectus.get('parse_success', False) or ra.get('score') is not None
                if ra_parse_ok:
                    for field in ('score', 'trade_score', 'valuation_score', 'theme_score',
                                  'ipo_trade_score', 'strict_ipo_score', 'raw_trade_signal_score',
                                  'strict_scoring_profile', 'ipo_trade_label', 'long_term_score',
                                  'long_term_label', 'subscription_recommendation',
                                  'recommendation_reasons', 'subscription_score',
                                  'weight_profile', 'score_trace'):
                        if ra.get(field) is not None:
                            base[field] = ra.get(field)

            for item in merged:
                item.pop('_full_result', None)

            merged.append(base)

        return merged

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
            if str(record.get('hk_code') or '').isdigit():
                record['hk_code'] = str(record.get('hk_code')).zfill(5)
            if existing.get(code, {}).get('post_listing') and not record.get('post_listing'):
                record['post_listing'] = copy.deepcopy(existing[code]['post_listing'])
            # 保护重新分析产生的数据不被缓存覆盖
            existing_record = existing.get(code, {})
            if existing_record.get('_reanalysis'):
                for re_field in ('score', 'ipo_trade_score', 'strict_ipo_score',
                                 'raw_trade_signal_score', 'strict_scoring_profile',
                                 'long_term_score', 'trade_score',
                                 'fundamental_score', 'valuation_score', 'theme_score',
                                 'subscription_recommendation', 'recommendation_reasons',
                                 'score_reasons', 'actual_over_sub_ratio', 'over_sub_ratio_source'):
                    if existing_record.get(re_field) is not None and record.get(re_field) is None:
                        record[re_field] = copy.deepcopy(existing_record[re_field])
            record['_archived_at'] = archived_at
            record['_archive_source'] = source
            record['_history_version'] = self.HISTORY_VERSION
            existing[code] = record
            count += 1

        if count:
            self._write_all(self._sort_records(existing.values()))
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

    def merge_analysis_result(self, result, source='reanalysis'):
        """Merge the latest analysis result into the unified history library.

        Reanalysis outputs often omit live-listing fields such as apply_end_date,
        so non-empty incoming values update the record while existing context
        and post_listing data are preserved.
        """
        code = self._stock_code(result)
        if not code:
            return False

        existing = {
            self._stock_code(item): item
            for item in self._read_all()
            if self._stock_code(item)
        }
        merged = copy.deepcopy(existing.get(code, {}))
        record = strip_runtime_fields(copy.deepcopy(result))
        if str(record.get('hk_code') or '').isdigit():
            record['hk_code'] = str(record.get('hk_code')).zfill(5)

        # 保护来自 post_listing_actual 的真实配发数据不被重分析估算值覆盖
        protected_oversub = False
        if merged.get('over_sub_ratio_source') == 'post_listing_actual':
            protected_oversub = True

        for key, value in record.items():
            if key == 'post_listing' and not value:
                continue
            if value is None or value == "":
                continue
            if key == 'prospectus_info' and isinstance(value, dict) and _is_dict_effectively_empty(value):
                continue
            if protected_oversub and key in ('actual_over_sub_ratio', 'over_sub_ratio', 'over_sub_ratio_source', 'market_heat'):
                continue
            merged[key] = value

        merged.setdefault('hk_code', code)
        merged['_archived_at'] = datetime.now().isoformat()
        merged['_archive_source'] = source
        merged['_history_version'] = self.HISTORY_VERSION
        existing[code] = merged
        self._write_all(self._sort_records(existing.values()))
        return True

    def update_post_listing(self, stock_code, post_listing):
        """Atomically merge post-listing data into one history record."""
        code = self._stock_code({'hk_code': stock_code})
        if not code:
            return None

        existing = {
            self._stock_code(item): item
            for item in self._read_all()
            if self._stock_code(item)
        }
        record = copy.deepcopy(existing.get(code, {'hk_code': code}))

        # _read_all 已剥离 _extracted_text，重读原始 JSON 恢复它以便评分重算
        saved_text = ''
        try:
            stat = os.stat(self.history_file)
            raw_data = copy.deepcopy(_load_json_snapshot(self.history_file, stat.st_mtime, stat.st_size))
            code_normalized = code.zfill(5) if code.isdigit() else code
            for item in raw_data if isinstance(raw_data, list) else []:
                if isinstance(item, dict):
                    item_code = str(item.get('hk_code', '')).zfill(5) if str(item.get('hk_code', '')).isdigit() else str(item.get('hk_code', ''))
                    if item_code == code_normalized:
                        pi = item.get('prospectus_info', {})
                        if isinstance(pi, dict):
                            saved_text = pi.get('_extracted_text', '') or ''
                        break
        except Exception:
            pass
        if saved_text and isinstance(record.get('prospectus_info'), dict):
            record['prospectus_info']['_extracted_text'] = saved_text

        current_post_listing = copy.deepcopy(record.get('post_listing') or {})
        current_post_listing.update(strip_runtime_fields(copy.deepcopy(post_listing or {})))
        if current_post_listing.get('status') == 'ok':
            current_post_listing.pop('message', None)
            if not current_post_listing.get('error'):
                current_post_listing.pop('error', None)
        record['post_listing'] = current_post_listing
        record['_post_listing_updated_at'] = datetime.now().isoformat()
        record['_history_version'] = self.HISTORY_VERSION
        
        # 从 post_listing 数据中提取真实公配倍数，填充到 actual_over_sub_ratio
        # 始终用配发公告的真实值覆盖旧的估算值
        public_sub = post_listing.get('public_subscription_level') if post_listing else None
        if public_sub is not None:
            record['actual_over_sub_ratio'] = public_sub
            record['over_sub_ratio'] = public_sub
            record['over_sub_ratio_source'] = 'post_listing_actual'
            record['market_heat'] = classify_market_heat(public_sub)
            self._recalculate_scores(record)
        
        existing[code] = record
        self._write_all(self._sort_records(existing.values()))
        self._sync_post_listing_to_cache(code, record, post_listing)
        return record

    def _sync_post_listing_to_cache(self, code, record, post_listing):
        """将 post_listing 更新同步到 results_cache.json，确保首页显示最新数据。"""
        import os
        from datetime import datetime

        cache_file = os.path.join(self.history_dir, 'results_cache.json')
        if not os.path.exists(cache_file):
            return

        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
            if not isinstance(cached_data, list):
                return

            normalized_code = code.zfill(5) if code.isdigit() else code
            found = False
            for item in cached_data:
                if not isinstance(item, dict):
                    continue
                item_code = str(item.get('hk_code', '')).zfill(5) if str(item.get('hk_code', '')).isdigit() else str(item.get('hk_code', ''))
                if item_code == normalized_code:
                    item['post_listing'] = copy.deepcopy(record.get('post_listing', {}))
                    if post_listing and post_listing.get('public_subscription_level') is not None:
                        item['actual_over_sub_ratio'] = post_listing['public_subscription_level']
                        item['over_sub_ratio'] = post_listing['public_subscription_level']
                        item['over_sub_ratio_source'] = 'post_listing_actual'
                        item['market_heat'] = classify_market_heat(post_listing['public_subscription_level'])
                    item['_cached_at'] = datetime.now().isoformat()
                    found = True
                    break

            if found:
                fast_dump_file(cache_file, cached_data)
                logger.info("已同步 post_listing 更新到 results_cache.json: %s", code)
        except Exception as e:
            logger.warning("同步 post_listing 到缓存文件失败: %s", e)
