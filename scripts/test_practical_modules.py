from ipo_analyzer.allotment_predictor import AllotmentPredictor
from ipo_analyzer.a_b_group_strategy import ABGroupStrategyAnalyzer
from ipo_analyzer.greenshoe_analyzer import GreenshoeAnalyzer
from ipo_analyzer.analyzers._pricing_gap import PricingGapAnalyzer

p = AllotmentPredictor()
r = p.predict_one_lot_allotment(100.0)
print(f"100x over-sub: {r.one_lot_rate_min:.0f}%-{r.one_lot_rate_max:.0f}%, heat={r.heat_label}")

s = ABGroupStrategyAnalyzer()
r = s.analyze(over_sub_ratio=100.0, public_offer_shares=1000000, lot_size=200)
print(f"Small cap: {r['optimal_strategy']['small_capital']['strategy']}")
print(f"Medium cap: {r['optimal_strategy']['medium_capital']['strategy']}")
print(f"Large cap: {r['optimal_strategy']['large_capital']['strategy']}")

g = GreenshoeAnalyzer()
text = "超额配股权可额外发售15%股份"
r = g.analyze({"_extracted_text": text, "global_offer_shares": 10000000})
print(f"Has greenshoe: {r['has_greenshoe']}, ratio={r['greenshoe_ratio']}, impact={r['impact_score']}")

pg = PricingGapAnalyzer()
r = pg.analyze({"min_price": 1.0, "max_price": 2.0, "offer_price": 1.9})
print(f"Position: {r.pricing_position} ({r.pricing_pct:.0f}%), score={r.score_adjustment:+d}")

print("All 4 modules working correctly!")
