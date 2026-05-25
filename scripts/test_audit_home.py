from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('http://localhost:3000')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(2000)

    page.screenshot(path='/tmp/home_audit.png', full_page=True)

    metric_cards = page.locator('.grid .rounded-xl, [class*="metric"], [class*="card"]').all()
    print(f"Found {len(metric_cards)} potential metric elements")

    all_text = page.locator('body').text_content()
    for keyword in ['--', 'undefined', 'null', 'NaN']:
        count = all_text.count(keyword)
        if count > 0:
            print(f'  Found "{keyword}" {count} times in page')

    browser.close()
