#!/usr/bin/env python3
"""调试基石提取问题。"""

import sys
import os
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

# 先测试 _is_numeric_cell 和 _parse_cornerstone_number
print("=== 测试 _is_numeric_cell ===")
test_tokens = ["10.0", "1,000,000", "5.0%", "2.5%", "OrbiMed", "Limited"]
for t in test_tokens:
    is_num = analyzer._is_numeric_cell(t)
    parsed = analyzer._parse_cornerstone_number(t)
    print(f"  '{t}' -> is_numeric={is_num}, parsed={parsed}")

print("\n=== 测试完整提取 ===")
rows = analyzer._extract_cornerstone_rows(text)
print(f"提取到 {len(rows)} 行")
for row in rows:
    print(f"  {row}")
