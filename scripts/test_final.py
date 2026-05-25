from playwright.sync_api import sync_playwright
import json

issues = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})

    page_errors = []
    page.on("pageerror", lambda err: page_errors.append(str(err)))

    # ========== TEST 1: Home Page ==========
    print("=" * 60)
    print("TEST 1: Home Page")
    print("=" * 60)
    page_errors.clear()
    page.goto('http://localhost:3000')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)

    rows = page.locator('table tbody tr').all()
    if rows:
        rows[0].click()
        page.wait_for_timeout(3000)

    detail_text = page.locator('body').inner_text()
    home_sections = ['公司信息', '评分概览', '估值分析', '风险提示', '博主观点', '基本信息']
    for s in home_sections:
        if s not in detail_text:
            issues.append(f"首页: 缺少 '{s}'")
            print(f"  ❌ Missing: {s}")
        else:
            print(f"  ✅ {s}")

    if page_errors:
        for e in page_errors[:3]:
            issues.append(f"首页 JS错误: {e[:100]}")
            print(f"  ❌ JS Error: {e[:100]}")
    else:
        print("  ✅ No JS errors")

    # ========== TEST 2: History Page ==========
    print("\n" + "=" * 60)
    print("TEST 2: History Page")
    print("=" * 60)
    page_errors.clear()
    page.goto('http://localhost:3000/history')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)

    hist_rows = page.locator('table tbody tr').all()
    print(f"  Records: {len(hist_rows)}")

    # Check all rows for blank data
    for row in hist_rows:
        cells = row.locator('td').all()
        if len(cells) >= 8:
            code = cells[2].text_content().strip()
            price = cells[4].text_content().strip()
            if price == '--':
                issues.append(f"历史: {code} 发行价为空")
                print(f"  ❌ {code}: 价格空白")
            else:
                print(f"  ✅ {code}: {price}")

    # Expand and check detail
    if hist_rows:
        hist_rows[0].click()
        page.wait_for_timeout(3000)
        hist_text = page.locator('body').inner_text()
        for s in ['公司信息', '估值分析', '风险提示', '博主观点']:
            if s not in hist_text:
                issues.append(f"历史详情: 缺少 '{s}'")
                print(f"  ❌ Detail missing: {s}")
            else:
                print(f"  ✅ Detail: {s}")

    if page_errors:
        for e in page_errors[:3]:
            issues.append(f"历史页 JS错误: {e[:100]}")
            print(f"  ❌ JS Error: {e[:100]}")
    else:
        print("  ✅ No JS errors")

    # ========== TEST 3: Peers Page ==========
    print("\n" + "=" * 60)
    print("TEST 3: Peers Page")
    print("=" * 60)
    page_errors.clear()
    page.goto('http://localhost:3000/peers')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)

    peer_rows = page.locator('table tbody tr').all()
    print(f"  Peer records: {len(peer_rows)}")

    if page_errors:
        for e in page_errors[:3]:
            issues.append(f"同行页 JS错误: {e[:100]}")
            print(f"  ❌ JS Error: {e[:100]}")
    else:
        print("  ✅ No JS errors")

    # ========== TEST 4: Upload & Reanalyze Pages ==========
    print("\n" + "=" * 60)
    print("TEST 4: Other Pages")
    print("=" * 60)
    for route, name in [('/upload', '上传'), ('/reanalyze', '重新分析')]:
        page_errors.clear()
        page.goto(f'http://localhost:3000{route}')
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(2000)
        if page_errors:
            issues.append(f"{name}页 JS错误: {page_errors[0][:100]}")
            print(f"  ❌ {name}: JS error")
        else:
            print(f"  ✅ {name}: OK")

    # ========== TEST 5: API Quality ==========
    print("\n" + "=" * 60)
    print("TEST 5: API Data Quality")
    print("=" * 60)
    import urllib.request

    # Live results
    resp = urllib.request.urlopen('http://localhost:8000/api/live/results', timeout=10)
    data = json.loads(resp.read())
    for r in data.get('results', []):
        code = r.get('hk_code', '?')
        key = ['offer_price', 'market_cap_hkd_million', 'board_lot', 'public_offer_lots', 'public_offer_ratio', 'international_offer_ratio']
        missing = [f for f in key if r.get(f) is None]
        if missing:
            issues.append(f"API Live {code}: 缺少 {missing}")
            print(f"  ❌ Live {code}: missing {missing}")
        else:
            print(f"  ✅ Live {code}: complete")

    # History results
    resp = urllib.request.urlopen('http://localhost:8000/api/history/records', timeout=10)
    data = json.loads(resp.read())
    for r in data.get('records', []):
        code = r.get('stock_code', '?')
        raw = r.get('_raw', {})
        key = ['offer_price', 'market_cap_hkd_million', 'board_lot', 'public_offer_lots', 'public_offer_ratio', 'international_offer_ratio']
        missing = [f for f in key if raw.get(f) is None]
        if missing:
            issues.append(f"API History {code}: 缺少 {missing}")
            print(f"  ❌ History {code}: missing {missing}")
        else:
            print(f"  ✅ History {code}: complete")

    # Blogger API
    resp = urllib.request.urlopen('http://localhost:8000/api/blogger/06872', timeout=10)
    data = json.loads(resp.read())
    print(f"  ✅ Blogger API: score={data.get('consensus_score')}, posts={data.get('total_posts')}")

    browser.close()

# ========== SUMMARY ==========
print("\n" + "=" * 60)
print("FINAL SUMMARY")
print("=" * 60)
if issues:
    for i, issue in enumerate(issues, 1):
        print(f"  {i}. {issue}")
    print(f"\n  Total: {len(issues)} issue(s)")
else:
    print("  ✅✅✅ All tests passed! No issues found.")
