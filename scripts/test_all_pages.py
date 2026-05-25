"""
Comprehensive page testing script for HKIPO Analyzer.
Visits all pages, takes screenshots, and checks data loading.
"""
import json
import os
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

OUTPUT_DIR = Path("/tmp/hkipo_test_screenshots")
OUTPUT_DIR.mkdir(exist_ok=True)

PAGES_TO_TEST = [
    {"url": "http://localhost:3000/", "name": "home", "description": "首页"},
    {"url": "http://localhost:3000/upload", "name": "upload", "description": "上传页面"},
    {"url": "http://localhost:3000/history", "name": "history", "description": "历史分析"},
    {"url": "http://localhost:3000/peers", "name": "peers", "description": "可比公司"},
    {"url": "http://localhost:3000/reanalyze", "name": "reanalyze", "description": "重新分析"},
]

API_ENDPOINTS = [
    {"url": "http://localhost:8000/api/health", "name": "health"},
    {"url": "http://localhost:8000/api/live/results", "name": "live_results"},
    {"url": "http://localhost:8000/api/live/status", "name": "live_status"},
    {"url": "http://localhost:8000/api/history/records", "name": "history_api"},
    {"url": "http://localhost:8000/api/peers", "name": "peers_api"},
    {"url": "http://localhost:8000/api/peers/meta", "name": "peers_meta_api"},
]

results = []

def check_api_endpoints(page):
    """Check API endpoints return valid data."""
    print("\n=== 检查 API 端点 ===")
    api_results = []
    
    for endpoint in API_ENDPOINTS:
        try:
            response = page.request.get(endpoint["url"])
            status = response.status
            try:
                body = response.json()
                has_data = bool(body)
                data_preview = str(body)[:200]
            except:
                has_data = False
                data_preview = response.text()[:200]
            
            result = {
                "endpoint": endpoint["name"],
                "url": endpoint["url"],
                "status": status,
                "has_data": has_data,
                "data_preview": data_preview,
                "ok": status == 200
            }
            api_results.append(result)
            
            status_icon = "✅" if result["ok"] else "❌"
            print(f"{status_icon} {endpoint['name']}: HTTP {status}, 有数据: {has_data}")
            
        except Exception as e:
            result = {
                "endpoint": endpoint["name"],
                "url": endpoint["url"],
                "status": 0,
                "has_data": False,
                "data_preview": str(e),
                "ok": False
            }
            api_results.append(result)
            print(f"❌ {endpoint['name']}: 错误 - {e}")
    
    return api_results

