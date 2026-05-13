import re
import logging
from ..utils import _is_num, extract_text_excerpts
from ..settings import SETTINGS
from . import _adjust_for_unit
logger = logging.getLogger(__name__)


class OrderBacklogAnalyzer:
    _ORDER_PATTERNS = [
        r'newly\s+signed',
        r'新签',
        r'order\s+book',
        r'backlog',
        r'remaining\s+(?:order|contract|backlog)',
        r'unconfirmed\s+revenue',
        r'未确认.*?收入',
        r'在手订单',
        r'待执行合同',
        r'contract\s+value',
        r'transaction\s+value',
    ]

    _AMOUNT_PATTERNS = [
        r'(?:RMB|HKD|USD|US\$)\s*([\d,]+\.?\d*)\s*(?:million|billion|m|bn)?',
        r'([\d,]+\.?\d*)\s*(?:million|billion)\s*(?:RMB|HKD|USD)',
    ]

    def analyze(self, prospectus_info, text='', ipo_data=None):
        if isinstance(text, dict):
            text = ''
        result = {
            'new_order_amount_million': None,
            'remaining_backlog_million': None,
            'post_period_new_order_million': None,
            'order_to_revenue_ratio': None,
            'backlog_coverage_months': None,
            'order_visibility_label': '缺失',
            'order_visibility_reasons': [],
            'confidence': 'missing',
            'evidence_excerpt': '',
        }
        try:
            new_order = self._extract_new_order_amount(text, prospectus_info)
            remaining = self._extract_remaining_backlog(text, prospectus_info)
            post_period = self._extract_post_period_order(text, prospectus_info)

            result['new_order_amount_million'] = new_order
            result['remaining_backlog_million'] = remaining
            result['post_period_new_order_million'] = post_period

            revenue = prospectus_info.get('revenue')
            if _is_num(new_order) and _is_num(revenue) and revenue > 0:
                result['order_to_revenue_ratio'] = round(new_order / revenue, 2)

            if _is_num(remaining) and _is_num(revenue) and revenue > 0:
                monthly_revenue = revenue / 12
                if monthly_revenue > 0:
                    result['backlog_coverage_months'] = round(remaining / monthly_revenue, 1)

            reasons = []
            label = '缺失'
            ot = SETTINGS.order_backlog
            ratio = result.get('order_to_revenue_ratio')
            months = result.get('backlog_coverage_months')

            if _is_num(ratio):
                if ratio >= ot.order_ratio_strong:
                    reasons.append(f'新签订单约为收入{ratio:.1f}倍')
                elif ratio >= ot.order_ratio_moderate:
                    reasons.append(f'新签订单约为收入{ratio:.1f}倍')
                else:
                    reasons.append(f'新签订单仅为收入{ratio:.1f}倍')

            if _is_num(months):
                if months >= ot.backlog_months_strong:
                    reasons.append(f'剩余订单覆盖约{months:.0f}个月收入')
                elif months >= ot.backlog_months_moderate:
                    reasons.append(f'剩余订单覆盖约{months:.0f}个月收入')
                else:
                    reasons.append(f'剩余订单仅覆盖约{months:.0f}个月收入')

            if _is_num(ratio) and _is_num(months):
                if ratio >= ot.order_ratio_strong and months >= ot.backlog_months_strong:
                    label = '强'
                elif ratio >= ot.order_ratio_moderate and months >= ot.backlog_months_moderate:
                    label = '中等'
                else:
                    label = '弱'
            elif _is_num(ratio):
                if ratio >= ot.order_ratio_moderate:
                    label = '中等'
                else:
                    label = '弱'
            elif _is_num(months):
                if months >= ot.backlog_months_moderate:
                    label = '中等'
                else:
                    label = '弱'

            result['order_visibility_label'] = label
            result['order_visibility_reasons'] = reasons

            if new_order is not None or remaining is not None:
                result['confidence'] = 'regex_context'

            excerpt_patterns = [r'newly\s+signed', r'backlog', r'remaining\s+order', r'新签', r'在手订单']
            result['evidence_excerpt'] = "\n\n".join(
                extract_text_excerpts(text, excerpt_patterns, window=200, max_chars=1000, limit=3)
            )
        except Exception as e:
            logger.warning("%s: %s", type(self).__name__, e)
            result['_error'] = str(e)
        return result

    def _extract_new_order_amount(self, text, prospectus_info):
        patterns = [
            r'newly\s+signed\s+(?:orders?|contracts?|agreements?).*?(?:RMB|HKD|USD|US\$)\s*([\d,]+\.?\d*)\s*(?:million|billion|m|bn)?',
            r'(?:RMB|HKD|USD|US\$)\s*([\d,]+\.?\d*)\s*(?:million|billion|m|bn)?.*?newly\s+signed',
            r'(?:new|total)\s+(?:order|contract)\s+(?:value|amount).*?(?:RMB|HKD|USD|US\$)\s*([\d,]+\.?\d*)',
            r'新签.*?(?:订单|合同).*?(?:约|approximately)?\s*([\d,]+\.?\d*)\s*(?:百万|亿元|million|billion)?',
            r'交易金额.*?约\s*(?:RMB|HKD)?\s*([\d,]+\.?\d*)\s*(?:百万|million)?',
        ]
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                try:
                    val = float(m.group(1).replace(',', ''))
                    unit_context = text[max(0, m.start() - 200):m.end()]
                    if 'billion' in unit_context.lower() or 'bn' in unit_context.lower() or '亿' in unit_context:
                        val = val * 1000
                    return _adjust_for_unit(val, unit_context)
                except ValueError:
                    continue
        return None

    def _extract_remaining_backlog(self, text, prospectus_info):
        patterns = [
            r'remaining\s+(?:order|contract|backlog).*?(?:RMB|HKD|USD|US\$)\s*([\d,]+\.?\d*)\s*(?:million|billion|m|bn)?',
            r'(?:RMB|HKD|USD|US\$)\s*([\d,]+\.?\d*)\s*(?:million|billion|m|bn)?.*?remaining\s+(?:order|contract|backlog)',
            r'unconfirmed\s+revenue.*?(?:RMB|HKD|USD|US\$)\s*([\d,]+\.?\d*)',
            r'剩余.*?(?:订单|合同|未确认).*?(?:约|approximately)?\s*([\d,]+\.?\d*)',
        ]
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                try:
                    val = float(m.group(1).replace(',', ''))
                    unit_context = text[max(0, m.start() - 200):m.end()]
                    if 'billion' in unit_context.lower() or 'bn' in unit_context.lower() or '亿' in unit_context:
                        val = val * 1000
                    return _adjust_for_unit(val, unit_context)
                except ValueError:
                    continue
        return None

    def _extract_post_period_order(self, text, prospectus_info):
        patterns = [
            r'(?:after|subsequent\s+to)\s+(?:the\s+)?(?:reporting|financial)\s+(?:period|year).*?(?:RMB|HKD|USD|US\$)\s*([\d,]+\.?\d*)',
            r'(?:after|subsequent\s+to).*?(?:new|additional)\s+(?:order|contract).*?(?:RMB|HKD|USD|US\$)\s*([\d,]+\.?\d*)',
            r'报告期后.*?(?:新签|新增).*?(?:约|approximately)?\s*([\d,]+\.?\d*)',
        ]
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                try:
                    val = float(m.group(1).replace(',', ''))
                    unit_context = text[max(0, m.start() - 200):m.end()]
                    if 'billion' in unit_context.lower() or 'bn' in unit_context.lower() or '亿' in unit_context:
                        val = val * 1000
                    return _adjust_for_unit(val, unit_context)
                except ValueError:
                    continue
        return None
