"""Debug script to trace business breakdown extraction for 06872."""
import sys
sys.path.insert(0, '/Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer')

import subprocess

# Extract text from the actual PDF
subprocess.run(
    ["pdftotext", "-layout", "storage/06872_prospectus.pdf", "/tmp/06872_extracted.txt"],
    capture_output=True
)
with open("/tmp/06872_extracted.txt", "r") as f:
    full_text = f.read()

print("=" * 80)
print("Debug: 业务分部数据链路 - 06872 丹诺医药-B")
print("=" * 80)

from ipo_analyzer.analyzers._business_breakdown import BusinessBreakdownAnalyzer

analyzer = BusinessBreakdownAnalyzer()

# Check what patterns the analyzer looks for
print("\n--- 业务分部提取关键词 ---")
for p in analyzer._BUSINESS_LINE_PATTERNS:
    found = p in full_text.lower()
    print(f"  {'✅' if found else '❌'} {p}")

# Check if any segment name patterns are found
print("\n--- 业务分部名称模式匹配 ---")
for pattern in analyzer._SEGMENT_NAME_PATTERNS[:10]:
    matches = list(__import__('re').finditer(pattern, full_text, __import__('re').IGNORECASE))
    print(f"  {'✅' if matches else '❌'} {pattern} - {len(matches)} matches")

# Try the analysis
print("\n--- 执行 BusinessBreakdownAnalyzer ---")
result = analyzer.analyze({}, full_text)

print(f"segments count: {len(result.get('segments', []))}")
print(f"business_model_label: {result.get('business_model_label')}")
print(f"growth_source: {result.get('growth_source')}")
print(f"confidence: {result.get('confidence')}")
print(f"business_breakdown_warning: {result.get('business_breakdown_warning')}")
print(f"main_segment: {result.get('main_segment')}")
print(f"error: {result.get('_error')}")

if result.get('segments'):
    print("\n--- 提取的业务分部 ---")
    for seg in result['segments']:
        print(f"  {seg.get('name')}: share={seg.get('share_pct')}%, revenue={seg.get('revenue_latest')}")

# Check the PDF text for business breakdown related content
print("\n--- PDF 文本搜索 ---")
import re

search_terms = ['business line', 'revenue by', 'business segment', 'business division', 
                'segment revenue', 'product segment', 'segment information']
for term in search_terms:
    matches = re.findall(r'.{0,60}' + re.escape(term) + r'.{0,60}', full_text, re.IGNORECASE)
    if matches:
        print(f"  Found '{term}' - {len(matches)} matches")
        for m in matches[:2]:
            print(f"    ...{m}...")
    else:
        print(f"  Not found: '{term}'")
