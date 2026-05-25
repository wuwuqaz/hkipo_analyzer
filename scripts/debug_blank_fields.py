"""Debug script to trace why depth analysis fields are blank for 06872."""
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
print("Debug: 深度分析空白字段追踪 - 06872 丹诺医药-B")
print("=" * 80)

from ipo_analyzer.core import IPOAnalyzer

analyzer = IPOAnalyzer()
result = analyzer.analyze(full_text, "06872", "丹诺医药-B")

pi = result.get("prospectus_info", {})

# Categorize blank fields
print("\n--- 1. 客户/供应商数据 ---")
cs = pi.get("customer_supplier", {})
blank_cs = [k for k, v in cs.items() if v is None or v == ""]
print(f"  空白字段: {blank_cs}")
print(f"  有值字段: {[k for k, v in cs.items() if v is not None and v != '']}")

print("\n--- 2. 现金流数据 ---")
cf = pi.get("cashflow", {})
print(f"  cash_balance_million: {cf.get('cash_balance_million')}")
print(f"  monthly_cash_burn_million: {cf.get('monthly_cash_burn_million')}")
print(f"  post_ipo_cash_runway_years: {cf.get('post_ipo_cash_runway_years')}")
print(f"  inventory_million: {cf.get('inventory_million')}")
print(f"  receivables_million: {cf.get('receivables_million')}")
print(f"  ocf_revenue_ratio: {cf.get('ocf_revenue_ratio')}")

print("\n--- 3. R&D/Pipeline 数据 ---")
rnd = pi.get("rnd_pipeline", {})
print(f"  pipeline_quality_label: {rnd.get('pipeline_quality_label')}")
print(f"  technology_moat_score: {rnd.get('technology_moat_score')}")
print(f"  hardtech_moat_label: {rnd.get('hardtech_moat_label')}")
print(f"  hardtech_moat_score: {rnd.get('hardtech_moat_score')}")
print(f"  patent_count: {rnd.get('patent_count')}")
print(f"  rd_staff_count: {rnd.get('rd_staff_count')}")
print(f"  rd_staff_ratio: {rnd.get('rd_staff_ratio')}")
print(f"  backlog_amount: {rnd.get('backlog_amount')}")
print(f"  industry_rank: {rnd.get('industry_rank')}")

print("\n--- 4. 估值数据 ---")
val = pi.get("valuation", {})
print(f"  market_cap_to_rd_ratio: {val.get('market_cap_to_rd_ratio')}")
print(f"  ipo_valuation_premium_pct: {val.get('ipo_valuation_premium_pct')}")
print(f"  cash_runway_years: {val.get('cash_runway_years')}")
print(f"  valuation_framework_label: {val.get('valuation_framework_label')}")
print(f"  latest_clinical_stage: {val.get('latest_clinical_stage')}")

print("\n--- 5. 业务分部 ---")
bb = pi.get("business_breakdown", {})
print(f"  segments: {len(bb.get('segments', []))}")
print(f"  business_model_label: {bb.get('business_model_label')}")
print(f"  growth_source: {bb.get('growth_source')}")
print(f"  business_breakdown_warning: {bb.get('business_breakdown_warning')}")

print("\n--- 6. 风险数据 ---")
risk = pi.get("risk_analysis", {})
print(f"  total_penalty: {risk.get('total_penalty')}")

# Check capacity analyzer
print("\n--- 7. 产能数据 ---")
cap = pi.get("capacity", {})
print(f"  utilization_rate: {cap.get('utilization_rate')}")

print("\n\n=== 分析结论 ===")
print("""
空白字段分类:
1. Bug: post_ipo_cash_runway_years 显示 "null年" (Python None -> JS null)
2. 正常空白 (Pre-revenue biotech 特征):
   - 客户留存率/NDR/Top5客户/最大客户: 无商业化收入，自然无客户数据
   - 库存/应收/在手订单/产能利用率: 无量产产品
   - IPO溢价: 尚未上市
   - 市值/R&D: 公式计算可能缺失
3. 数据提取问题:
   - 研发团队人数: 招股书可能有比例但无绝对值
   - 硬科技护城河: biotech 不适用硬科技评分体系
""")
