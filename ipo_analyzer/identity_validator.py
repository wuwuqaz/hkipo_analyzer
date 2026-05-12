"""PDF 身份验证模块 — 验证 PDF 内容是否匹配目标公司/股票代码"""

import re
import logging
from typing import Optional

from .utils import _normalize_company_name

logger = logging.getLogger(__name__)


_SIMPLIFIED_TO_TRADITIONAL = {
    '乐': '樂', '动': '動', '机': '機', '器': '器', '人': '人',
    '医': '醫', '药': '藥', '剂': '劑', '创': '創', '新': '新', '科': '科',
    '技': '技', '集': '集', '团': '團', '控': '控', '股': '股',
    '有': '有', '限': '限', '公': '公', '司': '司', '国': '國',
    '际': '際', '电': '電', '子': '子', '网': '網', '络': '絡',
    '智': '智', '能': '能', '芯': '芯', '片': '片', '半': '半',
    '导': '導', '体': '體', '光': '光', '学': '學', '生': '生',
    '物': '物', '食': '食', '品': '品', '饮': '飲', '料': '料',
    '消': '消', '费': '費', '服': '服', '装': '裝', '饰': '飾',
    '珠': '珠', '宝': '寶', '黄': '黃', '金': '金', '银': '銀',
    '汽': '汽', '车': '車', '房': '房', '地': '地', '产': '產',
    '业': '業', '建': '建', '筑': '築', '材': '材',
    '深': '深', '圳': '圳', '北': '北', '京': '京', '上': '上',
    '海': '海', '广': '廣', '州': '州', '杭': '杭',
}


def _to_traditional(s: str) -> str:
    return ''.join(_SIMPLIFIED_TO_TRADITIONAL.get(c, c) for c in s)


def build_company_aliases(company_name: str) -> list[str]:
    """生成公司名称的所有可能变体（含繁体转换、去后缀）。"""
    company_clean = _normalize_company_name(company_name)
    aliases = [company_name, company_clean]
    if len(company_clean) >= 4:
        aliases.append(company_clean[:4])
    aliases.append(_to_traditional(company_clean))
    if len(company_clean) >= 4:
        aliases.append(_to_traditional(company_clean[:4]))
    for suffix in ['股份有限公司', '有限公司', '公司', '股份', '有限']:
        if company_clean.endswith(_to_traditional(suffix)):
            stripped = company_clean[:-len(_to_traditional(suffix))]
            if len(stripped) >= 2:
                aliases.append(stripped)
        if company_clean.endswith(suffix):
            stripped = company_clean[:-len(suffix)]
            if len(stripped) >= 2:
                aliases.append(stripped)
    return list(dict.fromkeys(a for a in aliases if a))


def extract_company_name_from_first_page(text: str) -> tuple[Optional[str], Optional[str]]:
    """从 PDF 首页提取中英文公司名。"""
    first_page = text[:5000]
    extracted_cn = None
    extracted_en = None

    for line in first_page.splitlines():
        compact_line = re.sub(r'\s+', '', line or '')
        if '有限公司' not in compact_line:
            continue
        cn_name_match = re.search(r'([\u4e00-\u9fffA-Za-z0-9()（）]{2,50}有限公司)', compact_line)
        if not cn_name_match:
            continue
        candidate = cn_name_match.group(1)
        if candidate in ('股份有限公司', '有限公司') or candidate.startswith('有限公司'):
            continue
        extracted_cn = candidate
        break

    if not extracted_cn:
        cn_name_match = re.search(r'([\u4e00-\u9fff]{2,20}(?:股份)?有限公司)', first_page)
        if cn_name_match and cn_name_match.group(1) not in ('股份有限公司', '有限公司'):
            extracted_cn = cn_name_match.group(1)

    en_name_match = re.search(
        r'([A-Z][A-Za-z\s&.,]+(?:CO\.?,?\s*LTD\.?|LIMITED|INC\.?|CORP\.?))',
        first_page,
    )
    if en_name_match:
        extracted_en = en_name_match.group(1).strip()

    return extracted_cn, extracted_en


def extract_stock_code_from_first_page(text: str) -> Optional[str]:
    """从 PDF 首页提取股票代码。"""
    first_page = text[:5000]
    stock_code_match = re.search(r'Stock\s*code\s*:?\s*(\d{4,5})', first_page, re.IGNORECASE)
    if not stock_code_match:
        stock_code_match = re.search(r'股票\s*代[碼码]\s*:?\s*(\d{4,5})', first_page, re.IGNORECASE)
    if stock_code_match:
        return stock_code_match.group(1).zfill(5)
    return None


def validate_pdf_identity(
    text: str,
    stock_code: Optional[str] = None,
    company_name: Optional[str] = None,
) -> dict:
    """验证 PDF 文本是否匹配目标公司名和股票代码。

    返回字段：
    - name_match (bool)
    - stock_code_match (bool)
    - pdf_identity_confidence (str: high/medium/low)
    - extracted_company_name (str|None)
    - extracted_english_name (str|None)
    - extracted_stock_code (str|None)
    - company_name_aliases (list[str])
    """
    text_no_space = re.sub(r'\s+', '', text)

    name_match = False
    stock_code_match = False
    company_aliases: list[str] = []
    extracted_company_name, extracted_english_name = extract_company_name_from_first_page(text)
    extracted_stock_code = extract_stock_code_from_first_page(text)

    if company_name:
        company_aliases = build_company_aliases(company_name)
        name_match = any(kw in text or kw in text_no_space for kw in company_aliases if kw)

    # 更精确的名称匹配
    if extracted_company_name and company_name:
        trad_name = _to_traditional(_normalize_company_name(company_name))
        extracted_norm = _normalize_company_name(extracted_company_name)
        if trad_name in extracted_norm or extracted_norm in trad_name:
            name_match = True

    if extracted_english_name and not name_match and company_name:
        en_aliases = re.findall(r'[A-Za-z]{3,}', company_name or '')
        if en_aliases:
            en_clean = ' '.join(en_aliases).upper()
            if en_clean and en_clean in extracted_english_name.upper():
                name_match = True

    if stock_code:
        stock_variants = [
            stock_code,
            stock_code.lstrip('0'),
            stock_code.zfill(5),
            f"E{stock_code}",
            f"E{stock_code.lstrip('0')}",
        ]
        stock_code_match = any(v in text or v in text_no_space for v in stock_variants)
    elif extracted_stock_code:
        stock_code_match = True

    if stock_code_match and name_match:
        confidence = "high"
    elif stock_code_match or name_match:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "name_match": name_match,
        "stock_code_match": stock_code_match,
        "pdf_identity_confidence": confidence,
        "extracted_company_name": extracted_company_name,
        "extracted_english_name": extracted_english_name,
        "extracted_stock_code": extracted_stock_code,
        "company_name_aliases": company_aliases,
    }
