#!/usr/bin/env python3
"""测试所有格式的提取效果。"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ipo_analyzer.cornerstone import CornerstoneAnalyzer

analyzer = CornerstoneAnalyzer()

# 模拟真实招股书基石表格文本（多种格式）
test_prospectuses = [
    ("格式1: 标准表格（多空格分隔）", """The table below sets forth details of the cornerstone placing:

Cornerstone Investor                    Amount         Number of     Approximate %   Approximate %
                                        (USD in        Offer Shares  of the Offer    of the Issued
                                        millions)                     Shares          Share Capital

OrbiMed Asia Partners Limited           10.0           1,000,000     5.0%            2.5%
Deerfield Management Company L.P.       8.0            800,000       4.0%            2.0%
RTW Investments, LP                     6.0            600,000       3.0%            1.5%

Notes:
(1) Based on the offer price of HK$100.00 per share.
"""),

    ("格式2: 有引号短名", """The tables below set forth the details of the cornerstone placing:

Cornerstone Investor                    Total Investment   Number of     Approximate %
                                        Amount             Offer Shares  of the Offer
                                        (HK$ in millions)                Shares

"Lake Bleu" (Lake Bleu Capital          50.0               5,000,000     10.0%
 (Hong Kong) Limited)

Lilly Asia Ventures                     30.0               3,000,000     6.0%

Notes:
"""),

    ("格式3: 跨多行", """The table below sets forth details of the cornerstone placing:

Cornerstone Investor

Hillhouse Capital
Management Limited                      100.0              10,000,000    15.0%           7.5%

Greenwoods Asset
Management Limited                      50.0               5,000,000     7.5%            3.75%

Notes:
"""),

    ("格式4: footnote标记", """The table below sets forth details of the cornerstone placing:

Cornerstone Investor                    Amount      Number of      Approximate %
                                        (US$ in     Offer Shares   of the Offer
                                        millions)                  Shares

(1) UBS Asset Management                20.0        2,000,000      4.0%
    (Hong Kong) Limited

(2) JPMorgan Asset Management           25.0        2,500,000      5.0%
    (Asia Pacific) Limited

Notes:
"""),

    ("格式5: Capital在名字中", """The table below sets forth details of the cornerstone placing:

Cornerstone Investor         Total Investment   Number of    Approximate % of
                             Amount (HK$ in      Offer Shares the Offer Shares
                             millions)

Boyu Capital                 40.0               4,000,000    8.0%
Primavera Capital            35.0               3,500,000    7.0%
Qiming Venture Partners      20.0               2,000,000    4.0%

Notes:
"""),

    ("格式6: for and on behalf of", """The table below sets forth details of the cornerstone placing:

Cornerstone Investor                    Total Investment   Number of     Approximate %
                                        Amount             Offer Shares  of the Offer
                                        (HK$ in millions)                Shares

UBS AG London Branch for and on behalf  15.0               1,500,000     3.0%
of UBS Asset Management (Hong Kong)
Limited

Morgan Stanley & Co. International plc  20.0               2,000,000     4.0%

Notes:
"""),

    ("格式7: 只有3列", """The table below sets forth details of the cornerstone placing:

Cornerstone Investor         Amount      Number of    Approximate %
                             (USD in      Offer Shares of the Offer
                             millions)                 Shares

OrbiMed Asia Partners        10.0        1,000,000    5.0%
Deerfield Management         8.0         800,000      4.0%

Notes:
"""),
]

all_pass = True
for label, text in test_prospectuses:
    print(f"\n{'='*80}")
    print(f"测试 {label}")
    print(f"{'='*80}")
    rows = analyzer._extract_cornerstone_rows(text)
    if not rows:
        print("❌ 未提取到任何行")
        all_pass = False
        continue

    for row in rows:
        name = row.get('name', '')
        short = row.get('short_name', '')
        pct = row.get('offer_shares_pct')
        shares = row.get('offer_shares')
        amt = row.get('investment_amount_m')

        row_text = f"{name} {short}"
        profile = analyzer._best_profile(row_text)

        if profile:
            print(f"✅ name='{name:50s}' short='{short:30s}' → {profile['name']} ({profile['tier']}) 占比={pct}% 股数={shares} 金额={amt}m")
        else:
            print(f"❌ name='{name:50s}' short='{short:30s}' → 未命中! 占比={pct}% 股数={shares} 金额={amt}m")
            all_pass = False

print(f"\n{'='*80}")
if all_pass:
    print("🎉 所有测试通过!")
else:
    print("⚠️  有测试失败，需要进一步修复")
