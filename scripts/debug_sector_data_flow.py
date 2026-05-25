"""Debug script to trace sector_board and sector_flow data flow for 06872."""
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
print("Debug: 板块指数/板块资金流数据链路")
print("=" * 80)

# Step 1: Check BoardHeatAnalyzer output
print("\n--- Step 1: BoardHeatAnalyzer ---")
from ipo_analyzer.board_heat import BoardHeatAnalyzer

analyzer = BoardHeatAnalyzer()
prospectus_info = {
    "sector": "healthcare",
    "peer_comparison": {
        "subsector": "ai_drug_delivery_nanomedicine"
    }
}

board_result = analyzer.analyze(prospectus_info, full_text)
print(f"sector_board_label: {board_result.get('sector_board_label')}")
print(f"sector_board_heat_label: {board_result.get('sector_board_heat_label')}")
print(f"sector_board_flow_label: {board_result.get('sector_board_flow_label')}")
print(f"sector_board_detail: {board_result.get('sector_board_detail')}")
print(f"sector_flow_label: {board_result.get('sector_flow_label')}")
print(f"sector_flow_score: {board_result.get('sector_flow_score')}")
print(f"sector_flow_detail: {board_result.get('sector_flow_detail')}")
print(f"sector_momentum_label: {board_result.get('sector_momentum_label')}")
print(f"sector_momentum_score: {board_result.get('sector_momentum_score')}")
print(f"sector_momentum_detail: {board_result.get('sector_momentum_detail')}")

# Step 2: Check what live_market_heat would look like
print("\n--- Step 2: Simulated live_market_heat ---")
live_market_heat = {
    k: v for k, v in board_result.items()
    if k.startswith('sector_') or k in ['market_heat_source', 'market_heat_date']
}
print(f"live_market_heat keys: {list(live_market_heat.keys())}")
for k, v in live_market_heat.items():
    print(f"  {k}: {v}")

# Step 3: Check SignalAnalyzer with this data
print("\n--- Step 3: SignalAnalyzer ---")
from ipo_analyzer.signal_analyzer import SignalAnalyzer

mock_ipo_data = {
    "sector": "healthcare",
    "margin_total": 10.0,
    "public_offer": 1.0,
    "company_name": "丹诺医药-B",
    "stock_code": "06872",
    "live_market_heat": live_market_heat,
    "peer_comparison": {"subsector": "ai_drug_delivery_nanomedicine"}
}

signal_analyzer = SignalAnalyzer()
signal_result = signal_analyzer.analyze(mock_ipo_data, full_text)

signal_breakdown = signal_result.get('signal_breakdown', {})
print(f"signal_breakdown keys: {list(signal_breakdown.keys())}")

for key in ['sector_flow', 'sector_board', 'sector_momentum', 'market_heat']:
    item = signal_breakdown.get(key, {})
    print(f"\n{key}:")
    print(f"  strength: {item.get('strength')}")
    print(f"  detail: {item.get('detail')}")
    print(f"  label: {item.get('label')}")
    print(f"  score: {item.get('score')}")
