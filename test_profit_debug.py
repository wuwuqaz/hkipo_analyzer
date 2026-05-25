from ipo_analyzer.analyzers._profit_sustainability import ProfitSustainabilityAnalyzer

# 测试 sustainable_profit_score
text = """
扣非净利润为50百万元。
"""
prospectus_info = {'net_profit': 52.0, '_extracted_text': text}
result = ProfitSustainabilityAnalyzer().analyze(prospectus_info, text)
print(f"sustainable_profit_score: {result['sustainability_score']}")
print(f"  net_profit={result['net_profit']}")
print(f"  non_gaap_net_profit={result['non_gaap_net_profit']}")
print(f"  non_recurring_ratio={result['non_recurring_ratio']}")
print(f"  label={result['label']}")

# 测试 profit_quality_flag_opposite_direction
text2 = """
扣非净利润为-10百万元。
"""
prospectus_info2 = {'net_profit': 20.0, '_extracted_text': text2}
result2 = ProfitSustainabilityAnalyzer().analyze(prospectus_info2, text2)
print(f"\nprofit_quality_flag: {result2['sustainability_score']}")
print(f"  net_profit={result2['net_profit']}")
print(f"  non_gaap_net_profit={result2['non_gaap_net_profit']}")
print(f"  quality_flags={result2['quality_flags']}")
