from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})

    console_errors = []
    page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type in ['error', 'warning'] else None)

    page_errors = []
    page.on("pageerror", lambda err: page_errors.append(str(err)))

    # Test History page
    print("=" * 60)
    print("History Page - Precise Error Check")
    print("=" * 60)
    console_errors.clear()
    page_errors.clear()
    page.goto('http://localhost:3000/history')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)

    # Check for React error boundaries or Next.js error pages
    body_html = page.locator('body').inner_html()
    has_next_error = 'next-error' in body_html or '__next_error__' in body_html
    
    body_text = page.locator('body').inner_text()
    has_runtime_error = 'Unhandled Runtime Error' in body_text or 'Application error' in body_text or '500 Server Error' in body_text

    print(f"  Next.js error page: {has_next_error}")
    print(f"  Runtime error: {has_runtime_error}")
    print(f"  Page errors: {len(page_errors)}")
    for err in page_errors[:3]:
        print(f"    {err[:200]}")
    print(f"  Console errors: {len(console_errors)}")
    for err in console_errors[:5]:
        print(f"    {err[:200]}")

    page.screenshot(path='/tmp/debug_history2.png', full_page=True)

    # Test Peers page
    print("\n" + "=" * 60)
    print("Peers Page - Precise Error Check")
    print("=" * 60)
    console_errors.clear()
    page_errors.clear()
    page.goto('http://localhost:3000/peers')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)

    body_html = page.locator('body').inner_html()
    has_next_error = 'next-error' in body_html or '__next_error__' in body_html
    
    body_text = page.locator('body').inner_text()
    has_runtime_error = 'Unhandled Runtime Error' in body_text or 'Application error' in body_text or '500 Server Error' in body_text

    print(f"  Next.js error page: {has_next_error}")
    print(f"  Runtime error: {has_runtime_error}")
    print(f"  Page errors: {len(page_errors)}")
    for err in page_errors[:3]:
        print(f"    {err[:200]}")
    print(f"  Console errors: {len(console_errors)}")
    for err in console_errors[:5]:
        print(f"    {err[:200]}")

    page.screenshot(path='/tmp/debug_peers2.png', full_page=True)

    browser.close()
