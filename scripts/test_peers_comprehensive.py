from playwright.sync_api import sync_playwright
import json
import urllib.request

issues = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})

    # ========== API Check ==========
    print("=" * 60)
    print("1. API Data Quality Check")
    print("=" * 60)

    resp = urllib.request.urlopen('http://localhost:8000/api/peers/', timeout=10)
    data = json.loads(resp.read())
    peers = data.get('peers', [])

    stale_count = sum(1 for p in peers if p.get('is_stale'))
    quality_dist = {}
    for p in peers:
        q = p.get('data_quality', 'None')
        quality_dist[q] = quality_dist.get(q, 0) + 1
    print(f"  Total: {len(peers)}, Stale: {stale_count}, Quality: {quality_dist}")

    # Check is_stale field exists in all records
    missing_is_stale = [p['ticker'] for p in peers if 'is_stale' not in p]
    if missing_is_stale:
        issues.append(f"API: is_stale 字段缺失: {missing_is_stale}")
        print(f"  ❌ is_stale missing in: {missing_is_stale}")
    else:
        print("  ✅ is_stale field present in all records")

    # Check data_quality field
    missing_quality = [p['ticker'] for p in peers if p.get('data_quality') is None]
    if missing_quality:
        issues.append(f"API: data_quality 为 None: {missing_quality}")
        print(f"  ❌ data_quality is None in: {missing_quality}")
    else:
        print("  ✅ data_quality field present in all records")

    # Check stale_only filter
    resp = urllib.request.urlopen('http://localhost:8000/api/peers/?stale_only=true', timeout=10)
    stale_data = json.loads(resp.read())
    stale_peers = stale_data.get('peers', [])
    print(f"  stale_only filter: {len(stale_peers)} peers returned")
    if len(stale_peers) > 0:
        all_stale = all(p.get('is_stale') for p in stale_peers)
        if all_stale:
            print("  ✅ stale_only filter works correctly")
        else:
            issues.append("API: stale_only 过滤返回了非 stale 记录")
            print("  ❌ stale_only filter returns non-stale records")

    # Check meta API
    resp = urllib.request.urlopen('http://localhost:8000/api/peers/meta', timeout=10)
    meta = json.loads(resp.read())
    print(f"  Meta: source_date={meta.get('peer_data_source_date')}, age={meta.get('peer_data_age_days')}天, stale={meta.get('peer_data_is_stale')}")

    # ========== Frontend Check: Peers Page ==========
    print("\n" + "=" * 60)
    print("2. Peers Page Frontend Check")
    print("=" * 60)
    page.goto('http://localhost:3000/peers')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)
    page.screenshot(path='/tmp/peers_page.png', full_page=True)

    peers_text = page.locator('body').inner_text()

    # Check meta cards
    if '数据日期' in peers_text and '数据年龄' in peers_text:
        print("  ✅ Meta cards rendered")
    else:
        issues.append("同行页面: Meta 卡片未渲染")
        print("  ❌ Meta cards missing")

    # Check table
    peer_rows = page.locator('table tbody tr').all()
    print(f"  Table rows: {len(peer_rows)}")

    # Check stale indicators
    if '⚠ 过期' in peers_text:
        print("  ✅ Stale indicator found")
    elif '✓ 有效' in peers_text:
        print("  ✅ Valid indicators found (no stale peers)")
    else:
        issues.append("同行页面: 状态指示器未渲染")
        print("  ❌ Status indicators missing")

    # ========== Frontend Check: Home Page Peer Components ==========
    print("\n" + "=" * 60)
    print("3. Home Page Peer Components")
    print("=" * 60)
    page.goto('http://localhost:3000')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)

    rows = page.locator('table tbody tr').all()
    if rows:
        rows[0].click()
        page.wait_for_timeout(3000)

        detail_text = page.locator('body').inner_text()
        if '同行对比' in detail_text:
            print("  ✅ 同行对比 section found on home page")
        else:
            issues.append("首页: 同行对比面板缺失")
            print("  ❌ 同行对比 section missing on home page")

        if '估值定位' in detail_text or '估值合理' in detail_text or '偏贵' in detail_text:
            print("  ✅ 估值定位 data present")
        else:
            print("  ⚠️ 估值定位 may be missing (could be normal if no peer data)")

    # ========== Frontend Check: History Page Peer Components ==========
    print("\n" + "=" * 60)
    print("4. History Page Peer Components")
    print("=" * 60)
    page.goto('http://localhost:3000/history')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)

    hist_rows = page.locator('table tbody tr').all()
    if hist_rows:
        hist_rows[0].click()
        page.wait_for_timeout(3000)

        hist_text = page.locator('body').inner_text()
        if '同行对比' in hist_text:
            print("  ✅ 同行对比 section found on history page")
        else:
            issues.append("历史页面: 同行对比面板缺失")
            print("  ❌ 同行对比 section missing on history page")

    browser.close()

# ========== SUMMARY ==========
print("\n" + "=" * 60)
print("ISSUE SUMMARY")
print("=" * 60)
if issues:
    for i, issue in enumerate(issues, 1):
        print(f"  {i}. {issue}")
else:
    print("  ✅ All checks passed!")
