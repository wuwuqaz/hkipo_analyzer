import time
import os
from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = "/tmp/hkipo_test"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

def test_homepage(page):
    print("\n" + "="*60)
    print("TEST 1: Homepage")
    print("="*60)

    page.goto("http://localhost:3000")
    page.wait_for_load_state("networkidle")
    time.sleep(2)

    page.screenshot(path=f"{SCREENSHOT_DIR}/01_homepage.png", full_page=True)
    print("  [Screenshot] 01_homepage.png")

    title = page.title()
    print(f"  Page title: {title}")

    h1 = page.locator("h1").first
    if h1.is_visible():
        print(f"  H1 text: {h1.text_content()}")

    buttons = page.locator("button").all()
    print(f"  Buttons found: {len(buttons)}")
    for i, btn in enumerate(buttons[:10]):
        txt = btn.text_content().strip() if btn.text_content() else "(empty)"
        print(f"    [{i}] {txt}")

    links = page.locator("a").all()
    print(f"  Links found: {len(links)}")
    for i, link in enumerate(links[:10]):
        href = link.get_attribute("href") or ""
        txt = link.text_content().strip() if link.text_content() else ""
        print(f"    [{i}] {txt} -> {href}")

    print("  [PASS] Homepage loaded")


def test_history_page_initial(page):
    print("\n" + "="*60)
    print("TEST 2: History Page Initial Load")
    print("="*60)

    page.goto("http://localhost:3000/history")
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    page.screenshot(path=f"{SCREENSHOT_DIR}/02_history_initial.png", full_page=True)
    print("  [Screenshot] 02_history_initial.png")

    tables = page.locator("table").all()
    print(f"  Tables found: {len(tables)}")

    if tables:
        rows = tables[0].locator("tbody tr").all()
        print(f"  Table rows: {len(rows)}")

        headers = tables[0].locator("thead th").all()
        header_texts = [h.text_content().strip() for h in headers]
        print(f"  Table headers: {header_texts}")

        if rows:
            first_row = rows[0]
            cells = first_row.locator("td").all()
            cell_texts = [c.text_content().strip() for c in cells]
            print(f"  First row data: {cell_texts}")

            expand_arrows = first_row.locator("span").all()
            for arrow in expand_arrows:
                txt = arrow.text_content().strip()
                if txt in ["▶", "►", "▸"]:
                    print(f"  [OK] Expand arrow found: '{txt}'")
                    break
            else:
                print("  [WARN] No expand arrow found in first row")

    print("  [PASS] History page loaded")


def test_history_expand_row(page):
    print("\n" + "="*60)
    print("TEST 3: History Page Row Expand")
    print("="*60)

    page.goto("http://localhost:3000/history")
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    tables = page.locator("table").all()
    if not tables:
        print("  [FAIL] No table found")
        return

    rows = tables[0].locator("tbody tr").all()
    if not rows:
        print("  [FAIL] No rows found")
        return

    first_data_row = rows[0]
    print("  Clicking first row to expand...")

    first_data_row.click()
    time.sleep(2)

    page.screenshot(path=f"{SCREENSHOT_DIR}/03_history_expanded.png", full_page=True)
    print("  [Screenshot] 03_history_expanded.png")

    all_text = page.locator("body").text_content()
    keywords = ["公司信息", "评分概览", "评分理由", "综合分拆解", "维度拆解", "交易信号",
                "估值分析", "同行对比", "基石投资者", "股票质地", "风险提示", "核心财务",
                "业务分部", "长线视角"]
    found_keywords = [k for k in keywords if k in all_text]
    print(f"  Detail keywords found: {found_keywords}")
    missing_keywords = [k for k in keywords if k not in all_text]
    if missing_keywords:
        print(f"  [WARN] Missing keywords: {missing_keywords}")
    else:
        print("  [OK] All expected detail keywords found!")

    print("  Clicking first row again to collapse...")
    first_data_row.click()
    time.sleep(1)

    page.screenshot(path=f"{SCREENSHOT_DIR}/04_history_collapsed.png", full_page=True)
    print("  [Screenshot] 04_history_collapsed.png")

    all_text_after = page.locator("body").text_content()
    still_visible = [k for k in keywords if k in all_text_after]
    if still_visible:
        print(f"  [WARN] Keywords still visible after collapse: {still_visible}")
    else:
        print("  [OK] Detail content properly collapsed")

    print("  [PASS] Row expand/collapse test completed")


