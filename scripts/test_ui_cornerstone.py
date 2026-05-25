from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    
    page.goto('http://localhost:3000')
    page.wait_for_load_state('networkidle')
    time.sleep(3)
    
    # Click on 06872
    row = page.locator('text=06872').first
    if row.is_visible():
        row.click()
        page.wait_for_load_state('networkidle')
        time.sleep(3)
        
        page.screenshot(path='/tmp/detail_06872_fixed.png', full_page=True)
        
        body_text = page.locator('body').text_content() or ''
        # Find cornerstone section
        cs_idx = body_text.find('基石')
        if cs_idx >= 0:
            cs_text = body_text[cs_idx:cs_idx+800]
            print(f"基石 section:\n{cs_text}")
            
            # Check for the old wrong data
            if 'WuXi Fund 2,848,109' in cs_text:
                print("\n❌ OLD DATA STILL SHOWING: 'WuXi Fund 2,848,109'")
            elif 'WuXi Fund' in cs_text and '2,848,109' not in cs_text:
                print("\n✅ WuXi Fund mentioned but without wrong number")
            
            # Check for correct data
            if 'AMR Action Fund' in cs_text:
                print("✅ AMR Action Fund found in cornerstone section")
            if '57' in cs_text and 'investor' in cs_text.lower():
                print("❌ Still showing 57 investors")
    else:
        print("06872 not found on page")
    
    browser.close()
