#!/usr/bin/env python3
"""
Debug script to check IPO data structure and identify why dropdown is empty
"""
import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from ui.renderers.data_formatter import DataFormatter

def check_cache_data():
    """Check the cache data structure"""
    temp_dir = Path(__file__).parent / "temp"
    cache_file = temp_dir / "results_cache.json"

    if not cache_file.exists():
        print(f"❌ Cache file not found: {cache_file}")
        return

    with open(cache_file, 'r', encoding='utf-8') as f:
        cached_data = json.load(f)

    print(f"✅ Found cache file with {len(cached_data)} IPOs\n")

    for i, ipo in enumerate(cached_data[:3]):  # Check first 3 IPOs
        print(f"\n=== IPO {i+1}: {ipo.get('hk_code', 'N/A')} - {ipo.get('company_name', 'N/A')} ===")

        # Check required fields for dropdown
        required_fields = {
            'hk_code': '股票代码',
            'company_name': '公司名称',
            'score': '总评分'
        }

        for field, label in required_fields.items():
            value = ipo.get(field)
            print(f"  {label}: {value} (type: {type(value).__name__})")

        # Check if ipo_summary_rows produces correct output
        rows = DataFormatter.ipo_summary_rows([ipo])
        if rows:
            row = rows[0]
            dropdown_value = f"{row['股票代码']} - {row['公司名称']} ({row['总评分']})"
            print(f"  Dropdown display: {dropdown_value}")
        else:
            print(f"  ❌ ipo_summary_rows returned empty list!")

        # Check for prospectus_info structure
        pi = ipo.get('prospectus_info', {})
        if not pi:
            print(f"  ⚠️ prospectus_info is empty or missing")

    # Check if all IPOs can generate rows
    print(f"\n=== Testing all {len(cached_data)} IPOs ===")
    all_rows = DataFormatter.ipo_summary_rows(cached_data)
    print(f"Generated {len(all_rows)} summary rows")

    # Check for any issues in rows generation
    for i, row in enumerate(all_rows):
        issues = []
        if not row.get('股票代码') or row['股票代码'] == '--':
            issues.append('股票代码为空')
        if not row.get('公司名称') or row['公司名称'] == '--':
            issues.append('公司名称为空')
        if not row.get('总评分'):
            issues.append('总评分为空')

        if issues:
            print(f"  ⚠️ Row {i+1}: {', '.join(issues)}")
        else:
            print(f"  ✅ Row {i+1}: OK")

    # Generate dropdown codes
    print(f"\n=== Dropdown codes ===")
    codes = [f"{r['股票代码']} - {r['公司名称']} ({r['总评分']})" for r in all_rows]
    if codes:
        for code in codes[:5]:  # Show first 5
            print(f"  {code}")
        if len(codes) > 5:
            print(f"  ... and {len(codes) - 5} more")
    else:
        print("  ❌ No codes generated!")

if __name__ == "__main__":
    check_cache_data()
