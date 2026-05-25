from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto('http://localhost:3000')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)

    row = page.locator('table tbody tr').first
    row.click()
    page.wait_for_timeout(3000)

    blogger_section = page.locator('text=博主观点').first
    if blogger_section:
        blogger_section.scroll_into_view_if_needed()
        page.wait_for_timeout(2000)
        box = blogger_section.bounding_box()
        if box:
            page.screenshot(path='/tmp/blogger_final.png', clip={
                "x": 0,
                "y": max(0, box["y"] - 20),
                "width": 1400,
                "height": 600,
            })
            print(f'Screenshot taken, blogger section at y={box["y"]}')

    all_text = page.locator('body').inner_text()
    idx = all_text.find('博主观点')
    if idx >= 0:
        context = all_text[idx:idx+400]
        print(f'Blogger section content:\n{context}')

    browser.close()
