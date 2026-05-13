import re
import logging
from ..settings import SETTINGS
logger = logging.getLogger(__name__)


class ProductionCapacityAnalyzer:
    @staticmethod
    def _extract_utilization_rate(text):
        util_match = re.search(r'utili[sz]ation\s+rate(?:\s+of\s+production\s+line)?', text, re.IGNORECASE)
        if util_match:
            segment = text[util_match.start():util_match.start() + 1200]
            pcts = re.findall(r'(\d+(?:\.\d+)?)\s*%', segment)
            if pcts:
                try:
                    return float(pcts[-1])
                except ValueError:
                    return None

        direct_match = re.search(r'utili[sz]ation\s+rate\s*(?:of|was|:)\s*(\d+\.?\d*)\s*%', text, re.IGNORECASE)
        if direct_match:
            return float(direct_match.group(1))

        capacity_match = re.search(r'(\d+\.?\d*)\s*%\s*(?:of\s+)?(?:our\s+)?production\s+capacity', text, re.IGNORECASE)
        if capacity_match:
            return float(capacity_match.group(1))
        return None

    def analyze(self, prospectus_info, text='', ipo_data=None):
        # 防御：某些调用者把 ipo_data 传到了 text 位置
        if isinstance(text, dict):
            text = ''
        result = {
            'utilization_rate': None,
            'expansion_plan': None,
            'outsourced_production': None,
            'capacity_score': 0,
            'capacity_summary': '缺失',
            'confidence': 'missing',
        }
        try:
            result['utilization_rate'] = self._extract_utilization_rate(text)

            if re.search(r'outsourc|subcontract|sterilization\s+service', text, re.IGNORECASE):
                result['outsourced_production'] = True

            if re.search(r'expansion|new\s+production\s+facility|new\s+manufacturing', text, re.IGNORECASE):
                result['expansion_plan'] = True

            util = result.get('utilization_rate')
            ct = SETTINGS.capacity
            if util is not None:
                if util > ct.overload:
                    result['capacity_score'] = 8
                    result['capacity_summary'] = f'产能紧张(利用率{util:.0f}%)，扩产有紧迫性但需关注执行风险'
                elif util > ct.high:
                    result['capacity_score'] = 7
                    result['capacity_summary'] = f'产能利用率高({util:.0f}%)，扩产有合理性'
                elif util > ct.moderate:
                    result['capacity_score'] = 5
                    result['capacity_summary'] = f'产能利用率适中({util:.0f}%)'
                else:
                    result['capacity_score'] = 2
                    result['capacity_summary'] = f'产能利用率偏低({util:.0f}%)，募资扩产需谨慎'
                result['confidence'] = 'regex_context'
        except Exception as e:
            logger.warning("%s: %s", type(self).__name__, e)
            result['_error'] = str(e)
        return result
