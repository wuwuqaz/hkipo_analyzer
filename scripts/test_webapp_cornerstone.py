#!/usr/bin/env python3
"""测试前端基石分析显示。"""

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1920, 'height': 4000})
    
    # 访问历史页面
    page.goto('http://localhost:3000/history')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(2000)
    
    # 搜索剂泰科技
    search_input = page.locator('input[type="text"]').first
    if search_input.is_visible():
        search_input.fill('剂泰')
        page.wait_for_timeout(1000)
    
    # 点击剂泰科技的行（通过股票代码）
    stock_link = page.locator('text=07666').first
    if stock_link.is_visible():
        stock_link.click()
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(3000)
        
        # 截取全页面，但放大显示
        page.evaluate('document.body.style.zoom = "150%"')
        page.wait_for_timeout(500)
        
        # 滚动到页面中间部分
        page.evaluate('window.scrollTo(0, document.body.scrollHeight * 0.4)')
        page.wait_for_timeout(500)
        page.screenshot(path='/tmp/webapp_detail_mid.png')
        print("详情页面中部截图已保存到 /tmp/webapp_detail_mid.png")
        
        # 滚动到页面底部
        page.evaluate('window.scrollTo(0, document.body.scrollHeight * 0.7)')
        page.wait_for_timeout(500)
        page.screenshot(path='/tmp/webapp_detail_bottom.png')
        print("详情页面底部截图已保存到 /tmp/webapp_detail_bottom.png")
        
        # 再往下滚动
        page.evaluate('window.scrollTo(0, document.body.scrollHeight * 0.9)')
        page.wait_for_timeout(500)
        page.screenshot(path='/tmp/webapp_detail_end.png')
        print("详情页面末尾截图已保存到 /tmp/webapp_detail_end.png")
    else:
        print("未找到剂泰科技的链接")
        page.screenshot(path='/tmp/webapp_debug.png', full_page=True)
    
    browser.close()
