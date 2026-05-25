"""核心分析流程集成测试。"""

import sys
import os

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ipo_analyzer.parser import ProspectusParser
from ipo_analyzer.scoring import ScoringSystem
from ipo_analyzer.quality_analyzer import ProspectusQualityAnalyzer

print("=" * 60)
print("核心分析流程集成测试")
print("=" * 60)

# 测试1: 解析器实例化
try:
    parser = ProspectusParser()
    print("✅ 解析器实例化成功")
except Exception as e:
    print(f"❌ 解析器实例化失败: {e}")
    sys.exit(1)

# 测试2: 评分系统实例化
try:
    scoring = ScoringSystem()
    print("✅ 评分系统实例化成功")
except Exception as e:
    print(f"❌ 评分系统实例化失败: {e}")
    sys.exit(1)

# 测试3: 质地分析器实例化
try:
    quality = ProspectusQualityAnalyzer()
    print("✅ 质地分析器实例化成功")
except Exception as e:
    print(f"❌ 质地分析器实例化失败: {e}")
    sys.exit(1)

# 测试4: 模拟完整分析流程（无PDF，仅测试数据结构）
print("\n--- 模拟分析流程 ---")

try:
    # 模拟 prospectus_info 数据结构
    mock_prospectus_info = {
        'revenue': 500.0,
        'revenue_y1': 400.0,
        'net_profit': 50.0,
        'gross_margin': 45.0,
        'profitable': True,
        'industry': '半导体',
        'sector': 'technology',
        # 新增维度数据
        'management_governance': {
            'management_experience_years': 12.0,
            'founder_ownership_pct': 30.0,
            'independent_director_ratio': 0.40,
            'auditor_quality': '四大',
            'governance_risk_flags': [],
            'management_score': 80,
            'label': '优秀',
            'confidence': 'regex_context',
        },
        'balance_sheet': {
            'asset_liability_ratio': 0.45,
            'current_ratio': 2.5,
            'quick_ratio': 2.0,
            'interest_bearing_debt_ratio': 0.15,
            'interest_coverage_ratio': 10.0,
            'balance_sheet_score': 85,
            'label': '稳健',
            'risk_flags': [],
            'confidence': 'regex_context',
        },
        'profit_sustainability': {
            'net_profit': 50.0,
            'non_gaap_net_profit': 48.0,
            'non_recurring_ratio': 0.04,
            'government_subsidy': 2.0,
            'sustainability_score': 85,
            'label': '可持续',
            'quality_flags': [],
            'confidence': 'regex_context',
        },
    }

    # 测试质地分析
    quality_result = quality.analyze(mock_prospectus_info)
    print(f"✅ 质地分析成功: 分数={quality_result['score']}, 标签={quality_result['label']}")
    
    # 验证新维度出现在结果中
    if 'management_governance' in quality_result.get('dimensions', {}):
        print("  ✅ 管理层治理维度已集成")
    else:
        print("  ⚠️ 管理层治理维度未出现在结果中")
    
    if 'balance_sheet' in quality_result.get('dimensions', {}):
        print("  ✅ 资产负债维度已集成")
    else:
        print("  ⚠️ 资产负债维度未出现在结果中")
    
    if 'profit_sustainability' in quality_result.get('dimensions', {}):
        print("  ✅ 盈利可持续性维度已集成")
    else:
        print("  ⚠️ 盈利可持续性维度未出现在结果中")

    # 测试评分系统
    score_result = scoring.calculate(mock_prospectus_info)
    print(f"✅ 评分系统成功: 总分={score_result.get('total_score', 'N/A')}")
    
except Exception as e:
    print(f"❌ 分析流程测试失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("✅ 核心分析流程验证通过!")
print("=" * 60)
