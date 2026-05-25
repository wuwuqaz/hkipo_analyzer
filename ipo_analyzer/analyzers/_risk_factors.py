import re
import logging
from ..utils import _is_num
from ..settings import SETTINGS
logger = logging.getLogger(__name__)


class RiskFactorAnalyzer:
    _NOISE_PATTERNS = [
        re.compile(r'refers to\s+the\s+average', re.IGNORECASE),
        re.compile(r'\.\.+'),
        re.compile(r'well-positioning\s+it\s+to\s+capitalize', re.IGNORECASE),
        re.compile(r'strong\s+competitive\s+position', re.IGNORECASE),
        re.compile(r'competitive\s+advantage', re.IGNORECASE),
        re.compile(r'table\s+of\s+contents', re.IGNORECASE),
        re.compile(r'\.{5,}'),
    ]

    _COMPETITION_NEGATIVE_CONTEXT = [
        'intense', 'fierce', 'pressure', 'risk', 'threat', 'challenge',
        'declining', 'eroding', 'diminishing', 'adversely affected',
        'may not be able to compete', 'unable to compete',
        'highly competitive', 'significant competition',
    ]

    _HYPOTHETICAL_PREFIXES = re.compile(
        r'\b(may|might|could|would|if|should|potential|possible|hypothetical|assume|assuming|in\s+the\s+event)\b',
        re.IGNORECASE
    )

    _DEFINITION_PATTERN = re.compile(r'\b(means|refers to|is defined as)\b', re.IGNORECASE)
    _ACTUAL_EVENT_PATTERN = re.compile(r'\b(actual|existing|currently|已经|已发生|现有|正在|受到|遭受|面临)\b', re.IGNORECASE)
    _DIGIT_PATTERN = re.compile(r'\d')
    _ASP_DECLINE_PATTERN = re.compile(
        r'(?:average\s+selling\s+price|ASP)[^.\n]{0,180}?(?:decreas|declin)[^.\n]{0,120}?(\d+(?:\.\d+)?)\s*%',
        re.IGNORECASE,
    )

    _RISK_CATEGORIES = {
        'price_competition_risk': [re.compile(p, re.IGNORECASE) for p in
            ['average selling price', r'\bASP\b', 'price competition', 'price pressure', 'price reduction', 'decreased by']],
        'cash_flow_pressure_risk': [re.compile(p, re.IGNORECASE) for p in
            ['net cash used in operating activities', 'operating cash flow', 'working capital pressure', 'cash outflow']],
        'inventory_pressure_risk': [re.compile(p, re.IGNORECASE) for p in
            ['inventory', 'built up inventory', 'write-down', 'obsolete', 'slow-moving']],
        'customer_concentration_risk': [re.compile(p, re.IGNORECASE) for p in
            ['customer concentration', 'largest customer', 'dependent on']],
        'supplier_concentration_risk': [re.compile(p, re.IGNORECASE) for p in
            ['supplier', 'raw material', 'supply chain', 'single source']],
        'overseas_channel_tariff_risk': [re.compile(p, re.IGNORECASE) for p in
            ['overseas', 'export', 'tariff', 'trade protection', 'customs', 'amazon', 'sales channels', 'logistics']],
        'social_insurance_housing_fund_risk': [re.compile(p, re.IGNORECASE) for p in
            ['social insurance', 'housing provident fund', 'underpaid', 'shortfall', '住房公积金', '社保']],
        'product_liability_after_sales_risk': [re.compile(p, re.IGNORECASE) for p in
            ['product liability', 'warranty', 'after-sales', 'product recall', 'defect', 'return']],
        'foreign_exchange_risk': [re.compile(p, re.IGNORECASE) for p in
            ['foreign currency risk', 'exchange rate', 'RMB weakens', 'RMB strengthens']],
        'seasonality_risk': [re.compile(p, re.IGNORECASE) for p in
            ['seasonality', 'seasonal', 'seasonal fluctuations', 'peak season']],
        'fundraising_dependency_risk': [re.compile(p, re.IGNORECASE) for p in
            ['use of proceeds', 'fund our', 'working capital', 'cash runway', 'financing needs']],
        'competition_risk': [re.compile(p, re.IGNORECASE) for p in
            ['competition', 'competitive', 'market share', 'competitor']],
        'fvtpl_risk': [re.compile(p, re.IGNORECASE) for p in
            ['fvtpl', 'fair value', 'financial assets', 'investment securities']],
    }

    _RISK_CATEGORIES_RAW = {
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

    @classmethod
    def _is_quality_evidence(cls, text: str) -> bool:
        text_lower = text.lower()
        for pattern in cls._NOISE_PATTERNS:
            if pattern.search(text_lower):
                return False
        if cls._DEFINITION_PATTERN.search(text_lower):
            return False
        return True

    @classmethod
    def _has_negative_competition_context(cls, text: str) -> bool:
        text_lower = text.lower()
        return any(kw in text_lower for kw in cls._COMPETITION_NEGATIVE_CONTEXT)

    @classmethod
    def _classify_risk_tier(cls, evidence_text: str, cat_name: str) -> str:
        et_lower = evidence_text.lower()
        if cls._HYPOTHETICAL_PREFIXES.search(et_lower):
            return 'generic_risk_factor'
        if cls._ACTUAL_EVENT_PATTERN.search(et_lower):
            return 'actual_event'
        return 'potential_risk'

    def analyze(self, prospectus_info, text='', ipo_data=None):
        if isinstance(text, dict):
            text = ''
        result = {
            'risks': {},
            'total_penalty': 0,
            'confidence': 'missing',
        }
        try:
            risk_section = text
            risk_start = text.lower().find('risk factors')
            if risk_start >= 0:
                risk_section = text[risk_start:risk_start + 80000]

            total_penalty = 0
            rt = SETTINGS.risk_factor
            for cat_name, compiled_kws in RiskFactorAnalyzer._RISK_CATEGORIES.items():
                raw_kws = RiskFactorAnalyzer._RISK_CATEGORIES_RAW[cat_name]
                raw_evidence = []
                for kw_compiled, kw_raw in zip(compiled_kws, raw_kws):
                    count = len(kw_compiled.findall(risk_section))
                    if count > 0:
                        is_regex_kw = any(c in kw_raw for c in r'.+*?[](){}|^$')
                        if is_regex_kw:
                            first_match = re.search(rf'.{{0,60}}{kw_raw}.{{0,60}}', risk_section, re.IGNORECASE)
                        else:
                            first_match = re.search(rf'.{{0,60}}{re.escape(kw_raw)}.{{0,60}}', risk_section, re.IGNORECASE)
                        if first_match:
                            raw_evidence.append(first_match.group(0).strip()[:120])

                evidence = [e for e in raw_evidence if self._is_quality_evidence(e)]

                if cat_name == 'competition_risk' and evidence:
                    qualified = [e for e in evidence if self._has_negative_competition_context(e)]
                    if qualified:
                        evidence = qualified
                    else:
                        evidence = []

                level = '低'
                penalty = 0

                weighted_count = 0
                for e in evidence:
                    if RiskFactorAnalyzer._DIGIT_PATTERN.search(e):
                        weighted_count += 1.5
                    else:
                        weighted_count += 1.0

                if weighted_count >= rt.evidence_high:
                    level = '高'
                    penalty = rt.penalty_high
                elif weighted_count >= rt.evidence_mid + 1:
                    level = '中'
                    penalty = rt.penalty_mid
                total_penalty += penalty

                tiered_evidence = []
                for e in evidence[:2]:
                    tier = self._classify_risk_tier(e, cat_name)
                    tiered_evidence.append({
                        'excerpt': e,
                        'risk_tier': tier,
                        'confidence': 'keyword_match',
                    })

                result['risks'][cat_name] = {
                    'risk_level': level,
                    'evidence_count': len(evidence),
                    'evidence_sample': [e['excerpt'] for e in tiered_evidence],
                    'tiered_evidence': tiered_evidence,
                    'score_penalty': penalty,
                    'section_name': 'risk_factors' if risk_start >= 0 else 'full_text',
                }

            cashflow = prospectus_info.get('cashflow') or {}
            if _is_num(cashflow.get('operating_cash_flow')) and cashflow.get('operating_cash_flow') < 0:
                cat = result['risks'].setdefault('cash_flow_pressure_risk', {
                    'risk_level': '低', 'evidence_count': 0, 'evidence_sample': [], 'score_penalty': 0,
                    'tiered_evidence': [], 'section_name': 'financial_statements',
                })
                cat['risk_level'] = '中'
                cat['score_penalty'] = max(cat.get('score_penalty', 0), 1)
                cat['evidence_count'] = max(cat.get('evidence_count', 0), 1)
                cat['evidence_sample'] = (cat.get('evidence_sample') or [])[:1] + [
                    f"经营现金流为负({cashflow.get('operating_cash_flow')})"
                ]
                cat['tiered_evidence'] = (cat.get('tiered_evidence') or [])[:1] + [{
                    'excerpt': f"经营现金流为负({cashflow.get('operating_cash_flow')})",
                    'risk_tier': 'actual_event',
                    'confidence': 'financial_data',
                }]

            asp_evidence = []
            for match in RiskFactorAnalyzer._ASP_DECLINE_PATTERN.finditer(risk_section):
                asp_evidence.append(match.group(0).strip()[:160])
            if asp_evidence:
                cat = result['risks'].setdefault('price_competition_risk', {
                    'risk_level': '低', 'evidence_count': 0, 'evidence_sample': [], 'score_penalty': 0,
                    'tiered_evidence': [], 'section_name': 'risk_factors',
                })
                cat['risk_level'] = '中' if len(asp_evidence) < 2 else '高'
                cat['score_penalty'] = max(cat.get('score_penalty', 0), 1 if len(asp_evidence) < 2 else 3)
                cat['evidence_count'] = max(cat.get('evidence_count', 0), len(asp_evidence))
                cat['evidence_sample'] = asp_evidence[:2]
                cat['tiered_evidence'] = [
                    {'excerpt': e, 'risk_tier': 'actual_event', 'confidence': 'regex_match'}
                    for e in asp_evidence[:2]
                ]

            result['total_penalty'] = min(rt.max_total_penalty, sum(v.get('score_penalty', 0) for v in result['risks'].values()))
            result['confidence'] = 'keyword_only'
        except Exception as e:
            logger.warning("%s: %s", type(self).__name__, e)
            result['_error'] = str(e)
        return result
