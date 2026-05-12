import re
import logging
from ..utils import _is_num
from ..settings import SETTINGS
logger = logging.getLogger(__name__)


class RiskFactorAnalyzer:
    def analyze(self, prospectus_info, text='', ipo_data=None):
        # 防御：某些调用者把 ipo_data 传到了 text 位置
        if isinstance(text, dict):
            text = ''
        result = {
            'risks': {},
            'total_penalty': 0,
            'confidence': 'missing',
        }
        try:
            risk_categories = {
                'price_competition_risk': ['average selling price', r'\bASP\b', 'price competition', 'price pressure', 'price reduction', 'decreased by'],
                'cash_flow_pressure_risk': ['net cash used in operating activities', 'operating cash flow', 'working capital pressure', 'cash outflow'],
                'inventory_pressure_risk': ['inventory', 'built up inventory', 'write-down', 'obsolete', 'slow-moving'],
                'customer_concentration_risk': ['customer concentration', 'largest customer', 'dependent on'],
                'supplier_concentration_risk': ['supplier', 'raw material', 'supply chain', 'single source'],
                'overseas_channel_tariff_risk': ['overseas', 'export', 'tariff', 'trade protection', 'customs', 'amazon', 'sales channels', 'logistics'],
                'social_insurance_housing_fund_risk': ['social insurance', 'housing provident fund', 'underpaid', 'shortfall', '住房公积金', '社保'],
                'product_liability_after_sales_risk': ['product liability', 'warranty', 'after-sales', 'product recall', 'defect', 'return'],
                'foreign_exchange_risk': ['foreign currency risk', 'exchange rate', 'RMB weakens', 'RMB strengthens'],
                'seasonality_risk': ['seasonality', 'seasonal', 'seasonal fluctuations', 'peak season'],
                'fundraising_dependency_risk': ['use of proceeds', 'fund our', 'working capital', 'cash runway', 'financing needs'],
                'competition_risk': ['competition', 'competitive', 'market share', 'competitor'],
                'fvtpl_risk': ['fvtpl', 'fair value', 'financial assets', 'investment securities'],
            }

            risk_section = text
            risk_start = text.lower().find('risk factors')
            if risk_start >= 0:
                risk_section = text[risk_start:risk_start + 80000]

            total_penalty = 0
            rt = SETTINGS.risk_factor
            for cat_name, keywords in risk_categories.items():
                evidence = []
                level = '低'
                penalty = 0
                for kw in keywords:
                    count = len(re.findall(kw, risk_section, re.IGNORECASE))
                    if count > 0:
                        is_regex_kw = any(c in kw for c in r'\.+*?[](){}|^$')
                        if is_regex_kw:
                            first_match = re.search(rf'.{{0,60}}{kw}.{{0,60}}', risk_section, re.IGNORECASE)
                        else:
                            first_match = re.search(rf'.{{0,60}}{re.escape(kw)}.{{0,60}}', risk_section, re.IGNORECASE)
                        if first_match:
                            evidence.append(first_match.group(0).strip()[:120])
                if len(evidence) >= rt.evidence_high:
                    level = '高'
                    penalty = rt.penalty_high
                elif len(evidence) >= rt.evidence_mid:
                    level = '中'
                    penalty = rt.penalty_mid
                total_penalty += penalty
                result['risks'][cat_name] = {
                    'risk_level': level,
                    'evidence_count': len(evidence),
                    'evidence_sample': evidence[:2],
                    'score_penalty': penalty,
                }

            cashflow = prospectus_info.get('cashflow') or {}
            if _is_num(cashflow.get('operating_cash_flow')) and cashflow.get('operating_cash_flow') < 0:
                cat = result['risks'].setdefault('cash_flow_pressure_risk', {
                    'risk_level': '低', 'evidence_count': 0, 'evidence_sample': [], 'score_penalty': 0,
                })
                cat['risk_level'] = '中'
                cat['score_penalty'] = max(cat.get('score_penalty', 0), 1)
                cat['evidence_count'] = max(cat.get('evidence_count', 0), 1)
                cat['evidence_sample'] = (cat.get('evidence_sample') or [])[:1] + [
                    f"经营现金流为负({cashflow.get('operating_cash_flow')})"
                ]

            asp_evidence = []
            for match in re.finditer(
                r'(?:average\s+selling\s+price|ASP)[^.\n]{0,180}?(?:decreas|declin)[^.\n]{0,120}?(\d+(?:\.\d+)?)\s*%',
                risk_section,
                re.IGNORECASE,
            ):
                asp_evidence.append(match.group(0).strip()[:160])
            if asp_evidence:
                cat = result['risks'].setdefault('price_competition_risk', {
                    'risk_level': '低', 'evidence_count': 0, 'evidence_sample': [], 'score_penalty': 0,
                })
                cat['risk_level'] = '中' if len(asp_evidence) < 2 else '高'
                cat['score_penalty'] = max(cat.get('score_penalty', 0), 1 if len(asp_evidence) < 2 else 3)
                cat['evidence_count'] = max(cat.get('evidence_count', 0), len(asp_evidence))
                cat['evidence_sample'] = asp_evidence[:2]

            result['total_penalty'] = min(rt.max_total_penalty, sum(v.get('score_penalty', 0) for v in result['risks'].values()))
            result['confidence'] = 'keyword_only'
        except Exception as e:
            logger.warning("%s: %s", type(self).__name__, e)
            result['_error'] = str(e)
        return result
