#!/usr/bin/env python3
"""调试 _split_line_to_name_and_numbers。"""

import sys
import os
import re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ipo_analyzer.cornerstone import CornerstoneAnalyzer

analyzer = CornerstoneAnalyzer()

# 直接复制 _extract_cornerstone_rows 中的 _split_line_to_name_and_numbers 实现
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
        print(f"  i={i}, t='{t}', is_strict={is_strict_numeric}, has_letters={has_letters}, parsed={parsed_num}")
        if is_strict_numeric or (parsed_num is not None and not has_letters):
            number_tokens.insert(0, t)
            found_number = True
            print("    -> 数字token")
        elif found_number:
            if t.endswith(')') and has_letters and re.search(r'\([0-9]+\)', t):
                name_tokens = effective_tokens[:i + 1]
                print(f"    -> 名字+括号，break, name_tokens={name_tokens}")
                break
            elif not t.endswith(')'):
                name_tokens = effective_tokens[:i + 1]
                print(f"    -> 名字token，break, name_tokens={name_tokens}")
                break
            else:
                print("    -> 以)结尾但不是名字+括号，继续")
        elif not found_number and has_letters and t.endswith(')') and re.search(r'\([0-9]+\)', t):
            print("    -> 还没找到数字，跳过名字+括号")
            continue
        else:
            print("    -> 其他情况")
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

line = "OrbiMed Asia Partners Limited           10.0           1,000,000     5.0%            2.5%"
print(f"测试行: '{line}'")
name, nums = _split_line_to_name_and_numbers(line)
print(f"\n结果: name='{name}', nums={nums}")
