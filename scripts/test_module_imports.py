"""模块导入健康检查脚本。"""

import sys
import os

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 所有需要检查的模块
MODULES = [
    'ipo_analyzer',
    'ipo_analyzer.models',
    'ipo_analyzer.settings',
    'ipo_analyzer.parser',
    'ipo_analyzer.scoring',
    'ipo_analyzer.quality_analyzer',
    'ipo_analyzer.industry_router',
    'ipo_analyzer.core',
    'ipo_analyzer.history',
    'ipo_analyzer.market_heat',
    'ipo_analyzer.signal_analyzer',
    'ipo_analyzer.report',
    'ipo_analyzer.board_heat',
    'ipo_analyzer.float_dryness',
    'ipo_analyzer.post_listing',
    'ipo_analyzer.downloader',
    'ipo_analyzer.identity_validator',
    'ipo_analyzer.cache',
    'ipo_analyzer.utils',
    # 分析器
    'ipo_analyzer.analyzers._valuation',
    'ipo_analyzer.analyzers._business_breakdown',
    'ipo_analyzer.analyzers._geographic',
    'ipo_analyzer.analyzers._customer_supplier',
    'ipo_analyzer.analyzers._cashflow',
    'ipo_analyzer.analyzers._capacity',
    'ipo_analyzer.analyzers._rnd_pipeline',
    'ipo_analyzer.analyzers._risk_factors',
    'ipo_analyzer.analyzers._shareholder',
    'ipo_analyzer.analyzers._order_backlog',
    'ipo_analyzer.analyzers._piotroski_f',
    'ipo_analyzer.analyzers._dcf_valuation',
    'ipo_analyzer.analyzers._sector_analysis',
    'ipo_analyzer.analyzers._company_profile',
    'ipo_analyzer.analyzers._management_governance',
    'ipo_analyzer.analyzers._balance_sheet',
    'ipo_analyzer.analyzers._profit_sustainability',
    'ipo_analyzer.analyzers',
    # 回测框架
    'ipo_analyzer.backtest.engine',
    'ipo_analyzer.backtest.metrics',
    'ipo_analyzer.backtest.optimizer',
    'ipo_analyzer.backtest.store',
    'ipo_analyzer.backtest.collector',
    'ipo_analyzer.backtest.cli',
]

print("=" * 60)
print("模块导入健康检查")
print("=" * 60)

passed = 0
failed = 0
errors = []

for module_name in MODULES:
    try:
        __import__(module_name)
        print(f"✅ {module_name}")
        passed += 1
    except Exception as e:
        print(f"❌ {module_name}: {e}")
        failed += 1
        errors.append((module_name, str(e)))

print("=" * 60)
print(f"结果: {passed} 通过, {failed} 失败")
print("=" * 60)

if errors:
    print("\n错误详情:")
    for module, error in errors:
        print(f"  - {module}: {error}")

if failed > 0:
    sys.exit(1)
else:
    print("\n✅ 所有模块导入正常!")
