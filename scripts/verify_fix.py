"""Verify the sector flow/momentum fix for 06872."""
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
print("Verify: 板块资金流/板块指数/板块动能 修复验证")
print("=" * 80)

from ipo_analyzer.market_heat import LiveMarketHeatAnalyzer

prospectus_info = {
    "sector": "healthcare",
    "peer_comparison": {
        "subsector": "ai_drug_delivery_nanomedicine"
    }
}

# Test LiveMarketHeatAnalyzer (should now have flow/momentum even without peers)
analyzer = LiveMarketHeatAnalyzer()
result = analyzer.analyze(prospectus_info, full_text)

print("\n--- live_market_heat 结果 ---")
for key in sorted(result.keys()):
    val = result[key]
    if val is not None and val != "":
        print(f"  {key}: {val}")

print("\n--- 关键指标验证 ---")
checks = [
    ("sector_board_label", result.get("sector_board_label"), "不应为缺失"),
    ("sector_board_heat_label", result.get("sector_board_heat_label"), "不应为缺失"),
    ("sector_board_flow_label", result.get("sector_board_flow_label"), "不应为缺失"),
    ("sector_flow_label", result.get("sector_flow_label"), "不应为缺失（新增）"),
    ("sector_flow_score", result.get("sector_flow_score"), "应 > 0（新增）"),
    ("sector_flow_detail", result.get("sector_flow_detail"), "不应为空（新增）"),
    ("sector_momentum_label", result.get("sector_momentum_label"), "不应为缺失（新增）"),
    ("sector_momentum_score", result.get("sector_momentum_score"), "应 > 0（新增）"),
    ("sector_momentum_detail", result.get("sector_momentum_detail"), "不应为空（新增）"),
]

all_pass = True
for name, value, expected in checks:
    status = "✅" if value and value != "缺失" and value != 0 and value != "" else "❌"
    if status == "❌":
        all_pass = False
    print(f"  {status} {name}: {value} ({expected})")

print(f"\n{'✅ 全部通过!' if all_pass else '❌ 仍有问题'}")
