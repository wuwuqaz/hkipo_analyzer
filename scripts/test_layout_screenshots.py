from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})

    # Home page - overview
    page.goto('http://localhost:3000')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)
    page.screenshot(path='/tmp/layout_home.png', full_page=True)

    # Home page - detail expanded
    rows = page.locator('table tbody tr').all()
    if rows:
        rows[0].click()
        page.wait_for_timeout(3000)
        page.screenshot(path='/tmp/layout_home_detail.png', full_page=True)

    # History page
    page.goto('http://localhost:3000/history')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)
    page.screenshot(path='/tmp/layout_history.png', full_page=True)

    # History page - detail expanded
    hist_rows = page.locator('table tbody tr').all()
    if hist_rows:
        hist_rows[0].click()
        page.wait_for_timeout(3000)
        page.screenshot(path='/tmp/layout_history_detail.png', full_page=True)

    # Peers page
    page.goto('http://localhost:3000/peers')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)
    page.screenshot(path='/tmp/layout_peers.png', full_page=True)

    browser.close()
    print("All screenshots saved to /tmp/layout_*.png")
