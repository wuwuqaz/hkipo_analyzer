#!/usr/bin/env python3
"""
Enhanced Dogfood Testing Script - More detailed exploration
"""
import time
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

OUTPUT_DIR = Path(__file__).parent / "dogfood-output"
SCREENSHOTS_DIR = OUTPUT_DIR / "screenshots"

SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "http://localhost:8501"

def take_screenshot(page, name):
    """Take a screenshot"""
    path = SCREENSHOTS_DIR / f"{name}.png"
    page.screenshot(path=path, full_page=True)
    print(f"📸 Screenshot saved: {path}")
    return path

def get_page_html(page, name):
    """Get page HTML content"""
    path = SCREENSHOTS_DIR / f"{name}_html.txt"
    content = page.content()
    with open(path, "w") as f:
        f.write(content)
    print(f"📄 HTML saved: {path}")
    return content

def explore_page_structure(page, name):
    """Explore and document page structure"""
    print(f"\n=== Exploring {name} ===")

    # Get title
    title = page.title()
    print(f"Page title: {title}")

    # Get visible text content
    body_text = page.locator("body").inner_text()
    print(f"Body text preview: {body_text[:500]}...")

    # Count elements by type
    elements = {
        "buttons": page.locator("button").count(),
        "inputs": page.locator("input").count(),
        "selects": page.locator("select").count(),
        "tables": page.locator("table").count(),
        "divs": page.locator("div").count(),
        "spans": page.locator("span").count(),
    }
    print(f"Element counts: {elements}")

    return body_text, elements

def test_dashboard_detailed(page):
    """Detailed test of dashboard page"""
    print("\n=== Testing Dashboard Page (Detailed) ===")
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    take_screenshot(page, "dashboard_full")
    body_text, elements = explore_page_structure(page, "Dashboard")

    # Check for Streamlit elements
    st_elements = page.locator("[data-testid='st']").count()
    print(f"Streamlit elements: {st_elements}")

    # Check for specific Streamlit components
    st_buttons = page.locator("button").count()
    st_selectbox = page.locator("[data-testid='stSelectbox']").count()
    st_dataframe = page.locator("[data-testid='stDataFrame']").count()

    print(f"Streamlit buttons: {st_buttons}")
    print(f"Streamlit selectbox: {st_selectbox}")
    print(f"Streamlit dataframe: {st_dataframe}")

    # Check for empty state or data
    if "暂无" in body_text or "没有" in body_text:
        print("⚠️ Page shows empty state message")

    return body_text, elements

def test_upload_detailed(page):
    """Detailed test of upload page"""
    print("\n=== Testing Upload Page (Detailed) ===")
    page.goto(f"{BASE_URL}")
    page.wait_for_load_state("networkidle")

    # Find and click upload navigation
    try:
        # Look for the radio button navigation in sidebar
        sidebar = page.locator("[data-testid='stSidebar']")
        if sidebar.count() > 0:
            sidebar_text = sidebar.inner_text()
            print(f"Sidebar content: {sidebar_text[:300]}")

        # Click on upload option
        upload_radio = page.get_by_text("手动上传分析")
        if upload_radio.count() > 0:
            upload_radio.first.click()
            time.sleep(2)
            take_screenshot(page, "upload_full")
            body_text, elements = explore_page_structure(page, "Upload")

            # Look for file uploader
            file_uploader = page.locator("[data-testid='stFileUploader']")
            if file_uploader.count() > 0:
                print("✓ File uploader found")
            else:
                print("✗ File uploader not found")

            return body_text
    except Exception as e:
        print(f"Error in upload test: {e}")

    return ""

def test_navigation_flow(page):
    """Test complete navigation flow"""
    print("\n=== Testing Navigation Flow ===")

    pages_to_test = [
        ("Dashboard", "🏠"),
        ("Upload", "📤"),
        ("History", "📚"),
        ("Peer Admin", "🧩")
    ]

    results = {}
    for page_name, icon in pages_to_test:
        try:
            page.goto(BASE_URL)
            page.wait_for_load_state("networkidle")
            time.sleep(1)

            # Try to find and click the navigation
            nav_option = page.get_by_text(f"{icon} {page_name}")
            if nav_option.count() > 0:
                nav_option.first.click()
                time.sleep(2)
                take_screenshot(page, f"nav_{page_name.lower().replace(' ', '_')}")
                print(f"✓ {page_name} page navigated and screenshot taken")
                results[page_name] = "success"
            else:
                print(f"✗ {page_name} navigation option not found")
                results[page_name] = "not_found"
        except Exception as e:
            print(f"✗ {page_name} failed: {e}")
            results[page_name] = "error"

    return results

