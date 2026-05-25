import re

# Test 1: Management experience
text1 = '张先生拥有15年半导体行业经验。'
pattern1 = r'(?:拥有|具有|具备).{0,5}(\d+(?:\.\d+)?)\s*年.{0,20}(?:行业|领域|从业|经验)'
m = re.search(pattern1, text1)
print(f'管理经验: pattern1 match={m.group(1) if m else None}')

# Test 2: Founder ownership
text2 = '本公司创始人王明先生持有公司35.2%的股份。'
pattern2 = r'(?:创始人|控股股东|实际控制人).{0,50}(?:持有|持股|拥有).{0,10}(\d+(?:\.\d+)?)\s*%'
m2 = re.search(pattern2, text2)
print(f'创始人持股: pattern2 match={m2.group(1) if m2 else None}')

# Test 3: Asset liability ratio
text3 = '截至2023年12月31日，本公司资产负债率为55.2%。'
pattern3 = r'(?:资产负债率).{0,3}(?:为|=|:|\s)*(\d+(?:\.\d+)?)\s*%'
m3 = re.search(pattern3, text3)
print(f'资产负债率: pattern3 match={m3.group(1) if m3 else None}')

# Test 4: Current ratio
text4 = '流动比率：2.1'
pattern4 = r'(?:流动比率).{0,3}(?:为|=|:|：|\s)*(\d+(?:\.\d+)?)'
m4 = re.search(pattern4, text4)
print(f'流动比率: pattern4 match={m4.group(1) if m4 else None}')

# Test 5: Government subsidy
text5 = '本公司收到政府补助人民币15.5百万元。'
pattern5 = r'(?:政府补助|政府补贴).{0,10}(?:人民币)?\s*([\d,]+(?:\.\d+)?)'
m5 = re.search(pattern5, text5)
print(f'政府补贴: pattern5 match={m5.group(1) if m5 else None}')
