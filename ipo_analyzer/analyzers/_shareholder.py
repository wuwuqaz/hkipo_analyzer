import re
import logging
from ..utils import _is_num, extract_text_excerpts
logger = logging.getLogger(__name__)


class ShareholderAnalyzer:
    _PRE_IPO_PATTERNS = [
        r'pre[- ]IPO\s+investment',
        r'pre[- ]IPO\s+financing',
        r'series\s+[A-Z]',
        r'angel\s+(?:round|investment|financing)',
        r'上市前投资',
        r'上市前融资',
    ]

    _ROUND_PATTERNS = [
        (r'[Aa]ngel\s*(?:round|investment|financing)?', 'Angel'),
        (r'[Ss]eries\s+([A-Z](?:[-]\d)?)', 'Series'),
        (r'[Ss]eed\s*(?:round|investment|financing)?', 'Seed'),
        (r'[Pp]re[- ][A-Z]\s*(?:round|financing)?', 'Pre'),
        (r'[Ss]trategic\s*(?:round|investment|financing)?', 'Strategic'),
    ]

    _CONTROLLING_PATTERNS = [
        r'controlling\s+shareholders?\s+(?:collectively\s+)?(?:held|hold|own)\s+(?:approximately\s+)?([\d.]+)\s*%',
        r'controlling\s+shareholders?\s+(?:collectively\s+)?(?:were\s+)?interested\s+in\s+(?:approximately\s+)?([\d.]+)\s*%',
        r'控股股东.*?合计.*?(?:持有|持股|拥有).*?([\d.]+)\s*%',
    ]

    def analyze(self, prospectus_info, text='', ipo_data=None):
        if isinstance(text, dict):
            text = ''
        result = {
            'pre_ipo_rounds': [],
            'ipo_premium_vs_last_round_pct': None,
            'ipo_premium_label': '缺失',
            'controlling_shareholder_pct': None,
            'controlling_shareholder_label': '缺失',
            'shareholder_summary': '',
            'confidence': 'missing',
            'evidence_excerpt': '',
        }
        try:
            rounds = self._extract_pre_ipo_rounds(text, prospectus_info)
            result['pre_ipo_rounds'] = rounds

            if rounds:
                last_round = rounds[-1]
                cost_per_share = last_round.get('cost_per_share')
                offer_price = prospectus_info.get('offer_price')

                if _is_num(cost_per_share) and cost_per_share > 0 and _is_num(offer_price) and offer_price > 0:
                    premium = (offer_price - cost_per_share) / cost_per_share * 100
                    result['ipo_premium_vs_last_round_pct'] = round(premium, 1)
                    if premium > 50:
                        result['ipo_premium_label'] = '高溢价'
                    elif premium > 20:
                        result['ipo_premium_label'] = '溢价'
                    elif premium > -10:
                        result['ipo_premium_label'] = '持平'
                    else:
                        result['ipo_premium_label'] = '折让'

            ctrl_pct = self._extract_controlling_shareholder(text)
            if ctrl_pct is not None:
                result['controlling_shareholder_pct'] = ctrl_pct
                if ctrl_pct >= 30:
                    result['controlling_shareholder_label'] = '集中'
                elif ctrl_pct >= 20:
                    result['controlling_shareholder_label'] = '中等'
                else:
                    result['controlling_shareholder_label'] = '分散'

            parts = []
            if result['controlling_shareholder_pct'] is not None:
                parts.append(f"控股股东合计持股{result['controlling_shareholder_pct']:.1f}%")
            if rounds:
                last = rounds[-1]
                parts.append(f"Pre-IPO最后一轮{last.get('round_name', '')}({last.get('round_year', '')})投后估值RMB {last.get('post_money_valuation_million', '')}m")
            if result['ipo_premium_vs_last_round_pct'] is not None:
                parts.append(f"IPO溢价约{result['ipo_premium_vs_last_round_pct']:.1f}%")
            result['shareholder_summary'] = '，'.join(parts)

            if rounds or result['controlling_shareholder_pct'] is not None:
                result['confidence'] = 'regex_context'

            excerpt_patterns = [r'pre[- ]IPO\s+investment', r'controlling\s+shareholder', r'Series\s+[A-Z]']
            result['evidence_excerpt'] = "\n\n".join(
                extract_text_excerpts(text, excerpt_patterns, window=200, max_chars=1000, limit=3)
            )
        except Exception as e:
            logger.warning("%s: %s", type(self).__name__, e)
            result['_error'] = str(e)
        return result

    def _extract_pre_ipo_rounds(self, text, prospectus_info):
        rounds = []

        section_start = None
        lines = text.split('\n')
        for i, line in enumerate(lines):
            ll = line.lower().strip()
            if any(re.search(p, ll) for p in self._PRE_IPO_PATTERNS):
                section_start = i
                break

        if section_start is None:
            return rounds

        window_lines = lines[section_start:min(section_start + 300, len(lines))]
        window = '\n'.join(window_lines)

        for pattern, round_type in self._ROUND_PATTERNS:
            matches = list(re.finditer(pattern, window, re.IGNORECASE))
            for m in matches:
                round_name = m.group(0).strip()
                if round_type == 'Series':
                    suffix = m.group(1) if m.lastindex else ''
                    round_name = f"Series {suffix}"

                start_pos = m.start()
                context = window[start_pos:min(start_pos + 2000, len(window))]

                amount = self._extract_amount_from_context(context)
                valuation = self._extract_valuation_from_context(context)
                cost_per_share = self._extract_cost_per_share(context, prospectus_info)
                year = self._extract_year_from_context(context)

                if amount is not None or valuation is not None:
                    rounds.append({
                        'round_name': round_name,
                        'round_year': year,
                        'amount_million': amount,
                        'post_money_valuation_million': valuation,
                        'cost_per_share': cost_per_share,
                    })
                break

        if not rounds:
            table_pattern = re.search(
                r'(?:investment|financing)\s+(?:amount|consideration).*?(?:post[- ]?money\s+)?valuation.*?per\s+share',
                window, re.IGNORECASE | re.DOTALL
            )
            if table_pattern:
                table_context = window[table_pattern.start():min(table_pattern.start() + 3000, len(window))]
                for line in table_context.split('\n'):
                    for pattern, round_type in self._ROUND_PATTERNS:
                        if re.search(pattern, line, re.IGNORECASE):
                            nums = re.findall(r'[\d,]+\.?\d*', line)
                            if len(nums) >= 2:
                                round_name_match = re.search(pattern, line, re.IGNORECASE)
                                round_name = round_name_match.group(0).strip()
                                if round_type == 'Series' and round_name_match.lastindex:
                                    round_name = f"Series {round_name_match.group(1)}"
                                amount = None
                                valuation = None
                                cost = None
                                large_nums = [float(n.replace(',', '')) for n in nums if float(n.replace(',', '')) > 100]
                                small_nums = [float(n.replace(',', '')) for n in nums if 0 < float(n.replace(',', '')) <= 100]
                                if len(large_nums) >= 2:
                                    amount = large_nums[0]
                                    valuation = large_nums[1]
                                elif len(large_nums) >= 1:
                                    amount = large_nums[0]
                                if small_nums:
                                    cost = small_nums[0]
                                rounds.append({
                                    'round_name': round_name,
                                    'round_year': None,
                                    'amount_million': amount,
                                    'post_money_valuation_million': valuation,
                                    'cost_per_share': cost,
                                })
                            break

        return rounds

    def _extract_amount_from_context(self, context):
        patterns = [
            r'(?:investment|financing|amount|consideration).*?(?:RMB|HKD|USD|US\$)\s*([\d,]+\.?\d*)\s*(?:million|billion|m|bn)?',
            r'(?:RMB|HKD|USD|US\$)\s*([\d,]+\.?\d*)\s*(?:million|billion|m|bn)?\s*(?:investment|financing|amount|consideration)',
            r'invested\s+(?:an\s+aggregate\s+)?(?:amount|sum)\s+of\s+(?:approximately\s+)?(?:RMB|HKD|USD|US\$)\s*([\d,]+\.?\d*)',
        ]
        for p in patterns:
            m = re.search(p, context, re.IGNORECASE)
            if m:
                try:
                    val = float(m.group(1).replace(',', ''))
                    if 'billion' in context[m.start():m.end()].lower() or 'bn' in context[m.start():m.end()].lower():
                        val = val * 1000
                    return val
                except ValueError:
                    continue
        return None

    def _extract_valuation_from_context(self, context):
        patterns = [
            r'(?:post[- ]?money\s+)?valuation.*?(?:of\s+)?(?:approximately\s+)?(?:RMB|HKD|USD|US\$)\s*([\d,]+\.?\d*)\s*(?:million|billion|m|bn)?',
            r'(?:RMB|HKD|USD|US\$)\s*([\d,]+\.?\d*)\s*(?:million|billion|m|bn)?.*?(?:post[- ]?money\s+)?valuation',
        ]
        for p in patterns:
            m = re.search(p, context, re.IGNORECASE)
            if m:
                try:
                    val = float(m.group(1).replace(',', ''))
                    if 'billion' in context[m.start():m.end()].lower() or 'bn' in context[m.start():m.end()].lower():
                        val = val * 1000
                    return val
                except ValueError:
                    continue
        return None

    def _extract_cost_per_share(self, context, prospectus_info):
        patterns = [
            r'(?:cost|price)\s+per\s+share.*?(?:RMB|HKD|USD|US\$)\s*([\d,]+\.?\d*)',
            r'(?:RMB|HKD|USD|US\$)\s*([\d,]+\.?\d*)\s*(?:per\s+share|each\s+share)',
        ]
        for p in patterns:
            m = re.search(p, context, re.IGNORECASE)
            if m:
                try:
                    return float(m.group(1).replace(',', ''))
                except ValueError:
                    continue
        return None

    def _extract_year_from_context(self, context):
        m = re.search(r'\b(20\d{2})\b', context)
        if m:
            year = int(m.group(1))
            if 2010 <= year <= 2030:
                return year
        return None

    def _extract_controlling_shareholder(self, text):
        for pattern in self._CONTROLLING_PATTERNS:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                try:
                    return float(m.group(1))
                except ValueError:
                    continue
        return None
