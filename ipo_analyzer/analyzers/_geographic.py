import re
import logging
from ..utils import _is_num
from ..table_extraction import extract_segment_table
from ..settings import SETTINGS
logger = logging.getLogger(__name__)

_GEO_PCT_RE = re.compile(r'(\d+\.?\d*)\s*%')
_GEO_YEAR_RE = re.compile(r'\b(20\d{2})\b')
_GEO_NUMERIC_LINE_RE = re.compile(r'^(\d[\d,]*\.?\d*)$')


class GeographicExpansionAnalyzer:
    _CHINA_ALIASES = ['Chinese mainland', 'Mainland China', 'PRC', 'China market', "People's Republic of China"]
    _OVERSEAS_ALIASES = ['Overseas', 'International', 'Other countries and regions', 'Outside mainland China', 'Non-PRC', 'Outside the PRC']
    _HK_ALIASES = ['Hong Kong', 'HK', '香港', 'HKIA']

    def _classify_geo_line(self, line_lower):
        is_overseas = False
        is_china = False
        if 'outside mainland china' in line_lower or 'outside the prc' in line_lower or 'non-prc' in line_lower:
            return False, True
        for alias in self._OVERSEAS_ALIASES:
            if alias.lower() in line_lower and alias.lower() not in ('outside mainland china', 'outside the prc'):
                is_overseas = True
                break
        for alias in self._CHINA_ALIASES:
            if alias.lower() in line_lower:
                is_china = True
                break
        if is_overseas and is_china:
            if 'overseas' in line_lower or 'international' in line_lower:
                is_china = False
            else:
                is_overseas = False
        return is_china, is_overseas

    def _classify_geo_line_detailed(self, line_lower):
        for alias in self._HK_ALIASES:
            if alias.lower() in line_lower:
                return 'hong_kong'
        for alias in self._CHINA_ALIASES:
            if alias.lower() in line_lower:
                return 'mainland'
        for alias in self._OVERSEAS_ALIASES:
            if alias.lower() in line_lower:
                return 'other'
        return None

    def analyze(self, prospectus_info, text='', ipo_data=None):
        # 防御：某些调用者把 ipo_data 传到了 text 位置
        if isinstance(text, dict):
            text = ''
        result = {
            'china_revenue_latest': None,
            'overseas_revenue_latest': None,
            'overseas_revenue_pct': None,
            'overseas_growth_pct': None,
            'overseas_growth_label': '缺失',
            'overseas_risks': [],
            'geographic_table': {},
            'geographic_confidence': 'missing',
            'confidence': 'missing',
            'hong_kong_revenue_pct': None,
            'hong_kong_revenue_trend': '缺失',
            'mainland_revenue_pct': None,
            'detailed_geo_table': {},
        }
        try:
            geo_pct_data = self._extract_geo_with_pct(text)
            cn_pcts = geo_pct_data.get('china', {})
            os_pcts = geo_pct_data.get('overseas', {})

            if os_pcts:
                years = sorted(os_pcts.keys())
                latest = years[-1]
                result['overseas_revenue_pct'] = os_pcts.get(latest)
                if len(years) >= 2:
                    prev = years[-2]
                    os_prev = os_pcts.get(prev)
                    os_latest = os_pcts.get(latest)
                    if _is_num(os_prev) and os_prev > 0 and _is_num(os_latest):
                        result['overseas_growth_pct'] = round((os_latest - os_prev) / os_prev * 100, 1)
                result['geographic_table'] = {'china_pct': cn_pcts, 'overseas_pct': os_pcts}
                result['geographic_confidence'] = 'pct_from_text'
            else:
                geo_table = extract_segment_table(text, self._CHINA_ALIASES + self._OVERSEAS_ALIASES)
                cn_data = {}
                os_data = {}
                for alias in self._CHINA_ALIASES:
                    if alias in geo_table:
                        cn_data = geo_table[alias]
                        break
                for alias in self._OVERSEAS_ALIASES:
                    if alias in geo_table:
                        os_data = geo_table[alias]
                        break

                years = sorted(set(list(cn_data.keys()) + list(os_data.keys())))
                if years:
                    latest = years[-1]
                    result['china_revenue_latest'] = cn_data.get(latest)
                    result['overseas_revenue_latest'] = os_data.get(latest)
                    total = (cn_data.get(latest) or 0) + (os_data.get(latest) or 0)
                    if total > 0:
                        result['overseas_revenue_pct'] = round((os_data.get(latest) or 0) / total * 100, 1)
                    if len(years) >= 2:
                        prev = years[-2]
                        os_prev = os_data.get(prev)
                        os_latest = os_data.get(latest)
                        if _is_num(os_prev) and os_prev > 0 and _is_num(os_latest):
                            result['overseas_growth_pct'] = round((os_latest - os_prev) / os_prev * 100, 1)
                    result['geographic_table'] = {'china': cn_data, 'overseas': os_data}
                    result['geographic_confidence'] = 'regex_context'

            # 地域收入异常校验
            result['geo_validation'] = self._validate_geo_data(result, prospectus_info)
            if not result['geo_validation'].get('valid', True):
                result['overseas_growth_label'] = '解析失败/需人工复核'
                result['overseas_risks'].append(result['geo_validation'].get('reason', '地域收入数据异常'))

            overseas_pct = result.get('overseas_revenue_pct')
            overseas_growth = result.get('overseas_growth_pct')
            gt = SETTINGS.geographic
            if overseas_pct is not None and result['geo_validation'].get('valid', True):
                if overseas_pct >= gt.high_pct and (overseas_growth or 0) > gt.growth_extreme:
                    result['overseas_growth_label'] = '高速扩张'
                elif overseas_pct >= gt.high_pct:
                    result['overseas_growth_label'] = '快速扩张'
                elif overseas_pct >= gt.mid_pct:
                    result['overseas_growth_label'] = '初步验证'
                elif overseas_pct < gt.low_pct and (overseas_growth or 0) > gt.growth_high:
                    result['overseas_growth_label'] = '仍然很小'
                    result['overseas_risks'].append('海外增长快但基数低')
                else:
                    result['overseas_growth_label'] = '海外放缓'
                if overseas_pct >= gt.mid_pct:
                    result['overseas_risks'].extend(['监管/合规风险', '汇率波动风险', '渠道管理风险'])

            detailed_geo = self._extract_detailed_geo_with_pct(text)
            hk_pcts = detailed_geo.get('hong_kong', {})
            mainland_pcts = detailed_geo.get('mainland', {})
            other_pcts = detailed_geo.get('other', {})

            if not hk_pcts:
                hk_table = extract_segment_table(text, self._HK_ALIASES)
                for alias in self._HK_ALIASES:
                    if alias in hk_table:
                        hk_pcts = hk_table[alias]
                        break

            if hk_pcts:
                hk_years = sorted(hk_pcts.keys())
                hk_latest = hk_years[-1]
                result['hong_kong_revenue_pct'] = hk_pcts.get(hk_latest)
                if len(hk_years) >= 2:
                    hk_prev = hk_years[-2]
                    hk_prev_val = hk_pcts.get(hk_prev)
                    hk_latest_val = hk_pcts.get(hk_latest)
                    if _is_num(hk_prev_val) and _is_num(hk_latest_val):
                        diff = hk_latest_val - hk_prev_val
                        if diff > 1:
                            result['hong_kong_revenue_trend'] = '上升'
                        elif diff < -1:
                            result['hong_kong_revenue_trend'] = '下降'
                        else:
                            result['hong_kong_revenue_trend'] = '平稳'

            if mainland_pcts:
                ml_years = sorted(mainland_pcts.keys())
                ml_latest = ml_years[-1]
                result['mainland_revenue_pct'] = mainland_pcts.get(ml_latest)

            result['detailed_geo_table'] = {
                'mainland': mainland_pcts,
                'hong_kong': hk_pcts,
                'other': other_pcts,
            }

            if result['china_revenue_latest'] is not None or result['overseas_revenue_pct'] is not None:
                result['confidence'] = result['geographic_confidence']
        except Exception as e:
            logger.warning("%s: %s", type(self).__name__, e)
            result['_error'] = str(e)
        return result

    def _validate_geo_data(self, result, prospectus_info):
        """校验地域收入数据的合理性。"""
        from datetime import date
        current_year = date.today().year
        validation = {'valid': True, 'reason': ''}

        # 1. 检查年份是否超出合理范围（未来超过2年）
        geo_table = result.get('geographic_table', {})
        all_years = []
        for k, v in geo_table.items():
            if isinstance(v, dict):
                all_years.extend([int(y) for y in v.keys() if str(y).isdigit()])
        for y in all_years:
            if y > current_year + 2:
                validation['valid'] = False
                validation['reason'] = f"地域收入包含未来年份({y})，超出合理范围"
                return validation

        # 2. 检查分地区收入合计是否明显超过总收入
        revenue = prospectus_info.get('revenue')
        if _is_num(revenue) and revenue > 0:
            # 如果是从 segment table 提取的原始金额（非百分比）
            china_latest = result.get('china_revenue_latest')
            overseas_latest = result.get('overseas_revenue_latest')
            if _is_num(china_latest) and _is_num(overseas_latest):
                total_geo = china_latest + overseas_latest
                # 允许 10% 的误差（因为币种/单位可能不同）
                if total_geo > revenue * 1.5:
                    validation['valid'] = False
                    validation['reason'] = f"分地区收入合计({total_geo:.1f})显著超过总收入({revenue:.1f})，单位或币种可能不一致"
                    return validation

        # 3. 检查百分比合计是否超过 100%
        if isinstance(geo_table, dict):
            for year_str, vals in geo_table.items():
                if isinstance(vals, dict):
                    total_pct = sum(v for v in vals.values() if _is_num(v))
                    if total_pct > 110:
                        validation['valid'] = False
                        validation['reason'] = f"地域收入占比合计({total_pct:.1f}%)超过100%，数据可能重复计算"
                        return validation

        return validation

    def _extract_overseas_pct_direct(self, text):
        lines = text.split('\n')
        for i, line in enumerate(lines):
            ll = line.lower().strip()
            if any(alias.lower() in ll for alias in self._OVERSEAS_ALIASES):
                window = ' '.join(lines[i:min(i + 6, len(lines))])
                pcts = [float(m) for m in _GEO_PCT_RE.findall(window) if 0 < float(m) <= 100]
                if pcts:
                    return pcts[-1]
        return None

    def _extract_geo_with_pct(self, text):
        lines = text.split('\n')
        result = {'china': {}, 'overseas': {}}

        year_matches = _GEO_YEAR_RE.findall(text)
        geo_years = sorted({int(y) for y in year_matches if 2015 <= int(y) <= 2030})
        if len(geo_years) < 2:
            from datetime import date
            this_year = date.today().year
            geo_years = [this_year - 2, this_year - 1, this_year]

        for i, line in enumerate(lines):
            ll = line.lower().strip()
            if 'subtotal' in ll or 'total' in ll:
                continue
            is_china, is_overseas = self._classify_geo_line(ll)
            if not is_overseas and not is_china:
                continue

            key = 'overseas' if is_overseas else 'china'

            nums_after = []
            for j in range(i + 1, min(i + 15, len(lines))):
                next_line = lines[j].strip()
                next_lower = next_line.lower()
                if self._classify_geo_line(next_lower) != (False, False):
                    break
                if 'total' in next_lower:
                    break
                for m in _GEO_NUMERIC_LINE_RE.finditer(next_line):
                    raw = m.group(1).replace(',', '')
                    try:
                        val = float(raw)
                        nums_after.append(val)
                    except ValueError:
                        continue

            pcts = [v for v in nums_after if 0 < v <= 100]
            amounts = [v for v in nums_after if v > 100]

            if len(pcts) >= 2 and len(amounts) >= 2:
                if key in result and result[key]:
                    continue
                n_pcts = min(len(pcts), len(geo_years), 3)
                used_years = geo_years[-n_pcts:] if len(geo_years) >= n_pcts else geo_years
                result[key] = {used_years[yi]: pcts[yi] for yi in range(n_pcts)}

        return result

    def _extract_detailed_geo_with_pct(self, text):
        lines = text.split('\n')
        result = {'mainland': {}, 'hong_kong': {}, 'other': {}}

        year_matches = _GEO_YEAR_RE.findall(text)
        geo_years = sorted({int(y) for y in year_matches if 2015 <= int(y) <= 2030})
        if len(geo_years) < 2:
            from datetime import date
            this_year = date.today().year
            geo_years = [this_year - 2, this_year - 1, this_year]

        for i, line in enumerate(lines):
            ll = line.lower().strip()
            if 'subtotal' in ll or 'total' in ll:
                continue
            key = self._classify_geo_line_detailed(ll)
            if key is None:
                continue

            nums_after = []
            for j in range(i + 1, min(i + 15, len(lines))):
                next_line = lines[j].strip()
                next_lower = next_line.lower()
                if self._classify_geo_line_detailed(next_lower) is not None:
                    break
                if 'total' in next_lower:
                    break
                for m in _GEO_NUMERIC_LINE_RE.finditer(next_line):
                    raw = m.group(1).replace(',', '')
                    try:
                        val = float(raw)
                        nums_after.append(val)
                    except ValueError:
                        continue

            pcts = [v for v in nums_after if 0 < v <= 100]
            amounts = [v for v in nums_after if v > 100]

            if len(pcts) >= 2 and len(amounts) >= 2:
                if key in result and result[key]:
                    continue
                n_pcts = min(len(pcts), len(geo_years), 3)
                used_years = geo_years[-n_pcts:] if len(geo_years) >= n_pcts else geo_years
                result[key] = {used_years[yi]: pcts[yi] for yi in range(n_pcts)}

        return result
