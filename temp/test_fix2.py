import sys
sys.path.insert(0, '.')
from ipo_analyzer.core import reanalyze_with_historical_heat
import json

# 读取当前数据
with open('temp/ipo_history.json', 'r') as f:
    data = json.load(f)
    for item in data:
        if item.get('hk_code') == '01236':
            print('=== 当前乐动机器人数据 ===')
            print(f'over_sub_ratio: {item.get("over_sub_ratio")}')
            print(f'over_sub_ratio_source: {item.get("over_sub_ratio_source")}')
            print(f'actual_over_sub_ratio: {item.get("actual_over_sub_ratio")}')
            print(f'subscription_score: {item.get("subscription_score")}')
            break

# 执行重新分析
result = reanalyze_with_historical_heat(
    stock_code='01236',
    company_name='乐动机器人',
    historical_market_data=None,
    prospectus_info={'actual_over_sub_ratio': 5126.1563}
)

print()
print('=== 重新分析结果 ===')
print(f'status: {result.get("status")}')
if result.get('result'):
    r = result['result']
    print(f'over_sub_ratio: {r.get("over_sub_ratio")}')
    print(f'over_sub_ratio_source: {r.get("over_sub_ratio_source")}')
    print(f'subscription_score: {r.get("subscription_score")}')
