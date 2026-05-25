import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ipo_analyzer.cornerstone import CornerstoneAnalyzer
from ipo_analyzer.text_extractor import extract_pdf_text

pdf_path = "temp/06872_prospectus.pdf"
text = extract_pdf_text(pdf_path)
ca = CornerstoneAnalyzer()
result = ca.analyze(text)

investors = result.get('cornerstone_investors', [])
print(f"Current code - Investors count: {len(investors)}")
for i, inv in enumerate(investors):
    print(f"\n[{i+1}] Name: {inv.get('name')}")
    print(f"    Short: {inv.get('short_name')}")
    print(f"    Tier: {inv.get('tier')}")
    print(f"    Shares: {inv.get('offer_shares')}")
    print(f"    Offer%: {inv.get('offer_shares_pct')}")
    print(f"    Cap%: {inv.get('issued_share_pct')}")
    print(f"    Amount: {inv.get('investment_amount_m')} {inv.get('investment_currency')}")
