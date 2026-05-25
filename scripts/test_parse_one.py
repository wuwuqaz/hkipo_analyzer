import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ipo_analyzer.parser import ProspectusParser
from ipo_analyzer.text_extractor import extract_pdf_text
from ipo_analyzer.analyzers import RnDPipelineAnalyzer, GeographicExpansionAnalyzer, BusinessBreakdownAnalyzer

base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
temp_dir = os.path.join(base_dir, 'temp')

parser = ProspectusParser(cache_dir=temp_dir)
info = parser.parse("01236", "乐动机器人")

assertion_failures = []

def assert_approx(name, actual, expected, tolerance=0.05):
    if actual is None:
        assertion_failures.append(f"FAIL: {name} is None (expected ~{expected})")
        print(f"  ❌ {name}: None (expected ~{expected})")
        return
    diff = abs(actual - expected) / max(abs(expected), 1e-9)
    if diff > tolerance:
        assertion_failures.append(f"FAIL: {name} = {actual} (expected ~{expected}, diff={diff:.2%})")
        print(f"  ❌ {name}: {actual} (expected ~{expected}, diff={diff:.2%})")
    else:
        print(f"  ✅ {name}: {actual} (expected ~{expected})")

def assert_in(name, actual, valid_values):
    if actual not in valid_values:
        assertion_failures.append(f"FAIL: {name} = {actual} (expected one of {valid_values})")
        print(f"  ❌ {name}: {actual} (expected one of {valid_values})")
    else:
        print(f"  ✅ {name}: {actual}")

def assert_contains(name, actual_list, expected_item):
    if expected_item not in actual_list:
        assertion_failures.append(f"FAIL: {name} does not contain '{expected_item}' (got {actual_list})")
        print(f"  ❌ {name}: does not contain '{expected_item}' (got {actual_list})")
    else:
        print(f"  ✅ {name}: contains '{expected_item}'")

print("=" * 60)
print("1. 基础解析")
print("=" * 60)
print(f"parse_success: {info.get('parse_success')}")
print(f"parse_error: {info.get('parse_error')}")
print(f"pdf_text_length: {info.get('pdf_text_length')}")
print(f"pdf_stock_code_match: {info.get('pdf_stock_code_match')}")
print(f"pdf_name_match: {info.get('pdf_name_match')}")
print(f"pdf_identity_confidence: {info.get('pdf_identity_confidence')}")
print(f"extracted_company_name: {info.get('extracted_company_name')}")
print(f"extracted_english_name: {info.get('extracted_english_name')}")
print(f"financial_extract_confidence: {info.get('financial_extract_confidence')}")
print(f"pdf_validation_warning: {info.get('pdf_validation_warning')}")

assert_in("pdf_identity_confidence", info.get('pdf_identity_confidence'), ['high', 'medium'])

print()
print("=" * 60)
print("2. 核心财务字段")
print("=" * 60)
print(f"revenue: {info.get('revenue')}")
print(f"net_profit: {info.get('net_profit')}")
print(f"gross_margin: {info.get('gross_margin')}")
print(f"rd_expense: {info.get('rd_expense')}")

assert_approx("revenue", info.get('revenue'), 747.773, tolerance=0.1)
assert_approx("net_profit", info.get('net_profit'), -62.501, tolerance=0.1)
assert_approx("gross_margin", info.get('gross_margin'), 25.7, tolerance=0.05)

print()
print("=" * 60)
print("3. 研发费率")
print("=" * 60)
rnd = RnDPipelineAnalyzer().analyze(info, info.get('_extracted_text', ''))
print(f"rd_expense_latest: {rnd.get('rd_expense_latest')}")
print(f"rd_expense_ratio: {rnd.get('rd_expense_ratio')}")
print(f"rd_ratio_warning: {rnd.get('rd_ratio_warning')}")
print(f"confidence: {rnd.get('confidence')}")

assert_approx("rd_expense_ratio", rnd.get('rd_expense_ratio'), 16.2, tolerance=0.1)

print()
print("=" * 60)
print("4. 海外收入")
print("=" * 60)
pdf_path = os.path.join(temp_dir, "01236_prospectus.pdf")
if os.path.exists(pdf_path):
    text = extract_pdf_text(pdf_path)
else:
    text = info.get('_extracted_text', '')
geo = GeographicExpansionAnalyzer().analyze(info, text)
print(f"china_revenue_latest: {geo.get('china_revenue_latest')}")
print(f"overseas_revenue_latest: {geo.get('overseas_revenue_latest')}")
print(f"overseas_revenue_pct: {geo.get('overseas_revenue_pct')}")
print(f"overseas_growth_pct: {geo.get('overseas_growth_pct')}")
print(f"overseas_growth_label: {geo.get('overseas_growth_label')}")
print(f"geographic_confidence: {geo.get('geographic_confidence')}")

assert_approx("overseas_revenue_pct", geo.get('overseas_revenue_pct'), 18.4, tolerance=0.1)

print()
print("=" * 60)
print("5. 业务增长来源")
print("=" * 60)
biz = BusinessBreakdownAnalyzer().analyze(info, text)
print(f"growth_source: {biz.get('growth_source')}")
print(f"main_segment: {biz.get('main_segment')}")
print(f"fastest_growing_segment: {biz.get('fastest_growing_segment')}")
print(f"segments: {[s.get('name') for s in biz.get('segments', [])]}")
print(f"business_breakdown_confidence: {biz.get('business_breakdown_confidence')}")
print(f"business_breakdown_warning: {biz.get('business_breakdown_warning')}")

seg_names = [s.get('name') for s in biz.get('segments', [])]
assert_contains("segments contains Visual Perception Products", seg_names, "Visual Perception Products")
assert_contains("segments contains Robot lawn mowers", seg_names, "Robot lawn mowers")
assert_contains("segments contains Others", seg_names, "Others")

for seg in biz.get('segments', []):
    if seg.get('name') == 'Robot lawn mowers':
        assert_approx("Robot lawn mowers share_pct", seg.get('share_pct'), 18.3, tolerance=0.05)
        break

print()
print("=" * 60)
print("6. VBP/DRG/DIP 风险检查")
print("=" * 60)
print(f"sector: {info.get('sector')}")
print(f"vbp_risk_score: {biz.get('vbp_risk_score')}")
print(f"vbp_summary: {biz.get('vbp_summary')}")

if info.get('sector') not in ('healthcare', 'medical', 'biotech', 'pharmaceutical'):
    if biz.get('vbp_risk_score', 0) > 0:
        assertion_failures.append(f"FAIL: Non-healthcare sector should not have VBP risk, but score={biz.get('vbp_risk_score')}")
        print(f"  ❌ VBP风险误判: 非医疗行业不应有VBP风险 (score={biz.get('vbp_risk_score')})")
    else:
        print("  ✅ 非医疗行业无VBP/DRG/DIP风险")

print()
print("=" * 60)
print("7. 断言汇总")
print("=" * 60)
if assertion_failures:
    print(f"\n❌ {len(assertion_failures)} 个断言失败:")
    for f in assertion_failures:
        print(f"  {f}")
    sys.exit(1)
else:
    print("\n✅ 所有断言通过！")
