#!/usr/bin/env python3
"""调试剂泰科技基石提取。"""

import sys
import os
import re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ipo_analyzer.cornerstone import CornerstoneAnalyzer
from ipo_analyzer.text_extractor import extract_pdf_text

analyzer = CornerstoneAnalyzer()
text = extract_pdf_text('temp/07666_prospectus.pdf')

context, has_cs = analyzer._cornerstone_context(text)
idx = context.find('Based on the Offer Price of HK$10.50')
table_part = context[idx:idx+8000]

# 手动模拟 _extract_cornerstone_rows 的核心逻辑
lines = [analyzer._normalize_cornerstone_line(line) for line in table_part.splitlines()]
lines = [line for line in lines if line]

# 简化版 _is_noise
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

def _is_noise(line):
    ll = line.lower()
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

# 模拟状态机
name_buffer = []
numeric_buffer = []
pending_flush = False
rows = []

print("=== 状态机追踪 (China Venture 部分) ===")
for i, line in enumerate(lines[130:150]):
    global_i = i + 130
    lower_line = line.lower()
    is_noise = _is_noise(line)
    print(f"\nLine {global_i}: '{line}'")
    print(f"  is_noise={is_noise}, name_buffer={name_buffer}, numeric_buffer={numeric_buffer}")
    
    if is_noise:
        if lower_line == 'capital' and name_buffer and not numeric_buffer:
            name_buffer.append(line)
            print("  -> 特殊处理: Capital被保留")
            continue
        print("  -> 噪声，跳过")
        continue
    
    is_num = analyzer._is_numeric_cell(line)
    if is_num:
        if name_buffer:
            numeric_buffer.append(line)
            pending_flush = True
            print("  -> 数字行，追加到 numeric_buffer")
        continue
    
    # 纯名字行
    if pending_flush and name_buffer and numeric_buffer:
        has_sufficient_data = len(numeric_buffer) >= 8
        if has_sufficient_data:
            print("  -> 数据已完整，flush并开始新投资者")
            # 模拟 flush_row
            print(f"    flush_row: name={' '.join(name_buffer)}")
            name_buffer = [line]
            numeric_buffer = []
            pending_flush = False
        else:
            name_buffer.append(line)
            print("  -> 续行，追加到 name_buffer")
    else:
        name_buffer.append(line)
        print("  -> 纯名字行，追加到 name_buffer")

print("\n=== 最终状态 ===")
print(f"name_buffer={name_buffer}")
print(f"numeric_buffer={numeric_buffer}")
