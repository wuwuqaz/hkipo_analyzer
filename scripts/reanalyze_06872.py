import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ipo_analyzer.core import analyze_single_ipo
from ipo_analyzer.cache import ResultCache

result = analyze_single_ipo('06872', '丹诺医药－B', output_dir='storage')
if result:
    cache = ResultCache(cache_dir='storage')
    cache.save([result])
    print("Cache updated!")
    
    # Verify
    cached = cache.load()
    for item in cached:
        code = item.get('hk_code', '?')
        name = item.get('company_name', '?')
        pi = item.get('prospectus_info', {})
        ca = pi.get('cornerstone_analysis', {})
        inv_count = len(ca.get('cornerstone_investors', []))
        label = ca.get('label', '?')
        score = ca.get('score', 0)
        print(f'  {code} {name}: {label} (score={score}), {inv_count} investors')
        for i, inv in enumerate(ca.get('cornerstone_investors', [])):
            iname = inv.get('short_name') or inv.get('name', '?')
            tier = inv.get('tier', '?')
            amt = inv.get('investment_amount_m')
            cur = inv.get('investment_currency', '')
            print(f'    [{i+1}] {iname} | T:{tier} | A:{amt}{cur}')
else:
    print("Analysis failed")
