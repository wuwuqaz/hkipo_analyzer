import re
import logging
from ..utils import _is_num
from ..table_extraction import extract_segment_table
from ..settings import SETTINGS
logger = logging.getLogger(__name__)


class GeographicExpansionAnalyzer:
    _CHINA_ALIASES = ['Chinese mainland', 'Mainland China', 'PRC', 'China market', "People's Republic of China"]
    _OVERSEAS_ALIASES = ['Overseas', 'International', 'Other countries and regions', 'Outside mainland China', 'Non-PRC', 'Outside the PRC']

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

            overseas_pct = result.get('overseas_revenue_pct')
            overseas_growth = result.get('overseas_growth_pct')
            gt = SETTINGS.geographic
            if overseas_pct is not None:
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

            if result['china_revenue_latest'] is not None or result['overseas_revenue_pct'] is not None:
                result['confidence'] = result['geographic_confidence']
        except Exception as e:
            logger.warning("%s: %s", type(self).__name__, e)
            result['_error'] = str(e)
        return result

    def _extract_overseas_pct_direct(self, text):
        lines = text.split('\n')
        for i, line in enumerate(lines):
            ll = line.lower().strip()
            if any(alias.lower() in ll for alias in self._OVERSEAS_ALIASES):
                window = ' '.join(lines[i:min(i + 6, len(lines))])
                pcts = [float(m) for m in re.findall(r'(\d+\.?\d*)\s*%', window) if 0 < float(m) <= 100]
                if pcts:
                    return pcts[-1]
        return None

    def _extract_geo_with_pct(self, text):
        lines = text.split('\n')
        result = {'china': {}, 'overseas': {}}

        year_matches = re.findall(r'\b(20\d{2})\b', text)
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
                for m in re.finditer(r'^(\d[\d,]*\.?\d*)$', next_line):
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
