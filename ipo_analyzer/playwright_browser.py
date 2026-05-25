"""Playwright 浏览器实例管理器 — 全局复用，避免重复启动。"""

import logging

logger = logging.getLogger(__name__)

_browser_instance = None
_playwright_instance = None


def get_browser():
    """获取或创建全局浏览器实例（同步版本）。"""
    global _browser_instance, _playwright_instance
    if _browser_instance is not None:
        try:
            _browser_instance.version
            return _browser_instance
        except Exception:
            _browser_instance = None
            _playwright_instance = None

    try:
        from playwright.sync_api import sync_playwright
        _playwright_instance = sync_playwright().start()
        _browser_instance = _playwright_instance.chromium.launch(headless=True)
        logger.info("Playwright 浏览器实例已创建")
        return _browser_instance
    except ImportError:
        logger.warning("Playwright 未安装")
        return None
    except Exception as e:
        logger.error("Playwright 浏览器启动失败: %s", e)
        return None


def close_browser():
    """关闭全局浏览器实例。"""
    global _browser_instance, _playwright_instance
    if _browser_instance is not None:
        try:
            _browser_instance.close()
            logger.info("Playwright 浏览器实例已关闭")
        except Exception as e:
            logger.warning("关闭浏览器实例失败: %s", e)
        finally:
            _browser_instance = None
    if _playwright_instance is not None:
        try:
            _playwright_instance.stop()
        except Exception:
            pass
        finally:
            _playwright_instance = None
