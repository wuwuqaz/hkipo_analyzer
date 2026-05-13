import re
import logging
from ..utils import _is_num
from ..settings import SETTINGS
logger = logging.getLogger(__name__)


class CustomerSupplierAnalyzer:
    _NUM_WORDS = {
        'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
        'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
        'all': None,
    }

    @staticmethod
    def _latest_pct_after(text, phrase_pattern, window=900, stop_patterns=None):
        """Extract the latest track-record percentage after a customer/supplier phrase."""
        match = re.search(phrase_pattern, text, re.IGNORECASE)
        if not match:
            return None
        segment = text[match.end():match.end() + window]
        default_stops = [
            r'\n[A-Z][A-Z\s,&/()-]{8,}\n',
            r'CONTROLLING\s+SHAREHOLDERS\b',
            r'RISK\s+FACTORS\b',
        ]
        stop_positions = []
        for stop_pattern in (stop_patterns or []) + default_stops:
            stop = re.search(stop_pattern, segment, re.IGNORECASE)
            if stop:
                stop_positions.append(stop.start())
        if stop_positions:
            segment = segment[:min(stop_positions)]
        pcts = re.findall(r'(\d+(?:\.\d+)?)\s*%', segment)
        if not pcts:
            return None
        try:
            return float(pcts[-1])
        except ValueError:
            return None

    @classmethod
    def _num_token(cls, token, total=None):
        if token is None:
            return None
        raw = str(token).strip().lower()
        if raw.isdigit():
            return int(raw)
        if raw == 'all' and total is not None:
            return total
        return cls._NUM_WORDS.get(raw)

    @staticmethod
    def _latest_pct_near(text, phrase_pattern, window=900, stop_patterns=None):
        matches = list(re.finditer(phrase_pattern, text, re.IGNORECASE))
        if not matches:
            return None
        segment = text[matches[-1].start():matches[-1].end() + window]
        for stop_pattern in stop_patterns or []:
            stop = re.search(stop_pattern, segment[matches[-1].end() - matches[-1].start():], re.IGNORECASE)
            if stop:
                segment = segment[:matches[-1].end() - matches[-1].start() + stop.start()]
                break
        pcts = re.findall(r'(\d+(?:\.\d+)?)\s*%', segment)
        if pcts:
            try:
                return float(pcts[-1])
            except ValueError:
                return None
        year_pct = []
        for m in re.finditer(r'(20\d{2})[^%]{0,120}?(\d+(?:\.\d+)?)\s*%', segment, re.IGNORECASE):
            try:
                year_pct.append((int(m.group(1)), float(m.group(2))))
            except ValueError:
                continue
        if year_pct:
            return sorted(year_pct, key=lambda item: item[0])[-1][1]
        return None

    def _extract_customer_quality(self, text):
        lower = text.lower()
        result = {
            'customer_retention_rate_pct': None,
            'net_dollar_retention_rate_pct': None,
            'top_global_service_robotics_customers_count': None,
            'top_global_service_robotics_customers_total': None,
            'top_global_commercial_service_robotics_customers_count': None,
            'top_global_commercial_service_robotics_customers_total': None,
            'head_customer_supply_chain': None,
            'customer_quality_score': 0,
            'customer_quality_label': '缺失',
            'customer_quality_reasons': [],
            'customer_validation_summary': '',
        }

        top_service = re.search(
            r'\b(7|seven)\s+(?:of|out\s+of)\s+(?:the\s+)?(?:top\s+)?(10|ten)\s+global\s+service\s+robot(?:ics)?\s+compan',
            lower,
            re.IGNORECASE,
        )
        if not top_service:
            top_service = re.search(
                r'\b(7|seven)\s+(?:of|out\s+of)\s+(?:the\s+)?(?:world|global)[^.\n]{0,80}?service\s+robot(?:ics)?\s+compan',
                lower,
                re.IGNORECASE,
            )
        if top_service:
            count = self._num_token(top_service.group(1), 10)
            total = self._num_token(top_service.group(2), 10) if top_service.lastindex and top_service.lastindex >= 2 else 10
            result['top_global_service_robotics_customers_count'] = count
            result['top_global_service_robotics_customers_total'] = total or 10

        top_commercial = re.search(
            r'\b(all|5|five)\s+(?:of\s+)?(?:the\s+)?(?:top\s+)?(5|five)\s+global\s+commercial\s+service\s+robot(?:ics)?\s+compan',
            lower,
            re.IGNORECASE,
        )
        if top_commercial:
            total = self._num_token(top_commercial.group(2), 5) or 5
            count = self._num_token(top_commercial.group(1), total)
            result['top_global_commercial_service_robotics_customers_count'] = count
            result['top_global_commercial_service_robotics_customers_total'] = total

        result['customer_retention_rate_pct'] = self._latest_pct_near(
            text,
            r'customer\s+retention\s+rate|客户留存率',
            stop_patterns=[r'net\s+dollar\s+retention|net\s+revenue\s+retention|\bNDR\b|净美元留存|净收入留存'],
        )
        result['net_dollar_retention_rate_pct'] = self._latest_pct_near(
            text,
            r'net\s+dollar\s+retention\s+rate|net\s+revenue\s+retention|\bNDR\b|净美元留存率|净收入留存率',
        )

        has_head_customer = any([
            result['top_global_service_robotics_customers_count'],
            result['top_global_commercial_service_robotics_customers_count'],
            'supply chain' in lower and 'customer' in lower,
        ])
        result['head_customer_supply_chain'] = bool(has_head_customer) if has_head_customer else None

        sw = SETTINGS.scoring
        score = 0
        reasons = []
        service_count = result['top_global_service_robotics_customers_count']
        service_total = result['top_global_service_robotics_customers_total']
        if service_count and service_total:
            score += sw.customer_supply_chain_high if service_count / service_total >= 0.6 else sw.customer_supply_chain_mid
            reasons.append(f"进入全球头部服务机器人客户供应链({service_count}/{service_total})")
        commercial_count = result['top_global_commercial_service_robotics_customers_count']
        commercial_total = result['top_global_commercial_service_robotics_customers_total']
        if commercial_count and commercial_total:
            score += sw.customer_commercial_high if commercial_count >= commercial_total else sw.customer_commercial_mid
            reasons.append(f"覆盖全球头部商用服务机器人客户({commercial_count}/{commercial_total})")
        retention = result['customer_retention_rate_pct']
        if _is_num(retention):
            if retention >= 95:
                score += sw.customer_retention_high
            elif retention >= 85:
                score += sw.customer_retention_mid
            reasons.append(f"客户留存率{retention:.0f}%")
        ndr = result['net_dollar_retention_rate_pct']
        if _is_num(ndr):
            if ndr >= 120:
                score += sw.customer_ndr_high
            elif ndr >= 100:
                score += sw.customer_ndr_mid
            reasons.append(f"净美元留存率{ndr:.0f}%")

        result['customer_quality_score'] = min(100, score)
        if score >= 70:
            result['customer_quality_label'] = '强'
        elif score >= 45:
            result['customer_quality_label'] = '中'
        elif score > 0:
            result['customer_quality_label'] = '弱'
        result['customer_quality_reasons'] = reasons
        result['customer_validation_summary'] = '；'.join(reasons[:4])
        return result

    def analyze(self, prospectus_info: dict, text: str = '', ipo_data: dict = None) -> dict:
        # 防御：某些调用者把 ipo_data 传到了 text 位置
        if isinstance(text, dict):
            text = ''
        result = {
            'top5_customer_revenue_pct': None,
            'largest_customer_revenue_pct': None,
            'top5_supplier_purchase_pct': None,
            'largest_supplier_purchase_pct': None,
            'customer_retention_rate_pct': None,
            'net_dollar_retention_rate_pct': None,
            'top_global_service_robotics_customers_count': None,
            'top_global_service_robotics_customers_total': None,
            'top_global_commercial_service_robotics_customers_count': None,
            'top_global_commercial_service_robotics_customers_total': None,
            'head_customer_supply_chain': None,
            'customer_quality_score': 0,
            'customer_quality_label': '缺失',
            'customer_quality_reasons': [],
            'customer_validation_summary': '',
            'concentration_risk_label': '缺失',
            'concentration_score_penalty': 0,
            'confidence': 'missing',
        }
        try:
            result['top5_customer_revenue_pct'] = self._latest_pct_after(
                text,
                r'(?:five\s+largest\s+customers|top\s+five\s+customers)\b',
                stop_patterns=[
                    r'revenue\s+generated\s+from\s+our\s+largest\s+customer\b',
                    r'our\s+revenue\s+generated\s+from\s+our\s+largest\s+customer\b',
                    r'our\s+largest\s+customer\b',
                    r'our\s+suppliers\b',
                    r'suppliers\s+primarily',
                    r'five\s+largest\s+suppliers\b',
                ],
            )
            result['largest_customer_revenue_pct'] = self._latest_pct_after(
                text,
                r'(?:single\s+largest\s+customer|largest\s+customer(?!s))\b',
                stop_patterns=[
                    r'our\s+revenue\s+generated\s+from\s+our\s+five\s+largest\s+customers\b',
                    r'five\s+largest\s+customers\b',
                    r'five\s+largest\s+suppliers\b',
                    r'our\s+suppliers\b',
                    r'suppliers\s+primarily',
                    r'our\s+transaction\s+amounts\s+with\s+our\s+largest\s+supplier\b',
                ],
            )
            result['top5_supplier_purchase_pct'] = self._latest_pct_after(
                text,
                r'(?:five\s+largest\s+suppliers|top\s+five\s+suppliers)\b',
                stop_patterns=[
                    r'single\s+largest\s+supplier\b',
                    r'largest\s+supplier(?!s)\b',
                ],
            )
            result['largest_supplier_purchase_pct'] = self._latest_pct_after(
                text,
                r'(?:single\s+largest\s+supplier|largest\s+supplier(?!s))\b',
                stop_patterns=[
                    r'our\s+transaction\s+amounts\s+with\s+our\s+five\s+largest\s+suppliers\b',
                    r'five\s+largest\s+suppliers\b',
                    r'we\s+select\s+our\s+suppliers\b',
                    r'see\s+["“]business',
                ],
            )

            penalty = 0
            top5_cust = result.get('top5_customer_revenue_pct')
            largest_cust_val = result.get('largest_customer_revenue_pct')
            top5_supp = result.get('top5_supplier_purchase_pct')
            largest_supp_val = result.get('largest_supplier_purchase_pct')
            ct = SETTINGS.customer_concentration

            if top5_cust is not None and top5_cust > ct.top5_customer_high:
                penalty += 3
            if largest_cust_val is not None and largest_cust_val > ct.largest_customer_high:
                penalty += 2
            if top5_supp is not None and top5_supp > ct.top5_supplier_high:
                penalty += 2
            if largest_supp_val is not None and largest_supp_val > ct.largest_supplier_high:
                penalty += 1

            result['concentration_score_penalty'] = penalty
            if penalty >= ct.penalty_high:
                result['concentration_risk_label'] = '高'
            elif penalty >= ct.penalty_mid:
                result['concentration_risk_label'] = '中'
            else:
                result['concentration_risk_label'] = '低'

            if top5_cust is not None:
                result['confidence'] = 'regex_context'
            quality = self._extract_customer_quality(text)
            result.update(quality)
            if quality.get('customer_quality_score', 0) > 0:
                result['confidence'] = 'regex_context'
        except Exception as e:
            logger.warning("%s: %s", type(self).__name__, e)
            result['_error'] = str(e)
        return result
