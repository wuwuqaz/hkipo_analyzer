import re
from .utils import _find_year_headers, _extract_table_nums


def extract_financial_table_by_row(text, row_label_patterns, year_headers=None):
    lines = text.split('\n')
    found_years, table_start = _find_year_headers(lines)
    if not found_years or table_start is None:
        return {}
    n_years = len(found_years)
    sorted_years = sorted(found_years)

    for i, line in enumerate(lines):
        ll = line.lower().strip()
        for label_key, patterns in row_label_patterns.items():
            if any(p.lower() in ll for p in patterns):
                if i < table_start:
                    continue
                window_lines = lines[i:min(i + 5, len(lines))]
                combined = ' '.join(line.strip() for line in window_lines)
                nums = _extract_table_nums(combined, n_years)
                if len(nums) >= n_years:
                    row_data = {y: nums[yi] for yi, y in enumerate(sorted_years) if yi < len(nums)}
                    if row_data:
                        return {label_key: row_data}
    return {}


def extract_segment_table(text, segment_names):
    lines = text.split('\n')
    found_years, _ = _find_year_headers(lines)
    if not found_years:
        return {}
    n_years = len(found_years)
    sorted_years = sorted(found_years)
    results = {}

    for i, line in enumerate(lines):
        ll = line.lower().strip()
        for seg_name in segment_names:
            if seg_name.lower() in ll:
                nums = []
                for j in range(i, min(i + 6, len(lines))):
                    for m in re.finditer(r'(\(?\s*[0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?\s*\)?)', lines[j]):
                        raw = m.group(1).strip('( )')
                        raw = raw.replace(',', '')
                        try:
                            val = float(raw)
                            if 1900 <= val <= 2100:
                                continue
                            is_neg = m.group(1).count('(') > 0 and m.group(1).count(')') > 0
                            if is_neg:
                                val = -val
                            if 0 <= val <= 100:
                                continue
                            if seg_name.lower() in line.lower() or seg_name.lower() in lines[j].lower():
                                nums.append(val)
                        except ValueError:
                            continue
                    if len(nums) >= n_years * 2:
                        break
                filtered = [v for v in nums if abs(v) >= 500]
                use_nums = filtered if len(filtered) >= n_years else nums
                if len(use_nums) >= n_years:
                    seg_data = {y: use_nums[yi] for yi, y in enumerate(sorted_years) if yi < len(use_nums)}
                    results[seg_name] = seg_data
                break
    return results
