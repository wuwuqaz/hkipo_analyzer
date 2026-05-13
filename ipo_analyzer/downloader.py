import re
import os
import random
import time
import logging
import subprocess
import tempfile
from html import unescape
from types import SimpleNamespace
from datetime import datetime

import httpx

from .utils import _normalize_company_name, _normalize_stock_code
from .settings import SETTINGS

logger = logging.getLogger(__name__)


def _retry_request(method, url, max_retries=None, backoff_factor=None, **kwargs):
    nc = SETTINGS.network
    max_retries = max_retries if max_retries is not None else nc.max_retries
    backoff_factor = backoff_factor if backoff_factor is not None else nc.backoff_factor
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            kwargs.setdefault('timeout', nc.default_timeout)
            response = method(url, **kwargs)
            if response.status_code < 500:
                return response
            last_error = RuntimeError(f"HTTP {response.status_code}")
        except httpx.ConnectError as e:
            # SSL 错误时回退到不验证证书
            if kwargs.get('verify') is not False and 'ssl' in str(e).lower():
                logger.warning("SSL验证失败，尝试跳过证书验证: %s", e)
                kwargs['verify'] = False
                continue
            last_error = e
        except Exception as e:
            last_error = e
        if attempt < max_retries:
            wait = backoff_factor ** attempt + random.uniform(0, backoff_factor * 0.5)
            time.sleep(wait)
    raise last_error




