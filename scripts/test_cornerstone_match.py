#!/usr/bin/env python3
"""测试基石投资者匹配逻辑，找出"未命中·未知"的根本原因。"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ipo_analyzer.cornerstone import CornerstoneAnalyzer
from ipo_analyzer.utils import _contains_any  # noqa: E402

analyzer = CornerstoneAnalyzer()

# 模拟从招股书提取的投资者名（常见格式）
test_names = [
    # 医疗基金常见格式
    "OrbiMed Asia Partners Limited",
    "OrbiMed Asia Partners",
    "OrbiMed",
    "Deerfield Management",
    "Deerfield",
    "RTW Investments, LP",
    "RTW Investments",
    "RTW",
    "Lake Bleu Capital",
    "Lake Bleu",
    "Lilly Asia Ventures",
    "LAV",
    "Decheng Capital",
    "Decheng",
    "WuXi AppTec Fund",
    "WuXi",
    # 其他常见格式
    "Hillhouse Capital",
    "HHLR Fund",
    "HHLR",
    "Boyu Capital",
    "Boyu",
    "Qiming Venture Partners",
    "Qiming",
    "Greenwoods Asset Management",
    "Greenwoods",
    "UBS Asset Management",
    "UBS",
    "JPMorgan Asset Management",
    "JPMorgan",
    "Invesco",
    "M&G Investments",
    "M&G",
    "Morgan Stanley Investment Management",
    "Morgan Stanley",
    "General Atlantic",
    "Millennium Management",
    "Millennium",
    "ORIX Asia Asset Management",
    "ORIX",
    "YF Capital",
    "Yunfeng Capital",
    "Yunfeng",
    "Danshuiquan Capital",
    "Danshuiquan",
    "Gao Yi Asset Management",
    "Gao Yi",
    "IDG Capital",
    "IDG",
    "CPE",
    "Primavera Capital",
    "Primavera",
    # 主权/资管
    "GIC Private Limited",
    "GIC",
    "Temasek Holdings",
    "Temasek",
    "BlackRock",
    "Capital Group",
    "Fidelity International",
    "Fidelity",
    "T. Rowe Price",
    "Schroders",
    "Oaktree Capital",
    "Mubadala Investment",
    "Ontario Teachers Pension Plan",
    "Norges Bank",
    "Public Investment Fund",
    "PIF",
    # 产业战略
    "Tencent",
    "Alibaba",
    "CATL",
    "Xiaomi",
    # 新增
    "Jane Street",
    "Citadel Securities",
    "Point72",
    "D1 Capital",
    "Point72 Asset Management",
]

print("=" * 80)
print("测试 _best_profile 匹配")
print("=" * 80)

matched_count = 0
unmatched = []

for name in test_names:
    profile = analyzer._best_profile(name)
    if profile:
        matched_count += 1
        print(f"✅ {name:45s} → {profile['name']:25s} ({profile['tier']}) [{profile['category']}]")
    else:
        unmatched.append(name)
        print(f"❌ {name:45s} → 未命中")

print()
print("=" * 80)
print(f"匹配结果: {matched_count}/{len(test_names)} 命中")
print("=" * 80)

if unmatched:
    print("\n未命中的投资者名:")
    for name in unmatched:
        print(f"  - {name}")

# 测试 _contains_any 的边界匹配行为
print("\n" + "=" * 80)
print("测试 _contains_any 子串匹配行为")
print("=" * 80)

test_cases = [
    ("OrbiMed Asia Partners Limited", ["orbimed"]),
    ("Deerfield Management", ["deerfield"]),
    ("RTW Investments, LP", ["rtw"]),
    ("Lake Bleu Capital", ["lake bleu"]),
    ("Lilly Asia Ventures", ["lilly asia ventures", "lav"]),
    ("Hillhouse Capital", ["hillhouse"]),
    ("HHLR Fund", ["hhlr"]),
    ("Greenwoods Asset", ["greenwoods"]),
    ("UBS Asset Management", ["ubs asset management", "ubs am", "瑞银资管"]),
    ("JPMorgan Asset Management", ["jpmorgan asset management", "jpm am", "摩根资产"]),
    ("M&G Investments", ["m&g", "m g investment"]),
    ("Morgan Stanley IM", ["morgan stanley im"]),
    ("General Atlantic", ["general atlantic"]),
    ("Millennium Management", ["millennium"]),
    ("ORIX Asia AM", ["orix"]),
    ("YF Capital", ["yf capital", "yunfeng"]),
    ("Danshuiquan", ["danshuiquan", "dan shui quan"]),
    ("Gao Yi", ["gaoyi", "gao yi"]),
    ("IDG Capital", ["idg capital", "idg"]),
    ("CPE", ["cpe"]),
    ("Primavera", ["primavera"]),
    ("Decheng", ["decheng"]),
    ("WuXi AppTec", ["wuxi apptec", "wuxi fund"]),
    ("Qiming", ["qiming"]),
    ("Boyu", ["boyu"]),
    ("Invesco", ["invesco"]),
]

for text, aliases in test_cases:
    result = _contains_any(text, aliases)
    status = "✅" if result else "❌"
    print(f"{status} _contains_any({text!r:45s}, {aliases}) = {result}")

# 测试 short_name 提取
print("\n" + "=" * 80)
print("测试 _cornerstone_short_name 提取")
print("=" * 80)

test_full_names = [
    'OrbiMed Asia Partners Limited',
    'Deerfield Management Company L.P.',
    'RTW Investments, LP',
    'Lake Bleu Capital (Hong Kong) Limited',
    'Lilly Asia Ventures',
    'Hillhouse Capital Management',
    'HHLR Fund, L.P.',
    'Greenwoods Asset Management Limited',
    'UBS Asset Management (Hong Kong) Limited',
    'JPMorgan Asset Management (Asia Pacific) Limited',
    'M&G Investments (Hong Kong) Limited',
    'Morgan Stanley Investment Management Limited',
    'General Atlantic Singapore Fund Pte. Ltd.',
    'Millennium Management LLC',
    'ORIX Asia Asset Management Limited',
    'Yunfeng Capital Limited',
    'Danshuiquan Capital Management',
    'Gao Yi Asset Management',
    'IDG Capital',
    'CPE China Fund',
    'Primavera Capital',
    'Decheng Capital',
    'WuXi AppTec Fund I, L.P.',
    'Qiming Venture Partners',
    'Boyu Capital',
    'Invesco Hong Kong Limited',
]

for name in test_full_names:
    short = analyzer._cornerstone_short_name(name)
    profile = analyzer._best_profile(short)
    if profile:
        print(f"✅ {name:55s} → short='{short:35s}' → {profile['name']} ({profile['tier']})")
    else:
        print(f"❌ {name:55s} → short='{short:35s}' → 未命中")
