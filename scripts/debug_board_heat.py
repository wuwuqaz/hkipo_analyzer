"""Debug script to trace the sector board and sector flow data."""
import sys
sys.path.insert(0, '/Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer')

from ipo_analyzer.board_heat import BoardHeatAnalyzer

print("=" * 80)
print("Debug: 板块指数和板块资金流数据链路")
print("=" * 80)

# Test case 1: Check if akshare is available
print("\n--- 检查 akshare ---")
try:
    import akshare as ak
    print("✅ akshare 已安装")
except ImportError:
    print("❌ akshare 未安装 - 这是板块数据缺失的主要原因！")

# Test case 2: Try to load board data
print("\n--- 尝试加载板块数据 ---")
analyzer = BoardHeatAnalyzer()

concept_df = analyzer._load_board_df("concept")
industry_df = analyzer._load_board_df("industry")

print(f"概念板块数据: {'✅ 已加载' if concept_df is not None and not concept_df.empty else '❌ 加载失败'}")
print(f"行业板块数据: {'✅ 已加载' if industry_df is not None and not industry_df.empty else '❌ 加载失败'}")

if concept_df is not None and not concept_df.empty:
    print(f"概念板块数量: {len(concept_df)}")
    print(f"列名: {list(concept_df.columns)}")

if industry_df is not None and not industry_df.empty:
    print(f"行业板块数量: {len(industry_df)}")

# Test case 3: Simulate the full analysis for a healthcare company
print("\n--- 模拟 healthcare 公司分析 ---")
prospectus_info = {
    "sector": "healthcare",
    "peer_comparison": {
        "subsector": "ai_drug_delivery_nanomedicine"
    }
}

text = "TenNor Therapeutics (Suzhou) Limited 丹諾醫藥(蘇州)股份有限公司 innovative drug biotech clinical trial"

result = analyzer.analyze(prospectus_info, text)
print(f"板块标签: {result.get('sector_board_label')}")
print(f"板块类型: {result.get('sector_board_type')}")
print(f"涨跌幅: {result.get('sector_board_change_pct')}")
print(f"成交额: {result.get('sector_board_turnover')}")
print(f"公司家数: {result.get('sector_board_company_count')}")
print(f"热度标签: {result.get('sector_board_heat_label')}")
print(f"资金流标签: {result.get('sector_board_flow_label')}")
print(f"详情: {result.get('sector_board_detail')}")
print(f"来源: {result.get('sector_board_source')}")
print(f"置信度: {result.get('sector_board_confidence')}")
