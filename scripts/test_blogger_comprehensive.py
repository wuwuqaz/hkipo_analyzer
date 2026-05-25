from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})

    # Test 1: Home page blogger section
    page.goto('http://localhost:3000')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)

    row = page.locator('table tbody tr').first
    row.click()
    page.wait_for_timeout(3000)

    home_text = page.locator('body').inner_text()
    if '博主观点' in home_text:
        print('✅ Home page: 博主观点 section found')
        idx = home_text.find('博主观点')
        context = home_text[idx:idx+150]
        print(f'   Content: {context[:150]}')
    else:
        print('❌ Home page: 博主观点 section NOT found')

    # Test 2: History page blogger section
    page.goto('http://localhost:3000/history')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)

    hist_row = page.locator('table tbody tr').first
    hist_row.click()
    page.wait_for_timeout(3000)

    hist_text = page.locator('body').inner_text()
    if '博主观点' in hist_text:
        print('✅ History page: 博主观点 section found')
        idx = hist_text.find('博主观点')
        context = hist_text[idx:idx+150]
        print(f'   Content: {context[:150]}')
    else:
        print('❌ History page: 博主观点 section NOT found')

    # Test 3: API endpoints
    import json
    import urllib.request

    try:
        resp = urllib.request.urlopen('http://localhost:8000/api/blogger/06872')
        data = json.loads(resp.read())
        print(f'✅ GET /api/blogger/06872: consensus_score={data["consensus_score"]}, total_posts={data["total_posts"]}')
    except Exception as e:
        print(f'❌ GET /api/blogger/06872: {e}')

    try:
        req = urllib.request.Request(
            'http://localhost:8000/api/blogger/07688/search',
            method='POST',
            headers={'Content-Type': 'application/json'},
        )
        resp = urllib.request.urlopen(req, timeout=60)
        data = json.loads(resp.read())
        print(f'✅ POST /api/blogger/07688/search: consensus_score={data["consensus_score"]}, total_posts={data["total_posts"]}')
    except Exception as e:
        print(f'❌ POST /api/blogger/07688/search: {e}')

    browser.close()
