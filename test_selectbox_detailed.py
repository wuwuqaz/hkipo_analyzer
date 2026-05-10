#!/usr/bin/env python3
"""
Detailed test to reproduce the selectbox issue
"""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE_URL = "http://localhost:8501"

def test_selectbox_detailed():
    """Test the selectbox in detail"""
    print("=== Testing IPO Selectbox in Detail ===\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        # Enable console logging
        console_messages = []
        page.on("console", lambda msg: console_messages.append({
            "type": msg.type,
            "text": msg.text
        }) if msg.type in ["error", "warning"] else None)

        try:
            # Navigate to the page
            page.goto(BASE_URL)
            page.wait_for_load_state("networkidle")
            time.sleep(3)

            # Take a screenshot
            page.screenshot(path="dogfood-output/screenshots/test_selectbox_1_initial.png", full_page=True)
            print("📸 Screenshot saved: test_selectbox_1_initial.png")

            # Check if there's IPO data displayed
            page_text = page.locator("body").inner_text()

            # Look for the IPO count
            if "共 1 只正在招股" in page_text:
                print("✅ Found IPO count text: '共 1 只正在招股'")
            else:
                print("❌ IPO count text not found")

            # Look for the IPO in the text
            if "06871" in page_text or "翼菲科技" in page_text:
                print("✅ Found IPO data in page text")
            else:
                print("❌ IPO data not found in page text")

            # Look for the selectbox
            # Streamlit selectbox is rendered with specific attributes
            selectbox_div = page.locator("[data-testid='stSelectbox']")
            if selectbox_div.count() > 0:
                print(f"✅ Found {selectbox_div.count()} selectbox elements")

                # Get the selectbox content
                for i, sb in enumerate(selectbox_div.all()):
                    try:
                        # Try to find the actual select element or div with options
                        options = sb.locator("option").all()
                        if options:
                            print(f"  Selectbox {i+1} has {len(options)} options")
                            for opt in options[:5]:
                                print(f"    - {opt.inner_text()}")
                        else:
                            # Check for aria attributes which Streamlit uses
                            aria_label = sb.get_attribute("aria-label")
                            print(f"  Selectbox {i+1} aria-label: {aria_label}")

                            # Try to find the displayed text
                            displayed = sb.locator("[data-testid='stSelectbox'] label").first
                            if displayed.count() > 0:
                                label_text = displayed.inner_text()
                                print(f"  Selectbox label: {label_text}")

                            # Try clicking to see options
                            print(f"  Attempting to click selectbox to see options...")
                            sb.click()
                            time.sleep(1)

                            # Take screenshot after click
                            page.screenshot(path="dogfood-output/screenshots/test_selectbox_2_after_click.png", full_page=True)
                            print("📸 Screenshot saved: test_selectbox_2_after_click.png")

                            # Try to find option list
                            option_list = page.locator("[data-baseweb='select'] [role='option']")
                            if option_list.count() > 0:
                                print(f"  Found {option_list.count()} dropdown options:")
                                for opt in option_list.all():
                                    print(f"    - {opt.inner_text()}")
                            else:
                                print("  ❌ No dropdown options found after click")
                    except Exception as e:
                        print(f"  ❌ Error checking selectbox {i+1}: {e}")
            else:
                print("❌ No selectbox elements found")

            # Check for the "选择查看详情" section
            detail_section = page.get_by_text("选择查看详情")
            if detail_section.count() > 0:
                print("✅ Found '选择查看详情' section")
            else:
                print("❌ '选择查看详情' section not found")

            # Try to interact with the selectbox using different selectors
            print("\n=== Trying alternative selectors ===")

            # Try finding by label text
            label = page.get_by_text("选择IPO")
            if label.count() > 0:
                print("✅ Found label '选择IPO'")
            else:
                print("❌ Label '选择IPO' not found")

            # Try finding the actual select element
            select = page.locator("select").first
            if select.count() > 0:
                options = select.locator("option").all()
                print(f"Found native select with {len(options)} options")
                for opt in options:
                    print(f"  - {opt.inner_text()}")
            else:
                print("No native select element found")

        except Exception as e:
            print(f"\n❌ Test error: {e}")
            import traceback
            traceback.print_exc()

        finally:
            browser.close()

        # Report console messages
        if console_messages:
            print("\n🐛 Console Messages:")
            for msg in console_messages:
                print(f"  [{msg['type']}] {msg['text']}")

if __name__ == "__main__":
    test_selectbox_detailed()
