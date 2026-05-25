"""Debug script to trace sector board and sector flow data for 06872."""
import sys
import json
sys.path.insert(0, '/Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer')

from pathlib import Path
import subprocess

# Extract text from the actual PDF
subprocess.run(
    ["pdftotext", "-layout", "storage/06872_prospectus.pdf", "/tmp/06872_extracted.txt"],
    capture_output=True
)
with open("/tmp/06872_extracted.txt", "r") as f:
    full_text = f.read()

print("=" * 80)
print("Debug: 板块指数和板块资金流数据链路 - 06872 丹诺医药-B")
print("=" * 80)

# Step 1: Check board_heat module
print("\n--- Step 1: BoardHeatAnalyzer ---")
try:
    from ipo_analyzer.board_heat import BoardHeatAnalyzer
    
    analyzer = BoardHeatAnalyzer()
    
    # Check akshare availability
    from ipo_analyzer.board_heat import ak
    print(f"akshare: {'✅ 可用' if ak is not None else '❌ 不可用'}")
    
    # Load board data
    concept_df = analyzer._load_board_df("concept")
    industry_df = analyzer._load_board_df("industry")
    
    print(f"概念板块: {'✅' if concept_df is not None and not concept_df.empty else '❌'}")
    print(f"行业板块: {'✅' if industry_df is not None and not industry_df.empty else '❌'}")
    
    # Simulate analysis for healthcare company
    prospectus_info = {
        "sector": "healthcare",
        "peer_comparison": {
            "subsector": "ai_drug_delivery_nanomedicine"
        }
    }
    
    result = analyzer.analyze(prospectus_info, full_text)
    
    print(f"\n板块指数结果:")
    print(f"  sector_board_label: {result.get('sector_board_label')}")
    print(f"  sector_board_heat_label: {result.get('sector_board_heat_label')}")
    print(f"  sector_board_flow_label: {result.get('sector_board_flow_label')}")
    print(f"  sector_board_detail: {result.get('sector_board_detail')}")
    print(f"  sector_board_source: {result.get('sector_board_source')}")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

# Step 2: Check market_heat module
print("\n--- Step 2: MarketHeatSnapshot ---")
try:
    from ipo_analyzer.market_heat import MarketHeatSnapshot
    
    # Create a snapshot with board data
    snapshot = MarketHeatSnapshot(
        sector_board_label="创新药",
        sector_board_heat_label="温和",
        sector_board_flow_label="活跃",
        sector_board_detail="创新药 · 涨跌-0.56% · 成交额378.9亿 · 100家公司",
        sector_board_source="sina_sector_spot",
        sector_board_confidence="matched",
        sector_flow_label="活跃",
        sector_flow_score=3,
        sector_flow_detail="板块资金流活跃",
        sector_momentum_label="上行",
        sector_momentum_score=4,
        sector_momentum_detail="板块动能上行",
        sector_heat_label="热门",
        sector_heat_score=10,
        sector_heat_detail="板块热门",
    )
    
    data = snapshot.to_dict()
    
    print(f"MarketHeatSnapshot 输出字段:")
    for key in ['sector_flow_label', 'sector_flow_score', 'sector_flow_detail',
                'sector_momentum_label', 'sector_momentum_score', 'sector_momentum_detail',
                'sector_board_label', 'sector_board_heat_label', 'sector_board_flow_label',
                'sector_board_detail']:
        print(f"  {key}: {data.get(key)}")
        
except Exception as e:
    print(f" Error: {e}")
    import traceback
    traceback.print_exc()

# Step 3: Check signal_analyzer
print("\n--- Step 3: SignalAnalyzer - sector_board 和 sector_flow ---")
try:
    from ipo_analyzer.signal_analyzer import SignalAnalyzer
    
    # Create a mock IPO result with live_market_heat data
    mock_ipo = {
        "sector": "healthcare",
        "margin_total": 10.0,
        "public_offer": 1.0,
        "company_name": "丹诺医药-B",
        "stock_code": "06872",
        "live_market_heat": {
            "sector_board_label": "创新药",
            "sector_board_heat_label": "温和",
            "sector_board_flow_label": "活跃",
            "sector_board_detail": "创新药 · 涨跌-0.56% · 成交额378.9亿 · 100家公司",
            "sector_flow_label": "活跃",
            "sector_flow_score": 3,
            "sector_flow_detail": "板块资金流活跃",
            "sector_momentum_label": "上行",
            "sector_momentum_score": 4,
            "sector_momentum_detail": "板块动能上行",
            "sector_heat_label": "热门",
            "sector_heat_score": 10,
            "sector_heat_detail": "板块热门",
        },
        "peer_comparison": {"subsector": "ai_drug_delivery_nanomedicine"}
    }
    
    analyzer = SignalAnalyzer()
    result = analyzer.analyze(mock_ipo, full_text)
    
    signal_breakdown = result.get('signal_breakdown', {})
    print(f"signal_breakdown 包含的 keys: {list(signal_breakdown.keys())}")
    
    # Check sector_flow
    sector_flow = signal_breakdown.get('sector_flow', {})
    print(f"\nsector_flow:")
    print(f"  label: {sector_flow.get('label')}")
    print(f"  strength: {sector_flow.get('strength')}")
    print(f"  detail: {sector_flow.get('detail')}")
    print(f"  score: {sector_flow.get('score')}")
    
    # Check sector_momentum
    sector_momentum = signal_breakdown.get('sector_momentum', {})
    print(f"\nsector_momentum:")
    print(f"  label: {sector_momentum.get('label')}")
    print(f"  strength: {sector_momentum.get('strength')}")
    print(f"  detail: {sector_momentum.get('detail')}")
    print(f"  score: {sector_momentum.get('score')}")
    
    # Check sector_board
    sector_board = signal_breakdown.get('sector_board', {})
    print(f"\nsector_board:")
    print(f"  label: {sector_board.get('label')}")
    print(f"  strength: {sector_board.get('strength')}")
    print(f"  detail: {sector_board.get('detail')}")
    print(f"  score: {sector_board.get('score')}")
    
    # Check market_heat
    market_heat = signal_breakdown.get('market_heat', {})
    print(f"\nmarket_heat:")
    print(f"  label: {market_heat.get('label')}")
    print(f"  strength: {market_heat.get('strength')}")
    print(f"  detail: {market_heat.get('detail')}")
    print(f"  score: {market_heat.get('score')}")
    
    # Check the complete live_market_heat
    print(f"\nlive_market_heat:")
    live_heat = result.get('live_market_heat', {})
    for key in ['sector_flow_label', 'sector_flow_score', 'sector_flow_detail',
                'sector_momentum_label', 'sector_momentum_score', 'sector_momentum_detail',
                'sector_board_label', 'sector_board_heat_label', 'sector_board_flow_label',
                'sector_board_detail', 'sector_heat_label', 'sector_heat_score', 'sector_heat_detail']:
        print(f"  {key}: {live_heat.get(key)}")
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

# Step 4: Check the frontend data format expectation
print("\n--- Step 4: 前端期望的数据格式 ---")
print("""
前端 SignalBreakdown 组件期望的数据格式:
  result.signal_breakdown.sector_flow:
    - strength: "—" (当没有数据时)
    - detail: "—" (当没有数据时)
  
  result.signal_breakdown.sector_board:
    - strength: "—" (当没有数据时)
    - detail: "—" (当没有数据时)

当前问题: 这两个字段都显示 "--"，说明前端没有接收到正确的数据。
""")
