import re
import logging
from ..utils import _is_num, _extract_table_nums, extract_text_excerpts
from ..table_extraction import extract_financial_table_by_row
from ..settings import SETTINGS
from ..industry_router import classify_company
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
            'patent_count': None, 'software_copyright_count': None,
            'rd_staff_count': None, 'rd_staff_ratio': None,
            'backlog_amount': None, 'industry_rank': None, 'market_size_notes': None,
            'product_count_approved': None, 'product_count_pipeline': None,
            'core_product_names': [], 'latest_clinical_stage': None,
            'phase_iii_count': 0, 'nda_or_approved_count': 0,
            'technology_moat_score': 0, 'pipeline_quality_label': '缺失',
            'commercialization_risk': '缺失', 'confidence': 'missing',
            'clinical_stage_score': 0,
            'hardtech_moat_label': '缺失', 'hardtech_moat_reasons': [],
            'hardtech_moat_score': 0,
            'evidence_excerpt': '',
        }
        try:
            rd_from_info = prospectus_info.get('rd_expense')
            revenue_from_info = prospectus_info.get('revenue')
            sector = prospectus_info.get('sector', 'unknown')
            raw_text = (text or '') + ' ' + (prospectus_info.get('_extracted_text', '') or '')
            lower_text = raw_text.lower()
            profile = classify_company(prospectus_info, raw_text)
            is_hardtech = sector == 'hardtech' or any(
                kw in lower_text for kw in (
                    'robot', 'automation', 'scara', 'amr', 'agv', 'controller',
                    'vision system', 'wafer handling', 'parallel robot', 'industrial robot',
                    '机器人', '自动化', '工业机器人', '并联机器人', '移动机器人', '晶圆搬运',
                )
            )

            # --- 研发费用（对生物科技不隐藏高比例） ---
            is_biotech = False
            if profile.is_biotech or sector == 'healthcare':
                biotech_kw = ['biotech', 'biopharma', 'clinical trial', 'drug candidate',
                              '18a', 'innovative drug', 'pipeline', 'phase']
                biotech_hits = sum(1 for kw in biotech_kw if kw in lower_text)
                is_biotech = profile.is_biotech or (biotech_hits >= SETTINGS.rnd.biotech_keyword_hits_min) or ('-b' in str(prospectus_info.get('extracted_company_name', '')).lower())

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

            def _extract_best_int(patterns, min_value=1):
                best = None
                for pat in patterns:
                    for m in re.finditer(pat, raw_text, re.IGNORECASE):
                        candidate = None
                        if m.lastindex and m.group(1):
                            try:
                                candidate = int(float(m.group(1).replace(',', '')))
                            except ValueError:
                                candidate = None
                        if candidate is None:
                            snippet = raw_text[max(0, m.start() - 180):min(len(raw_text), m.end() + 260)]
                            nums = _extract_table_nums(snippet, 5, min_val=min_value)
                            if nums:
                                candidate = max(nums)
                        if candidate is not None and candidate >= min_value:
                            if best is None or candidate > best:
                                best = candidate
                return int(best) if best is not None else None

            def _extract_best_float(patterns, min_value=0.0):
                best = None
                for pat in patterns:
                    for m in re.finditer(pat, raw_text, re.IGNORECASE):
                        snippet = raw_text[max(0, m.start() - 180):min(len(raw_text), m.end() + 260)]
                        nums = _extract_table_nums(snippet, 5, min_val=min_value)
                        if nums:
                            candidate = max(nums)
                            if best is None or candidate > best:
                                best = candidate
                return round(best, 1) if best is not None else None

            result['patent_count'] = _extract_best_int([
                r'(\d+)\s+(?:patents?|patent\s+applications?)',
                r'(\d+)\s+项?\s*专利',
                r'专利[^\n\r]{0,40}?(\d+)\s+项?',
            ], min_value=1)
            result['software_copyright_count'] = _extract_best_int([
                r'(\d+)\s+(?:software\s+copyrights?|software\s+copyright\s+registrations?)',
                r'(\d+)\s+项?\s*软件著作权',
                r'软件著作权[^\n\r]{0,40}?(\d+)\s+项?',
            ], min_value=1)
            result['rd_staff_count'] = _extract_best_int([
                r'(\d+)\s+(?:R&D|research\s+and\s+development)\s+(?:staff|employees|personnel)',
                r'(\d+)\s+名?\s*研发人员',
                r'研发人员[^\n\r]{0,40}?(\d+)\s+名?',
            ], min_value=1)

            rd_staff_ratio = None
            for pat in [
                r'(?:R&D|研发)[^\n\r]{0,40}?(\d+(?:\.\d+)?)\s*%',
                r'(\d+(?:\.\d+)?)\s*%\s*(?:of|of\s+the)\s+(?:total\s+)?(?:employees|staff|personnel)',
                r'占(?:总|员工)?(?:员工|员工总数|员工人数)[^\n\r]{0,30}?(\d+(?:\.\d+)?)\s*%',
            ]:
                m = re.search(pat, raw_text, re.IGNORECASE)
                if m:
                    try:
                        rd_staff_ratio = float(m.group(1))
                        break
                    except ValueError:
                        continue
            if rd_staff_ratio is None and result.get('rd_staff_count'):
                total_staff = _extract_best_int([
                    r'(\d+)\s+(?:employees|staff|personnel)',
                    r'员工总数[^\n\r]{0,20}?(\d+)',
                    r'总员工数[^\n\r]{0,20}?(\d+)',
                ], min_value=1)
                if total_staff and total_staff >= result['rd_staff_count']:
                    rd_staff_ratio = round(result['rd_staff_count'] / total_staff * 100, 1)
            result['rd_staff_ratio'] = rd_staff_ratio

            result['backlog_amount'] = None
            for pat in [
                r'backlog',
                r'order\s+book',
                r'在手订单',
                r'未履行订单',
                r'未交付订单',
            ]:
                m = re.search(pat, raw_text, re.IGNORECASE)
                if not m:
                    continue
                snippet = raw_text[max(0, m.start() - 180):min(len(raw_text), m.end() + 300)]
                nums = _extract_table_nums(snippet, 4, min_val=10)
                if nums:
                    result['backlog_amount'] = _adjust_backlog_value(max(nums), snippet)
                    break

            rank_val = None
            for pat in [
                r'ranked\s+(?:No\.?\s*)?(\d+)(?:st|nd|rd|th)?',
                r'No\.?\s*(\d+)(?:st|nd|rd|th)?',
                r'第\s*(\d+)\s*(?:大|位|名)',
            ]:
                m = re.search(pat, raw_text, re.IGNORECASE)
                if m:
                    try:
                        rank_val = int(m.group(1))
                        break
                    except ValueError:
                        continue
            if rank_val is not None:
                result['industry_rank'] = f'第{rank_val}位'

            tam_matches = re.findall(r'(?:TAM|market\s+size|market\s+opportunity|市场规模|潜在市场规模)[^\n\r]{0,120}', raw_text, re.IGNORECASE)
            if tam_matches:
                result['market_size_notes'] = '；'.join(tam_matches[:2])

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

            if is_hardtech and not is_biotech:
                hardtech_reasons = []
                if rd_ratio is not None:
                    if rd_ratio >= 15:
                        moat += 3
                    elif rd_ratio >= 10:
                        moat += 2
                    elif rd_ratio >= 5:
                        moat += 1
                    hardtech_reasons.append(f"研发费率{rd_ratio:.1f}%")
                if result.get('patent_count') is not None:
                    if result['patent_count'] >= 200:
                        moat += 2
                    elif result['patent_count'] >= 50:
                        moat += 1
                    hardtech_reasons.append(f"专利{result['patent_count']}项")
                if result.get('software_copyright_count') is not None:
                    if result['software_copyright_count'] >= 50:
                        moat += 1
                    hardtech_reasons.append(f"软著{result['software_copyright_count']}项")
                if result.get('rd_staff_ratio') is not None:
                    if result['rd_staff_ratio'] >= 20:
                        moat += 2
                    elif result['rd_staff_ratio'] >= 10:
                        moat += 1
                    hardtech_reasons.append(f"研发人员占比{result['rd_staff_ratio']:.1f}%")
                if result.get('backlog_amount') is not None:
                    if _is_num(revenue_from_info) and revenue_from_info > 0:
                        backlog_ratio = result['backlog_amount'] / revenue_from_info
                        if backlog_ratio >= 1:
                            moat += 2
                        elif backlog_ratio >= 0.5:
                            moat += 1
                    hardtech_reasons.append(f"在手订单约{result['backlog_amount']:.1f}M")
                if result.get('industry_rank'):
                    hardtech_reasons.append(result['industry_rank'])
                if result.get('market_size_notes'):
                    hardtech_reasons.append(result['market_size_notes'][:80])
                result['hardtech_moat_reasons'] = hardtech_reasons
                result['hardtech_moat_score'] = min(rt.moat_max_score, moat)
                if result['hardtech_moat_score'] >= rt.moat_strong_threshold:
                    result['hardtech_moat_label'] = '强'
                elif result['hardtech_moat_score'] >= rt.moat_medium_threshold:
                    result['hardtech_moat_label'] = '中'
                else:
                    result['hardtech_moat_label'] = '弱'

            result['technology_moat_score'] = min(rt.moat_max_score, moat)
            if is_hardtech and not is_biotech and result.get('hardtech_moat_label') not in (None, '缺失'):
                result['pipeline_quality_label'] = result['hardtech_moat_label']
            elif moat >= rt.moat_strong_threshold:
                result['pipeline_quality_label'] = '强'
            elif moat >= rt.moat_medium_threshold:
                result['pipeline_quality_label'] = '中'
            else:
                result['pipeline_quality_label'] = '弱'

            if is_biotech and max_phase >= rt.phase_iii_threshold:
                result['commercialization_risk'] = '中-上市临近'
            elif is_biotech and max_phase >= rt.phase_ii_threshold:
                result['commercialization_risk'] = '中'
            elif is_hardtech and result.get('backlog_amount') is not None:
                result['commercialization_risk'] = '中'
            elif result.get('product_count_approved', 0) or class_iii:
                result['commercialization_risk'] = '中'
            else:
                result['commercialization_risk'] = '高'

            excerpt_patterns = [
                r'patents?',
                r'software\s+copyrights?',
                r'R&D\s+(?:employees|staff|personnel)',
                r'研发人员',
                r'backlog',
                r'order\s+book',
                r'在手订单',
                r'未交付订单',
                r'ranked\s+(?:No\.?\s*)?\d+',
                r'第\s*\d+\s*(?:位|名|大)',
            ]
            result['evidence_excerpt'] = "\n\n".join(
                extract_text_excerpts(raw_text, excerpt_patterns, window=200, max_chars=1000, limit=3)
            )

            if rd_ratio is not None or is_biotech:
                if result['confidence'] == 'missing':
                    result['confidence'] = 'regex_context'
        except Exception as e:
            logger.warning("%s: %s", type(self).__name__, e)
            result['_error'] = str(e)
        return result


def _adjust_backlog_value(value, context):
    if value is None:
        return None
    try:
        adjusted = float(value)
    except Exception:
        return None
    lower = (context or '').lower()
    if any(kw in lower for kw in ("rmb'000", "rmb’000", "in thousands", "thousands")):
        adjusted = adjusted / 1000
    if any(kw in lower for kw in ('billion', 'bn', '十亿')):
        adjusted = adjusted * 1000
    return round(adjusted, 3)
