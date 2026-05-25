from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})

    page.goto('http://localhost:3000')
    page.wait_for_load_state('networkidle')
    page.screenshot(path='layout_home.png', full_page=True)
    print("Homepage screenshot saved")

    page.goto('http://localhost:3000/history')
    page.wait_for_load_state('networkidle')
    page.screenshot(path='layout_history.png', full_page=True)
    print("History page screenshot saved")

    page.goto('http://localhost:3000/peers')
    page.wait_for_load_state('networkidle')
    page.screenshot(path='layout_peers.png', full_page=True)
    print("Peers page screenshot saved")

    page.goto('http://localhost:3000')
    page.wait_for_load_state('networkidle')
    rows = page.locator('tbody tr')
    if rows.count() > 0:
        rows.first.click()
        page.wait_for_timeout(1500)
        page.screenshot(path='layout_home_detail.png', full_page=True)
        print("Homepage detail screenshot saved")
    else:
        print("No rows to expand on homepage")

    page.goto('http://localhost:3000/history')
    page.wait_for_load_state('networkidle')
    hist_rows = page.locator('tbody tr')
    if hist_rows.count() > 0:
        hist_rows.first.click()
        page.wait_for_timeout(1500)
        page.screenshot(path='layout_history_detail.png', full_page=True)
        print("History detail screenshot saved")
    else:
        print("No rows to expand on history page")

    browser.close()
    print("All screenshots captured!")
