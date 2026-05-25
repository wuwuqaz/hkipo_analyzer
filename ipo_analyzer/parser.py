import re
import os
import logging
import copy
from datetime import datetime
from typing import Optional

from ._threadsafe_cache import ThreadSafeLRUCache

from .utils import _is_num
from .table_extraction import extract_financial_table_by_row
from .cornerstone import CornerstoneAnalyzer, investor_profiles_signature
from .text_extractor import extract_pdf_text
from .identity_validator import validate_pdf_identity
from .prospectus_basic_extractor import extract_prospectus_basic_info
from .settings import SETTINGS

logger = logging.getLogger(__name__)

_PRICE_PATTERNS = [
    re.compile(r'highest offer price[^0-9]*?HK?\$?\s*([0-9,]+(?:\.[0-9]+)?)', re.IGNORECASE),
    re.compile(r'offer price[^0-9]*?([0-9,]+(?:\.[0-9]+)?)\s*(?:to|-)\s*([0-9,]+(?:\.[0-9]+)?)', re.IGNORECASE),
    re.compile(r'offer price[^0-9]*?HK?\$?\s*([0-9,]+(?:\.[0-9]+)?)', re.IGNORECASE),
    re.compile(r'發售價[^0-9]*?(?:每股.*?)?\s*(?:HK\$|港元)?\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:港元|HKD)', re.IGNORECASE),
    re.compile(r'最終發售價[^0-9]*?\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:港元|HKD)', re.IGNORECASE),
]

_LOT_SIZE_PATTERNS = [
    re.compile(r'board[\x00-\x1f\x7f-\x9f\s]+lot[\x00-\x1f\x7f-\x9f\s]+size[^\d]*?(\d[\d,]*)', re.IGNORECASE | re.DOTALL),
    re.compile(r'each[\x00-\x1f\x7f-\x9f\s]+board[\x00-\x1f\x7f-\x9f\s]+lot[^\d]*?(\d[\d,]*)', re.IGNORECASE | re.DOTALL),
    re.compile(r'每\s*手[^\d]*?(\d[\d,]*)\s*股', re.IGNORECASE | re.DOTALL),
    re.compile(r'每\s*手\s*買\s*賣\s*單\s*位[^\d]*?(\d[\d,]*)\s*股', re.IGNORECASE | re.DOTALL),
    re.compile(r'買\s*賣\s*單\s*位\s*每\s*手[^\d]*?(\d[\d,]*)\s*股', re.IGNORECASE | re.DOTALL),
    re.compile(r'每\s*手[^\d]*?(\d[\d,]*)', re.IGNORECASE | re.DOTALL),
    re.compile(r'買\s*賣\s*單\s*位\s*[:：][^\d]*?(\d[\d,]*)\s*股', re.IGNORECASE | re.DOTALL),
]

_CRE_PARSER_MILLION_BILLION = re.compile(r'(million|billion)', re.IGNORECASE)
_CRE_PARSER_YEAR = re.compile(r'(20[0-9]{2})(?:年|\b)')
_CRE_PARSER_YEAR_ALT = re.compile(r'(20\d{2})(?:年|\b)')
_CRE_PARSER_NUMERIC_TOKEN = re.compile(r'\(?-?[0-9][0-9,]*(?:\.[0-9]+)?\)?%?')
_CRE_PARSER_HAS_LETTER = re.compile(r'[A-Za-z]')
_CRE_PARSER_LOSS = re.compile(r'^(?:adjusted\s+net\s+)?loss\b', re.IGNORECASE)
_CRE_PARSER_CN_LOSS = re.compile(r'虧損|亏损')
_CRE_PARSER_CASH_USED = re.compile(r'^net\s+cash\s+used\b', re.IGNORECASE)
_CRE_PARSER_CN_CASH_USED = re.compile(r'所用現金|所用现金|現金流出|现金流出')
_CRE_PARSER_CONTROL_CHARS = re.compile(r'[\x00-\x1f\x7f-\x9f]+')
_CRE_PARSER_GROSS_MARGIN = re.compile(r'([0-9]+\.[0-9]+|[0-9]+)\s*%')

