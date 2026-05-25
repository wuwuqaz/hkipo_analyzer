from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('http://localhost:3000')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)

    page.screenshot(path='/tmp/home_audit3.png', full_page=True)

    visible_text = page.evaluate('''() => {
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
            acceptNode: function(node) {
                if (node.parentElement && (
                    window.getComputedStyle(node.parentElement).display === 'none' ||
                    window.getComputedStyle(node.parentElement).visibility === 'hidden' ||
                    node.parentElement.tagName === 'SCRIPT' ||
                    node.parentElement.tagName === 'STYLE'
                )) {
                    return NodeFilter.FILTER_REJECT;
                }
                return NodeFilter.FILTER_ACCEPT;
            }
        });
        let text = '';
        while (walker.nextNode()) {
            const t = walker.currentNode.textContent.trim();
            if (t) text += t + ' ';
        }
        return text;
    }''')

    for keyword in ['undefined', 'null', 'NaN']:
        count = visible_text.count(keyword)
        if count > 0:
            print(f'Found "{keyword}" {count} times in VISIBLE text')
            idx = 0
            found = 0
            while found < 5:
                pos = visible_text.find(keyword, idx)
                if pos == -1:
                    break
                start = max(0, pos - 30)
                end = min(len(visible_text), pos + len(keyword) + 30)
                context = visible_text[start:end]
                print(f'  ...{context}...')
                idx = pos + 1
                found += 1

    browser.close()
