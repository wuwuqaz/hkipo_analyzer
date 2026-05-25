from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('http://localhost:3000')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)

    row = page.locator('table tbody tr').first
    row.click()
    page.wait_for_timeout(3000)

    page.screenshot(path='/tmp/blogger_detail.png', full_page=True)

    all_text = page.locator('body').inner_text()
    if '博主观点' in all_text:
        print('✅ "博主观点" section found after clicking IPO row')
        idx = all_text.find('博主观点')
        context = all_text[idx:idx+300]
        print(f'  Context: {context[:300]}')
    else:
        print('❌ "博主观点" section NOT found even after clicking IPO row')

    browser.close()