class AiPOMarginClient:
    """AiPO孖展数据客户端"""
    
    def __init__(self):
        self.base_url = "https://aipo.myiqdii.com"
        self.jyb_api = "https://jybdata.iqdii.com"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "X-Requested-With": "XMLHttpRequest"
        }
        self.token = None
        self.last_error = None
    
    def _fetch_page_with_token(self):
        """从页面获取Token"""
        try:
            response = _retry_request(httpx.get, f"{self.base_url}/margin/index", headers=self.headers, timeout=SETTINGS.network.default_timeout)
            if response.status_code == 200:
                match = re.search(r'name="__RequestVerificationToken"\s+type="hidden"\s+value="([^"]+)"', response.text)
                if match:
                    self.token = match.group(1).strip()
                    return True
                self.last_error = "获取Token失败: 页面中未找到Token"
            else:
                self.last_error = f"获取Token失败: HTTP {response.status_code}"
        except Exception as e:
            self.last_error = f"获取Token失败: {e}"
            logger.warning("获取Token失败: %s", e)
        return False
    
    def fetch_live_ipos(self):
        """获取正在招股的IPO列表"""
        self.last_error = None
        logger.info("\n【获取最新招股列表】")
        logger.info("="*60)
        
        if not self.token:
            if not self._fetch_page_with_token():
                self.last_error = self.last_error or "无法获取Token"
                logger.error("✗ 无法获取Token")
                return []
        
        api_headers = self.headers.copy()
        api_headers["Referer"] = f"{self.base_url}/margin/index"
        api_headers["RequestVerificationToken"] = self.token
        
        try:
            params = {"sector": "", "pageIndex": 1, "pageSize": SETTINGS.network.margin_page_size}
            response = _retry_request(httpx.get, f"{self.base_url}/Home/GetMarginList", params=params, headers=api_headers, timeout=30)
            
            if response.status_code != 200:
                self.last_error = f"获取招股列表失败: HTTP {response.status_code}"
                return []

            data = response.json()
            if data.get("result") != 1:
                self.last_error = data.get("message") or data.get("msg") or "获取招股列表接口返回异常"
                return []

            items = data.get("data", {})
            if isinstance(items, dict):
                items = items.get("dataList", []) or []
            
            logger.info("✓ 获取到 %d 个IPO项目", len(items))
            
            live_ipos = []
            now = datetime.now()
            
            for item in items:
                stock_code = item.get('symbol', '') or item.get('stockCode', '')
                company_name = item.get('shortname', '') or item.get('shortName', '') or item.get('name', '')
                apply_end_str = item.get('enddate', '') or item.get('EndDate', '')
                
                if apply_end_str:
                    try:
                        if 'T' in apply_end_str:
                            apply_end = datetime.strptime(apply_end_str.split('T')[0], '%Y-%m-%d')
                        else:
                            apply_end = datetime.strptime(apply_end_str.split(' ')[0], '%Y-%m-%d')
                        
                        if apply_end.date() >= now.date():
                            live_ipos.append(item)
                            logger.info("  ✓ %s (%s) - 招股中", company_name, stock_code)
                        else:
                            logger.info("  ✗ %s (%s) - 已结束", company_name, stock_code)
                    except Exception:
                        live_ipos.append(item)
                else:
                    live_ipos.append(item)

            return live_ipos
        except Exception as e:
            self.last_error = f"获取招股列表失败: {e}"
            logger.error("✗ 获取招股列表失败: %s", e)
        
        return []

    def fetch_margin_detail(self, stock_code):
        """获取孖展详情，包含资金总计、公开集资额与超购数据"""
        try:
            payload = {
                "code": f"E{stock_code}",
                "session": "",
                "uid": ""
            }
            response = _retry_request(
                httpx.post,
                f"{self.jyb_api}/jybapp/F10Service/MarginInfo?v={datetime.now().timestamp()}&lang=cht",
                json=payload,
                timeout=SETTINGS.network.default_timeout,
                headers={
                    "User-Agent": self.headers["User-Agent"],
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            if response.status_code != 200:
                return {}

            data = response.json()
            if data.get("result") == 1:
                return data.get("data") or {}
        except Exception as e:
            logger.warning("  ✗ 获取孖展详情失败: %s", e)
        return {}

class ProspectusDownloader:
    """招股书下载器"""
    
    def __init__(self, cache_dir='/tmp/hkipo_prospectus'):
        self.cache_dir = cache_dir
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "X-Requested-With": "XMLHttpRequest"
        }
        os.makedirs(cache_dir, exist_ok=True)

    @staticmethod
    def _strip_html(text):
        text = re.sub(r'<[^>]+>', ' ', text or '')
        text = unescape(text)
        return re.sub(r'\s+', ' ', text).strip()

    def _fetch_new_listing_rows(self, page_url):
        """抓取新上市信息页的表格行"""
        try:
            response = _retry_request(httpx.get, page_url, headers=self.headers, timeout=SETTINGS.network.default_timeout, follow_redirects=True)
            if response.status_code != 200:
                return []

            html = response.text
            rows = []
            for row_html in re.findall(r'<tr\b[^>]*>(.*?)</tr>', html, re.IGNORECASE | re.DOTALL):
                cells = re.findall(r'<td\b[^>]*>(.*?)</td>', row_html, re.IGNORECASE | re.DOTALL)
                if len(cells) < 4:
                    continue

                row = {
                    'stock_code': self._strip_html(cells[0]),
                    'stock_name': self._strip_html(cells[1]),
                    'announcement_links': re.findall(r'href="([^"]+)"', cells[2], re.IGNORECASE),
                    'prospectus_links': re.findall(r'href="([^"]+)"', cells[3], re.IGNORECASE),
                    'allotment_links': re.findall(r'href="([^"]+)"', cells[4], re.IGNORECASE) if len(cells) > 4 else [],
                    'raw_html': row_html,
                }
                rows.append(row)
            return rows
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.warning(f"_fetch_new_listing_rows 失败 ({page_url}): {e}")
            return []

    def _find_prospectus_from_new_listing_page(self, stock_code, company_name, page_url):
        normalized_code = _normalize_stock_code(stock_code)
        normalized_name = _normalize_company_name(company_name)

        for row in self._fetch_new_listing_rows(page_url):
            row_code = _normalize_stock_code(row.get('stock_code', ''))
            row_name = _normalize_company_name(row.get('stock_name', ''))

            code_match = row_code == normalized_code
            name_match = bool(normalized_name) and (
                normalized_name in row_name or row_name in normalized_name
            )

            if not (code_match or name_match):
                continue

            prospectus_links = row.get('prospectus_links', [])
            for href in prospectus_links:
                if not href:
                    continue
                if href.startswith('/'):
                    logger.info("  → 命中新上市信息页: %s %s", row.get("stock_code", ""), row.get("stock_name", ""))
                    return f"https://www1.hkexnews.hk{href}"
                if href.startswith('http'):
                    logger.info("  → 命中新上市信息页: %s %s", row.get("stock_code", ""), row.get("stock_name", ""))
                    return href

        return None

    def _download_pdf_with_fallback(self, pdf_url):
        """下载 PDF，必要时在 https/http 之间回退"""
        candidate_urls = [pdf_url]
        if pdf_url.startswith('https://'):
            candidate_urls.append(pdf_url.replace('https://', 'http://', 1))
        elif pdf_url.startswith('http://'):
            candidate_urls.append(pdf_url.replace('http://', 'https://', 1))

        last_error = None
        for url in candidate_urls:
            try:
                response = _retry_request(httpx.get, url, timeout=SETTINGS.network.pdf_download_timeout, follow_redirects=True)
                if response.status_code == 200 and response.content[:4] == b'%PDF':
                    return response, url
            except Exception as e:
                last_error = e
                continue

        for url in candidate_urls:
            tmp_path = None
            try:
                fd, tmp_path = tempfile.mkstemp(suffix='.pdf')
                os.close(fd)
                cmd = [
                    'curl',
                    '-kL',
                    '--silent',
                    '--show-error',
                    '--fail',
                    url,
                    '-o',
                    tmp_path,
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
                if result.returncode == 0 and os.path.exists(tmp_path):
                    with open(tmp_path, 'rb') as f:
                        content = f.read()
                    size_mb = len(content) / 1024 / 1024
                    max_size = SETTINGS.network.max_pdf_size_mb
                    if size_mb > max_size:
                        logger.warning("  ✗ PDF 超出大小限制: %.2f MB > %d MB", size_mb, max_size)
                        last_error = RuntimeError(f"PDF 超出大小限制: {size_mb:.1f} MB > {max_size} MB")
                        continue
                    if content[:4] == b'%PDF':
                        return SimpleNamespace(content=content), url
                    last_error = RuntimeError("curl 下载结果不是有效 PDF")
            except Exception as e:
                last_error = e
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass

        if last_error:
            raise last_error
        raise RuntimeError("无法下载有效的 PDF")
    
    def download_from_hkex(self, stock_code, company_name):
        """从港交所下载招股书"""
        logger.info("\n  从港交所搜索招股书: %s(%s)", company_name, stock_code)

        listing_pages = [
            "https://www2.hkexnews.hk/New-Listings/New-Listing-Information/Main-Board?sc_lang=en",
            "https://www2.hkexnews.hk/New-Listings/New-Listing-Information/GEM?sc_lang=en",
        ]

        for page_url in listing_pages:
            try:
                matched_pdf = self._find_prospectus_from_new_listing_page(stock_code, company_name, page_url)
                if matched_pdf:
                    response, final_url = self._download_pdf_with_fallback(matched_pdf)
                    size_mb = len(response.content) / 1024 / 1024
                    max_size = SETTINGS.network.max_pdf_size_mb
                    if size_mb > max_size:
                        logger.warning("  ✗ PDF 超出大小限制: %.2f MB > %d MB", size_mb, max_size)
                        return None
                    pdf_path = os.path.join(self.cache_dir, f"{stock_code}_prospectus.pdf")
                    with open(pdf_path, 'wb') as f:
                        f.write(response.content)
                    scheme_note = "https" if final_url.startswith('https://') else "http"
                    logger.info("  ✓ 通过新上市信息页下载成功: %s (%.2f MB, %s)", pdf_path, size_mb, scheme_note)
                    return pdf_path
            except Exception as e:
                logger.warning("  通过新上市信息页下载失败: %s", e)

        try:
            from playwright.sync_api import sync_playwright
            
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                
                pages_to_try = [
                    "https://www2.hkexnews.hk/new-listings/new-listing-information/main-board?sc_lang=en",
                    "https://www2.hkexnews.hk/new-listings/new-listing-information/growth-enterprise-market?sc_lang=en",
                ]
                
                for page_url in pages_to_try:
                    try:
                        page.goto(page_url, timeout=60000)
                        page.wait_for_load_state('networkidle', timeout=60000)
                        page.wait_for_timeout(3000)
                        
                        pdf_links = page.evaluate('''
                            () => {
                                const links = [];
                                document.querySelectorAll('a[href]').forEach(a => {
                                    const href = a.getAttribute('href');
                                    if (href && href.includes('.pdf')) {
                                        const text = (a.innerText || a.textContent || '').trim();
                                        const parentText = (a.parentElement?.innerText || '').trim();
                                        links.push({ href, text, parentText });
                                    }
                                });
                                return links;
                            }
                        ''')

                        company_key = _normalize_company_name(company_name)
                        stock_keys = {
                            _normalize_stock_code(stock_code),
                            str(stock_code).lstrip('0'),
                        }
                        prospectus_candidates = []

                        for link in pdf_links:
                            href = link.get('href', '')
                            if href.startswith('/'):
                                full_url = f"https://www1.hkexnews.hk{href}"
                            elif href.startswith('http'):
                                full_url = href
                            else:
                                continue

                            search_text = " ".join([
                                href,
                                link.get('text', ''),
                                link.get('parentText', ''),
                            ]).upper()
                            normalized_text = re.sub(r'[\s\-\u3000()（）]+', '', search_text)
                            href_name = _normalize_company_name(search_text)

                            is_prospectus = any(
                                keyword in search_text
                                for keyword in ['PROSPECTUS', 'APPLICATION PROOF', 'POST HEARING', 'PHIP']
                            )
                            company_match = company_key and (
                                company_key in normalized_text or company_key in href_name
                            )
                            stock_match = any(key and key in normalized_text for key in stock_keys)

                            if is_prospectus and (company_match or stock_match):
                                prospectus_candidates.append(full_url)

                        for full_url in prospectus_candidates:
                            try:
                                response = _retry_request(httpx.head, full_url, timeout=SETTINGS.network.head_timeout, follow_redirects=True)
                                if response.status_code == 200:
                                    size = int(response.headers.get('content-length', 0))
                                    max_size = SETTINGS.network.max_pdf_size_mb * 1024 * 1024
                                    if size > 1000000 and size <= max_size:
                                        pdf_path = os.path.join(self.cache_dir, f"{stock_code}_prospectus.pdf")
                                        response = _retry_request(httpx.get, full_url, timeout=SETTINGS.network.pdf_download_timeout, follow_redirects=True)
                                        with open(pdf_path, 'wb') as f:
                                            f.write(response.content)
                                        logger.info("  ✓ 下载成功: %s (%.2f MB)", pdf_path, size / 1024 / 1024)
                                        return pdf_path
                                    elif size > max_size:
                                        logger.warning("  ✗ PDF 超出大小限制: %.2f MB > %d MB", size / 1024 / 1024, max_size)
                            except Exception:
                                continue
                    except Exception as e:
                        logger.warning("  访问页面失败: %s", e)
                        continue
                
                browser.close()
        except ImportError:
            logger.info("  Playwright未安装，跳过港交所搜索")
        
        return None