def check_page(page, page_config):
    """Check a single page for data loading."""
    print(f"\n=== 检查页面: {page_config['description']} ({page_config['url']}) ===")
    
    page.goto(page_config["url"], wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)  # Additional wait for dynamic content
    
    screenshot_path = OUTPUT_DIR / f"{page_config['name']}.png"
    page.screenshot(path=str(screenshot_path), full_page=True)
    print(f"📸 截图: {screenshot_path}")
    
    # Get page content info
    title = page.title()
    content = page.content()
    
    # Check for various data indicators
    checks = {
        "has_title": bool(title),
        "title": title,
        "has_content": len(content) > 100,
        "content_length": len(content),
        "has_errors": False,
        "error_messages": [],
        "data_elements": {},
    }
    
    # Check for console errors
    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    
    # Check for loading states
    loading_selectors = [
        '[data-testid="loading"]',
        '.loading',
        '.spinner',
        'text=加载中',
        'text=Loading',
    ]
    
    is_loading = False
    for selector in loading_selectors:
        try:
            if page.locator(selector).first.is_visible(timeout=1000):
                is_loading = True
                checks["error_messages"].append(f"仍在加载中: {selector}")
                break
        except:
            pass
    
    # Check for empty states
    empty_selectors = [
        'text=暂无数据',
        'text=没有记录',
        'text=Empty',
        'text=No data',
    ]
    
    is_empty = False
    for selector in empty_selectors:
        try:
            if page.get_by_text(selector).first.is_visible(timeout=1000):
                is_empty = True
                checks["error_messages"].append(f"空状态: {selector}")
                break
        except:
            pass
    
    # Check for data elements based on page type
    if page_config["name"] == "home":
        # Check for main content areas
        data_elements = {
            "has_main_content": page.locator("main").count() > 0,
            "has_heading": page.locator("h1, h2").count() > 0,
            "has_cards": page.locator('[class*="card"]').count() > 0 or page.locator("section").count() > 0,
        }
        checks["data_elements"] = data_elements
    
    elif page_config["name"] == "history":
        # Check for history table/list
        data_elements = {
            "has_table": page.locator("table").count() > 0,
            "has_rows": page.locator("tbody tr").count() > 0,
            "row_count": page.locator("tbody tr").count(),
            "has_pagination": page.locator('[class*="pagination"]').count() > 0,
        }
        checks["data_elements"] = data_elements
    
    elif page_config["name"] == "peers":
        # Check for peer comparison data
        data_elements = {
            "has_table": page.locator("table").count() > 0,
            "has_peer_data": page.locator("tbody tr").count() > 0,
            "peer_count": page.locator("tbody tr").count(),
        }
        checks["data_elements"] = data_elements
    
    elif page_config["name"] == "upload":
        # Check for upload form
        data_elements = {
            "has_upload_button": page.locator('input[type="file"]').count() > 0,
            "has_form": page.locator("form").count() > 0,
            "has_instructions": page.locator('text=上传').count() > 0,
        }
        checks["data_elements"] = data_elements
    
    elif page_config["name"] == "reanalyze":
        # Check for reanalysis options
        data_elements = {
            "has_form": page.locator("form").count() > 0,
            "has_select": page.locator("select").count() > 0,
            "has_submit": page.locator('button[type="submit"]').count() > 0,
        }
        checks["data_elements"] = data_elements
    
    # Check for network errors in console
    console_logs = []
    page.on("console", lambda msg: console_logs.append({"type": msg.type, "text": msg.text}))
    
    # Determine overall status
    has_issues = is_loading or is_empty or checks["has_errors"]
    status = "⚠️ 警告" if has_issues else "✅ 正常"
    if not checks["has_content"]:
        status = "❌ 异常"
    
    print(f"标题: {title}")
    print(f"内容长度: {checks['content_length']}")
    print(f"加载中: {is_loading}")
    print(f"空状态: {is_empty}")
    print(f"数据元素: {json.dumps(data_elements, ensure_ascii=False, indent=2)}")
    print(f"状态: {status}")
    
    return {
        "page": page_config["name"],
        "description": page_config["description"],
        "url": page_config["url"],
        "screenshot": str(screenshot_path),
        "title": title,
        "status": status,
        "checks": checks,
        "is_loading": is_loading,
        "is_empty": is_empty,
    }

def main():
    print("开始 HKIPO Analyzer 全面页面测试...")
    print(f"截图输出目录: {OUTPUT_DIR}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            locale="zh-CN",
        )
        
        # Enable console logging
        page = context.new_page()
        
        # First check API endpoints
        api_results = check_api_endpoints(page)
        
        # Then check each page
        page_results = []
        for page_config in PAGES_TO_TEST:
            try:
                result = check_page(page, page_config)
                page_results.append(result)
            except Exception as e:
                print(f"❌ 页面 {page_config['name']} 检查失败: {e}")
                page_results.append({
                    "page": page_config["name"],
                    "description": page_config["description"],
                    "url": page_config["url"],
                    "status": "❌ 异常",
                    "error": str(e),
                })
        
        browser.close()
    
    # Generate summary report
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    
    print("\nAPI 端点:")
    for api in api_results:
        icon = "✅" if api["ok"] else "❌"
        print(f"  {icon} {api['endpoint']}: HTTP {api['status']}")
    
    print("\n页面检查:")
    for page_result in page_results:
        print(f"  {page_result['status']} {page_result['description']} ({page_result['url']})")
        if page_result.get("error"):
            print(f"    错误: {page_result['error']}")
    
    # Count issues
    total_pages = len(page_results)
    ok_pages = sum(1 for p in page_results if "✅" in p.get("status", ""))
    warn_pages = sum(1 for p in page_results if "⚠️" in p.get("status", ""))
    fail_pages = sum(1 for p in page_results if "❌" in p.get("status", ""))
    
    print(f"\n总计: {total_pages} 个页面")
    print(f"✅ 正常: {ok_pages}")
    print(f"⚠️ 警告: {warn_pages}")
    print(f"❌ 异常: {fail_pages}")
    
    # Save detailed results
    report_path = OUTPUT_DIR / "test_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "api_results": api_results,
            "page_results": page_results,
            "summary": {
                "total": total_pages,
                "ok": ok_pages,
                "warning": warn_pages,
                "failed": fail_pages,
            }
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n详细报告: {report_path}")
    print(f"截图目录: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
