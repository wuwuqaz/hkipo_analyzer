import re

text = '\n        本公司创始人王明先生持有公司35.2%的股份。\n        '
print(f'完整文本: {repr(text)}')

# 测试现有模式
pattern = r'创始人.{0,30}持有.{0,10}(\d+(?:\.\d+)?)\s*%'
for m in re.finditer(pattern, text):
    print(f'pattern match: {m.group(1)}, full: {m.group(0)}')

# 测试更精确的模式
pattern2 = r'创始人.*?持有.*?(\d+(?:\.\d+)?)%'
for m in re.finditer(pattern2, text, re.DOTALL):
    print(f'pattern2 match: {m.group(1)}, full: {m.group(0)}')

# 测试最简单的模式
pattern3 = r'(\d+(?:\.\d+)?)\s*%.*?股份'
for m in re.finditer(pattern3, text, re.DOTALL):
    print(f'pattern3 match: {m.group(1)}, full: {m.group(0)}')
