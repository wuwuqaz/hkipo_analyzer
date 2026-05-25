"""Search for business/revenue breakdown terminology in 06872 PDF."""
import sys
import re
sys.path.insert(0, '/Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer')

import subprocess

subprocess.run(
    ["pdftotext", "-layout", "storage/06872_prospectus.pdf", "/tmp/06872_extracted.txt"],
    capture_output=True
)
with open("/tmp/06872_extracted.txt", "r") as f:
    full_text = f.read()

print("=" * 80)
print("Search for revenue breakdown terminology in 06872 PDF")
print("=" * 80)

# Common pharma/biotech revenue breakdown patterns
search_patterns = [
    r'revenue\s+breakdown',
    r'breakdown\s+of\s+revenue',
    r'revenue\s+by\s+\w+',
    r'breakdown\s+of\s+total\s+revenue',
    r'product\s+pipeline',
    r'pipeline\s+products',
    r'product\s+candidates',
    r'our\s+products?',
    r'core\s+products?',
    r'product\s+portfolio',
    r'drug\s+candidates',
    r'therapeutic\s+areas',
    r'revenue\s+from',
    r'total\s+revenue',
    r'operating\s+revenue',
    r'segment\s+information',
    r'by\s+product',
    r'by\s+business',
    r'by\s+therapeutic',
    r'by\s+indication',
    r'by\s+geography',
    r'by\s+region',
    r'by\s+country',
    r'by\s+market',
    r'by\s+category',
    r'by\s+type',
]

for pattern in search_patterns:
    matches = list(re.finditer(pattern, full_text, re.IGNORECASE))
    if matches:
        print(f"\n✅ Pattern '{pattern}' - {len(matches)} matches")
        for m in matches[:3]:
            start = max(0, m.start() - 100)
            end = min(len(full_text), m.end() + 100)
            snippet = full_text[start:end].replace('\n', ' ')
            print(f"  ...{snippet}...")

# Also check for Chinese patterns
chinese_patterns = [
    r'收入按',
    r'收入拆分',
    r'业务分部',
    r'分部信息',
    r'产品收入',
    r'按产品',
    r'按业务',
    r'按地区',
    r'按区域',
    r'总收入',
    r'营业收入',
]

print("\n\n--- Chinese patterns ---")
for pattern in chinese_patterns:
    matches = list(re.finditer(pattern, full_text, re.IGNORECASE))
    if matches:
        print(f"\n✅ Pattern '{pattern}' - {len(matches)} matches")
        for m in matches[:3]:
            start = max(0, m.start() - 100)
            end = min(len(full_text), m.end() + 100)
            snippet = full_text[start:end].replace('\n', ' ')
            print(f"  ...{snippet}...")

# Look for revenue numbers and context
print("\n\n--- Revenue numbers and context ---")
revenue_pattern = r'(?:revenue|income|sales)\s*(?:for|in|of|from)?\s*(?:the\s+)?(?:year|period|three|six|nine)?\s*(?:ended|ending)?\s*(?:december|December|March|June|September)?'
matches = list(re.finditer(revenue_pattern, full_text, re.IGNORECASE))
print(f"Found {len(matches)} revenue-related matches")
for m in matches[:5]:
    start = max(0, m.start() - 50)
    end = min(len(full_text), m.end() + 150)
    snippet = full_text[start:end].replace('\n', ' ')
    print(f"  ...{snippet}...")