def test_api_endpoints(page):
    print("\n" + "="*60)
    print("TEST 4: API Endpoints")
    print("="*60)

    api_response = page.request.get("http://localhost:8000/api/live/results")
    print(f"  GET /api/live/results: {api_response.status}")
    if api_response.status == 200:
        data = api_response.json()
        if isinstance(data, list):
            print(f"  Results count: {len(data)}")
            if data:
                first = data[0]
                print(f"  First result keys: {list(first.keys())[:15]}...")
                if "_raw" in first:
                    raw_keys = list(first["_raw"].keys()) if isinstance(first["_raw"], dict) else []
                    print(f"  _raw keys count: {len(raw_keys)}")
                    important_fields = ["stock_code", "stock_name", "final_score", "score_breakdown",
                                       "prospectus_info", "lot_size", "board_lot", "hk_offer_shares",
                                       "public_offer_lots"]
                    found = [f for f in important_fields if f in raw_keys]
                    missing = [f for f in important_fields if f not in raw_keys]
                    print(f"  Important fields found in _raw: {found}")
                    if missing:
                        print(f"  [WARN] Missing fields in _raw: {missing}")
                else:
                    print("  [WARN] No _raw field in first result")

    history_response = page.request.get("http://localhost:8000/api/history/records")
    print(f"  GET /api/history/records: {history_response.status}")
    if history_response.status == 200:
        hist_data = history_response.json()
        if isinstance(hist_data, list):
            print(f"  History records count: {len(hist_data)}")
        elif isinstance(hist_data, dict) and "records" in hist_data:
            print(f"  History records count: {len(hist_data['records'])}")
        elif isinstance(hist_data, dict):
            print(f"  History response keys: {list(hist_data.keys())[:10]}")

    print("  [PASS] API endpoint test completed")


def test_console_errors(page):
    print("\n" + "="*60)
    print("TEST 5: Console Errors Check")
    print("="*60)

    errors = []
    warnings = []

    def handle_console(msg):
        if msg.type == "error":
            errors.append(msg.text)
        elif msg.type == "warning":
            warnings.append(msg.text)

    page.on("console", handle_console)

    page.goto("http://localhost:3000")
    page.wait_for_load_state("networkidle")
    time.sleep(2)

    page.goto("http://localhost:3000/history")
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    tables = page.locator("table").all()
    if tables:
        rows = tables[0].locator("tbody tr").all()
        if rows:
            rows[0].click()
            time.sleep(2)

    print(f"  Console errors: {len(errors)}")
    for i, err in enumerate(errors[:10]):
        print(f"    [{i}] {err[:200]}")

    print(f"  Console warnings: {len(warnings)}")
    for i, warn in enumerate(warnings[:5]):
        print(f"    [{i}] {warn[:200]}")

    if not errors:
        print("  [OK] No console errors!")
    else:
        print("  [WARN] Console errors detected")

    print("  [PASS] Console error check completed")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN"
        )
        page = context.new_page()

        try:
            test_homepage(page)
            test_history_page_initial(page)
            test_history_expand_row(page)
            test_api_endpoints(page)
            test_console_errors(page)
        except Exception as e:
            print(f"\n[FATAL ERROR] {e}")
            import traceback
            traceback.print_exc()
            page.screenshot(path=f"{SCREENSHOT_DIR}/error.png", full_page=True)
        finally:
            browser.close()

    print("\n" + "="*60)
    print("ALL TESTS COMPLETED")
    print(f"Screenshots saved to: {SCREENSHOT_DIR}")
    print("="*60)


if __name__ == "__main__":
    main()
