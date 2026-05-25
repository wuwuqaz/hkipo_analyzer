#!/usr/bin/env python3
"""调试基石提取问题 - 追踪状态机。"""

import sys
import os
import re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ipo_analyzer.cornerstone import CornerstoneAnalyzer

analyzer = CornerstoneAnalyzer()

text = """The table below sets forth details of the cornerstone placing:

Cornerstone Investor                    Amount         Number of     Approximate %   Approximate %
                                        (USD in        Offer Shares  of the Offer    of the Issued
                                        millions)                     Shares          Share Capital

OrbiMed Asia Partners Limited           10.0           1,000,000     5.0%            2.5%
Deerfield Management Company L.P.       8.0            800,000       4.0%            2.0%
RTW Investments, LP                     6.0            600,000       3.0%            1.5%

Notes:
(1) Based on the offer price of HK$100.00 per share.
"""

# 手动模拟 _extract_cornerstone_rows 的核心逻辑
lower_context = text.lower()
start_idx = lower_context.find('the table below sets forth details of the cornerstone placing')
end_markers = ['notes:', 'the information about our cornerstone investors']
end_idx = len(text)
for marker in end_markers:
    idx = lower_context.find(marker, start_idx)
    if idx >= 0:
        end_idx = min(end_idx, idx)

table_text = text[start_idx:end_idx]
lines = [analyzer._normalize_cornerstone_line(line) for line in table_text.splitlines()]
lines = [line for line in lines if line]

# 简化版 _is_noise (只保留关键逻辑)
def _is_noise(line):
    ll = line.lower()
    _NOISE_KW = [
        'the table below sets forth details of the cornerstone',
        'the tables below set forth',
        'cornerstone investor',
        'total investment amount',
        'number of offer shares',
        'approximate % of the offer shares',
        'approximate % of the issued share capital',
        '(usd in millions)',
        'based on the offer price',
        'assuming the over-allotment',
        'assuming the offer size',
        'option is not exercised',
        'option is exercised',
        'offer shares to be acquired',
        'immediately upon',
        'completion of the global offering',
        '(in hk$)',
        'note ',
        'subject to rounding',
        'notes:',
        'appropriate %',
        'of the total',
        'issued share capital',
        'completion of',
        'assuming the',
    ]
    _NOISE_EXACT = {
        'total', 'investment', 'amount', 'subscription', 'subscription amount',
        'number of', 'number of offer', 'offer', 'shares', 'offer shares',
        'shares to be acquired', 'approximate', '%', '% of the', '% of our',
        '% of total', '% of the total', 'issued share', 'share capital',
        'capital', 'total issued', 'issued', 'immediately', 'upon',
        'completion of', 'the global', 'offering', 'global offering',
        '(usd in', 'usd in', 'millions)', 'millions', '($u.s. in',
        '$u.s. in', '(in hk$)', 'in hk$', 'assuming', 'the over',
        'allotment', 'option is', 'not', 'exercised', 'fully',
        'cornerstone investor', 'amount1', 'shares rounded',
        'down to nearest', 'whole board lot', 'of 500 h shares',
        'of 200 h shares', 'approximate % of total',
        'approximate % of h shares', 'approximate % of the',
        'approximate % of our', 'number of offer shares',
        'in issue immediately', 'following the completion of',
        'the global offering', 'shares in issue immediately',
        'cornerstone investors', 'esop', 'employee share option',
        'employee stock ownership', 'pre ipo', 'pre-ipo',
        'appropriate', 'appropriate %', 'total issued share',
        'share capital immediately', 'immediately upon',
        'cornerstone', 'investor', 'investment amount',
        'offer price', 'global offering', 'offer size',
        'over-allotment', 'over allotment',
    }
    table_keywords = ['appropriate', 'assuming', 'over-allotment', 'allotment',
                    'offer size', 'adjustment option', 'exercised', 'not exercised',
                    'completion of', 'global offering', 'issued share capital',
                    'approximate %', 'of the total', 'immediately upon']
    if sum(1 for kw in table_keywords if kw in ll) >= 2:
        return True
    repeated_keywords = ['issued share', 'capital', 'immediately', 'upon', 'appropriate']
    for kw in repeated_keywords:
        if ll.count(kw) >= 2:
            return True
    if 'set out in this prospectus' in ll:
        return True
    if 'cornerstone' in ll and 'number of' in ll and 'offer' in ll:
        return True
    if 'investment amount' in ll and 'offer shares' in ll:
        return True
    if ll.count('shares offering') >= 2:
        return True
    if ll.count('millions)') >= 2:
        return True
    if 'us$ in' in ll or 'hk$ in' in ll:
        return True
    compact = re.sub(r'\([0-9]+\)', '', ll)
    compact = re.sub(r'[^a-z0-9%$.\s]+', ' ', compact)
    compact = re.sub(r'\s+', ' ', compact).strip()
    if compact.startswith('total') and not any(kw in compact for kw in ['fund', 'capital', 'asset', 'management']):
        return True
    if re.fullmatch(r'\d{1,3}', compact):
        return True
    if compact.startswith('based on the offer price'):
        return True
    if re.fullmatch(r'amount\d*', compact):
        return True
    if compact in ('investment amount', 'number of offer shares', 'offer shares', 'issued share capital',
                   'share capital', 'approximate', 'investment', 'amount', 'shares',
                   'cornerstone investor', 'cornerstone investors', 'cornerstone', 'investor'):
        return True
    if 'million' in compact and ('hk' in compact or 'usd' in compact or 'us' in compact or '$' in ll):
        if 'limited' not in compact and not any(kw in compact for kw in ['partners', 'capital', 'management', 'fund']):
            return True
    table_header_kws = ['usd', 'us$', 'hk$', 'u.s.', 'amount', 'shares', 'offer', 'approximate', '%', 'million']
    header_hits = sum(1 for kw in table_header_kws if kw in compact)
    if header_hits >= 3 and 'limited' not in compact:
        return True
    if ('us$' in compact or 'usd' in compact or 'hk$' in compact) and ('offer' in compact or 'shares' in compact) and 'limited' not in compact:
        return True
    if 'shares' in compact and 'capital' in compact and 'million' in compact and 'limited' not in compact:
        return True
    if 'million' in compact and 'shares' in compact and len(compact.split()) <= 3 and 'limited' not in compact:
        return True
    investor_keywords = ['partners', 'capital', 'management', 'investments', 'fund', 'venture', 'asset', 'group', 'corporation', 'holdings', 'plc', 'inc', 'corp']
    if re.fullmatch(r'\(?[a-z\s]+\)?\s*limited\)?', compact) and len(compact.split()) <= 4 and not any(kw in compact for kw in investor_keywords):
        return True
    if 'esop' in compact or 'employee share' in compact or 'employee stock' in compact:
        return True
    return compact in _NOISE_EXACT or ll in _NOISE_EXACT or any(kw in ll for kw in _NOISE_KW)

