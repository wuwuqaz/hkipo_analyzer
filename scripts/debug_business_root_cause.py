"""Debug script to check what pipeline data is available for 06872."""
import sys
sys.path.insert(0, '/Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer')

import subprocess
subprocess.run(
    ["pdftotext", "-layout", "storage/06872_prospectus.pdf", "/tmp/06872_extracted.txt"],
    capture_output=True
)
with open("/tmp/06872_extracted.txt", "r") as f:
    full_text = f.read()

print("=" * 80)
print("Debug: 06872 业务分部问题根因分析")
print("=" * 80)

# Check what the pipeline analyzer extracts
from ipo_analyzer.analyzers._rnd_pipeline import RnDPipelineAnalyzer
from ipo_analyzer.parser import ProspectusParser

# Try to parse the full prospectus
print("\n--- 检查 R&D Pipeline 分析结果 ---")
pipeline = RnDPipelineAnalyzer().analyze({}, full_text)
print(f"Pipeline quality: {pipeline.get('pipeline_quality_label')}")
print(f"Pipeline candidates: {len(pipeline.get('pipeline', []))}")
print(f"Technology moat: {pipeline.get('technology_moat_label')}")
print(f"Error: {pipeline.get('_error')}")

if pipeline.get('pipeline'):
    print("\nPipeline 产品列表:")
    for p in pipeline['pipeline'][:10]:
        print(f"  - {p.get('name')}: stage={p.get('clinical_stage')}, indication={p.get('indication')}")

# Check what revenue data exists
print("\n--- 检查收入数据 ---")
import re
# Look for revenue numbers
rev_matches = list(re.finditer(r'(?:revenue|income)\s*(?:was|of|:)?\s*([\$RMB\d,\.]+)', full_text, re.IGNORECASE))
print(f"Found {len(rev_matches)} revenue number patterns")
for m in rev_matches[:5]:
    start = max(0, m.start() - 80)
    end = min(len(full_text), m.end() + 80)
    snippet = full_text[start:end].replace('\n', ' ')
    print(f"  ...{snippet}...")

# Check if this is a pre-revenue biotech
print("\n--- 检查是否为 pre-revenue 生物科技公司 ---")
pre_revenue_indicators = [
    'pre-revenue',
    'no revenue',
    'has not generated',
    'not generated any revenue',
    'we have not',
    'since inception',
    'operating losses',
    'accumulated deficit',
    'net loss',
]

for indicator in pre_revenue_indicators:
    matches = list(re.finditer(indicator, full_text, re.IGNORECASE))
    if matches:
        print(f"  ✅ '{indicator}' - {len(matches)} matches")
        if len(matches) <= 3:
            for m in matches[:2]:
                start = max(0, m.start() - 100)
                end = min(len(full_text), m.end() + 100)
                snippet = full_text[start:end].replace('\n', ' ')
                print(f"    ...{snippet}...")

# Check for Chapter 18A indicators
print("\n--- 检查 Chapter 18A 相关指标 ---")
chapter18a_indicators = [
    'chapter 18a',
    'innovative drug',
    'clinical trial',
    'drug candidate',
    'pipeline',
    'preclinical',
    'phase 1',
    'phase 2',
    'phase 3',
    'IND',
    'NDA',
]

for indicator in chapter18a_indicators:
    matches = list(re.finditer(indicator, full_text, re.IGNORECASE))
    if matches:
        print(f"  ✅ '{indicator}' - {len(matches)} matches")
