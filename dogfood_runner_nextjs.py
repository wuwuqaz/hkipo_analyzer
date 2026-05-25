#!/usr/bin/env python3
"""
Dogfood QA Runner for Next.js Frontend (HK IPO Analyzer)
Systematic exploratory testing using Playwright.
"""
import json
import time
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright, expect

OUTPUT_DIR = Path("./dogfood-output")
SCREENSHOTS_DIR = OUTPUT_DIR / "screenshots"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "http://localhost:3000"
APP_NAME = "HK IPO Analyzer (Next.js Frontend)"


class DogfoodTester:
    def __init__(self):
        self.issues = []
        self.console_logs = []
        self.pages_tested = []
        self.features_tested = []
        self.screenshots = []

    def log_issue(self, title, severity, category, description, url, steps,
                  expected, actual, screenshot=None, console_errors=None):
        self.issues.append({
            "number": len(self.issues) + 1,
            "title": title,
            "severity": severity,
            "category": category,
            "description": description,
            "url": url,
            "steps": steps,
            "expected": expected,
            "actual": actual,
            "screenshot": screenshot,
            "console_errors": console_errors or [],
        })

    def screenshot(self, page, name):
        path = SCREENSHOTS_DIR / f"{name}.png"
        page.screenshot(path=path, full_page=True)
        self.screenshots.append(str(path))
        print(f"  📸 {path.name}")
        return str(path)

    def setup_console_listener(self, page):
        def handle_console(msg):
            entry = {"type": msg.type, "text": msg.text, "url": page.url, "time": datetime.now().isoformat()}
            self.console_logs.append(entry)
            if msg.type == "error":
                print(f"    🐛 Console [{msg.type}]: {msg.text[:150]}")
        page.on("console", handle_console)

        def handle_page_error(err):
            entry = {"type": "pageerror", "text": str(err), "url": page.url, "time": datetime.now().isoformat()}
            self.console_logs.append(entry)
            print(f"    🐛 PageError: {str(err)[:150]}")
        page.on("pageerror", handle_page_error)

    def get_console_errors_for_url(self, url, include_all=False):
        errors = [e for e in self.console_logs if e["url"] == url and e["type"] in ("error", "pageerror")]
        if include_all:
            errors += [e for e in self.console_logs if e["url"] == url and e["type"] == "warning"]
        return errors

    def check_console_errors(self, page, url, context=""):
        errors = self.get_console_errors_for_url(url)
        if errors:
            print(f"    ⚠️ {len(errors)} console error(s) {context}")
            for e in errors[:3]:
                print(f"       - {e['text'][:120]}")
        return errors

    def test_dashboard(self, page):
        print("\n🏠 Testing Dashboard (\/)")
        page.goto(f"{BASE_URL}/")
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        url = page.url
        self.pages_tested.append("Dashboard")
        self.features_tested.extend(["IPO list table", "Filter checkboxes", "Refresh buttons", "IPO detail expand"])

        shot = self.screenshot(page, "01_dashboard")
        errors = self.check_console_errors(page, url, "after load")

        body_text = page.locator("body").inner_text()

        # Check hero section
        if "港股 IPO 打新分析" in body_text:
            print("  ✓ Hero title found")
        else:
            print("  ⚠️ Hero title not found")
            self.log_issue(
                title="Dashboard hero title missing",
                severity="Medium", category="Content",
                description="The main hero title '港股 IPO 打新分析' was not found on the dashboard.",
                url=url, steps=["Navigate to Dashboard"],
                expected="Hero title visible",
                actual="Hero title not found",
                screenshot=shot,
            )

        # Check for table or empty state
        table_exists = page.locator("table").count() > 0
        empty_state = "暂无正在招股" in body_text or "没有匹配" in body_text

        if table_exists:
            print(f"  ✓ Table found with {page.locator('table tbody tr').count()} row(s)")
        elif empty_state:
            print("  ℹ️ Dashboard shows empty state")
        else:
            print("  ⚠️ No table or empty state found")
            self.log_issue(
                title="Dashboard missing IPO table and empty state",
                severity="High", category="Visual",
                description="Dashboard did not render an IPO table nor an empty state message.",
                url=url, steps=["Navigate to Dashboard", "Wait for load"],
                expected="Table with IPO data or empty state message",
                actual="Neither table nor empty state visible",
                screenshot=shot,
                console_errors=[e["text"] for e in errors],
            )

        # Check filter checkboxes
        cb_count = page.locator('input[type="checkbox"]').count()
        print(f"  ✓ Found {cb_count} checkbox(es)")

        # Check buttons
        btn_count = page.locator("button").count()
        print(f"  ✓ Found {btn_count} button(s)")

        # Check navbar
        nav_links = page.locator("nav a").count()
        print(f"  ✓ Found {nav_links} nav link(s)")

        if errors:
            self.log_issue(
                title="Console errors on Dashboard load",
                severity="High" if any("error" in e["type"] for e in errors) else "Medium",
                category="Console",
                description=f"{len(errors)} console error(s) detected on Dashboard load.",
                url=url, steps=["Navigate to Dashboard"],
                expected="No console errors",
                actual=f"{len(errors)} console errors",
                screenshot=shot,
                console_errors=[e["text"] for e in errors],
            )

        return shot

    def test_dashboard_filters(self, page):
        print("\n🔘 Testing Dashboard Filters")
        page.goto(f"{BASE_URL}/")
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        url = page.url
        self.features_tested.append("Filter interactions")

        # Click a filter checkbox
        checkboxes = page.locator('input[type="checkbox"]').all()
        if len(checkboxes) > 0:
            try:
                checkboxes[0].scroll_into_view_if_needed()
                time.sleep(0.5)
                checkboxes[0].click()
                time.sleep(1.5)
                shot = self.screenshot(page, "02_dashboard_filter_active")
                errors = self.check_console_errors(page, url, "after filter click")
                print("  ✓ Filter checkbox clicked")

                # Uncheck it
                checkboxes[0].click()
                time.sleep(1)
                print("  ✓ Filter checkbox unclicked")

                if errors:
                    self.log_issue(
                        title="Console errors when toggling dashboard filters",
                        severity="Medium", category="Console",
                        description="Console errors appeared after clicking a filter checkbox.",
                        url=url, steps=["Navigate to Dashboard", "Click filter checkbox"],
                        expected="No console errors",
                        actual=f"{len(errors)} console errors",
                        screenshot=shot,
                        console_errors=[e["text"] for e in errors],
                    )
                return shot
            except Exception as e:
                print(f"  ⚠️ Error clicking filter: {e}")
                shot = self.screenshot(page, "02_dashboard_filter_error")
                self.log_issue(
                    title="Dashboard filter interaction failed",
                    severity="Medium", category="Functional",
                    description=f"Could not interact with filter checkbox: {e}",
                    url=url, steps=["Navigate to Dashboard", "Attempt to click filter"],
                    expected="Filter checkbox clickable",
                    actual=f"Exception: {e}",
                    screenshot=shot,
                )
                return shot
        else:
            print("  ℹ️ No checkboxes to test")
            return None

    def test_dashboard_detail_expand(self, page):
        print("\n📋 Testing Dashboard IPO Detail Expand")
        page.goto(f"{BASE_URL}/")
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        url = page.url
        self.features_tested.append("IPO detail expand/collapse")

        body_text = page.locator("body").inner_text()
        if "暂无正在招股" in body_text:
            print("  ℹ️ No IPOs to expand")
            return None

        # Try clicking a table row
        rows = page.locator("table tbody tr").all()
        if len(rows) > 0:
            try:
                rows[0].scroll_into_view_if_needed()
                time.sleep(0.5)
                rows[0].click()
                time.sleep(2)
                shot = self.screenshot(page, "03_dashboard_detail_expanded")
                errors = self.check_console_errors(page, url, "after row click")

                body_after = page.locator("body").inner_text()
                detail_found = any(kw in body_after for kw in ["评分分析", "估值与同行", "投资参考", "深度分析"])

                if detail_found:
                    print("  ✓ Detail panel expanded with sections")
                else:
                    print("  ⚠️ Detail panel may not have expanded properly")
                    self.log_issue(
                        title="IPO detail panel not showing expected sections",
                        severity="Medium", category="Functional",
                        description="After clicking an IPO row, expected detail sections were not found.",
                        url=url, steps=["Navigate to Dashboard", "Click first IPO row"],
                        expected="Detail sections visible (评分分析, 估值与同行, etc.)",
                        actual="Detail sections not found",
                        screenshot=shot,
                        console_errors=[e["text"] for e in errors],
                    )

                # Click again to collapse
                rows[0].click()
                time.sleep(1)
                print("  ✓ Row clicked again to collapse")

                if errors:
                    self.log_issue(
                        title="Console errors on IPO detail expand",
                        severity="Medium", category="Console",
                        description="Console errors when expanding IPO detail.",
                        url=url, steps=["Navigate to Dashboard", "Click IPO row"],
                        expected="No console errors",
                        actual=f"{len(errors)} console errors",
                        screenshot=shot,
                        console_errors=[e["text"] for e in errors],
                    )
                return shot
            except Exception as e:
                print(f"  ⚠️ Error expanding row: {e}")
                shot = self.screenshot(page, "03_dashboard_detail_error")
                self.log_issue(
                    title="Cannot expand IPO detail row",
                    severity="High", category="Functional",
                    description=f"Exception when clicking IPO row: {e}",
                    url=url, steps=["Navigate to Dashboard", "Click IPO row"],
                    expected="Row expands to show detail",
                    actual=f"Exception: {e}",
                    screenshot=shot,
                )
                return shot
        else:
            print("  ℹ️ No table rows to test")
            return None

    def test_upload_page(self, page):
        print("\n📤 Testing Upload Page (\/upload)")
        page.goto(f"{BASE_URL}/upload")
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        url = page.url
        self.pages_tested.append("Upload")
        self.features_tested.extend(["File upload form", "Form validation", "PDF upload"])

        shot = self.screenshot(page, "04_upload")
        errors = self.check_console_errors(page, url, "after load")

        body_text = page.locator("body").inner_text()

        if "Upload Prospectus" in body_text:
            print("  ✓ Upload page title found")
        else:
            print("  ⚠️ Upload page title not found")

        # Check form elements
        file_input = page.locator('input[type="file"]')
        text_inputs = page.locator('input[type="text"], input[type="password"]').count()
        submit_btn = page.locator('button[type="submit"]')

        if file_input.count() > 0:
            print("  ✓ File input found")
        else:
            self.log_issue(
                title="File upload input missing",
                severity="High", category="Functional",
                description="The PDF file input is not present on the upload page.",
                url=url, steps=["Navigate to /upload"],
                expected="File input visible",
                actual="No file input found",
                screenshot=shot,
            )

        print(f"  ✓ Found {text_inputs} text/password input(s)")

        if submit_btn.count() > 0:
            print("  ✓ Submit button found")
        else:
            self.log_issue(
                title="Submit button missing on Upload page",
                severity="High", category="Functional",
                description="Submit button not found on upload form.",
                url=url, steps=["Navigate to /upload"],
                expected="Submit button visible",
                actual="No submit button",
                screenshot=shot,
            )

        # Test form validation - submit without file
        if submit_btn.count() > 0:
            try:
                submit_btn.first.click()
                time.sleep(1)
                shot2 = self.screenshot(page, "05_upload_validation")
                body_after = page.locator("body").inner_text()
                if "Please select" in body_after or "PDF" in body_after or "token" in body_after.lower():
                    print("  ✓ Form validation triggered")
                else:
                    print("  ⚠️ Form validation may not have triggered")
                errors_after = self.check_console_errors(page, url, "after submit")
                if errors_after:
                    self.log_issue(
                        title="Console errors on Upload form submit",
                        severity="Medium", category="Console",
                        description="Console errors when submitting empty upload form.",
                        url=url, steps=["Navigate to /upload", "Click submit without file"],
                        expected="No console errors",
                        actual=f"{len(errors_after)} console errors",
                        screenshot=shot2,
                        console_errors=[e["text"] for e in errors_after],
                    )
            except Exception as e:
                print(f"  ⚠️ Error testing form submit: {e}")

        if errors:
            self.log_issue(
                title="Console errors on Upload page load",
                severity="Medium", category="Console",
                description=f"{len(errors)} console error(s) on Upload page load.",
                url=url, steps=["Navigate to /upload"],
                expected="No console errors",
                actual=f"{len(errors)} console errors",
                screenshot=shot,
                console_errors=[e["text"] for e in errors],
            )

        return shot

    def test_history_page(self, page):
        print("\n📚 Testing History Page (\/history)")
        page.goto(f"{BASE_URL}/history")
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        url = page.url
        self.pages_tested.append("History")
        self.features_tested.extend(["History table", "Search filter", "Sort dropdown", "Track status filter", "Expand record detail"])

        shot = self.screenshot(page, "06_history")
        errors = self.check_console_errors(page, url, "after load")

        body_text = page.locator("body").inner_text()

        if "历史 IPO 分析" in body_text:
            print("  ✓ History page title found")
        else:
            print("  ⚠️ History page title not found")

        # Check stats cards
        stats_found = any(kw in body_text for kw in ["历史股票数", "已跟踪", "仍在招股"])
        if stats_found:
            print("  ✓ Stats cards found")
        else:
            print("  ⚠️ Stats cards not found")

        # Check filters
        search_input = page.locator('input[type="text"]').count()
        selects = page.locator("select").count()
        print(f"  ✓ Found {search_input} text input(s), {selects} select(s)")

        # Try typing in search
        search_box = page.locator('input[type="text"]').first
        if search_box.count() > 0:
            try:
                search_box.fill("test")
                time.sleep(1.5)
                shot2 = self.screenshot(page, "07_history_search")
                print("  ✓ Search input filled")
                search_box.fill("")
                time.sleep(1)
            except Exception as e:
                print(f"  ⚠️ Error testing search: {e}")

        # Check table or empty state
        if page.locator("table").count() > 0:
            print(f"  ✓ History table found with {page.locator('table tbody tr').count()} row(s)")
        elif "暂无历史记录" in body_text:
            print("  ℹ️ History shows empty state")
        else:
            print("  ⚠️ No history table or empty state")

        # Try expanding a record row
        rows = page.locator("table tbody tr").all()
        if len(rows) > 1:
            try:
                # Click a row that has the expand arrow (first cell with ▶)
                rows[0].scroll_into_view_if_needed()
                time.sleep(0.5)
                rows[0].click()
                time.sleep(2)
                shot3 = self.screenshot(page, "08_history_expanded")
                body_after = page.locator("body").inner_text()
                if "评分分析" in body_after or "重新分析" in body_after:
                    print("  ✓ History record expanded")
                else:
                    print("  ⚠️ History record may not have expanded")
                rows[0].click()
                time.sleep(1)
            except Exception as e:
                print(f"  ⚠️ Error expanding history row: {e}")

        if errors:
            self.log_issue(
                title="Console errors on History page load",
                severity="Medium", category="Console",
                description=f"{len(errors)} console error(s) on History page load.",
                url=url, steps=["Navigate to /history"],
                expected="No console errors",
                actual=f"{len(errors)} console errors",
                screenshot=shot,
                console_errors=[e["text"] for e in errors],
            )

        return shot

    def test_peers_page(self, page):
        print("\n🧩 Testing Peers Page (\/peers)")
        page.goto(f"{BASE_URL}/peers")
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        url = page.url
        self.pages_tested.append("Peers")
        self.features_tested.extend(["Peer table", "Sector filter", "Subsector filter", "Listed-only filter", "Refresh peers"])

        shot = self.screenshot(page, "09_peers")
        errors = self.check_console_errors(page, url, "after load")

        body_text = page.locator("body").inner_text()

        if "同行库管理" in body_text:
            print("  ✓ Peers page title found")
        else:
            print("  ⚠️ Peers page title not found")

        # Check meta cards
        if any(kw in body_text for kw in ["数据日期", "最近检查", "数据年龄"]):
            print("  ✓ Meta stat cards found")
        else:
            print("  ⚠️ Meta stat cards not found")

        # Check filters
        selects = page.locator("select").count()
        checkboxes = page.locator('input[type="checkbox"]').count()
        print(f"  ✓ Found {selects} select(s), {checkboxes} checkbox(es)")

        # Check table
        if page.locator("table").count() > 0:
            print(f"  ✓ Peer table found with {page.locator('table tbody tr').count()} row(s)")
        elif "同行数据库为空" in body_text:
            print("  ℹ️ Peers database empty")
        else:
            print("  ⚠️ No peer table or empty state")

        # Try changing sector filter if available
        sector_select = page.locator("select").first
        if sector_select.count() > 0:
            options = sector_select.locator("option").all()
            if len(options) > 1:
                try:
                    sector_select.select_option(index=0)
                    time.sleep(1.5)
                    shot2 = self.screenshot(page, "10_peers_filter")
                    print("  ✓ Sector filter changed")
                except Exception as e:
                    print(f"  ⚠️ Error changing sector: {e}")

        if errors:
            self.log_issue(
                title="Console errors on Peers page load",
                severity="Medium", category="Console",
                description=f"{len(errors)} console error(s) on Peers page load.",
                url=url, steps=["Navigate to /peers"],
                expected="No console errors",
                actual=f"{len(errors)} console errors",
                screenshot=shot,
                console_errors=[e["text"] for e in errors],
            )

        return shot

    def test_reanalyze_page(self, page):
        print("\n🔁 Testing Reanalyze Page (\/reanalyze)")
        page.goto(f"{BASE_URL}/reanalyze")
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        url = page.url
        self.pages_tested.append("Reanalyze")
        self.features_tested.extend(["Reanalyze form", "Query param prefill"])

        shot = self.screenshot(page, "11_reanalyze")
        errors = self.check_console_errors(page, url, "after load")

        body_text = page.locator("body").inner_text()

        if "重新分析" in body_text or "Reanalyze" in body_text:
            print("  ✓ Reanalyze page loaded")
        else:
            print("  ⚠️ Reanalyze page title not found")

        # Test with query params
        page.goto(f"{BASE_URL}/reanalyze?stock_code=01234&company_name=Test%20Company")
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        shot2 = self.screenshot(page, "12_reanalyze_prefilled")
        errors2 = self.check_console_errors(page, page.url, "after query params")
        print("  ✓ Tested with query params")

        all_errors = errors + errors2
        if all_errors:
            self.log_issue(
                title="Console errors on Reanalyze page load",
                severity="Medium", category="Console",
                description=f"{len(all_errors)} console error(s) on Reanalyze page load.",
                url=url, steps=["Navigate to /reanalyze", "Navigate with query params"],
                expected="No console errors",
                actual=f"{len(all_errors)} console errors",
                screenshot=shot,
                console_errors=[e["text"] for e in all_errors],
            )

        return shot

    def test_jobs_page(self, page):
        print("\n💼 Testing Jobs Page (\/jobs\/nonexistent)")
        page.goto(f"{BASE_URL}/jobs/nonexistent-id")
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        url = page.url
        self.pages_tested.append("Jobs (detail)")
        self.features_tested.append("Job status polling")

        shot = self.screenshot(page, "13_jobs_nonexistent")
        errors = self.check_console_errors(page, url, "after load")

        body_text = page.locator("body").inner_text()
        if "not found" in body_text.lower() or "不存在" in body_text or "错误" in body_text:
            print("  ✓ Proper error state for non-existent job")
        elif "分析中" in body_text or "loading" in body_text.lower():
            print("  ℹ️ Shows loading state for job")
        else:
            print("  ⚠️ Unexpected content for non-existent job")

        if errors:
            self.log_issue(
                title="Console errors on Jobs page",
                severity="Low", category="Console",
                description=f"{len(errors)} console error(s) on Jobs page with non-existent ID.",
                url=url, steps=["Navigate to /jobs/nonexistent-id"],
                expected="No console errors",
                actual=f"{len(errors)} console errors",
                screenshot=shot,
                console_errors=[e["text"] for e in errors],
            )

        return shot

    def test_navigation(self, page):
        print("\n🧭 Testing Navigation (Navbar)")
        page.goto(f"{BASE_URL}/")
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        self.features_tested.append("Navbar navigation")

        nav_items = [
            ("/", "Dashboard"),
            ("/upload", "Upload"),
            ("/history", "History"),
            ("/peers", "Peers"),
            ("/reanalyze", "Reanalyze"),
        ]

        for href, label in nav_items:
            try:
                nav_link = page.locator(f"nav a[href='{href}']")
                if nav_link.count() > 0:
                    nav_link.first.click()
                    time.sleep(1.5)
                    print(f"  ✓ Navigated to {label}")
                else:
                    print(f"  ⚠️ Nav link for {label} not found")
                    self.log_issue(
                        title=f"Navbar link missing: {label}",
                        severity="High", category="Functional",
                        description=f"The navbar link to {label} ({href}) was not found.",
                        url=page.url, steps=["Navigate to home", f"Look for nav link to {href}"],
                        expected=f"Nav link to {label} visible",
                        actual="Nav link not found",
                        screenshot=self.screenshot(page, f"14_nav_missing_{label.lower()}") if nav_link.count() == 0 else None,
                    )
            except Exception as e:
                print(f"  ⚠️ Error navigating to {label}: {e}")

        shot = self.screenshot(page, "15_nav_end")
        return shot

    def test_responsive(self, page):
        print("\n📱 Testing Responsive Viewports")
        viewports = [
            (1920, 1080, "desktop"),
            (1366, 768, "laptop"),
            (768, 1024, "tablet"),
            (375, 667, "mobile"),
        ]
        self.features_tested.append("Responsive layout")

        for w, h, name in viewports:
            page.set_viewport_size({"width": w, "height": h})
            page.goto(f"{BASE_URL}/")
            page.wait_for_load_state("networkidle")
            time.sleep(2)
            shot = self.screenshot(page, f"16_responsive_{name}_{w}x{h}")
            print(f"  ✓ {name} ({w}x{h})")

            # Check for horizontal scroll (indicates overflow)
            has_scroll = page.evaluate("() => document.documentElement.scrollWidth > window.innerWidth")
            if has_scroll and name in ("tablet", "mobile"):
                self.log_issue(
                    title=f"Horizontal overflow on {name} viewport",
                    severity="Medium", category="Visual",
                    description=f"Page has horizontal scroll at {w}x{h} viewport, indicating layout overflow.",
                    url=page.url, steps=[f"Set viewport to {w}x{h}", "Navigate to Dashboard"],
                    expected="No horizontal scroll",
                    actual="Horizontal scroll detected",
                    screenshot=shot,
                )

    def test_keyboard_navigation(self, page):
        print("\n⌨️ Testing Keyboard Navigation")
        page.goto(f"{BASE_URL}/")
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        self.features_tested.append("Keyboard navigation")

        # Tab through nav links
        for _ in range(8):
            page.keyboard.press("Tab")
            time.sleep(0.3)

        active = page.evaluate("() => document.activeElement?.tagName + ' ' + (document.activeElement?.getAttribute('href') || document.activeElement?.innerText?.slice(0,30) || '')")
        print(f"  ✓ Tabbed to: {active}")

        shot = self.screenshot(page, "17_keyboard_focus")
        return shot

    def test_scroll_and_layout(self, page):
        print("\n📜 Testing Scroll and Long Page Layout")
        page.goto(f"{BASE_URL}/")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # Scroll to bottom
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)
        shot = self.screenshot(page, "18_scrolled_bottom")
        print("  ✓ Scrolled to bottom")

        # Scroll back to top
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(0.5)
        return shot

    def generate_report(self):
        print("\n📝 Generating Report...")
        sev_counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
        for issue in self.issues:
            sev_counts[issue["severity"]] = sev_counts.get(issue["severity"], 0) + 1

        total = len(self.issues)
        if total == 0:
            assessment = "No issues found during testing."
        else:
            severity_order = ["Low", "Medium", "High", "Critical"]
            most_severe = max(self.issues, key=lambda x: severity_order.index(x["severity"]))["severity"]
            assessment = f"Found {total} issue(s). Most severe: {most_severe}."

        issues_md = ""
        for issue in self.issues:
            console_items = ["- `{}`".format(e) for e in issue["console_errors"]] if issue["console_errors"] else ["None"]
            console_str = "\n".join(console_items)
            screenshot_line = "**Screenshot:**\nMEDIA:{}\n".format(issue["screenshot"]) if issue["screenshot"] else ""
            steps_items = ["{}. {}".format(i+1, s) for i, s in enumerate(issue["steps"])]
            steps_str = "\n".join(steps_items)
            issues_md += (
                "### Issue #{}: {}\n\n".format(issue["number"], issue["title"]) +
                "| Field | Value |\n|-------|-------|\n" +
                "| **Severity** | {} |\n".format(issue["severity"]) +
                "| **Category** | {} |\n".format(issue["category"]) +
                "| **URL** | {} |\n\n".format(issue["url"]) +
                "**Description:**\n{}\n\n".format(issue["description"]) +
                "**Steps to Reproduce:**\n{}\n\n".format(steps_str) +
                "**Expected Behavior:**\n{}\n\n".format(issue["expected"]) +
                "**Actual Behavior:**\n{}\n\n".format(issue["actual"]) +
                screenshot_line +
                "**Console Errors** (if applicable):\n{}\n\n---\n\n".format(console_str)
            )

        summary_table = "| # | Title | Severity | Category | URL |\n|---|-------|----------|----------|-----|\n"
        for issue in self.issues:
            summary_table += "| {} | {} | {} | {} | {} |\n".format(
                issue["number"], issue["title"], issue["severity"], issue["category"], issue["url"]
            )

        pages_items = ["- {}".format(p) for p in sorted(set(self.pages_tested))]
        pages_list = "\n".join(pages_items)
        features_items = ["- {}".format(f) for f in sorted(set(self.features_tested))]
        features_list = "\n".join(features_items)
        errors_count = len([e for e in self.console_logs if e["type"] in ("error", "pageerror")])
        warnings_count = len([e for e in self.console_logs if e["type"] == "warning"])

        report_lines = [
            "# Dogfood Report: {}".format(APP_NAME),
            "",
            "| Field | Value |",
            "|-------|-------|",
            "| **Date** | {} |".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
            "| **App URL** | {} |".format(BASE_URL),
            "| **Scope** | Full site testing - all pages, navigation, forms, filters, responsive |",
            "| **Tester** | Dogfood Agent (automated exploratory QA) |",
            "",
            "## Summary",
            "",
            "| Severity | Count |",
            "|----------|-------|",
            "| 🔴 Critical | {} |".format(sev_counts['Critical']),
            "| 🟠 High | {} |".format(sev_counts['High']),
            "| 🟡 Medium | {} |".format(sev_counts['Medium']),
            "| 🔵 Low | {} |".format(sev_counts['Low']),
            "| **Total** | **{}** |".format(total),
            "",
            "**Overall Assessment:** {}".format(assessment),
            "",
            "## Issues",
            "",
            issues_md if self.issues else "_No issues found during testing._\n",
            "",
            "## Issues Summary Table",
            "",
            summary_table if self.issues else "_No issues._\n",
            "",
            "## Testing Coverage",
            "",
            "### Pages Tested",
            pages_list,
            "",
            "### Features Tested",
            features_list,
            "",
            "### Not Tested / Out of Scope",
            "- Actual PDF upload and analysis (requires real PDF file)",
            "- API token-authenticated operations (refresh IPOs, track records, refresh peers)",
            "- File download flows",
            "- WebSocket / real-time updates",
            "- End-to-end analysis job completion",
            "",
            "### Blockers",
            "- None",
            "",
            "## Console Errors Summary",
            "",
            "Total console entries logged: {}".format(len(self.console_logs)),
            "Errors: {}".format(errors_count),
            "Warnings: {}".format(warnings_count),
            "",
            "## Notes",
            "",
            "- Application is a Next.js 15+ frontend with App Router.",
            "- Dark theme UI with CSS custom properties (var(--accent), var(--danger), etc.).",
            "- All screenshots saved to `{}`.".format(SCREENSHOTS_DIR),
            "",
        ]
        report = "\n".join(report_lines)

        report_path = OUTPUT_DIR / "report.md"
        report_path.write_text(report, encoding="utf-8")
        print("  📄 Report saved: {}".format(report_path))

        json_path = OUTPUT_DIR / "test_results.json"
        json_path.write_text(json.dumps({
            "app_name": APP_NAME,
            "url": BASE_URL,
            "date": datetime.now().isoformat(),
            "issues": self.issues,
            "console_logs": self.console_logs,
            "pages_tested": list(set(self.pages_tested)),
            "features_tested": list(set(self.features_tested)),
            "screenshots": self.screenshots,
        }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print("  📄 JSON saved: {}".format(json_path))

        return report_path

    def run(self):
        print("🎯 Starting Dogfood QA Test")
        print("=" * 60)
        print(f"Target: {BASE_URL}")
        print(f"Output: {OUTPUT_DIR}")
        print("=" * 60)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1920, "height": 1080})
            page = context.new_page()
            self.setup_console_listener(page)

            try:
                self.test_dashboard(page)
                self.test_dashboard_filters(page)
                self.test_dashboard_detail_expand(page)
                self.test_upload_page(page)
                self.test_history_page(page)
                self.test_peers_page(page)
                self.test_reanalyze_page(page)
                self.test_jobs_page(page)
                self.test_navigation(page)
                self.test_responsive(page)
                self.test_keyboard_navigation(page)
                self.test_scroll_and_layout(page)
            except Exception as e:
                print(f"\n❌ Test execution error: {e}")
                import traceback
                traceback.print_exc()
            finally:
                browser.close()

        report_path = self.generate_report()
        print(f"\n📊 Done. {len(self.issues)} issue(s) found.")
        return report_path


if __name__ == "__main__":
    tester = DogfoodTester()
    tester.run()
