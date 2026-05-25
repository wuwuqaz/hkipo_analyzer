#!/usr/bin/env python3
"""测试修复后的效果。"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ipo_analyzer.cornerstone import CornerstoneAnalyzer

analyzer = CornerstoneAnalyzer()

# 模拟截图中的问题行
test_cases = [
    ("Cumbre", "Cumbre 6,153,028 10.0 1,000,000 5.0% 2.5%"),
    ("Big Bend 77", "Big Bend 77 1,466,857 10.0 800,000 4.0% 2.0%"),
    ("Big Bend 72", "Big Bend 72 448,108 10.0 600,000 3.0% 1.5%"),
    ("Big Bend 73", "Big Bend 73 117,357 10.0 200,000 1.0% 0.5%"),
    ("ESOP Platforms", "ESOP Platforms 4,540,146 10.0 500,000 2.5% 1.2%"),
    ("The Cumbre Entities", "The Cumbre Entities(3) 8,185,350 10.0 1,500,000 7.5% 3.75%"),
]

for expected_name, line in test_cases:
    text = f"""The table below sets forth details of the cornerstone placing:

Cornerstone Investor                    Amount         Number of     Approximate %   Approximate %
                                        (USD in        Offer Shares  of the Offer    of the Issued
                                        millions)                     Shares          Share Capital

{line}

Notes:
"""
    rows = analyzer._extract_cornerstone_rows(text)
    if rows:
        for row in rows:
            name = row.get('name', '')
            short = row.get('short_name', '')
            pct = row.get('offer_shares_pct')
            shares = row.get('offer_shares')
            amt = row.get('investment_amount_m')
            print(f"✅ {expected_name:20s} -> name={name!r}, short={short!r}, pct={pct}%, shares={shares}, amt={amt}m")
    else:
        print(f"❌ {expected_name:20s} -> 未提取到行")