# _extract_consolidated_financial_table 静态数据提升到模块级
_PARSER_YEAR_HEADERS = [
    r'Year ended December 31',
    r'For the year ended December 31',
    r'For the years ended December 31',
    r'For the six months ended',
    r'Six months ended',
    r'Year ended',
    r'Track Record Period',
    r'截至.*?12月31日止年度',
    r'截至.*?止年度',
    r'截至.*?止六個月',
    r'截至.*?止六个月',
    r'截至.*?止三個月',
    r'截至.*?止三个月',
]
_CRE_PARSER_YEAR_HEADER = re.compile('|'.join(_PARSER_YEAR_HEADERS), re.IGNORECASE)

_PARSER_UNIT_PATTERNS = [
    r"RMB[’'‘`]000",
    r"HK\$[’'‘`]000",
    r'RMB thousand',
    r'HKD thousand',
    r'RMB in thousands',
    r'HK\$ in thousands',
    r'rmb in thousands',
    r'hk\$ in thousands',
    r'人民幣.*?千元',
    r'港元.*?千元',
    r'港幣.*?千元',
    r'人民幣.*?千(?!萬|万)',
    r'港元.*?千(?!萬|万)',
]
_PARSER_MILLION_UNIT_PATTERNS = [
    r'RMB\s*million',
    r'HK\$\s*million',
    r'HKD\s*million',
    r'rmb\s*million',
    r'hk\$\s*million',
    r'hkd\s*million',
    r'RMB\s*\(?million\)?',
    r'HKD\s*\(?million\)?',
    r'人民幣.*?百萬',
    r'港元.*?百萬',
    r'港幣.*?百萬',
]
_CRE_PARSER_UNIT = re.compile('|'.join(_PARSER_UNIT_PATTERNS), re.IGNORECASE | re.DOTALL)
_CRE_PARSER_MILLION_UNIT = re.compile('|'.join(_PARSER_MILLION_UNIT_PATTERNS), re.IGNORECASE | re.DOTALL)

# _extract_consolidated_financial_table row_patterns 预编译
_PARSER_ROW_PATTERNS = [
    ('revenue', [re.compile(p, re.IGNORECASE) for p in [r'^Revenue\b', r'^收益\b', r'^收入\b']]),
    ('cost_of_sales', [re.compile(p, re.IGNORECASE) for p in [r'^Cost of sales\b', r'^銷售成本\b', r'^營業成本\b']]),
    ('gross_profit', [re.compile(p, re.IGNORECASE) for p in [r'^Gross profit\b', r'^毛利\b']]),
    ('rd_expense', [re.compile(p, re.IGNORECASE) for p in [r'^Research and development expenses\b', r'^研發開支\b', r'^研發費用\b']]),
    ('net_profit', [re.compile(p, re.IGNORECASE) for p in [
        r'^(?:Profit|Loss) for the year\b', r'^Profit/\(Loss\) for the year\b',
        r'^(?:Profit|Loss) for the period\b',
        r'^年內虧損\b', r'^年內利潤\b', r'^年度虧損\b', r'^年度利潤\b',
        r'^年內虧損及全面收益總額\b', r'^年內利潤及全面收益總額\b']]),
    ('adjusted_net_profit', [re.compile(p, re.IGNORECASE) for p in [
        r'^Adjusted net profit\b', r'^Adjusted net loss\b',
        r'^經調整.*?利潤\b', r'^經調整.*?虧損\b']]),
    ('operating_cash_flow', [re.compile(p, re.IGNORECASE) for p in [
        r'^Net cash (?:generated|used) (?:from|in) operating activities\b',
        r'^經營活動.*?現金流量\b', r'^經營活動.*?淨額\b']]),
]