def test_functionality(page):
    """Test actual functionality - buttons, forms, etc."""
    print("\n=== Testing Functionality ===")

    # Go to dashboard
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")
    time.sleep(2)

    # Look for buttons
    buttons = page.locator("button").all()
    print(f"Found {len(buttons)} buttons")
    for i, btn in enumerate(buttons[:5]):  # First 5 buttons
        try:
            btn_text = btn.inner_text()
            print(f"  Button {i+1}: '{btn_text}'")
        except:
            print(f"  Button {i+1}: (could not get text)")

    # Try clicking update button
    try:
        update_btn = page.get_by_text("更新IPO")
        if update_btn.count() > 0:
            print("✓ Found '更新IPO' button")
            # Don't actually click - just verify it exists
    except Exception as e:
        print(f"✗ Error finding update button: {e}")

def test_responsive_design(page):
    """Test different viewport sizes"""
    print("\n=== Testing Responsive Design ===")

    viewports = [
        (1920, 1080, "Desktop"),
        (1366, 768, "Laptop"),
        (768, 1024, "Tablet"),
        (375, 667, "Mobile")
    ]

    for width, height, device in viewports:
        page.set_viewport_size({"width": width, "height": height})
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        take_screenshot(page, f"responsive_{device.lower()}_{width}x{height}")
        print(f"✓ {device} ({width}x{height}) screenshot taken")

def main():
    """Main test runner"""
    print("🎯 Starting Enhanced HKIPO Analyzer Dogfood Test")
    print("=" * 60)

    console_errors = []
    issues = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        # Enable console logging
        page.on("console", lambda msg: console_errors.append({
            "type": msg.type,
            "text": msg.text,
            "url": page.url
        }) if msg.type == "error" else None)

        try:
            # Run tests
            dashboard_text, dashboard_elements = test_dashboard_detailed(page)
            upload_text = test_upload_detailed(page)
            nav_results = test_navigation_flow(page)
            test_functionality(page)
            test_responsive_design(page)

            # Analyze results and identify issues
            if not dashboard_elements.get("tables", 0) and "暂无" not in dashboard_text:
                issues.append({
                    "severity": "medium",
                    "category": "ux",
                    "title": "Dashboard显示问题",
                    "description": "Dashboard页面可能没有显示IPO列表数据，需要确认是空数据还是显示问题",
                    "url": BASE_URL
                })

            if not upload_text:
                issues.append({
                    "severity": "medium",
                    "category": "ux",
                    "title": "上传页面加载问题",
                    "description": "无法获取上传页面的内容，可能页面导航存在问题",
                    "url": f"{BASE_URL}?page=upload"
                })

        except Exception as e:
            print(f"\n❌ Test execution error: {e}")
            issues.append({
                "severity": "critical",
                "category": "functional",
                "description": f"Test execution failed: {e}"
            })

        finally:
            browser.close()

    # Report console errors
    if console_errors:
        print("\n🐛 Console Errors Found:")
        for err in console_errors:
            print(f"  [{err['type']}] {err['text']} @ {err['url']}")
            issues.append({
                "severity": "high",
                "category": "console",
                "description": err['text'],
                "url": err['url']
            })

    # Save test results
    results = {
        "test_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "app_url": BASE_URL,
        "issues_found": len(issues),
        "issues": issues,
        "console_errors": console_errors,
        "screenshots": [str(p) for p in SCREENSHOTS_DIR.glob("*.png")]
    }

    results_file = OUTPUT_DIR / "test_results_detailed.json"
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n📊 Test Results: {len(issues)} issues found")
    print(f"📝 Results saved to: {results_file}")
    print(f"📸 Screenshots saved to: {SCREENSHOTS_DIR}")

    return issues

if __name__ == "__main__":
    main()
