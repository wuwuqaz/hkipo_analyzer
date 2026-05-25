from playwright.sync_api import sync_playwright
import json

issues = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})

    # ========== TEST 1: Home Page ==========
    print("=" * 60)
    print("TEST 1: Home Page - Load & IPO Detail")
    print("=" * 60)
    page.goto('http://localhost:3000')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)
    page.screenshot(path='/tmp/test_home_loaded.png', full_page=True)

    # Check for console errors
    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

    # Check table loaded
    rows = page.locator('table tbody tr').all()
    print(f"  IPO rows found: {len(rows)}")
    if len(rows) == 0:
        issues.append("首页: 没有IPO数据行")

    # Click first IPO to expand detail
    if rows:
        first_row = rows[0]
        first_row.click()
        page.wait_for_timeout(3000)
        page.screenshot(path='/tmp/test_home_detail.png', full_page=True)

        detail_text = page.locator('body').inner_text()

        # Check all detail sections
        sections = [
            '公司信息', '评分总览', '维度评分', '信号分解',
            '估值分析', '同行对比', '基石投资者', '股票质地',
            '风险提示', '博主观点', '基本信息',
        ]
        for section in sections:
            if section in detail_text:
                print(f"  ✅ Section found: {section}")
            else:
                print(f"  ❌ Section MISSING: {section}")
                issues.append(f"首页: 缺少 '{section}' 面板")

        # Check for -- in metric cards
        metric_cards_text = detail_text
        double_dash_count = metric_cards_text.count('--')
        print(f"  '--' occurrences in page: {double_dash_count}")

        # Check specific data points
        if 'HK$' in detail_text or 'HKD' in detail_text:
            print("  ✅ Price data present")
        else:
            print("  ❌ No price data found")
            issues.append("首页: 没有价格数据")

        if '博主观点' in detail_text:
            blogger_idx = detail_text.find('博主观点')
            blogger_context = detail_text[blogger_idx:blogger_idx+200]
            if '共识分' in blogger_context or '搜索博主观点' in blogger_context:
                print("  ✅ Blogger section renders correctly")
            else:
                print("  ❌ Blogger section renders but may have issues")
                issues.append("首页: 博主观点面板渲染异常")

    # Check console errors
    if console_errors:
        for err in console_errors[:5]:
            if 'Failed to fetch' in err or '500' in err:
                print(f"  ⚠️ Console error: {err[:100]}")
                issues.append(f"首页: 控制台错误 - {err[:80]}")

    # ========== TEST 2: History Page ==========
    print("\n" + "=" * 60)
    print("TEST 2: History Page")
    print("=" * 60)
    page.goto('http://localhost:3000/history')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)
    page.screenshot(path='/tmp/test_history_loaded.png', full_page=True)

    hist_rows = page.locator('table tbody tr').all()
    print(f"  History rows found: {len(hist_rows)}")
    if len(hist_rows) == 0:
        issues.append("历史页面: 没有历史记录")

    # Check table columns for -- values
    if hist_rows:
        for i, row in enumerate(hist_rows[:3]):
            cells = row.locator('td').all()
            if len(cells) >= 8:
                code = cells[2].text_content().strip() if len(cells) > 2 else "?"
                price = cells[4].text_content().strip() if len(cells) > 4 else "?"
                mcap = cells[5].text_content().strip() if len(cells) > 5 else "?"
                lots = cells[6].text_content().strip() if len(cells) > 6 else "?"
                lot_size = cells[7].text_content().strip() if len(cells) > 7 else "?"
                print(f"  {code}: 价格={price}, 市值={mcap}, 手数={lots}, 每手={lot_size}")
                if price == '--' and mcap == '--':
                    issues.append(f"历史页面: {code} 数据全为空")

        # Click first row to expand
        first_hist_row = hist_rows[0]
        first_hist_row.click()
        page.wait_for_timeout(3000)
        page.screenshot(path='/tmp/test_history_detail.png', full_page=True)

        hist_detail_text = page.locator('body').inner_text()

        hist_sections = [
            '公司信息', '评分总览', '风险提示', '博主观点',
        ]
        for section in hist_sections:
            if section in hist_detail_text:
                print(f"  ✅ Section found: {section}")
            else:
                print(f"  ❌ Section MISSING: {section}")
                issues.append(f"历史页面: 缺少 '{section}' 面板")

    # ========== TEST 3: Upload Page ==========
    print("\n" + "=" * 60)
    print("TEST 3: Upload Page")
    print("=" * 60)
    page.goto('http://localhost:3000/upload')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(2000)
    page.screenshot(path='/tmp/test_upload.png', full_page=True)

    upload_text = page.locator('body').inner_text()
    if '上传' in upload_text or 'Upload' in upload_text or 'PDF' in upload_text:
        print("  ✅ Upload page renders correctly")
    else:
        print("  ❌ Upload page may have issues")
        issues.append("上传页面: 渲染异常")

    # ========== TEST 4: Peers Page ==========
    print("\n" + "=" * 60)
    print("TEST 4: Peers Page")
    print("=" * 60)
    page.goto('http://localhost:3000/peers')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)
    page.screenshot(path='/tmp/test_peers.png', full_page=True)

    peers_text = page.locator('body').inner_text()
    if '同行' in peers_text or 'Peer' in peers_text or 'sector' in peers_text.lower():
        print("  ✅ Peers page renders")
        peer_rows = page.locator('table tbody tr').all()
        print(f"  Peer rows found: {len(peer_rows)}")
    else:
        print("  ⚠️ Peers page may have no data or issues")

    # ========== TEST 5: Reanalyze Page ==========
    print("\n" + "=" * 60)
    print("TEST 5: Reanalyze Page")
    print("=" * 60)
    page.goto('http://localhost:3000/reanalyze')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(2000)
    page.screenshot(path='/tmp/test_reanalyze.png', full_page=True)

    reanalyze_text = page.locator('body').inner_text()
    if '重新分析' in reanalyze_text or 'Reanalyze' in reanalyze_text:
        print("  ✅ Reanalyze page renders")
    else:
        print("  ⚠️ Reanalyze page may have issues")

    # ========== TEST 6: API Endpoints ==========
    print("\n" + "=" * 60)
    print("TEST 6: API Endpoints")
    print("=" * 60)
    import urllib.request

    api_tests = [
        ('GET /api/health', 'http://localhost:8000/api/health'),
        ('GET /api/live/results', 'http://localhost:8000/api/live/results'),
        ('GET /api/history/records', 'http://localhost:8000/api/history/records'),
        ('GET /api/blogger/06872', 'http://localhost:8000/api/blogger/06872'),
        ('GET /api/peers', 'http://localhost:8000/api/peers'),
    ]

    for name, url in api_tests:
        try:
            resp = urllib.request.urlopen(url, timeout=10)
            data = json.loads(resp.read())
            print(f"  ✅ {name}: status=200")
        except Exception as e:
            print(f"  ❌ {name}: {e}")
            issues.append(f"API: {name} 失败 - {e}")

    browser.close()

# ========== SUMMARY ==========
print("\n" + "=" * 60)
print("ISSUE SUMMARY")
print("=" * 60)
if issues:
    for i, issue in enumerate(issues, 1):
        print(f"  {i}. {issue}")
else:
    print("  ✅ No issues found!")
