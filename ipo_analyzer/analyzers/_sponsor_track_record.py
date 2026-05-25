"""保荐人战绩分析器 — 从 YAML 数据库加载保荐人历史战绩，评估保荐质量。"""

import os
import re
import yaml
import logging

logger = logging.getLogger(__name__)

_SPONSOR_NAME_PATTERNS = [
    r'(?:保荐人|保薦人|sponsor).{0,5}[：:]\s*([^\n]{2,60})',
    r'(?:联席保荐人|聯席保薦人|joint sponsor).{0,5}[：:]\s*([^\n]{2,60})',
    r'(?:独家保荐人|獨家保薦人|sole sponsor).{0,5}[：:]\s*([^\n]{2,60})',
    r'(?:保荐人|保薦人).{0,30}为\s*([^\n,，、]{2,40})',
    r'(?:保荐人|保薦人).{0,30}爲\s*([^\n,，、]{2,40})',
]

_CLEAN_SUFFIXES = [
    '有限公司', '股份有限公司', '国际控股有限公司',
    '香港有限公司', '亚洲有限公司', 'Limited', 'Ltd',
    'Asia Limited', 'Asia Ltd',
]


class SponsorTrackRecordAnalyzer:
    """保荐人战绩分析器"""

    _database_cache = None
    _database_hash = None

    def _load_database(self):
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'data', 'sponsor_track_record.yaml'
        )
        try:
            mtime = os.path.getmtime(db_path)
            cache_key = '{0}:{1}'.format(db_path, mtime)
            if self._database_cache is not None and self._database_hash == cache_key:
                return self._database_cache

            with open(db_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            self._database_cache = data
            self._database_hash = cache_key
            return data
        except Exception as e:
            logger.warning("加载保荐人数据库失败: %s", e)
            return {'sponsors': []}

    def analyze(self, prospectus_info, text=''):
        result = {
            'sponsor_name': None,
            'sponsor_tier': None,
            'sponsor_break_rate': None,
            'sponsor_avg_return': None,
            'sponsor_ipo_count': None,
            'sponsor_score': 0,
            'sponsor_label': '未知',
            'matched_by': 'none',
            'confidence': 'missing',
        }

        try:
            text_content = text or prospectus_info.get('_extracted_text', '')
            db = self._load_database()
            sponsors_db = db.get('sponsors', [])

            sponsor_name = self._extract_sponsor_name(text_content)
            if not sponsor_name:
                return result

            result['sponsor_name'] = sponsor_name

            sponsor_record = self._match_sponsor(sponsor_name, sponsors_db)
            if sponsor_record:
                result['sponsor_tier'] = sponsor_record['tier']
                result['sponsor_break_rate'] = sponsor_record.get('break_rate')
                result['sponsor_avg_return'] = sponsor_record.get('avg_first_day_return')
                result['sponsor_ipo_count'] = sponsor_record.get('recent_ipo_count')
                result['sponsor_score'] = self._calculate_score(sponsor_record)
                result['sponsor_label'] = sponsor_record['tier'] + '级 - ' + sponsor_record['name']
                result['matched_by'] = 'exact_or_alias'
                result['confidence'] = 'database'
            else:
                result['sponsor_tier'] = 'C'
                result['sponsor_score'] = 0
                result['sponsor_label'] = '未知保荐人: ' + sponsor_name
                result['matched_by'] = 'default'
                result['confidence'] = 'unknown'

        except Exception as e:
            logger.warning("%s: %s", type(self).__name__, e)
            result['_error'] = str(e)

        return result

    def _extract_sponsor_name(self, text):
        for pattern in _SPONSOR_NAME_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                name = self._clean_name(name)
                if len(name) >= 2:
                    return name
        return None

    def _clean_name(self, name):
        name = re.sub(r'^[,，、\s]+', '', name)
        name = re.sub(r'[,，、\s]+$', '', name)
        name = re.sub(r'\s+', ' ', name)
        name = re.sub(r'[）\)]$', '', name)
        for suffix in _CLEAN_SUFFIXES:
            name = re.sub(re.escape(suffix) + r'$', '', name, flags=re.IGNORECASE)
        return name.strip()

    def _match_sponsor(self, name, sponsors_db):
        name_lower = name.lower().strip()
        for sponsor in sponsors_db:
            main_name_lower = sponsor['name'].lower().strip()
            if name_lower == main_name_lower or name_lower in main_name_lower or main_name_lower in name_lower:
                return sponsor
            for alias in sponsor.get('aliases', []):
                alias_lower = alias.lower().strip()
                if name_lower == alias_lower or name_lower in alias_lower or alias_lower in name_lower:
                    return sponsor
        return None

    def _get_default_sponsor(self, sponsors_db):
        for s in sponsors_db:
            if s.get('name') == '未知保荐人':
                return s
        return {'tier': 'C', 'break_rate': 0.50, 'recent_ipo_count': 0}

    def _calculate_score(self, sponsor_record):
        from ..settings import SETTINGS
        st = SETTINGS.sponsor
        tier = sponsor_record.get('tier', 'C')
        count = sponsor_record.get('recent_ipo_count', 0)
        if count < st.min_project_count:
            return st.sponsor_missing_score
        if tier == 'S':
            return st.tier_s_score
        elif tier == 'A':
            return st.tier_a_score
        elif tier == 'B':
            return st.tier_b_score
        else:
            return st.sponsor_missing_score