def _split_line_to_name_and_numbers(line):
    tokens = line.split()
    if not tokens:
        return None, []
    start_idx = 0
    if tokens and re.match(r'^\([0-9]+\)$', tokens[0]):
        start_idx = 1
    effective_tokens = tokens[start_idx:]
    if not effective_tokens:
        return None, []
    number_tokens = []
    name_tokens = []
    found_number = False
    for i in range(len(effective_tokens) - 1, -1, -1):
        t = effective_tokens[i]
        is_strict_numeric = analyzer._is_numeric_cell(t)
        has_letters = bool(re.search(r'[a-zA-Z]', t))
        parsed_num = None if has_letters else analyzer._parse_cornerstone_number(t)
        if is_strict_numeric or (parsed_num is not None and not has_letters):
            number_tokens.insert(0, t)
            found_number = True
        elif found_number:
            if t.endswith(')') and has_letters and re.search(r'\([0-9]+\)', t):
                name_tokens = effective_tokens[:i + 1]
                break
            elif not t.endswith(')'):
                name_tokens = effective_tokens[:i + 1]
                break
        elif not found_number and has_letters and t.endswith(')') and re.search(r'\([0-9]+\)', t):
            continue
    if len(number_tokens) >= 2:
        first_num = analyzer._parse_cornerstone_number(number_tokens[0])
        second_num = analyzer._parse_cornerstone_number(number_tokens[1])
        if first_num is not None and second_num is not None:
            if first_num < 1000 and second_num > first_num * 10:
                name_tokens.append(number_tokens.pop(0))
    if not name_tokens and found_number:
        return None, number_tokens
    if not found_number:
        return line, []
    return ' '.join(name_tokens), number_tokens

# 模拟状态机
name_buffer = []
numeric_buffer = []
pending_flush = False
rows = []

print("=== 状态机追踪 ===")
for i, line in enumerate(lines):
    lower_line = line.lower()
    is_noise = _is_noise(line)
    print(f"\nLine {i}: '{line}'")
    print(f"  is_noise={is_noise}")
    
    if is_noise:
        print("  -> 噪声，跳过")
        if pending_flush or len(numeric_buffer) >= 4:
            print(f"  -> 尝试 flush (pending={pending_flush}, numeric_len={len(numeric_buffer)})")
        elif numeric_buffer:
            name_buffer = []
            numeric_buffer = []
            pending_flush = False
        continue
    
    name_part, number_parts = _split_line_to_name_and_numbers(line)
    print(f"  name_part='{name_part}', number_parts={number_parts}")
    
    if name_part and number_parts and len(number_parts) >= 3:
        print("  -> 混合行（名字+数字）")
        if pending_flush:
            print("  -> 有待flush，先flush再处理新行")
        elif name_buffer and not numeric_buffer:
            print("  -> name_buffer有内容但numeric_buffer为空")
        else:
            print("  -> 新混合行，设置 pending_flush=True")
            name_buffer = [name_part]
            numeric_buffer = number_parts
            pending_flush = True
        continue
    
    if analyzer._is_numeric_cell(line):
        print("  -> 纯数字行")
        if name_buffer:
            numeric_buffer.append(line)
            pending_flush = True
            print("  -> 追加到 numeric_buffer")
        continue
    
    print("  -> 纯名字行")
    if pending_flush and name_buffer and numeric_buffer:
        print("  -> 有待flush的行，检查是否是续行...")
    elif numeric_buffer:
        print("  -> 有numeric_buffer，处理中...")
    
    name_buffer.append(line)
    print("  -> 追加到 name_buffer")

print("\n=== 最终状态 ===")
print(f"name_buffer={name_buffer}")
print(f"numeric_buffer={numeric_buffer}")
print(f"pending_flush={pending_flush}")
print(f"rows={rows}")
