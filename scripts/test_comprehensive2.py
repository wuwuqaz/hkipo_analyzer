from playwright.sync_api import sync_playwright
import json

issues = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})

    # ========== TEST 1: Home Page ==========
    print("=" * 60)
    print("TEST 1: Home Page - Full Detail Check")
    print("=" * 60)
    page.goto('http://localhost:3000')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)

    rows = page.locator('table tbody tr').all()
    print(f"  IPO rows: {len(rows)}")

    if rows:
        rows[0].click()
        page.wait_for_timeout(3000)
        page.screenshot(path='/tmp/test1_home_detail.png', full_page=True)

        detail_text = page.locator('body').inner_text()

        home_sections = [
            '公司信息', '评分概览', '评分理由', '综合分拆解',
            '维度拆解', '交易信号', '估值分析', '同行对比',
            '基石投资者', '股票质地', '风险提示', '博主观点',
            '基本信息', '业务分部', '长线视角',
        ]
        for section in home_sections:
            if section in detail_text:
                print(f"  ✅ {section}")
            else:
                print(f"  ❌ MISSING: {section}")
                issues.append(f"首页: 缺少 '{section}' 面板")

        # Check for -- in key data areas
        # Extract the detail section text only
        detail_start = detail_text.find('公司信息')
        if detail_start > 0:
            detail_area = detail_text[detail_start:detail_start+3000]
            
            # Check for common blank indicators in key metrics
            blank_patterns = [
                ('发行价', 'HK$'),
                ('市值', 'M HKD'),
                ('每手股数', None),
            ]
            for label, expected in blank_patterns:
                idx = detail_area.find(label)
                if idx >= 0:
                    context = detail_area[idx:idx+50]
                    if '--' in context:
                        print(f"  ⚠️ {label} shows '--': {context.strip()}")
                        issues.append(f"首页: {label} 显示为空白")

        # Check blogger section
        blogger_idx = detail_text.find('博主观点')
        if blogger_idx >= 0:
            blogger_area = detail_text[blogger_idx:blogger_idx+300]
            if '共识分' in blogger_area or '搜索博主观点' in blogger_area or '暂无博主观点' in blogger_area:
                print("  ✅ 博主观点 renders correctly")
            else:
                print("  ❌ 博主观点 renders but content unexpected")
                issues.append("首页: 博主观点内容异常")

    # ========== TEST 2: History Page ==========
    print("\n" + "=" * 60)
    print("TEST 2: History Page - All Records")
    print("=" * 60)
    page.goto('http://localhost:3000/history')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)

    hist_rows = page.locator('table tbody tr').all()
    print(f"  History rows: {len(hist_rows)}")

    # Check each row's data
    for row in hist_rows:
        cells = row.locator('td').all()
        if len(cells) >= 8:
            code = cells[2].text_content().strip()
            price = cells[4].text_content().strip()
            mcap = cells[5].text_content().strip()
            lots = cells[6].text_content().strip()
            lot_size = cells[7].text_content().strip()
            blanks = []
            if price == '--':
                blanks.append('发行价')
            if mcap == '--':
                blanks.append('市值')
            if lots == '--':
                blanks.append('公开发售手数')
            if lot_size == '--':
                blanks.append('每手股数')
            if blanks:
                print(f"  ❌ {code}: 空白字段 {blanks}")
                issues.append(f"历史页面: {code} 空白字段 {blanks}")
            else:
                print(f"  ✅ {code}: 数据完整 (价格={price})")

    # Expand first row and check detail
    if hist_rows:
        hist_rows[0].click()
        page.wait_for_timeout(3000)
        page.screenshot(path='/tmp/test2_history_detail.png', full_page=True)

        hist_detail = page.locator('body').inner_text()
        hist_sections = [
            '公司信息', '评分概览', '估值分析', '风险提示', '博主观点',
        ]
        for section in hist_sections:
            if section in hist_detail:
                print(f"  ✅ Detail section: {section}")
            else:
                print(f"  ❌ Detail MISSING: {section}")
                issues.append(f"历史页面详情: 缺少 '{section}' 面板")

    # ========== TEST 3: All Pages Load ==========
    print("\n" + "=" * 60)
    print("TEST 3: All Pages Load Check")
    print("=" * 60)

    page_routes = [
        ('/', '首页'),
        ('/history', '历史分析'),
        ('/upload', '上传'),
        ('/peers', '同行对比'),
        ('/reanalyze', '重新分析'),
    ]

    for route, name in page_routes:
        page.goto(f'http://localhost:3000{route}')
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(2000)

        # Check for error text
        body_text = page.locator('body').inner_text()
        has_error = any(kw in body_text for kw in ['404', '500', 'Application error', 'Unhandled Runtime Error'])
        
        if has_error:
            print(f"  ❌ {name} ({route}): Page has error")
            issues.append(f"页面 {name}: 有错误")
        else:
            print(f"  ✅ {name} ({route}): OK")

    # ========== TEST 4: API Endpoints Deep Check ==========
    print("\n" + "=" * 60)
    print("TEST 4: API Data Quality Check")
    print("=" * 60)
    import urllib.request

    # Check live results data completeness
    try:
        resp = urllib.request.urlopen('http://localhost:8000/api/live/results', timeout=10)
        data = json.loads(resp.read())
        results = data.get('results', [])
        for r in results:
            code = r.get('hk_code', '?')
            key_fields = ['offer_price', 'market_cap_hkd_million', 'lot_size', 'board_lot', 
                         'public_offer_lots', 'public_offer_ratio', 'international_offer_ratio']
            missing = [f for f in key_fields if r.get(f) is None]
            if missing:
                print(f"  ⚠️ Live {code}: missing {missing}")
                issues.append(f"API Live: {code} 缺少字段 {missing}")
            else:
                print(f"  ✅ Live {code}: data complete")
    except Exception as e:
        print(f"  ❌ Live API error: {e}")
        issues.append("API: Live results 失败")

    # Check history data completeness
    try:
        resp = urllib.request.urlopen('http://localhost:8000/api/history/records', timeout=10)
        data = json.loads(resp.read())
        records = data.get('records', [])
        for r in records:
            code = r.get('stock_code', '?')
            raw = r.get('_raw', {})
            key_fields = ['offer_price', 'market_cap_hkd_million', 'board_lot', 
                         'public_offer_lots', 'public_offer_ratio', 'international_offer_ratio']
            missing = [f for f in key_fields if raw.get(f) is None]
            if missing:
                print(f"  ⚠️ History {code}: missing {missing}")
                issues.append(f"API History: {code} 缺少字段 {missing}")
            else:
                print(f"  ✅ History {code}: data complete")
    except Exception as e:
        print(f"  ❌ History API error: {e}")
        issues.append("API: History records 失败")

    # Check blogger API
    try:
        resp = urllib.request.urlopen('http://localhost:8000/api/blogger/06872', timeout=10)
        data = json.loads(resp.read())
        print(f"  ✅ Blogger API: consensus_score={data.get('consensus_score')}, total_posts={data.get('total_posts')}")
    except Exception as e:
        print(f"  ❌ Blogger API error: {e}")
        issues.append("API: Blogger 失败")

    browser.close()

# ========== SUMMARY ==========
print("\n" + "=" * 60)
print("FINAL ISSUE SUMMARY")
print("=" * 60)
if issues:
    for i, issue in enumerate(issues, 1):
        print(f"  {i}. {issue}")
    print(f"\n  Total issues: {len(issues)}")
else:
    print("  ✅ All tests passed! No issues found.")
