import copy
import json
import logging
import os
import tempfile
from datetime import date, datetime

from .utils import strip_runtime_fields, classify_market_heat
from .settings import SETTINGS

logger = logging.getLogger(__name__)


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
        os.makedirs(history_dir, exist_ok=True)
        os.makedirs(self.reanalysis_dir, exist_ok=True)

    def _get_reanalysis_latest_path(self, stock_code):
        """获取重新分析最新版本文件路径"""
        return os.path.join(self.reanalysis_dir, f"{stock_code}_latest.json")

    def _get_reanalysis_timestamp_path(self, stock_code, timestamp):
        """获取重新分析时间戳版本文件路径"""
        return os.path.join(self.reanalysis_dir, f"{stock_code}_{timestamp}.json")

    def _read_reanalysis_latest(self, stock_code):
        """读取上次重新分析结果"""
        latest_path = self._get_reanalysis_latest_path(stock_code)
        if not os.path.exists(latest_path):
            return None
        try:
            with open(latest_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"读取reanalysis latest失败: {e}")
            return None

    def _save_reanalysis_record(self, stock_code, record, timestamp):
        """保存重新分析记录（时间戳版本）"""
        timestamp_path = self._get_reanalysis_timestamp_path(stock_code, timestamp)
        fd, tmp_file = tempfile.mkstemp(prefix=f'reanalysis_{stock_code}_', suffix='.tmp', dir=self.reanalysis_dir)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(record, f, ensure_ascii=False, indent=2, default=str)
            os.replace(tmp_file, timestamp_path)
            return timestamp_path
        except Exception:
            if os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except Exception:
                    pass
            raise

    def _save_reanalysis_latest(self, stock_code, record):
        """保存重新分析最新版本"""
        latest_path = self._get_reanalysis_latest_path(stock_code)
        fd, tmp_file = tempfile.mkstemp(prefix=f'reanalysis_{stock_code}_latest_', suffix='.tmp', dir=self.reanalysis_dir)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(record, f, ensure_ascii=False, indent=2, default=str)
            os.replace(tmp_file, latest_path)
            return latest_path
        except Exception:
            if os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except Exception:
                    pass
            raise

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
        dimensions = ['ipo_trade_score', 'long_term_score', 'trade_score', 'fundamental_score', 'valuation_score', 'theme_score', 'data_quality_score']
        for dim in dimensions:
            prev_val = previous_result.get(dim) or previous_result.get('score_breakdown', {}).get(dim)
            curr_val = current_result.get(dim) or current_result.get('score_breakdown', {}).get(dim)
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
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
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
            'reanalyzed_at': datetime.now().isoformat(),
            'analyzer_version': self.HISTORY_VERSION,
            'source_version': SETTINGS.version if hasattr(SETTINGS, 'version') else 'unknown',
            'weight_profile': result.get('weight_profile'),
            'score': result.get('score'),
            'score_breakdown': {
                'ipo_trade_score': result.get('ipo_trade_score'),
                'long_term_score': result.get('long_term_score'),
                'trade_score': result.get('trade_score'),
                'fundamental_score': result.get('fundamental_score'),
                'valuation_score': result.get('valuation_score'),
                'theme_score': result.get('theme_score'),
                'data_quality_score': result.get('data_quality_score'),
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
                'trade_score', 'valuation_score', 'theme_score', 'data_quality_score',
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
                'valuation_pressure_label', 'subscription_recommendation',
                'recommendation_reasons',
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
                    with open(filepath, 'r', encoding='utf-8') as f:
                        records.append(json.load(f))
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
            if str(record.get('hk_code') or '').isdigit():
                record['hk_code'] = str(record.get('hk_code')).zfill(5)
            if existing.get(code, {}).get('post_listing') and not record.get('post_listing'):
                record['post_listing'] = copy.deepcopy(existing[code]['post_listing'])
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

        for key, value in record.items():
            if key == 'post_listing' and not value:
                continue
            if value is None or value == "":
                continue
            if key == 'prospectus_info' and isinstance(value, dict) and _is_dict_effectively_empty(value):
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
        if public_sub:
            record['actual_over_sub_ratio'] = public_sub
            record['over_sub_ratio'] = public_sub
            record['over_sub_ratio_source'] = 'post_listing_actual'
            record['market_heat'] = classify_market_heat(public_sub)
            self._recalculate_scores(record)
        
        existing[code] = record
        self._write_all(self._sort_records(existing.values()))
        return record
