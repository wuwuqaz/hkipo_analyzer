from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('http://localhost:3000/history')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(2000)

    page.screenshot(path='/tmp/history_full_audit.png', full_page=True)

    rows = page.locator('table tbody tr').all()
    print(f"Total rows: {len(rows)}")

    for row in rows:
        cells = row.locator('td').all()
        if len(cells) >= 8:
            code = cells[2].text_content().strip()
            if code in ['07688', '01511', '07666', '06872', '06871', '07630', '01236']:
                price = cells[4].text_content().strip()
                mcap = cells[5].text_content().strip()
                lots = cells[6].text_content().strip()
                lot_size = cells[7].text_content().strip()
                print(f'  {code}: 发行价={price}, 市值={mcap}, 公开发售手数={lots}, 每手股数={lot_size}')

    browser.close()
