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

    def _extract_customer_quality(self, text, sector='unknown'):
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

        # --- 机器人行业客户质量提取（原有逻辑） ---
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

        # --- 多行业客户质量提取（新增） ---
        industry_customer_data = self._extract_industry_customer(text, sector)

        has_head_customer = any([
            result['top_global_service_robotics_customers_count'],
            result['top_global_commercial_service_robotics_customers_count'],
            industry_customer_data.get('has_head_customer'),
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
        
        # 多行业客户质量得分
        if industry_customer_data.get('head_customer_score', 0) > 0:
            score += industry_customer_data['head_customer_score']
            reasons.extend(industry_customer_data.get('head_customer_reasons', []))
        
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

    def _extract_industry_customer(self, text, sector):
        """按行业提取客户质量数据（Biotech/SaaS/硬件/消费）"""
        lower = text.lower()
        data = {
            'has_head_customer': False,
            'head_customer_score': 0,
            'head_customer_reasons': [],
        }

        if sector == 'healthcare':
            # Biotech: 头部医院、CRO、药企合作伙伴
            head_hospital = re.search(
                r'(?:top|leading|major|prestigious)\s+(?:\d+\s+)?(?:hospitals|medical centers|medical institutions)'
                r'(?:\s+in\s+(?:china|asia|the\s+world))?'
                r'[^.]{0,200}?(?:partner|collaborat|customer|client)',
                lower,
            )
            if head_hospital:
                data['has_head_customer'] = True
                data['head_customer_score'] += 30
                data['head_customer_reasons'].append("覆盖头部医院/医疗机构合作伙伴")

            pharma_partner = re.search(
                r'(?:top|leading|major|global|multinational)\s+(?:\d+\s+)?(?:pharma|pharmaceutical|biotech)\s+(?:compan|partner|collaborat)',
                lower,
            )
            if pharma_partner:
                data['has_head_customer'] = True
                data['head_customer_score'] += 25
                data['head_customer_reasons'].append("与头部药企/跨国药企合作")

            cro_partner = re.search(
                r'(?:top|leading|major)\s+(?:\d+\s+)?(?:CRO|contract\s+research|contract\s+manufacturing)',
                lower,
            )
            if cro_partner:
                data['has_head_customer'] = True
                data['head_customer_score'] += 20
                data['head_customer_reasons'].append("与头部CRO/CMO合作")

            # 临床合作机构数量
            site_count = re.search(r'(\d+)\s+(?:clinical\s+)?(?:sites?|hospitals|centers?|institutions?)\s+(?:in|across|worldwide)', lower)
            if site_count:
                count = int(site_count.group(1))
                if count >= 50:
                    data['head_customer_score'] += 15
                    data['head_customer_reasons'].append(f"临床覆盖{count}+机构，网络广泛")
                elif count >= 20:
                    data['head_customer_score'] += 10
                    data['head_customer_reasons'].append(f"临床覆盖{count}+机构")

        elif sector in ('saas', 'software', 'technology'):
            # SaaS: 头部企业客户、Fortune 500
            fortune_500 = re.search(
                r'(?:fortune\s+500|fortune\s+global\s+500|fortune\s+1000|forbes\s+global\s+2000)',
                lower,
            )
            if fortune_500:
                data['has_head_customer'] = True
                data['head_customer_score'] += 30
                data['head_customer_reasons'].append("覆盖Fortune 500/全球头部企业客户")

            enterprise_count = re.search(
                r'(?:over|more\s+than|approximately)?\s*(\d+,?\d*)\s+(?:enterprise|business|corporate)\s+(?:customers?|clients?)',
                lower,
            )
            if enterprise_count:
                count_str = enterprise_count.group(1).replace(',', '')
                count = int(count_str) if count_str.isdigit() else 0
                if count >= 1000:
                    data['head_customer_score'] += 20
                    data['head_customer_reasons'].append(f"服务{count}+企业客户")
                elif count >= 100:
                    data['head_customer_score'] += 15
                    data['head_customer_reasons'].append(f"服务{count}+企业客户")
                elif count >= 10:
                    data['head_customer_score'] += 10
                    data['head_customer_reasons'].append(f"服务{count}+企业客户")

        elif sector == 'hardtech':
            # 硬件/制造: 头部渠道商、订单可见度、供应链伙伴
            head_customer = re.search(
                r'(?:top|leading|major|global)\s+(?:\d+\s+)?(?:customer|client|partner|distributor|channel)',
                lower,
            )
            if head_customer:
                data['has_head_customer'] = True
                data['head_customer_score'] += 25
                data['head_customer_reasons'].append("与头部客户/渠道商合作")

            backlog = re.search(
                r'(?:backlog|order\s+book|orders?[\s-]in[-\s]hand)[^.]{0,200}?(\$|€|¥|HKD?|RMB?)?\s*([0-9,]+(?:\.[0-9]+)?)\s*(million|billion|m|bn|亿|万)?',
                lower,
            )
            if backlog:
                data['has_head_customer'] = True
                data['head_customer_score'] += 15
                data['head_customer_reasons'].append("订单可见度高（有明确backlog）")

        elif sector == 'consumer':
            # 消费品牌: 头部渠道、零售网点数量
            retail_count = re.search(
                r'(?:over|more\s+than|approximately)?\s*(\d+,?\d*)\s+(?:retail\s+)?(?:stores?|outlets?|shops?|points?\s+of\s+sale)',
                lower,
            )
            if retail_count:
                count_str = retail_count.group(1).replace(',', '')
                count = int(count_str) if count_str.isdigit() else 0
                if count >= 1000:
                    data['has_head_customer'] = True
                    data['head_customer_score'] += 20
                    data['head_customer_reasons'].append(f"零售网络覆盖{count}+网点")
                elif count >= 100:
                    data['has_head_customer'] = True
                    data['head_customer_score'] += 15
                    data['head_customer_reasons'].append(f"零售网络覆盖{count}+网点")

        return data

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
            sector = prospectus_info.get('sector', 'unknown')
            quality = self._extract_customer_quality(text, sector)
            result.update(quality)
            if quality.get('customer_quality_score', 0) > 0:
                result['confidence'] = 'regex_context'
        except Exception as e:
            logger.warning("%s: %s", type(self).__name__, e)
            result['_error'] = str(e)
        return result
