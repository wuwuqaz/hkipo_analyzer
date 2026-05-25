from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('http://localhost:3000')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)

    page.screenshot(path='/tmp/home_audit2.png', full_page=True)

    all_text = page.locator('body').inner_text()
    
    for keyword in ['undefined', 'null']:
        idx = 0
        while True:
            pos = all_text.find(keyword, idx)
            if pos == -1:
                break
            start = max(0, pos - 40)
            end = min(len(all_text), pos + len(keyword) + 40)
            context = all_text[start:end].replace('\n', ' ')
            print(f'  "{keyword}" at pos {pos}: ...{context}...')
            idx = pos + 1
            if idx > pos + 200:
                break

    browser.close()
