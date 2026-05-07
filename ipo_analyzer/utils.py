import re


def _is_num(x):
    return isinstance(x, (int, float))


def format_iso_date(value):
    if not value:
        return ""
    if isinstance(value, str):
        if "T" in value:
            return value.split("T", 1)[0]
        if " " in value:
            return value.split(" ", 1)[0]
        return value
    return str(value)


def _format_cornerstone_amount(row):
    if not row:
        return "--"
    currency = row.get('investment_currency')
    amount_m = row.get('investment_amount_m')
    hkd_m = row.get('investment_amount_hkd_m') or row.get('total_investment_amount_hkd_m')
    usd_m = row.get('total_investment_amount_usd_m')
    if _is_num(amount_m) and currency:
        if currency == 'HKD':
            return f"HK${amount_m:.1f}m"
        if currency == 'USD':
            return f"US${amount_m:.1f}m"
        return f"{currency} {amount_m:.1f}m"
    if _is_num(hkd_m):
        return f"HK${hkd_m:.1f}m"
    if _is_num(usd_m):
        return f"US${usd_m:.1f}m"
    return "--"


def _normalize_gm(gm):
    if not _is_num(gm):
        return None
    return gm * 100 if 0 < gm <= 1 else gm


def _contains_any(text, aliases):
    lower_text = (text or '').lower()
    for alias in aliases:
        alias_lower = alias.lower().strip()
        if not alias_lower:
            continue
        if re.search(r'[a-z0-9]', alias_lower):
            if re.search(rf'(?<![a-z0-9]){re.escape(alias_lower)}(?![a-z0-9])', lower_text):
                return True
        elif alias_lower in lower_text:
            return True
    return False


def _find_year_headers(lines, max_scan=8):
    found_years = []
    table_start = None
    for i, line in enumerate(lines):
        ll = line.strip().lower()
        if any(p in ll for p in ('year ended december 31', '31 december', 'for the years ended', 'fiscal year ended')):
            table_start = i
            found_years = []
            for j in range(i, min(i + max_scan, len(lines))):
                for m in re.finditer(r'\b(20\d{2})\b', lines[j]):
                    y = int(m.group(1))
                    if y not in found_years:
                        found_years.append(y)
            if len(found_years) >= 2:
                break
    return found_years, table_start


def _extract_table_nums(text_block, n_years, min_val=500):
    nums = []
    for m in re.finditer(r'(\(?\s*[0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?\s*\)?)', text_block):
        raw = m.group(1).strip('( )')
        raw = raw.replace(',', '')
        try:
            val = float(raw)
            if 1900 <= val <= 2100:
                continue
            is_neg = m.group(1).count('(') > 0 and m.group(1).count(')') > 0
            if is_neg:
                val = -val
            nums.append(val)
        except ValueError:
            continue
    filtered = [v for v in nums if abs(v) >= min_val]
    return filtered if len(filtered) >= n_years else nums


SECTOR_KEYWORDS = {
    'healthcare': {
        'classify': [
            'clinical trial', 'biotech', 'biopharmaceutical', 'pharmaceutical',
            'surgery', 'orthopaedic', 'fda', 'drug candidate', 'life sciences',
            '18a', 'medicine', 'therapy', 'surgical implant', 'medical device',
            'hospital', 'diagnostic', 'therapeutic',
        ],
        'mainline': ['medical device', 'surgery', 'orthopaedic', 'innovative drug', 'biotech', 'pharmaceutical', '医疗器械', '创新药'],
        'industrial': ['healthcare', 'medical', 'pharma', 'biotech', 'life sciences', '医疗', '医药'],
    },
    'hardtech': {
        'classify': [
            'semiconductor', 'chip', 'artificial intelligence', 'robot',
            'sensor', 'lidar', 'hardware', 'software', 'saas', 'cloud',
            'intelligent', 'automation', 'platform', 'algorithm',
            'visual perception', 'deep learning', 'neural network',
        ],
        'mainline': ['ai', 'artificial intelligence', 'semiconductor', 'chip', 'robot', 'compute', 'cloud', 'hardware', '芯片', '半导体', '人工智能'],
        'industrial': ['technology', 'semiconductor', 'industrial', 'ai', 'innovation', '科技', '半导体'],
    },
    'consumer': {
        'classify': [
            'consumer', 'retail', 'restaurant', 'food', 'beverage', 'beauty', 'fashion',
        ],
        'mainline': ['gold', 'jewelry', 'brand', 'beauty', 'retail', '黄金', '珠宝', '美妆'],
        'industrial': ['consumer', 'brand', 'retail', 'food', '消费', '品牌'],
    },
}


def _infer_sector(text):
    lower_text = text.lower()
    scores = {}
    for sector, kw_groups in SECTOR_KEYWORDS.items():
        scores[sector] = sum(lower_text.count(kw) for kw in kw_groups['classify'])
    if not scores or max(scores.values()) == 0:
        return 'unknown'
    return max(scores, key=scores.get)


def _normalize_company_name(company_name):
    normalized = company_name.upper()
    for suffix in ['－Ｗ', '－Ｐ', '－Ｂ', '-W', '-P', '-B', ' W', ' P', ' B']:
        normalized = normalized.replace(suffix, '')
    normalized = re.sub(r'[\s\-\u3000()（）]+', '', normalized)
    return normalized.strip()


def _normalize_stock_code(stock_code):
    code = re.sub(r'\D', '', str(stock_code or ''))
    return code.lstrip('0') or code


_RUNTIME_ONLY_FIELDS = {'_extracted_text'}


def strip_runtime_fields(value):
    """Return a copy without large runtime-only fields before caching/exporting."""
    if isinstance(value, dict):
        return {
            key: strip_runtime_fields(item)
            for key, item in value.items()
            if key not in _RUNTIME_ONLY_FIELDS
        }
    if isinstance(value, list):
        return [strip_runtime_fields(item) for item in value]
    return value
