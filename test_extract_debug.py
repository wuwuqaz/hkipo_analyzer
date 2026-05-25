import re

text = """
扣非净利润为50百万元。
"""

# 测试完整正则
pattern = r'(?:扣非净利润|扣除非經常性損益後淨利潤|non[- ]GAAP\s+net\s+profit).{0,10}(-?[\d,]+(?:\.\d+)?)'
for m in re.finditer(pattern, text, re.IGNORECASE):
    print(f"完整正则匹配: '{m.group(0)}' -> 捕获: '{m.group(1)}'")

# 使用非贪婪版本
pattern2 = r'(?:扣非净利润|扣除非經常性損益後淨利潤|non[- ]GAAP\s+net\s+profit).*?(-?[\d,]+(?:\.\d+)?)'
for m in re.finditer(pattern2, text, re.IGNORECASE | re.DOTALL):
    print(f"非贪婪版本匹配: '{m.group(0)}' -> 捕获: '{m.group(1)}'")

# 更精确的版本
pattern3 = r'扣非净利润为(\d+(?:\.\d+)?)'
m3 = re.search(pattern3, text)
if m3:
    print(f"精确版本匹配: '{m3.group(0)}' -> 捕获: '{m3.group(1)}'")
