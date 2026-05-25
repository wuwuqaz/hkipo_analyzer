from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})

    # Check homepage with expanded detail
    page.goto('http://localhost:3000')
    page.wait_for_load_state('networkidle')
    
    rows = page.locator('tbody tr')
    if rows.count() > 0:
        rows.first.click()
        page.wait_for_timeout(2000)
        
        # Check for group section headers with colored bars
        headers = page.locator('h3')
        print(f"Found {headers.count()} h3 headers:")
        for i in range(headers.count()):
            text = headers.nth(i).text_content()
            print(f"  - {text}")
        
        # Check for MetricCard grid (should be 3 cols now)
        metric_grid = page.locator('.grid.lg\\:grid-cols-3').first
        if metric_grid:
            print("\nMetricCard grid found with 3 columns")
        
        # Check for ResultSection titles
        section_titles = page.locator('section p.text-xs.font-semibold')
        print(f"\nResultSection titles found ({section_titles.count()}):")
        for i in range(min(section_titles.count(), 20)):
            print(f"  - {section_titles.nth(i).text_content()}")
        
        # Check for colored bar indicators in group headers
        bars = page.locator('span.inline-block.h-5.w-1.rounded-full')
        print(f"\nColored bar indicators: {bars.count()}")
        for i in range(bars.count()):
            bar = bars.nth(i)
            bg = bar.evaluate('el => el.className')
            print(f"  - Bar {i}: {bg}")
        
        # Take focused screenshot of detail area
        detail_section = page.locator('section.mt-8')
        if detail_section.count() > 0:
            detail_section.first.screenshot(path='detail_section.png')
            print("\nDetail section screenshot saved")
    else:
        print("No rows found to expand")

    browser.close()
    print("\nVerification complete!")