# _extract_currency_unit 模式预编译
_PARSER_CURRENCY_PATTERNS = [
    (re.compile(r"RMB\s*million|RMB\s*\(?million\)?|rmb\s*million", re.IGNORECASE), "RMB", "million"),
    (re.compile(r"HK\$\s*million|HKD\s*million|hk\$\s*million|HKD\s*\(?million\)?", re.IGNORECASE), "HKD", "million"),
    (re.compile(r"US\$\s*million|USD\s*million|us\$\s*million", re.IGNORECASE), "USD", "million"),
    (re.compile(r"RMB[’'‘`]?000|RMB\s*thousand|RMB\s*in\s*thousands|rmb[’'‘`]?000|rmb\s*thousand", re.IGNORECASE), "RMB", "thousand"),
    (re.compile(r"HK\$[’'‘`]?000|HK\$\s*thousand|HK\$\s*in\s*thousands|HKD\s*thousand|hk\$[’'‘`]?000", re.IGNORECASE), "HKD", "thousand"),
    (re.compile(r"US\$[’'‘`]?000|USD\s*thousand|us\$[’'‘`]?000", re.IGNORECASE), "USD", "thousand"),
    (re.compile(r'人民幣百萬|人民幣.*?百萬', re.IGNORECASE), "RMB", "million"),
    (re.compile(r'港元百萬|港元.*?百萬|港幣百萬', re.IGNORECASE), "HKD", "million"),
    (re.compile(r'美元百萬|美元.*?百萬', re.IGNORECASE), "USD", "million"),
    (re.compile(r'人民幣千元|人民幣.*?千元', re.IGNORECASE), "RMB", "thousand"),
    (re.compile(r'港元千元|港元.*?千元|港幣千元', re.IGNORECASE), "HKD", "thousand"),
    (re.compile(r'美元千元|美元.*?千元', re.IGNORECASE), "USD", "thousand"),
]


