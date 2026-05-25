"""Debug script to trace why depth analysis fields are blank for 06872."""
import sys
sys.path.insert(0, '/Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer')

import subprocess
import json
subprocess.run(
    ["pdftotext", "-layout", "storage/06872_prospectus.pdf", "/tmp/06872_extracted.txt"],
    capture_output=True
)
with open("/tmp/06872_extracted.txt", "r") as f:
    full_text = f.read()

print("=" * 80)
print("Debug: 深度分析空白字段追踪")
print("=" * 80)

from ipo_analyzer.core import IPOAnalyzer

analyzer = IPOAnalyzer()
result = analyzer.analyze(full_text, "06872", "丹诺医药-B")

# Get prospectus_info
pi = result.get("prospectus_info", {})

# Check the blank fields one by one
print("\n--- 1. 客户集中度 ---")
cs = pi.get("customer_supplier", {})
print(f"  customer_concentration_label: {cs.get('customer_concentration_label')}")
print(f"  top_customer_ratio_pct: {cs.get('top_customer_ratio_pct')}")
print(f"  top5_customer_ratio_pct: {cs.get('top5_customer_ratio_pct')}")

print("\n--- 2. 客户质量 ---")
print(f"  customer_quality_label: {cs.get('customer_quality_label')}")
print(f"  customer_quality_score: {cs.get('customer_quality_score')}")

print("\n--- 3. 客户留存率 ---")
print(f"  customer_retention_label: {cs.get('customer_retention_label')}")
print(f"  ndr_label: {cs.get('ndr_label')}")

print("\n--- 4. 现金流 ---")
cf = pi.get("cashflow", {})
print(f"  operating_cashflow_latest: {cf.get('operating_cashflow_latest')}")
print(f"  net_income_latest: {cf.get('net_income_latest')}")
print(f"  revenue_latest: {cf.get('revenue_latest')}")
print(f"  ocf_revenue_ratio: {cf.get('ocf_revenue_ratio')}")
print(f"  cash_balance_million: {cf.get('cash_balance_million')}")
print(f"  monthly_cash_burn_million: {cf.get('monthly_cash_burn_million')}")
print(f"  post_ipo_cash_runway_years: {cf.get('post_ipo_cash_runway_years')}")
print(f"  pre_ipo_cash_runway_years: {cf.get('pre_ipo_cash_runway_years')}")

print("\n--- 5. 库存/应收 ---")
print(f"  inventory_million: {cf.get('inventory_million')}")
print(f"  receivables_million: {cf.get('receivables_million')}")

print("\n--- 6. R&D / Pipeline ---")
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

print("\n--- 7. 估值 ---")
val = pi.get("valuation", {})
print(f"  market_cap_to_rd_ratio: {val.get('market_cap_to_rd_ratio')}")
print(f"  ipo_valuation_premium_pct: {val.get('ipo_valuation_premium_pct')}")
print(f"  cash_runway_years: {val.get('cash_runway_years')}")
print(f"  valuation_framework_label: {val.get('valuation_framework_label')}")

print("\n--- 8. 风险 ---")
risk = pi.get("risk_analysis", {})
print(f"  total_penalty: {risk.get('total_penalty')}")

# Now let's check what the frontend expects
print("\n\n--- 前端期望字段映射 ---")
frontend_fields = [
    ("客户集中度", "customer_concentration_label"),
    ("客户质量", "customer_quality_label", "customer_quality_score"),
    ("客户留存率", "customer_retention_label"),
    ("NDR", "ndr_label"),
    ("Top5客户占比", "top5_customer_ratio_pct"),
    ("最大客户占比", "top_customer_ratio_pct"),
    ("现金流质量", "cashflow_quality_label"),
    ("营运资本趋势", "working_capital_trend_label"),
    ("营运资本压力", "working_capital_pressure_label"),
    ("OCF/收入", "ocf_revenue_ratio"),
    ("现金余额", "cash_balance_million"),
    ("月耗现金", "monthly_cash_burn_million"),
    ("库存金额", "inventory_million"),
    ("应收金额", "receivables_million"),
    ("募资后runway", "post_ipo_cash_runway_years"),
    ("技术壁垒", "pipeline_quality_label", "technology_moat_score"),
    ("硬科技护城河", "hardtech_moat_label", "hardtech_moat_score"),
    ("专利/软著", "patent_count", "software_copyright_count"),
    ("研发团队", "rd_staff_count", "rd_staff_ratio"),
    ("在手订单", "backlog_amount"),
    ("行业排名", "industry_rank"),
    ("产能利用率", "utilization_rate"),
    ("招股书风险因子", "total_penalty"),
    ("估值框架", "valuation_framework_label"),
    ("市值/R&D", "market_cap_to_rd_ratio"),
    ("IPO溢价", "ipo_valuation_premium_pct"),
    ("现金runway", "cash_runway_years"),
    ("临床阶段", "latest_clinical_stage"),
]

for field_tuple in frontend_fields:
    name = field_tuple[0]
    keys = field_tuple[1:]
    values = []
    for key in keys:
        # Search in all sub-dicts
        found = None
        for subdict_name in ["customer_supplier", "cashflow", "rnd_pipeline", "valuation", "risk_analysis", "business_breakdown"]:
            subdict = pi.get(subdict_name, {})
            if key in subdict:
                found = subdict[key]
                break
        if found is not None:
            values.append(f"{key}={found}")
        else:
            values.append(f"{key}=None")
    print(f"  {name}: {'; '.join(values)}")
