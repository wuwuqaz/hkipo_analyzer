"""PDF 文本提取模块 — 独立于 parser，支持 PyMuPDF / PyPDF2 双引擎回退"""

import os
import logging

logger = logging.getLogger(__name__)


def extract_pdf_text(pdf_path: str, max_pages: int = 350) -> str:
    """从 PDF 提取纯文本。优先 PyMuPDF，缺失时回退 PyPDF2。"""
    if not os.path.exists(pdf_path):
        return ""

    # 1. PyMuPDF (fitz)
    try:
        import fitz

        doc = fitz.open(pdf_path)
        page_count = min(max_pages, doc.page_count)
        return "\n".join(doc.load_page(i).get_text("text") or "" for i in range(page_count))
    except ImportError:
        pass
    except Exception as e:
        logger.warning("PyMuPDF 解析失败: %s，回退到 PyPDF2", e)

    # 2. PyPDF2 回退
    try:
        import PyPDF2 as _PyPDF2_mod

        with open(pdf_path, "rb") as f:
            reader = _PyPDF2_mod.PdfReader(f)
            num_pages = len(reader.pages)
            text_parts = []
            for i in range(min(max_pages, num_pages)):
                try:
                    text_parts.append(reader.pages[i].extract_text() or "")
                except Exception:
                    continue
            return "\n".join(text_parts)
    except ImportError:
        logger.warning("PyPDF2 未安装，无法回退 PDF 解析")
        return ""
    except Exception as e:
        logger.warning("PyPDF2 解析失败: %s", e)
        return ""
