import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ipo_analyzer.cornerstone import CornerstoneAnalyzer
from ipo_analyzer.text_extractor import extract_pdf_text

pdfs = [
    ("temp/07666_prospectus.pdf", "07666"),
    ("temp/07688_prospectus.pdf", "07688"),
    ("temp/06872_prospectus.pdf", "06872"),
    ("temp/07630_prospectus.pdf", "07630"),
    ("temp/01236_prospectus.pdf", "01236"),
    ("temp/01511_prospectus.pdf", "01511"),
]

for pdf_path, code in pdfs:
    if not os.path.exists(pdf_path):
        print(f"\n{code}: File not found")
        continue
    text = extract_pdf_text(pdf_path)
    ca = CornerstoneAnalyzer()
    result = ca.analyze(text)
    
    investors = result.get('cornerstone_investors', [])
    label = result.get('label', '?')
    score = result.get('score', 0)
    
    print(f"\n{'='*60}")
    print(f"{code}: {label} (score={score}), {len(investors)} investors")
    print(f"{'='*60}")
    
    for i, inv in enumerate(investors):
        name = inv.get('short_name') or inv.get('name', '?')
        tier = inv.get('tier', '?')
        shares = inv.get('offer_shares', 0)
        pct = inv.get('offer_shares_pct')
        cap = inv.get('issued_share_pct')
        amt = inv.get('investment_amount_m')
        cur = inv.get('investment_currency')
        print(f"  [{i+1}] {name} | T:{tier} | S:{shares:,} | O%:{pct} | C%:{cap} | A:{amt}{cur}")
