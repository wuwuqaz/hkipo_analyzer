import sys
sys.path.insert(0, '.')
from ipo_analyzer.scoring import ScoringSystem
from ipo_analyzer.settings import SETTINGS
from ipo_analyzer.utils import _is_num

# 模拟乐动机器人的数据
ipo_data = {
    'over_sub_ratio': 5126.1563,
    'over_sub_ratio_source': 'missing',
    'actual_over_sub_ratio': 5126.1563,
}

prospectus_info = {}

# 测试 _is_num
print(f"_is_num(5126.1563): {_is_num(5126.1563)}")
print(f"_is_num('5126.1563'): {_is_num('5126.1563')}")

# 检查阈值
print(f"\n市场热度阈值:")
print(f"  extreme: {SETTINGS.market_heat.extreme}")
print(f"  hot: {SETTINGS.market_heat.hot}")
print(f"  warm: {SETTINGS.market_heat.warm}")

# 检查权重配置
ss = ScoringSystem()
weight_profile = ss._detect_weight_profile(ipo_data)
print(f"\n权重配置: {weight_profile}")

# 测试热度分数计算
print(f"\n超购倍数 {ipo_data['over_sub_ratio']} 应该落在哪个区间:")
print(f"  >= {SETTINGS.market_heat.extreme} (极热)? {ipo_data['over_sub_ratio'] >= SETTINGS.market_heat.extreme}")
print(f"  >= {SETTINGS.market_heat.hot} (热门)? {ipo_data['over_sub_ratio'] >= SETTINGS.market_heat.hot}")
print(f"  >= {SETTINGS.market_heat.warm} (温和)? {ipo_data['over_sub_ratio'] >= SETTINGS.market_heat.warm}")

# 模拟评分计算
components = {
    'heat': {'score': 0, 'label': '缺失', 'detail': ''},
    'scale': {'score': 0, 'label': '缺失', 'detail': ''},
    'market': {'score': 0, 'label': '缺失', 'detail': ''},
    'cornerstone': {'score': 0, 'label': '缺失', 'detail': ''},
}

over_sub = ipo_data.get('over_sub_ratio')
if _is_num(over_sub):
    mh = SETTINGS.market_heat
    if over_sub >= mh.extreme:
        components['heat']['score'] = SETTINGS.scoring.heat_max
        print(f"\n应该得到 heat_max = {SETTINGS.scoring.heat_max} 分")
    elif over_sub >= mh.hot:
        components['heat']['score'] = 35
        print(f"\n应该得到 35 分")
    elif over_sub >= mh.warm:
        components['heat']['score'] = 30
        print(f"\n应该得到 30 分")
    elif over_sub >= 5:
        components['heat']['score'] = 20
        print(f"\n应该得到 20 分")
    else:
        components['heat']['score'] = 10
        print(f"\n应该得到 10 分")

print(f"\n实际计算的 heat score: {components['heat']['score']}")

# 计算 subscription_score
subscription_raw = components['heat']['score'] + components['scale']['score'] + components['market']['score'] + components['cornerstone']['score']
subscription_raw_max = SETTINGS.scoring.heat_max + SETTINGS.scoring.scale_max + SETTINGS.scoring.market_max + SETTINGS.scoring.cornerstone_max
subscription_score = min(100, round(subscription_raw / subscription_raw_max * 100))

print(f"\nsubscription_raw = {subscription_raw}")
print(f"subscription_raw_max = {subscription_raw_max}")
print(f"subscription_score = {subscription_score}")
