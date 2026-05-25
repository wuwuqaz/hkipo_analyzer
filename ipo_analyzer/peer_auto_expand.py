"""同行比对数据库自动扩展 — 从招股书中提取可比公司名称，供 peer_comps.yaml 扩充参考。"""

import re
import logging

logger = logging.getLogger(__name__)

# 可比公司章节关键词
_PEER_SECTION_PATTERNS = [
    r'(?:可比公司|同行业|同行|同业|同业可比|行业可比|竞争格局|competitors?|comparable\s+companies?|peer\s+companies?)',
]

# 公司名称模式（中英文）
_COMPANY_NAME_PATTERNS = [
    # 中文上市公司（含后缀）
    r'(?:[\u4e00-\u9fff]{2,6}(?:集团|控股|科技|医药|生物|半导体|芯片|新能源|电子|通信|软件|股份|实业|国际|香港|中国)?(?:有限公司|股份有限公司|集团)?)',
    # 英文上市公司
    r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4})\s*(?:Inc\.?|Corp\.?|Ltd\.?|Limited|PLC|AG|SA|NV|SE)',
    # 知名公司简写
    r'(?:Tesla|Apple|Microsoft|Amazon|Google|Meta|NVIDIA|AMD|Intel|Samsung|TSMC|ASML|Qualcomm|Broadcom|Analog\s+Devices|Texas\s+Instruments|Applied\s+Materials)',
]

# 排除词（非公司名）
_EXCLUDE_WORDS = [
    '行业', '市场', '领域', '公司', '企业', '集团',
    '数据来源', '资料来源', '招股书', '弗若斯特', '沙利文', '灼识',
    '港交所', '联交所', '证监会', '证券', '交易所',
]


def extract_peer_companies_from_text(prospectus_text: str) -> list[str]:
    """从招股书文本中提取被提及的可比公司名称。

    Args:
        prospectus_text: 招股书全文

    Returns:
        list[str]: 提取到的可比公司名称列表（去重）
    """
    if not prospectus_text:
        return []

    companies = []

    try:
        # 定位可比公司相关章节
        peer_section_text = _find_peer_section(prospectus_text)

        # 方法1：从可比公司章节表格提取
        table_companies = _extract_from_table_section(peer_section_text)
        companies.extend(table_companies)

        # 方法2：模式匹配
        matched = _extract_by_patterns(peer_section_text)
        companies.extend(matched)

        # 去除已存在的重复项
        result = list(dict.fromkeys(companies))
        result = [c for c in result if len(c) >= 1 and c not in _EXCLUDE_WORDS]
        return result[:30]

    except Exception as e:
        logger.warning("同行公司提取失败: %s", e)
        return []


def _find_peer_section(text: str) -> str:
    """定位可比公司相关章节。"""
    for pattern in _PEER_SECTION_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            start = max(0, m.start() - 500)
            end = min(len(text), m.end() + 8000)
            return text[start:end]
    return text[:15000]  # 未找到则用前15000字符


def _extract_from_table_section(text: str) -> list[str]:
    """从表格样式的可比公司章节提取公司名。"""
    companies = []

    # 表格行模式：序号 公司名 代码 估值
    table_row_pattern = re.compile(
        r'^\s*(?:\d+[\.\)、]\s*)?([\u4e00-\u9fffA-Za-z\s\-\.&]+?)\s+'
        r'(?:[A-Z]{1,5}\.)?\d{4,6}\.?(?:HK|SZ|SH|US|NASDAQ|NYSE)?',
        re.MULTILINE | re.IGNORECASE,
    )

    for m in table_row_pattern.finditer(text):
        name = m.group(1).strip()
        if 2 <= len(name) <= 40 and any(c.isalpha() for c in name):
            companies.append(name)

    return companies


def _extract_by_patterns(text: str) -> list[str]:
    """通过公司名模式匹配提取。"""
    companies = []

    for pattern in _COMPANY_NAME_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            name = m.group(0).strip()
            if name not in _EXCLUDE_WORDS and 2 <= len(name) <= 50:
                companies.append(name)

    return companies
