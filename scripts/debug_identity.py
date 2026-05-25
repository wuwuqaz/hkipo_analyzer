"""
Debug script to trace the company name matching logic for 丹诺医药-B.
"""
import re
import subprocess
import sys
sys.path.insert(0, '/Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer')

from ipo_analyzer.identity_validator import (
    build_company_aliases,
    extract_company_name_from_first_page,
    validate_pdf_identity,
    _to_traditional,
)
from ipo_analyzer.utils import _normalize_company_name

print("=" * 80)
print("Debug: Company Name Matching for 丹诺医药-B")
print("=" * 80)

# Try to extract text from the actual PDF
try:
    result_extract = subprocess.run(
        ["pdftotext", "-layout", "storage/06872_prospectus.pdf", "/tmp/06872_extracted.txt"],
        capture_output=True
    )
    
    with open("/tmp/06872_extracted.txt", "r") as f:
        full_text = f.read()
    
    print(f"\nPDF text length: {len(full_text)}")
    print(f"First 1000 chars:\n{full_text[:1000]}")
    
    # Check what name is extracted from first page
    extracted_cn, extracted_en = extract_company_name_from_first_page(full_text)
    print(f"\nExtracted CN name: {extracted_cn}")
    print(f"Extracted EN name: {extracted_en}")
    
    # Test with different company name variations
    test_names = [
        "丹诺医药-B",
        "丹诺医药",
        "丹諾醫藥",
        "丹諾醫藥(蘇州)股份有限公司",
    ]
    
    for test_name in test_names:
        print(f"\n{'='*60}")
        print(f"Testing with company_name: '{test_name}'")
        print(f"{'='*60}")
        
        aliases = build_company_aliases(test_name)
        print(f"Aliases generated: {aliases}")
        
        # Check normalization
        company_clean = _normalize_company_name(test_name)
        trad_company_clean = _to_traditional(company_clean)
        print(f"Normalized: {company_clean}")
        print(f"Traditional: {trad_company_clean}")
        
        if extracted_cn:
            extracted_norm = _normalize_company_name(extracted_cn)
            print(f"Extracted normalized: {extracted_norm}")
            
            # Check the precise matching logic
            trad_name = _to_traditional(company_clean)
            print(f"Precise match check:")
            print(f"  trad_name (target): {trad_name}")
            print(f"  extracted_norm (PDF): {extracted_norm}")
            print(f"  trad_name in extracted_norm: {trad_name in extracted_norm}")
            print(f"  extracted_norm in trad_name: {extracted_norm in trad_name}")
        
        # Run full validation
        result = validate_pdf_identity(full_text, "06872", test_name)
        print(f"Full validation result:")
        print(f"  name_match: {result['name_match']}")
        print(f"  stock_code_match: {result['stock_code_match']}")
        print(f"  confidence: {result['pdf_identity_confidence']}")
        print(f"  extracted_company_name: {result['extracted_company_name']}")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
