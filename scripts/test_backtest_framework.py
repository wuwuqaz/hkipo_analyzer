"""回测框架健康检查。"""

import sys
import os
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("=" * 60)
print("回测框架健康检查")
print("=" * 60)

# 测试1: 导入回测模块
try:
    from ipo_analyzer.backtest.engine import run_backtest
    from ipo_analyzer.backtest.metrics import compute_objective, compute_objective_cv
    from ipo_analyzer.backtest.optimizer import optimize_weights
    from ipo_analyzer.backtest.store import BacktestStore
    print("✅ 回测模块导入成功")
except Exception as e:
    print(f"❌ 回测模块导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 测试2: 简单回测验证
try:
    # 创建模拟数据集（使用简单对象）
    @dataclass
    class MockIPORecord:
        hk_code: str
        trade_score: float
        fundamental_score: float
        valuation_score: float
        theme_score: float
        data_quality_score: float
        first_day_return: float
        list_date: str
        is_break: bool = False
    
    mock_dataset = [
        MockIPORecord('00001', 80, 75, 70, 65, 60, 15.0, '2023-01-01'),
        MockIPORecord('00002', 60, 55, 50, 45, 40, -5.0, '2023-02-01'),
        MockIPORecord('00003', 90, 85, 80, 75, 70, 25.0, '2023-03-01'),
        MockIPORecord('00004', 50, 45, 40, 35, 30, -10.0, '2023-04-01'),
        MockIPORecord('00005', 70, 65, 60, 55, 50, 8.0, '2023-05-01'),
    ]
    
    weights = {
        'trade': 0.30,
        'fundamental': 0.25,
        'valuation': 0.20,
        'theme': 0.15,
        'data_quality': 0.10,
    }
    
    result = run_backtest(mock_dataset, weights, qualify_threshold=60)
    print(f"✅ 回测引擎运行成功")
    print(f"   - 合格样本数: {result.qualified_count}")
    print(f"   - 胜率: {result.win_rate:.2%}")
    print(f"   - 期望收益: {result.expected_return:.2%}")
    
    # 测试目标函数计算
    obj = compute_objective(result)
    print(f"✅ 目标函数计算成功: {obj:.4f}")
    
    # 测试交叉验证
    obj_cv = compute_objective_cv(mock_dataset, weights, k=3)
    print(f"✅ 交叉验证成功: {obj_cv:.4f}")
    
except Exception as e:
    print(f"❌ 回测引擎测试失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("✅ 回测框架验证通过!")
print("=" * 60)
