import re
import logging
from ..utils import _is_num
from ..table_extraction import extract_financial_table_by_row
from ..settings import SETTINGS
logger = logging.getLogger(__name__)


class RnDPipelineAnalyzer:
    _BIOTECH_CLINICAL_PATTERNS = [
        r'(?:Phase|Ph)\s*(I{1,3}|1|2|3)\s*(?:/\s*(?:Phase|Ph)\s*(I{1,3}|1|2|3))?\s*(?:clinical\s*trial|study|trial)?',
        r'Core\s+Product',
        r'drug\s+candidate',
        r'clinical[- ]?stage',
        r'NDA|BLA|IND',
        r'Pivotal\s+(?:trial|study)',
        r'approved\s+(?:for|by|as)',
        r'commercialization',
        r'pipeline',
    ]

    def analyze(self, prospectus_info, text='', ipo_data=None):
        # 防御：某些调用者把 ipo_data 传到了 text 位置
        if isinstance(text, dict):
            text = ''
        result = {
            'rd_expense_latest': None, 'rd_expense_ratio': None,
            'product_count_approved': None, 'product_count_pipeline': None,
            'core_product_names': [], 'latest_clinical_stage': None,
            'phase_iii_count': 0, 'nda_or_approved_count': 0,
            'technology_moat_score': 0, 'pipeline_quality_label': '缺失',
            'commercialization_risk': '缺失', 'confidence': 'missing',
            'clinical_stage_score': 0,
        }
        try:
            rd_from_info = prospectus_info.get('rd_expense')
            revenue_from_info = prospectus_info.get('revenue')
            sector = prospectus_info.get('sector', 'unknown')
            prospectus_info.get('financial_currency', 'RMB')
            raw_text = (text or '') + ' ' + (prospectus_info.get('_extracted_text', '') or '')

            # --- 研发费用（对生物科技不隐藏高比例） ---
            is_biotech = False
            if sector == 'healthcare':
                biotech_kw = ['biotech', 'biopharma', 'clinical trial', 'drug candidate',
                              '18a', 'innovative drug', 'pipeline', 'phase']
                biotech_hits = sum(1 for kw in biotech_kw if kw in raw_text.lower())
                is_biotech = (biotech_hits >= SETTINGS.rnd.biotech_keyword_hits_min) or ('-b' in str(prospectus_info.get('extracted_company_name', '')).lower())

            if _is_num(rd_from_info) and _is_num(revenue_from_info) and revenue_from_info > 0:
                rd_latest = abs(rd_from_info)
                rd_ratio = rd_latest / revenue_from_info * 100
                # 对生物科技：研发费用率 >100% 是正常现象
                if rd_ratio > SETTINGS.rnd.expense_ratio_anomaly and not is_biotech and rd_latest > revenue_from_info * SETTINGS.rnd.expense_ratio_unit_mismatch_multiplier:
                    rd_latest = rd_latest / 1000
                    rd_ratio = rd_latest / revenue_from_info * 100
                if rd_ratio > SETTINGS.rnd.expense_ratio_anomaly and not is_biotech:
                    result['rd_expense_latest'] = rd_latest
                    result['rd_expense_ratio'] = None
                    result['rd_ratio_warning'] = '研发费率疑似单位错位'
                else:
                    result['rd_expense_latest'] = round(rd_latest, 3)
                    result['rd_expense_ratio'] = round(rd_ratio, 1)
                    result['confidence'] = 'from_consolidated_statement'
                    if is_biotech and rd_ratio > SETTINGS.rnd.expense_ratio_anomaly:
                        result['rd_ratio_biotech'] = True
            else:
                rd_table = extract_financial_table_by_row(text, {
                    'rd_expense': ['research and development expenses', 'r&d expenses'],
                })
                if rd_table and 'rd_expense' in rd_table:
                    years = sorted(rd_table['rd_expense'].keys())
                    if years:
                        rd_latest = abs(rd_table['rd_expense'][years[-1]])
                        if _is_num(revenue_from_info) and revenue_from_info > 0:
                            rd_ratio = rd_latest / revenue_from_info * 100
                            if rd_ratio > SETTINGS.rnd.expense_ratio_anomaly and not is_biotech and rd_latest > revenue_from_info * SETTINGS.rnd.expense_ratio_unit_mismatch_multiplier:
                                rd_latest = rd_latest / 1000
                                rd_ratio = rd_latest / revenue_from_info * 100
                            if rd_ratio > SETTINGS.rnd.expense_ratio_anomaly and not is_biotech:
                                result['rd_expense_latest'] = rd_latest
                                result['rd_expense_ratio'] = None
                                result['rd_ratio_warning'] = '研发费率疑似单位错位'
                            else:
                                result['rd_expense_latest'] = rd_latest
                                result['rd_expense_ratio'] = round(rd_ratio, 1) if rd_ratio is not None else None
                                result['confidence'] = 'regex_context'
                        else:
                            result['rd_expense_latest'] = rd_latest
                            result['confidence'] = 'regex_context'

            # --- 创新药管线识别（替代医疗器械 Class II/III） ---
            core_products = list(dict.fromkeys(
                m.group(0) for m in re.finditer(r'(?:Core\s+Product|核心产品)\s*[:\-]?\s*([A-Za-z0-9\-]+)', raw_text, re.IGNORECASE)
            ))[:5]
            result['core_product_names'] = [c.split()[-1] for c in core_products] if core_products else []

            # 临床阶段检测
            phases = []
            for pat in self._BIOTECH_CLINICAL_PATTERNS:
                for m in re.finditer(pat, raw_text, re.IGNORECASE):
                    phases.append(m.group(0)[:50])

            phase_map = {"phase iii": 3, "phase 3": 3, "phase ii": 2, "phase 2": 2,
                         "phase i": 1, "phase 1": 1, "iii": 3, "ii": 2, "i": 1}
            max_phase = 0
            for p in phases:
                pl = p.lower()
                for key, val in phase_map.items():
                    if key in pl:
                        max_phase = max(max_phase, val)

            result['latest_clinical_stage'] = f"Phase {'I' * max_phase}" if max_phase else "Pre-clinical"
            result['phase_iii_count'] = sum(1 for p in phases if "phase iii" in p.lower() or "phase 3" in p.lower())
            result['nda_or_approved_count'] = len(re.findall(r'\b(NDA|BLA|approved|commercialization)\b', raw_text, re.IGNORECASE))
            result['clinical_stage_score'] = max_phase

            # 一般管线数量（医疗器械/其他）
            class_ii = len(re.findall(r'Class\s+II(?:a|b)?\s+(?:medical\s+device|certificate|registration)', text, re.IGNORECASE))
            class_iii = len(re.findall(r'Class\s+III\s+(?:medical\s+device|certificate|registration)', text, re.IGNORECASE))
            result['class_ii_count'] = class_ii
            result['class_iii_count'] = class_iii

            # 技术护城河评分
            moat = 0
            rd_ratio = result.get('rd_expense_ratio')
            rt = SETTINGS.rnd
            if rd_ratio is not None:
                if rd_ratio >= rt.moat_high:
                    moat += 4
                elif rd_ratio >= rt.moat_mid:
                    moat += 3
                elif rd_ratio >= rt.moat_low:
                    moat += 2
                else:
                    moat += 1
            if is_biotech:
                if max_phase >= 3:
                    moat += 3
                elif max_phase >= 2:
                    moat += 2
                else:
                    moat += 1
            rt = SETTINGS.rnd
            if class_iii >= rt.class_iii_high_threshold:
                moat += rt.class_iii_high_bonus
            elif class_iii >= rt.class_iii_low_threshold:
                moat += rt.class_iii_low_bonus

            result['technology_moat_score'] = min(rt.moat_max_score, moat)
            if moat >= rt.moat_strong_threshold:
                result['pipeline_quality_label'] = '强'
            elif moat >= rt.moat_medium_threshold:
                result['pipeline_quality_label'] = '中'
            else:
                result['pipeline_quality_label'] = '弱'

            if is_biotech and max_phase >= rt.phase_iii_threshold:
                result['commercialization_risk'] = '中-上市临近'
            elif is_biotech and max_phase >= rt.phase_ii_threshold:
                result['commercialization_risk'] = '中'
            elif result.get('product_count_approved', 0) or class_iii:
                result['commercialization_risk'] = '中'
            else:
                result['commercialization_risk'] = '高'

            if rd_ratio is not None or is_biotech:
                if result['confidence'] == 'missing':
                    result['confidence'] = 'regex_context'
        except Exception as e:
            logger.warning("%s: %s", type(self).__name__, e)
            result['_error'] = str(e)
        return result
