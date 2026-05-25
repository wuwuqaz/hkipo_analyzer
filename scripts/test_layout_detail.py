from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})

    page.goto('http://localhost:3000')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)

    rows = page.locator('table tbody tr').all()
    if rows:
        rows[0].click()
        page.wait_for_timeout(3000)

        # Check metric cards layout
        metric_cards = page.locator('article.rounded-3xl').all()
        print(f'Metric cards: {len(metric_cards)}')
        for i, card in enumerate(metric_cards):
            title = card.locator('p').first.text_content().strip()
            value = card.locator('p').nth(1).text_content().strip()
            box = card.bounding_box()
            print(f'  Card {i+1}: {title} = {value} (width={box["width"]:.0f}px)')

        # Check section headings
        headings = page.locator('h3').all()
        print(f'\nSection headings: {len(headings)}')
        for h in headings:
            print(f'  {h.text_content().strip()}')

        # Check grid layout of ResultSections
        grids = page.locator('.grid.lg\\:grid-cols-2').all()
        print(f'\n2-column grids: {len(grids)}')
        for i, grid in enumerate(grids):
            sections = grid.locator('section').all()
            print(f'  Grid {i+1}: {len(sections)} sections side by side')

        # Take focused screenshots of each group
        for i, heading in enumerate(headings):
            heading.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            box = heading.bounding_box()
            if box:
                page.screenshot(path=f'/tmp/group_{i+1}.png', clip={
                    "x": 0,
                    "y": max(0, box["y"] - 10),
                    "width": 1400,
                    "height": 600,
                })
                print(f'  Screenshot group_{i+1}.png saved')

    browser.close()
