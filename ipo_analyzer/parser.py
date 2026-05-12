import re
import os
import logging
from datetime import datetime

from .utils import _is_num
from .table_extraction import extract_financial_table_by_row
from .cornerstone import CornerstoneAnalyzer
from .text_extractor import extract_pdf_text
from .identity_validator import validate_pdf_identity
from .prospectus_basic_extractor import extract_prospectus_basic_info
from .settings import SETTINGS

logger = logging.getLogger(__name__)


class ProspectusParser:
    """招股书解析器"""
    
    def __init__(self, cache_dir='/tmp/hkipo_prospectus'):
        self.cache_dir = cache_dir

    @staticmethod
    def _parse_financial_amount(value_str, unit_str):
        """统一转换为百万港元口径，便于后续比较"""
        value_text = value_str.replace(',', '').strip()
        negative = value_text.startswith('(') and value_text.endswith(')')
        value_text = value_text.strip('()')
        value = float(value_text)
        if negative:
            value = -value
        unit = unit_str.lower()
        if 'billion' in unit:
            return value * 1000
        return value

    @staticmethod
    def _extract_line_value(line, field_keywords, allow_loss=False):
        keywords = '|'.join(re.escape(k) for k in field_keywords)
        patterns = [
            rf'(?:{keywords})[^.\n]{{0,180}}?(?:HK\$|HKD|RMB|US\$)?\s*([\(]?-?[0-9,]+(?:\.[0-9]+)?[\)]?)\s*(million|billion)',
            rf'(?:{keywords})[^.\n]{{0,180}}?(?:HK\$|HKD|RMB|US\$)\s*([\(]?-?[0-9,]+(?:\.[0-9]+)?[\)]?)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, line, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    if len(match) == 2:
                        raw_value, raw_unit = match
                    else:
                        raw_value, raw_unit = match[0], 'million'
                else:
                    raw_value, raw_unit = match, 'million'
                try:
                    value = ProspectusParser._parse_financial_amount(raw_value, raw_unit)
                except Exception:
                    continue
                if raw_unit == 'million' and not re.search(r'(million|billion)', line, re.IGNORECASE):
                    value_text = raw_value.replace(',', '').strip('()')
                    try:
                        numeric_value = float(value_text)
                    except Exception:
                        continue
                    if 1900 <= abs(numeric_value) <= 2100:
                        continue
                if allow_loss and value > 0:
                    value = -value
                return value

        return None

    def _extract_financial_series(self, text, field_keywords):
        values = []
        seen = set()
        lower_keywords = [kw.lower() for kw in field_keywords]
        allow_loss = any('loss' in kw for kw in lower_keywords)

        for line in text.split('\n'):
            lower_line = line.lower()
            if not any(kw in lower_line for kw in lower_keywords):
                continue

            value = self._extract_line_value(line, field_keywords, allow_loss=allow_loss)
            if value is None:
                continue

            dedupe_key = round(value, 4)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            values.append(value)
            if len(values) >= 2:
                return values

        return values

    @staticmethod
    def _extract_years(text):
        years = []
        for year in re.findall(r'(20[0-9]{2})(?:年|\b)', text):
            year_int = int(year)
            if 2010 <= year_int <= datetime.now().year:
                years.append(year_int)
        return years

    @staticmethod
    def _extract_numeric_tokens(text, percent=False):
        tokens = []
        if percent:
            pattern = r'([\(]?-?[0-9,]+(?:\.[0-9]+)?[\)]?)\s*%'
        else:
            pattern = r'([\(]?-?[0-9,]+(?:\.[0-9]+)?[\)]?)\s*(million|billion)?'

        for match in re.finditer(pattern, text, re.IGNORECASE):
            raw_value = match.group(1)
            raw_unit = match.group(2) if not percent and len(match.groups()) > 1 else 'million'
            cleaned = raw_value.replace(',', '').strip()
            try:
                plain_value = float(cleaned.strip('()'))
            except Exception:
                continue
            if 2010 <= abs(plain_value) <= datetime.now().year + 3:
                continue
            try:
                value = (
                    ProspectusParser._parse_financial_amount(raw_value, raw_unit or 'million')
                    if not percent else plain_value
                )
            except Exception:
                continue
            if percent and not (0 < value <= 100):
                continue
            tokens.append(value)
        return tokens

    def _extract_year_bound_series(self, text, field_keywords, percent=False):
        """尽量把指标值和年份列绑定，避免按 PDF 文本顺序误取旧年份。"""
        lines = text.split('\n')
        lower_keywords = [kw.lower() for kw in field_keywords]

        for idx, line in enumerate(lines):
            lower_line = line.lower()
            if not any(kw in lower_line for kw in lower_keywords):
                continue

            window = " ".join(lines[max(0, idx - 2): idx + 4])
            years = self._extract_years(window)
            values = self._extract_numeric_tokens(window, percent=percent)
            if len(set(years)) < 2 or len(values) < 2:
                continue

            unique_years = []
            for year in years:
                if year not in unique_years:
                    unique_years.append(year)

            if len(unique_years) > len(values):
                unique_years = unique_years[:len(values)]
            elif len(values) > len(unique_years):
                context_lines = lines[max(0, idx - 8): idx + 8]
                table_like = any(
                    token in ctx.lower()
                    for ctx in context_lines
                    for token in (
                        'amount', '% of',
                        'rmb in thousands', 'hk$ in thousands',
                        "rmb'000", "hk$'000",
                        'rmb thousand', 'hkd thousand',
                        # 中文表格上下文
                        '人民幣千元', '港元千元', '人民幣百萬', '港元百萬',
                        '截至', '年度', '止年度',
                    )
                )
                if not table_like:
                    continue
                values = values[-len(unique_years):]

            pairs = sorted(zip(unique_years, values), key=lambda item: item[0], reverse=True)
            if len(pairs) >= 2:
                return {
                    'latest_year': pairs[0][0],
                    'latest_value': pairs[0][1],
                    'previous_year': pairs[1][0],
                    'previous_value': pairs[1][1],
                    'confidence': 'year_bound',
                }

        return None

    @staticmethod
    def _parse_table_number_token(token):
        if not token:
            return None
        cleaned = token.strip().replace('−', '-').replace('–', '-').replace('—', '-')
        if cleaned in ('-', '-*'):
            return None
        negative = cleaned.startswith('(') and cleaned.endswith(')')
        cleaned = cleaned.strip('()').replace(',', '').replace('%', '')
        try:
            value = float(cleaned)
        except Exception:
            return None
        if negative and value > 0:
            value = -value
        # Use a wider range to avoid filtering financial values near current year
        if 2010 <= abs(value) <= datetime.now().year + 3:
            return None
        return value

    @classmethod
    def _numeric_values_from_table_line(cls, line):
        values = []
        for match in re.finditer(r'\(?-?[0-9][0-9,]*(?:\.[0-9]+)?\)?%?', line or ''):
            value = cls._parse_table_number_token(match.group(0))
            if value is not None:
                values.append(value)
        return values

    @classmethod
    def _extract_financial_row_values(cls, block_lines, row_idx, year_count):
        values = []
        for j in range(row_idx + 1, min(len(block_lines), row_idx + 14)):
            line = (block_lines[j] or '').strip()
            if not line:
                continue
            line_values = cls._numeric_values_from_table_line(line)
            if re.search(r'[A-Za-z]', line) and not line_values and len(values) >= year_count:
                break
            values.extend(line_values)
            if len(values) >= year_count * 2:
                break

        if not values:
            return []

        amount_like = [value for value in values if abs(value) >= 500]
        if len(amount_like) >= year_count:
            return amount_like[:year_count]

        if len(values) >= year_count * 2:
            paired_amounts = values[:year_count * 2:2]
            if len(paired_amounts) >= year_count:
                return paired_amounts[:year_count]

        return values[:year_count] if len(values) >= year_count else []

    @staticmethod
    def _row_implies_negative(key, row_line):
        lower = (row_line or '').lower()
        if key in ('net_profit', 'adjusted_net_profit'):
            if re.match(r'^(?:adjusted\s+net\s+)?loss\b', lower):
                return True
            # 中文亏损行
            if re.search(r'虧損|亏损', row_line or ''):
                return True
        if key == 'operating_cash_flow':
            if re.match(r'^net\s+cash\s+used\b', lower):
                return True
            # 中文经营现金流为负
            if re.search(r'所用現金|所用现金|現金流出|现金流出', row_line or ''):
                return True
        return False

    def _extract_consolidated_financial_table(self, text):
        """提取综合损益表主表，避免业务分部表或叙述段落覆盖核心财务值。"""
        lines = text.split('\n')
        row_patterns = [
            ('revenue', [r'^Revenue\b', r'^收益\b', r'^收入\b']),
            ('cost_of_sales', [r'^Cost of sales\b', r'^銷售成本\b', r'^營業成本\b']),
            ('gross_profit', [r'^Gross profit\b', r'^毛利\b']),
            ('rd_expense', [r'^Research and development expenses\b', r'^研發開支\b', r'^研發費用\b']),
            ('net_profit', [r'^(?:Profit|Loss) for the year\b', r'^Profit/\(Loss\) for the year\b', r'^(?:Profit|Loss) for the period\b',
                           r'^年內虧損\b', r'^年內利潤\b', r'^年度虧損\b', r'^年度利潤\b',
                           r'^年內虧損及全面收益總額\b', r'^年內利潤及全面收益總額\b']),
            ('adjusted_net_profit', [r'^Adjusted net profit\b', r'^Adjusted net loss\b',
                                     r'^經調整.*?利潤\b', r'^經調整.*?虧損\b']),
            ('operating_cash_flow', [r'^Net cash (?:generated|used) (?:from|in) operating activities\b',
                                     r'^經營活動.*?現金流量\b', r'^經營活動.*?淨額\b']),
        ]

        _YEAR_HEADERS = [
            r'Year ended December 31',
            r'For the year ended December 31',
            r'For the years ended December 31',
            r'For the six months ended',
            r'Six months ended',
            r'Year ended',
            r'Track Record Period',
            # 中文招股书财年表头
            r'截至.*?12月31日止年度',
            r'截至.*?止年度',
            r'截至.*?止六個月',
            r'截至.*?止六个月',
            r'截至.*?止三個月',
            r'截至.*?止三个月',
        ]
        _year_header_re = re.compile('|'.join(_YEAR_HEADERS), re.IGNORECASE)

        _UNIT_PATTERNS = [
            r"RMB[’'‘`]000",
            r"HK\$[’'‘`]000",
            r'RMB thousand',
            r'HKD thousand',
            r'RMB in thousands',
            r'HK\$ in thousands',
            r'rmb in thousands',
            r'hk\$ in thousands',
            # 中文单位：千元（可能跨行，DOTALL 已启用）
            r'人民幣.*?千元',
            r'港元.*?千元',
            r'港幣.*?千元',
            r'人民幣.*?千(?!萬|万)',
            r'港元.*?千(?!萬|万)',
        ]
        _MILLION_UNIT_PATTERNS = [
            r'RMB\s*million',
            r'HK\$\s*million',
            r'HKD\s*million',
            r'rmb\s*million',
            r'hk\$\s*million',
            r'hkd\s*million',
            r'RMB\s*\(?million\)?',
            r'HKD\s*\(?million\)?',
            # 中文单位：百万元（可能跨行，DOTALL 已启用）
            r'人民幣.*?百萬',
            r'港元.*?百萬',
            r'港幣.*?百萬',
        ]
        _unit_re = re.compile('|'.join(_UNIT_PATTERNS), re.IGNORECASE | re.DOTALL)
        _million_unit_re = re.compile('|'.join(_MILLION_UNIT_PATTERNS), re.IGNORECASE | re.DOTALL)

        _CORE_STATEMENT_TOKENS = [
            'consolidated statements of profit or loss',
            'consolidated statement of profit or loss',
            'consolidated statements of profit or loss and other comprehensive income',
            'summary of consolidated statements',
            'selected consolidated financial information',
            'results of operations',
            'summary financial data',
            'summary of our consolidated statements',
            # 中文财报标识
            '綜合全面收益表',
            '綜合損益表',
            '合併損益表',
            '合併全面收益表',
            '損益表',
            '財務資料',
            '經營業績',
        ]
        _BREAKDOWN_TOKENS = [
            'key operating data',
            'breakdown of our revenue',
            'breakdown of our cost',
            'gross profit and gross margins by',
            'revenue by geographical',
            'revenue by product',
            # 中文分部/明细标识（应避免当作主表）
            '收益明細',
            '收入明細',
            '分部收益',
            '按地區',
            '按產品',
        ]

        for start_idx, line in enumerate(lines):
            if not _year_header_re.search(line or ''):
                continue

            preceding_text = '\n'.join(lines[max(0, start_idx - 12):start_idx]).lower()
            is_core_statement = any(token in preceding_text for token in _CORE_STATEMENT_TOKENS)
            is_breakdown_table = any(token in preceding_text for token in _BREAKDOWN_TOKENS)
            if not is_core_statement or is_breakdown_table:
                continue

            header_block = '\n'.join(lines[start_idx:start_idx + 18])
            years = []
            # 中英文年份识别：20\d{2} 后可能跟 年 或非单词字符
            for match in re.finditer(r'(20\d{2})(?:年|\b)', header_block):
                year = int(match.group(1))
                if year not in years:
                    years.append(year)
            if len(years) < 2:
                continue

            block_lines = lines[start_idx:start_idx + 190]
            block_text = '\n'.join(block_lines)
            lower_block = block_text.lower()
            if 'revenue' not in lower_block and '收益' not in block_text and '收入' not in block_text:
                continue

            # 只取表头附近（前25行）做单位检测，避免远处叙述文字中百萬干扰千元判断
            header_zone = '\n'.join(block_lines[:25])
            is_thousand_unit = _unit_re.search(header_zone)
            is_million_unit = _million_unit_re.search(header_zone)
            table_unit = None
            if is_thousand_unit and not is_million_unit:
                table_unit = 'thousand'
            elif is_million_unit and not is_thousand_unit:
                table_unit = 'million'
            elif is_thousand_unit and is_million_unit:
                # 两者都出现时，检查哪个更靠近表头
                thu_pos = min((m.start() for m in _unit_re.finditer(header_zone)), default=99999)
                mpu_pos = min((m.start() for m in _million_unit_re.finditer(header_zone)), default=99999)
                table_unit = 'thousand' if thu_pos < mpu_pos else 'million'
            else:
                continue

            table = {}
            table['_table_unit'] = table_unit
            for key, patterns in row_patterns:
                if key in table:
                    continue
                for row_idx, row_line in enumerate(block_lines):
                    cleaned_line = re.sub(r'[\x00-\x1f\x7f-\x9f]+', ' ', row_line or '').strip()
                    if any(re.search(pattern, cleaned_line, re.IGNORECASE) for pattern in patterns):
                        if key == 'gross_profit' and 'margin' in cleaned_line.lower():
                            continue
                        values = self._extract_financial_row_values(block_lines, row_idx, len(years))
                        if self._row_implies_negative(key, cleaned_line):
                            values = [-abs(v) for v in values]
                        if len(values) >= len(years):
                            table[key] = {year: values[pos] for pos, year in enumerate(years)}
                        break

            revenue_row = table.get('revenue') or {}
            if len(revenue_row) >= 2 and all(value > 0 for value in revenue_row.values()):
                return table

        return {}

    def _detect_financial_currency(self, text):
        """从财务表附近识别币种：RMB/HKD/USD，默认 RMB。
        同时返回币种和单位（million/thousand/unknown）。"""
        patterns = [
            # (pattern, currency, unit)
            # 英文模式
            (r"RMB\s*million|RMB\s*\(?million\)?|rmb\s*million", "RMB", "million"),
            (r"HK\$\s*million|HKD\s*million|hk\$\s*million|HKD\s*\(?million\)?", "HKD", "million"),
            (r"US\$\s*million|USD\s*million|us\$\s*million", "USD", "million"),
            (r"RMB[’'‘`]?000|RMB\s*thousand|RMB\s*in\s*thousands|rmb[’'‘`]?000|rmb\s*thousand", "RMB", "thousand"),
            (r"HK\$[’'‘`]?000|HK\$\s*thousand|HK\$\s*in\s*thousands|HKD\s*thousand|hk\$[’'‘`]?000", "HKD", "thousand"),
            (r"US\$[’'‘`]?000|USD\s*thousand|us\$[’'‘`]?000", "USD", "thousand"),
            # 中文模式
            (r'人民幣百萬|人民幣.*?百萬', "RMB", "million"),
            (r'港元百萬|港元.*?百萬|港幣百萬', "HKD", "million"),
            (r'美元百萬|美元.*?百萬', "USD", "million"),
            (r'人民幣千元|人民幣.*?千元', "RMB", "thousand"),
            (r'港元千元|港元.*?千元|港幣千元', "HKD", "thousand"),
            (r'美元千元|美元.*?千元', "USD", "thousand"),
        ]
        for pat, currency, unit in patterns:
            if re.search(pat, text, re.IGNORECASE):
                return currency, unit
        return "RMB", "unknown"  # 默认

    def _apply_financial_table_to_info(self, info, fin_table, source, force=False):
        if not fin_table:
            return

        info['financial_table'] = fin_table
        info['financial_table_source'] = source
        if force:
            info['financial_extract_confidence'] = source

        table_unit = fin_table.get('_table_unit')
        quality_flags = info.setdefault('financial_data_quality_flags', [])

        for key in ['revenue', 'net_profit', 'cost_of_sales', 'rd_expense', 'operating_cash_flow']:
            if key not in fin_table:
                continue
            years = sorted(fin_table[key].keys())
            vals = [fin_table[key][y] for y in years]

            if table_unit == 'thousand':
                divisor = 1000
            elif table_unit == 'million':
                divisor = 1
            else:
                is_thousands = any(abs(v) > 5000 for v in vals if _is_num(v))
                divisor = 1000 if is_thousands else 1
                flag_key = f'_unit_fallback_{key}'
                if divisor == 1000 and table_unit is None and flag_key not in quality_flags:
                    quality_flags.append(f'未能识别表格单位，{key}按heuristic推断为thousand')
            latest = fin_table[key][years[-1]] / divisor
            previous = fin_table[key][years[-2]] / divisor if len(years) >= 2 else None

            should_update = force or key not in info
            if not should_update and key in ('revenue', 'net_profit'):
                old_latest = info.get(key)
                if _is_num(old_latest) and _is_num(latest):
                    should_update = abs(latest) > abs(old_latest) * 1.2

            if not should_update:
                continue

            info[key] = latest
            info[f'{key}_year'] = years[-1]
            if previous is not None:
                info[f'{key}_y1'] = previous
                info[f'{key}_y1_year'] = years[-2]
            if key == 'net_profit':
                info['profitable'] = latest > 0

        revenue_row = fin_table.get('revenue') or {}
        gross_profit_row = fin_table.get('gross_profit') or {}
        common_years = sorted(set(revenue_row.keys()) & set(gross_profit_row.keys()))
        if common_years:
            latest_year = common_years[-1]
            latest_revenue = revenue_row.get(latest_year)
            latest_gross_profit = gross_profit_row.get(latest_year)
            if latest_revenue:
                info['gross_margin'] = latest_gross_profit / latest_revenue * 100
                info['gross_margin_year'] = latest_year
            if len(common_years) >= 2:
                previous_year = common_years[-2]
                previous_revenue = revenue_row.get(previous_year)
                previous_gross_profit = gross_profit_row.get(previous_year)
                if previous_revenue:
                    info['gross_margin_y1'] = previous_gross_profit / previous_revenue * 100
                    info['gross_margin_y1_year'] = previous_year

    def _has_financial_loss_context(self, text):
        loss_keywords = [
            'loss for the year',
            'loss for the period',
            'net loss',
            'loss attributable',
        ]
        # Only search within the financial statement section to avoid false matches
        # from table of contents, risk factors, or notes
        fs_start = text.lower().find('consolidated statement of profit or loss')
        if fs_start < 0:
            return False
        window_start = max(0, fs_start - 2000)
        window_end = min(len(text), fs_start + 8000)
        window = text[window_start:window_end]

        risk_context_patterns = [
            'risk factor',
            'may result in',
            'could result in',
            'may incur',
            'may be adversely',
            'forward-looking',
        ]
        for i, line in enumerate(window.split('\n')):
            lower_line = line.lower()
            if any(keyword in lower_line for keyword in loss_keywords):
                context_window = '\n'.join(window.split('\n')[max(0, i - 3):i]).lower()
                if any(p in context_window for p in risk_context_patterns):
                    continue
                return True
        return False

    def _sanitize_financial_info(self, info):
        """过滤明显不合理的财务值，减少把年份/表头误识别为财务数据"""
        quality_flags = info.setdefault('financial_data_quality_flags', [])
        needs_review = False

        def add_flag(flag, requires_review=True):
            nonlocal needs_review
            if flag not in quality_flags:
                quality_flags.append(flag)
            if requires_review:
                needs_review = True

        revenue = info.get('revenue')
        revenue_y1 = info.get('revenue_y1')
        trusted_statement = info.get('financial_table_source') == 'consolidated_statement'
        if _is_num(revenue) and revenue <= 0:
            info.pop('revenue', None)
            info.pop('revenue_year', None)
            add_flag('收入为非正数，已剔除')
            revenue = None
        if _is_num(revenue_y1) and revenue_y1 <= 0:
            info.pop('revenue_y1', None)
            info.pop('revenue_y1_year', None)
            add_flag('上一期收入为非正数，已剔除')
            revenue_y1 = None
        if _is_num(revenue) and _is_num(revenue_y1):
            ratio = max(revenue, revenue_y1) / max(min(revenue, revenue_y1), 1e-9)
            if ratio > SETTINGS.data_sanitization.revenue_variance_max:
                if trusted_statement:
                    add_flag('收入两期差异超过20倍，已按财务主表保留，请核实增长原因', requires_review=False)
                else:
                    info.pop('revenue_y1', None)
                    info.pop('revenue_y1_year', None)
                    add_flag('收入两期差异超过20倍，上一期收入已剔除')

        net_profit = info.get('net_profit')
        net_profit_y1 = info.get('net_profit_y1')
        if _is_num(net_profit_y1) and abs(net_profit_y1) > SETTINGS.data_sanitization.net_profit_sanity_max:
            info.pop('net_profit_y1', None)
            info.pop('net_profit_y1_year', None)
            add_flag('上一期净利润疑似单位错位，已剔除')
        if _is_num(net_profit) and revenue and abs(net_profit) > max(revenue * 100, SETTINGS.data_sanitization.net_profit_sanity_max):
            info.pop('net_profit', None)
            info.pop('net_profit_year', None)
            info.pop('profitable', None)
            add_flag('净利润疑似单位错位，已剔除')
        if _is_num(info.get('net_profit')):
            info['profitable'] = info['net_profit'] > 0
        if needs_review:
            info['financial_extract_confidence'] = 'needs_review'
        elif quality_flags:
            info.setdefault('financial_extract_confidence', info.get('financial_table_source') or 'reviewed_with_flags')
        else:
            info.pop('financial_data_quality_flags', None)

    # 基础信息提取已迁移至 prospectus_basic_extractor.py

    def parse_pdf_file(self, pdf_path, stock_code=None, company_name=None):
        """统一解析入口：提取文本、身份识别、extract_info、诊断字段。"""
        if not pdf_path or not os.path.exists(pdf_path):
            return {
                'parse_success': False,
                'parse_error': f'PDF文件不存在: {pdf_path}',
                '_extracted_text': '',
            }

        try:
            text = extract_pdf_text(pdf_path)
        except Exception as e:
            return {
                'parse_success': False,
                'parse_error': f'PDF文本提取失败: {e}',
                'pdf_text_length': 0,
                '_extracted_text': '',
            }

        if not text:
            return {
                'parse_success': False,
                'parse_error': 'PDF文本提取为空',
                'pdf_text_length': 0,
                '_extracted_text': '',
            }

        identity = validate_pdf_identity(text, stock_code=stock_code, company_name=company_name)

        try:
            info = self.extract_info(text)
        except Exception as e:
            return {
                'parse_success': False,
                'parse_error': str(e),
                'pdf_text_length': len(text),
                **identity,
                'pdf_validation_warning': 'PDF文本已提取，但 extract_info 解析阶段失败',
                '_extracted_text': text,
            }

        info.update(identity)
        info['pdf_name_match'] = identity.get('name_match')
        info['pdf_stock_code_match'] = identity.get('stock_code_match')
        info['pdf_text_length'] = len(text)
        info['_extracted_text'] = text

        if not identity['name_match'] and not identity['stock_code_match']:
            info['pdf_validation_warning'] = 'PDF正文未匹配公司名或股票代码，请人工核对'
        elif not identity['name_match'] and identity['stock_code_match']:
            info['pdf_validation_warning'] = '公司名未匹配，但股票代码已匹配，基本可接受，请人工核对'
        else:
            if identity['name_match']:
                logger.info("PDF内容匹配公司名称")
            if identity['stock_code_match']:
                logger.info("PDF内容匹配股票代码")

        # 提取 listing_suffix
        listing_suffix = None
        if company_name:
            cn_lower = company_name.lower()
            if any(s in cn_lower for s in ['-b', '－b', '－ｂ', '－Ｂ']):
                info['sector'] = 'healthcare'
                listing_suffix = 'B'
            elif any(s in cn_lower for s in ['-w', '－w', '－ｗ', '－Ｗ']):
                listing_suffix = 'W'
            elif any(s in cn_lower for s in ['-p', '－p', '－ｐ', '－Ｐ']) and info.get('sector') == 'hardtech':
                healthcare_signals = [
                    'drug', 'pharmaceutical', 'medicine', 'clinical trial',
                    'biotech', 'therapeutic', 'pipeline', 'drug candidate',
                    '医药', '药物', '临床', '创新药', '疗法', '制药',
                ]
                if any(s in text.lower() for s in healthcare_signals):
                    info['sector'] = 'healthcare'
                    listing_suffix = 'P'
        if listing_suffix:
            info['listing_suffix'] = listing_suffix

        info['parse_success'] = True
        return info

    def parse(self, stock_code, company_name):
        """解析招股书（通过 stock_code 查找本地 PDF）"""
        pdf_path = os.path.join(self.cache_dir, f"{stock_code}_prospectus.pdf")

        if not os.path.exists(pdf_path):
            return {'parse_error': f'PDF文件不存在: {pdf_path}', 'parse_success': False, '_extracted_text': ''}

        return self.parse_pdf_file(pdf_path, stock_code=stock_code, company_name=company_name)
    
    def _extract_metric_with_fallback(self, text, info_key, year_bound_keywords, line_fallback_keywords, percent=False, sanity_check=None):
        series = self._extract_year_bound_series(text, year_bound_keywords, percent=percent)
        use_fallback = False
        if series and info_key not in self._current_info:
            latest = series['latest_value']
            previous = series['previous_value']
            if sanity_check:
                use_fallback = sanity_check(latest, previous)
            if not use_fallback:
                self._current_info[info_key] = latest
                self._current_info[f'{info_key}_y1'] = previous
                self._current_info[f'{info_key}_year'] = series['latest_year']
                self._current_info[f'{info_key}_y1_year'] = series['previous_year']
                self._current_info['financial_extract_confidence'] = 'year_bound'
                return True

        if (info_key not in self._current_info) and (not series or use_fallback):
            values = self._extract_financial_series(text, line_fallback_keywords)
            if values:
                if sanity_check and len(values) >= 2 and sanity_check(values[0], values[1]):
                    return False
                self._current_info[info_key] = values[0]
                if len(values) > 1:
                    self._current_info[f'{info_key}_y1'] = values[1]
                self._current_info.setdefault('financial_extract_confidence', 'line_fallback')
                return True
        return False

    def extract_info(self, text):
        """提取关键信息"""
        info = {}
        self._current_info = info

        price_patterns = [
            r'highest offer price[^0-9]*?HK?\$?\s*([0-9,]+(?:\.[0-9]+)?)',
            r'offer price[^0-9]*?([0-9,]+(?:\.[0-9]+)?)\s*(?:to|-)\s*([0-9,]+(?:\.[0-9]+)?)',
            r'offer price[^0-9]*?HK?\$?\s*([0-9,]+(?:\.[0-9]+)?)',
            # 中文发售價
            r'發售價[^0-9]*?(?:每股.*?)?\s*(?:HK\$|港元)?\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:港元|HKD)',
            r'最終發售價[^0-9]*?\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:港元|HKD)',
        ]
        for pattern in price_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                try:
                    if isinstance(matches[0], tuple):
                        info['min_price'] = float(matches[0][0].replace(',', ''))
                        info['max_price'] = float(matches[0][1].replace(',', ''))
                    else:
                        info['max_price'] = float(matches[0].replace(',', ''))
                    break
                except (ValueError, IndexError):
                    pass

        lot_patterns = [
            r'board lot size[^0-9]*?([0-9,]+)',
            r'each board lot[^0-9]*?([0-9,]+)',
            # 中文每手股数
            r'每手[^0-9]*?([0-9,]+)\s*股',
            r'每手買賣單位[^0-9]*?([0-9,]+)\s*股',
            r'買賣單位每手([0-9,]+)\s*股',
        ]
        for pattern in lot_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                try:
                    info['lot_size'] = int(matches[0].replace(',', ''))
                    break
                except (ValueError, IndexError):
                    pass

        def _revenue_sanity(latest, previous):
            if latest <= 0 or previous <= 0:
                return True
            ratio = max(latest, previous) / max(min(latest, previous), 1e-9)
            return ratio > 20

        def _profit_sanity(latest, previous):
            revenue_for_check = info.get('revenue')
            if _is_num(revenue_for_check) and revenue_for_check > 0:
                return abs(latest) > max(revenue_for_check * 20, 1000)
            return False

        gross_margin_series = self._extract_year_bound_series(text, ['gross profit margin'], percent=True)
        if gross_margin_series and 'gross_margin' not in info:
            info['gross_margin'] = gross_margin_series['latest_value']
            info['gross_margin_year'] = gross_margin_series['latest_year']
            info['financial_extract_confidence'] = 'year_bound'
            logger.info("找到毛利率: %.1f%% (%s)", info['gross_margin'], info['gross_margin_year'])
        elif 'gross_margin' not in info:
            for line in text.split('\n'):
                if 'gross profit margin' in line.lower():
                    valid_values = [float(m) for m in re.findall(r'([0-9]+\.[0-9]+|[0-9]+)\s*%', line) if 0 < float(m) <= 100]
                    if valid_values:
                        info['gross_margin'] = valid_values[-1]
                        info['financial_extract_confidence'] = 'line_fallback'
                        logger.info("找到毛利率: %.1f%%", info['gross_margin'])
                        break

        self._extract_metric_with_fallback(
            text, 'revenue',
            ['revenue', 'total revenue', 'sales'],
            ['revenue', 'total revenue', 'sales', 'turnover'],
            sanity_check=_revenue_sanity,
        )

        self._extract_metric_with_fallback(
            text, 'net_profit',
            ['net profit', 'profit for the year', 'profit attributable', 'loss for the year', 'net loss',
             'profit/(loss) for the year', 'profit for the period', 'loss for the period'],
            ['net profit', 'profit for the year', 'profit attributable', 'loss for the year',
             'profit/(loss) for the year', 'profit for the period', 'loss for the period'],
            sanity_check=_profit_sanity,
        )
        if 'net_profit' in info:
            info['profitable'] = info['net_profit'] > 0
        if 'profitable' not in info and self._has_financial_loss_context(text):
            info['profitable'] = False

        consolidated_fin_table = self._extract_consolidated_financial_table(text)
        if consolidated_fin_table:
            self._apply_financial_table_to_info(
                info,
                consolidated_fin_table,
                source='consolidated_statement',
                force=True,
            )
        else:
            fin_table = extract_financial_table_by_row(text, {
                'revenue': ['revenue'],
                'net_profit': ['profit for the year', 'loss for the year'],
                'cost_of_sales': ['cost of sales'],
                'rd_expense': ['research and development expenses'],
                'operating_cash_flow': ['cash generated from operations', 'net cash from operating'],
            })
            self._apply_financial_table_to_info(
                info,
                fin_table,
                source='row_fallback',
                force=False,
            )

        cornerstone_analysis = CornerstoneAnalyzer().analyze(text)
        info['cornerstone_analysis'] = cornerstone_analysis
        info['cornerstone_investors'] = cornerstone_analysis.get('cornerstone_investors', [])
        info['cornerstone_pct'] = cornerstone_analysis.get('cornerstone_pct')
        extract_prospectus_basic_info(text, info)

        # 财务币种检测
        if 'financial_currency' not in info or info.get('financial_currency_unit') is None:
            detected_currency, detected_unit = self._detect_financial_currency(text)
            info['financial_currency'] = detected_currency
            info['financial_currency_unit'] = detected_unit
            info['financial_currency_source'] = 'table_header_regex'

        self._sanitize_financial_info(info)

        # 通过 dataclass 做一次结构校验与规范化（兼容层，失败时回退原始 dict）
        try:
            from .models import ProspectusInfo
            normalized = ProspectusInfo.from_dict(info)
            if normalized is not None:
                return normalized.to_dict(drop_runtime=False)
        except Exception as e:
            logger.warning("ProspectusInfo 模型规范化失败: %s，返回原始 dict", e)

        return info
