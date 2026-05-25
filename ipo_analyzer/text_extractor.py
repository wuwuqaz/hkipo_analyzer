"""PDF 文本提取模块 — 独立于 parser，支持 PyMuPDF / pypdf 双引擎回退

优化点：
1. 基于 PDF路径+mtime 的 LRU 缓存，避免重复提取
2. doc 对象显式关闭，防止文件句柄泄漏
3. 默认最大页数从 250 提升至 500（覆盖 99%+ 有效内容）
"""

import os
import logging
from collections import OrderedDict
from typing import Optional

logger = logging.getLogger(__name__)

_TEXT_CACHE: "OrderedDict[tuple[str, float, int, int], str]" = OrderedDict()
_MAX_CACHE_ENTRIES = 10


def _get_cache_key(pdf_path: str) -> Optional[tuple[str, float, int]]:
    try:
        stat = os.stat(pdf_path)
        return (pdf_path, stat.st_mtime, stat.st_size)
    except OSError:
        return None


def extract_pdf_text(pdf_path: str, max_pages: int = 500) -> str:
    """从 PDF 提取纯文本。优先 PyMuPDF，缺失时回退 pypdf。

    内置缓存：同一文件（路径+mtime+大小一致）不会重复提取。
    """
    if not os.path.exists(pdf_path):
        return ""

    cache_key = _get_cache_key(pdf_path)
    if cache_key is not None:
        key = (cache_key[0], cache_key[1], cache_key[2], max_pages)
        cached = _TEXT_CACHE.get(key)
        if cached is not None:
            _TEXT_CACHE.move_to_end(key)
            return cached

    text = _extract_pdf_text_impl(pdf_path, max_pages)

    if cache_key is not None:
        if len(_TEXT_CACHE) >= _MAX_CACHE_ENTRIES:
            _TEXT_CACHE.popitem(last=False)
        _TEXT_CACHE[(cache_key[0], cache_key[1], cache_key[2], max_pages)] = text

    return text


def _extract_pdf_text_impl(pdf_path: str, max_pages: int) -> str:
    try:
        import fitz

        doc = fitz.open(pdf_path)
        page_count = min(max_pages, doc.page_count)
        pages = []
        for i in range(page_count):
            try:
                pages.append(doc.load_page(i).get_text("text") or "")
            except Exception:
                continue
        doc.close()
        return "\n".join(pages)
    except ImportError:
        pass
    except Exception as e:
        logger.warning("PyMuPDF 解析失败: %s，回退到 pypdf", e)

    try:
        import pypdf as _pypdf_mod

        with open(pdf_path, "rb") as f:
            reader = _pypdf_mod.PdfReader(f)
            num_pages = len(reader.pages)
            text_parts = []
            for i in range(min(max_pages, num_pages)):
                try:
                    text_parts.append(reader.pages[i].extract_text() or "")
                except Exception:
                    continue
            return "\n".join(text_parts)
    except ImportError:
        logger.warning("pypdf 未安装，无法回退 PDF 解析")
        return ""
    except Exception as e:
        logger.warning("pypdf 解析失败: %s", e)
        return ""


def clear_text_cache():
    _TEXT_CACHE.clear()