class ProspectusParser:
    """招股书解析器"""
    _PARSE_CACHE = ThreadSafeLRUCache(maxsize=8)

    def __init__(self, cache_dir=None):
        if cache_dir is None:
            import tempfile
            cache_dir = os.path.join(tempfile.gettempdir(), "hkipo_prospectus")
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
        if 'thousand' in unit:
            return value / 1000
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
                if raw_unit == 'million' and not _CRE_PARSER_MILLION_BILLION.search(line):
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
        for year in _CRE_PARSER_YEAR.findall(text):
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
            if percent and not (-200 < value <= 200):
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
        for match in _CRE_PARSER_NUMERIC_TOKEN.finditer(line or ''):
            value = cls._parse_table_number_token(match.group(0))
            if value is not None:
                values.append(value)
        return values

    @classmethod
    def _extract_financial_row_values(cls, block_lines, row_idx, year_count):
        # 优先从匹配行本身提取（中文表格标签与数值同行）
        match_line_values = cls._numeric_values_from_table_line(
            (block_lines[row_idx] or '').strip(),
        )
        amount_like = [v for v in match_line_values if abs(v) >= 500]
        if len(amount_like) >= year_count:
            return amount_like[:year_count]
        if len(match_line_values) >= year_count:
            return match_line_values[:year_count]

        # 回退：从后续行扫描（英文表格数值可能在下一行或多行展开）
        values = list(match_line_values)
        for j in range(row_idx + 1, min(len(block_lines), row_idx + 14)):
            line = (block_lines[j] or '').strip()
            if not line:
                continue
            line_values = cls._numeric_values_from_table_line(line)
            if _CRE_PARSER_HAS_LETTER.search(line) and not line_values and len(values) >= year_count:
                break
            values.extend(line_values)
            if len(values) >= year_count * 2:
                break

        if not values:
            return []

        amount_like = [v for v in values if abs(v) >= 500]
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
            if _CRE_PARSER_LOSS.match(lower):
                return True
            if _CRE_PARSER_CN_LOSS.search(row_line or ''):
                return True
        if key == 'operating_cash_flow':
            if _CRE_PARSER_CASH_USED.match(lower):
                return True
            if _CRE_PARSER_CN_CASH_USED.search(row_line or ''):
                return True
        return False

    def _extract_consolidated_financial_table(self, text):
        """提取综合损益表主表，避免业务分部表或叙述段落覆盖核心财务值。"""
        lines = text.split('\n')

        _CORE_STATEMENT_TOKENS = [
            'consolidated statements of profit or loss',
            'consolidated statement of profit or loss',
            'consolidated statements of profit or loss and other comprehensive income',
            'summary of consolidated statements',
            'selected consolidated financial information',
            'results of operations',
            'summary financial data',
            'summary of our consolidated statements',
            '綜合全面收益表', '綜合損益表', '合併損益表',
            '合併全面收益表', '損益表', '財務資料', '經營業績',
            '綜合損益及其他全面收益表', '財務摘要', '歷史財務資料',
            '合併財務狀況表', '綜合財務狀況表',
        ]
        _BREAKDOWN_TOKENS = [
            'key operating data',
            'breakdown of our revenue',
            'breakdown of our cost',
            'gross profit and gross margins by',
            'revenue by geographical',
            'revenue by product',
            '收益明細', '收入明細', '分部收益', '按地區', '按產品',
        ]

        for start_idx, line in enumerate(lines):
            if not _CRE_PARSER_YEAR_HEADER.search(line or ''):
                continue

            preceding_window = lines[max(0, start_idx - 25):start_idx]
            preceding_text = '\n'.join(preceding_window).lower()
            is_core_statement = any(token in preceding_text for token in _CORE_STATEMENT_TOKENS)
            is_breakdown_table = any(token in preceding_text for token in _BREAKDOWN_TOKENS)
            if not is_core_statement or is_breakdown_table:
                continue

            header_block = '\n'.join(lines[start_idx:start_idx + 18])
            years = []
            for match in _CRE_PARSER_YEAR_ALT.finditer(header_block):
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

            header_zone = '\n'.join(block_lines[:40])
            is_thousand_unit = _CRE_PARSER_UNIT.search(header_zone)
            is_million_unit = _CRE_PARSER_MILLION_UNIT.search(header_zone)
            table_unit = None
            if is_thousand_unit and not is_million_unit:
                table_unit = 'thousand'
            elif is_million_unit and not is_thousand_unit:
                table_unit = 'million'
            elif is_thousand_unit and is_million_unit:
                thu_pos = min((m.start() for m in _CRE_PARSER_UNIT.finditer(header_zone)), default=99999)
                mpu_pos = min((m.start() for m in _CRE_PARSER_MILLION_UNIT.finditer(header_zone)), default=99999)
                table_unit = 'thousand' if thu_pos < mpu_pos else 'million'
            else:
                continue

            table = {}
            table['_table_unit'] = table_unit
            for key, patterns in _PARSER_ROW_PATTERNS:
                if key in table:
                    continue
                for row_idx, row_line in enumerate(block_lines):
                    cleaned_line = _CRE_PARSER_CONTROL_CHARS.sub(' ', row_line or '').strip()
                    if any(pattern.search(cleaned_line) for pattern in patterns):
                        if key == 'gross_profit' and 'margin' in cleaned_line.lower():
                            continue
                        values = self._extract_financial_row_values(block_lines, row_idx, len(years))
                        if self._row_implies_negative(key, cleaned_line):
                            values = [-abs(v) for v in values]
                        if len(values) >= len(years):
                            table[key] = {year: values[pos] for pos, year in enumerate(years)}
                        break

            revenue_row = table.get('revenue') or {}
            if len(revenue_row) >= 2 and all(value >= 0 for value in revenue_row.values()):
                return table

        return {}

    def _detect_financial_currency(self, text):
        """从财务表附近识别币种：RMB/HKD/USD，默认 HKD。
        同时返回币种和单位（million/thousand/unknown）。"""
        for pat, currency, unit in _PARSER_CURRENCY_PATTERNS:
            if pat.search(text):
                return currency, unit
        return "HKD", "unknown"  # 默认

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
            if latest_revenue and latest_revenue != 0:
                info['gross_margin'] = latest_gross_profit / latest_revenue * 100
                info['gross_margin_year'] = latest_year
            if len(common_years) >= 2:
                previous_year = common_years[-2]
                previous_revenue = revenue_row.get(previous_year)
                previous_gross_profit = gross_profit_row.get(previous_year)
                if previous_revenue and previous_revenue != 0:
                    info['gross_margin_y1'] = previous_gross_profit / previous_revenue * 100
                    info['gross_margin_y1_year'] = previous_year

    def _has_financial_loss_context(self, text):
        loss_keywords = [
            'loss for the year', 'loss for the period', 'net loss',
            'loss attributable',
            '年內虧損', '年内亏损', '淨虧損', '净亏损', '虧損淨額', '亏损净额',
        ]
        # 中英文财报章节标志
        _FS_TOKENS = [
            'consolidated statement of profit or loss',
            'consolidated statements of profit or loss',
            '綜合損益表', '合併損益表', '損益表',
            '綜合全面收益表', '合併全面收益表',
            '綜合損益及其他全面收益表',
        ]
        fs_start = -1
        text_lower = text.lower()
        for token in _FS_TOKENS:
            pos = text_lower.find(token.lower())
            if pos >= 0:
                fs_start = pos
                break
        if fs_start < 0:
            # 回退：在整个文本中搜索（中文招股书可能没有明显的英文章节标识）
            fs_start = 0
        window_start = max(0, fs_start - 2000)
        window_end = min(len(text), fs_start + 8000)
        window = text[window_start:window_end]

        risk_context_patterns = [
            'risk factor', 'may result in', 'could result in',
            'may incur', 'may be adversely', 'forward-looking',
            '風險因素', '风险因素',
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
        if _is_num(revenue) and revenue < 0:
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

        cache_key = None
        try:
            stat = os.stat(pdf_path)
            cache_key = (
                os.path.abspath(pdf_path),
                stat.st_mtime,
                stat.st_size,
                stock_code,
                company_name,
                investor_profiles_signature(),
            )
            cached = self._PARSE_CACHE.get(cache_key)
            if cached is not None:
                return copy.deepcopy(cached)
        except OSError:
            cache_key = None

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

        if cache_key is not None:
            self._PARSE_CACHE.put(cache_key, copy.deepcopy(info))

        return info

    def parse(self, stock_code, company_name):
        """解析招股书（通过 stock_code 查找本地 PDF）"""
        pdf_path = os.path.join(self.cache_dir, f"{stock_code}_prospectus.pdf")

        if not os.path.exists(pdf_path):
            return {'parse_error': f'PDF文件不存在: {pdf_path}', 'parse_success': False, '_extracted_text': ''}

        return self.parse_pdf_file(pdf_path, stock_code=stock_code, company_name=company_name)
    
    def _extract_metric_with_fallback(self, text, info, info_key, year_bound_keywords, line_fallback_keywords, percent=False, sanity_check=None):
        series = self._extract_year_bound_series(text, year_bound_keywords, percent=percent)
        use_fallback = False
        if series and info_key not in info:
            latest = series['latest_value']
            previous = series['previous_value']
            if sanity_check:
                use_fallback = sanity_check(latest, previous)
            if not use_fallback:
                info[info_key] = latest
                info[f'{info_key}_y1'] = previous
                info[f'{info_key}_year'] = series['latest_year']
                info[f'{info_key}_y1_year'] = series['previous_year']
                info['financial_extract_confidence'] = 'year_bound'
                return True

        if (info_key not in info) and (not series or use_fallback):
            values = self._extract_financial_series(text, line_fallback_keywords)
            if values:
                if sanity_check and len(values) >= 2 and sanity_check(values[0], values[1]):
                    return False
                info[info_key] = values[0]
                if len(values) > 1:
                    info[f'{info_key}_y1'] = values[1]
                info.setdefault('financial_extract_confidence', 'line_fallback')
                return True
        return False

    def extract_info(self, text):
        """提取关键信息"""
        info = {}

        for pattern in _PRICE_PATTERNS:
            matches = pattern.findall(text)
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

        for pattern in _LOT_SIZE_PATTERNS:
            matches = pattern.findall(text)
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
                    valid_values = [float(m) for m in _CRE_PARSER_GROSS_MARGIN.findall(line) if 0 < float(m) <= 100]
                    if valid_values:
                        info['gross_margin'] = valid_values[-1]
                        info['financial_extract_confidence'] = 'line_fallback'
                        logger.info("找到毛利率: %.1f%%", info['gross_margin'])
                        break

        self._extract_metric_with_fallback(
            text, info, 'revenue',
            ['revenue', 'total revenue', 'sales', '收益', '收入', '營業收入', '营业收入'],
            ['revenue', 'total revenue', 'sales', 'turnover', '收益', '收入', '營業收入', '营业收入'],
            sanity_check=_revenue_sanity,
        )

        self._extract_metric_with_fallback(
            text, info, 'net_profit',
            ['net profit', 'profit for the year', 'profit attributable', 'loss for the year', 'net loss',
             'profit/(loss) for the year', 'profit for the period', 'loss for the period',
             '净利润', '淨利潤', '純利', '年內利潤', '年內虧損', '年内利润', '年内亏损',
             '本公司權益股東應佔利潤', '本公司权益股东应占利润', '年度溢利',
            ],
            ['net profit', 'profit for the year', 'profit attributable', 'loss for the year',
             'profit/(loss) for the year', 'profit for the period', 'loss for the period',
             '净利润', '淨利潤', '純利', '年內利潤', '年內虧損', '年内利润', '年内亏损',
             '本公司權益股東應佔利潤', '本公司权益股东应占利润', '年度溢利',
            ],
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

        # 如果文本提取的 cornerstone_pct 缺失或无效，使用表格计算值 fallback
        text_pct = info.get('cornerstone_pct')
        table_pct = info.get('cornerstone_offer_ratio_pct')
        if (text_pct is None or text_pct <= 0) and table_pct is not None and table_pct > 0:
            info['cornerstone_pct'] = table_pct
            info['cornerstone_analysis']['cornerstone_pct'] = table_pct
        # 反向 fallback：如果表格计算为 0 但文本提取到了有效占比，用文本值填充
        if table_pct == 0 and text_pct is not None and text_pct > 0:
            info['cornerstone_offer_ratio_pct'] = text_pct

        # 财务币种检测
        if 'financial_currency' not in info or info.get('financial_currency_unit') is None:
            detected_currency, detected_unit = self._detect_financial_currency(text)
            info['financial_currency'] = detected_currency
            info['financial_currency_unit'] = detected_unit
            info['financial_currency_source'] = 'table_header_regex'

        self._sanitize_financial_info(info)

        # --- gross_margin fallback：无销售成本/许可收入型公司 ---
        if info.get('gross_margin') is None and _is_num(info.get('revenue')) and info['revenue'] > 0:
            cos = info.get('cost_of_sales')
            has_no_cos = (cos is None or cos == 0)
            text_lower = text.lower()
            license_signals = [
                'upfront payment', 'milestone payment', 'license payment',
                'collaboration revenue', 'partnership revenue',
                '许可费', '授权首付款', '里程碑付款', '合作收入',
            ]
            has_license_revenue = any(s in text_lower for s in license_signals)
            if has_no_cos and has_license_revenue:
                info['gross_margin'] = 100.0
                info['gross_margin_year'] = info.get('revenue_year')
                info['financial_data_quality_flags'] = info.get('financial_data_quality_flags', []) + ['gross_margin_inferred_from_license_revenue']
                logger.info("毛利率fallback: 许可/里程碑收入无销售成本，推断毛利率100%%")
            elif has_no_cos and _is_num(info.get('net_profit')) and info['net_profit'] > 0:
                # 保守估计：净利率 + 15% 运营费用缓冲
                inferred_gm = min(100.0, info['net_profit'] / info['revenue'] * 100 + 15)
                if inferred_gm > 50:
                    info['gross_margin'] = inferred_gm
                    info['gross_margin_year'] = info.get('revenue_year')
                    info['financial_data_quality_flags'] = info.get('financial_data_quality_flags', []) + ['gross_margin_inferred_from_net_margin']
                    logger.info("毛利率fallback: 无销售成本数据，保守推断毛利率%.1f%%", inferred_gm)

        # 质地增强分析器 — 管理层治理、资产负债、盈利可持续性
        from .analyzers._management_governance import ManagementGovernanceAnalyzer
        from .analyzers._balance_sheet import BalanceSheetAnalyzer
        from .analyzers._profit_sustainability import ProfitSustainabilityAnalyzer
        from .analyzers._sponsor_track_record import SponsorTrackRecordAnalyzer

        info['management_governance'] = ManagementGovernanceAnalyzer().analyze(info, text)
        info['balance_sheet'] = BalanceSheetAnalyzer().analyze(info, text)
        info['profit_sustainability'] = ProfitSustainabilityAnalyzer().analyze(info, text)
        info['sponsor_track_record'] = SponsorTrackRecordAnalyzer().analyze(info, text)

        # 通过 dataclass 做一次结构校验与规范化（兼容层，失败时回退原始 dict）
        try:
            from .models import ProspectusInfo
            normalized = ProspectusInfo.from_dict(info)
            if normalized is not None:
                return normalized.to_dict(drop_runtime=False)
        except Exception as e:
            logger.warning("ProspectusInfo 模型规范化失败: %s，返回原始 dict", e)

        return info
