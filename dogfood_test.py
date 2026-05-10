#!/usr/bin/env python3
"""
Dogfood Testing Script for HKIPO Analyzer
Tests all pages and features of the Streamlit application
"""
import time
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

OUTPUT_DIR = Path(__file__).parent / "dogfood-output"
SCREENSHOTS_DIR = OUTPUT_DIR / "screenshots"
VIDEOS_DIR = OUTPUT_DIR / "videos"

SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "http://localhost:8501"

def take_screenshot(page, name, annotate=False):
    """Take a screenshot with optional annotation"""
    path = SCREENSHOTS_DIR / f"{name}.png"
    page.screenshot(path=path)
    print(f"📸 Screenshot saved: {path}")
    return path

def test_dashboard_page(page):
    """Test the main Dashboard page"""
    print("\n=== Testing Dashboard Page ===")
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")
    time.sleep(2)

    take_screenshot(page, "dashboard_initial", annotate=True)

    # Check for IPO list
    try:
        page.wait_for_selector("table", timeout=5000)
        print("✓ IPO list table found")
    except:
        print("✗ IPO list table not found")

    # Check for filters
    try:
        page.wait_for_selector('input[type="checkbox"]', timeout=3000)
        print("✓ Filter controls found")
    except:
        print("✗ Filter controls not found")

    # Check console errors
    console_logs = []
    page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}") if msg.type == "error" else None)
    time.sleep(1)

    return console_logs

def test_upload_page(page):
    """Test the Upload page"""
    print("\n=== Testing Upload Page ===")
    page.goto(f"{BASE_URL}?page=upload")
    page.wait_for_load_state("networkidle")
    time.sleep(2)

    take_screenshot(page, "upload_page", annotate=True)

    # Check for file upload
    try:
        file_input = page.locator('input[type="file"]')
        if file_input.count() > 0:
            print("✓ File upload input found")
        else:
            print("✗ File upload input not found")
    except Exception as e:
        print(f"✗ Error checking file upload: {e}")

def test_history_page(page):
    """Test the History page"""
    print("\n=== Testing History Page ===")
    page.goto(f"{BASE_URL}?page=history")
    page.wait_for_load_state("networkidle")
    time.sleep(2)

    take_screenshot(page, "history_page", annotate=True)

    # Check for history list
    try:
        page.wait_for_selector("table", timeout=5000)
        print("✓ History table found")
    except:
        print("✗ History table not found")

def test_peer_admin_page(page):
    """Test the Peer Admin page"""
    print("\n=== Testing Peer Admin Page ===")
    page.goto(f"{BASE_URL}?page=peer_admin")
    page.wait_for_load_state("networkidle")
    time.sleep(2)

    take_screenshot(page, "peer_admin_page", annotate=True)

    # Check for peer data table
    try:
        page.wait_for_selector("table", timeout=5000)
        print("✓ Peer data table found")
    except:
        print("✗ Peer data table not found")

def test_ipo_detail(page):
    """Test clicking on an IPO to view details"""
    print("\n=== Testing IPO Detail View ===")

    # Go to dashboard first
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")
    time.sleep(2)

    # Try to find and click on an IPO row
    try:
        # Look for expandable rows or links
        first_row = page.locator("table tbody tr").first
        if first_row.count() > 0:
            print("✓ Found IPO table rows")
            first_row.click()
            time.sleep(3)
            take_screenshot(page, "ipo_detail", annotate=True)
        else:
            print("✗ No IPO rows found to click")
    except Exception as e:
        print(f"✗ Error clicking IPO: {e}")

def test_navigation(page):
    """Test sidebar navigation"""
    print("\n=== Testing Navigation ===")

    pages = [
        ("Dashboard", BASE_URL),
        ("Upload", f"{BASE_URL}?page=upload"),
        ("History", f"{BASE_URL}?page=history"),
        ("Peer Admin", f"{BASE_URL}?page=peer_admin")
    ]

    for page_name, url in pages:
        try:
            page.goto(url)
            page.wait_for_load_state("networkidle")
            time.sleep(1)
            print(f"✓ {page_name} page loaded")
        except Exception as e:
            print(f"✗ {page_name} page failed: {e}")

def main():
    """Main test runner"""
    print("🎯 Starting HKIPO Analyzer Dogfood Test")
    print("=" * 60)

    issues = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        # Enable console logging
        console_errors = []
        page.on("console", lambda msg: console_errors.append({
            "type": msg.type,
            "text": msg.text,
            "url": page.url
        }) if msg.type == "error" else None)

        try:
            # Run all tests
            test_dashboard_page(page)
            test_upload_page(page)
            test_history_page(page)
            test_peer_admin_page(page)
            test_ipo_detail(page)
            test_navigation(page)

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
        "console_errors": console_errors
    }

    results_file = OUTPUT_DIR / "test_results.json"
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n📊 Test Results: {len(issues)} issues found")
    print(f"📝 Results saved to: {results_file}")
    print(f"📸 Screenshots saved to: {SCREENSHOTS_DIR}")

    return issues

if __name__ == "__main__":
    main()
