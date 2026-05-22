"""评分管道共享工具 — biotech 判断、阈值读取等."""

from __future__ import annotations

from typing import Any


def is_biotech(prospectus_info: dict[str, Any]) -> bool:
    """统一判断是否为 biotech/18A 公司.

    当前散落在 valuation、scoring、quality、signal 四处的判断逻辑汇总:
    1. 股票代码/公司名以 -B 结尾
    2. 行业代码为 biotech/pharma/healthcare + 关键词命中
    3. 收入结构以 license upfront 为主
    """
    name = prospectus_info.get("extracted_company_name", "")
    aliases = prospectus_info.get("company_name_aliases", [])
    sector = prospectus_info.get("sector", "")
    text = prospectus_info.get("_extracted_text", "")

    # -B 后缀强制命中
    names = [name] + aliases
    if any(n.strip().upper().endswith("-B") for n in names if isinstance(n, str)):
        return True

    # 行业 + 关键词
    biotech_sectors = {"biotech", "pharma", "healthcare", "pharmaceutical"}
    if sector and sector.lower() in biotech_sectors:
        if "biotech" in text.lower() or "pipeline" in text.lower():
            return True

    # revenue 结构特征 (license upfront driven)
    revenue = prospectus_info.get("revenue", 0)
    if isinstance(revenue, (int, float)) and revenue > 0:
        if "license" in text.lower() and "upfront" in text.lower():
            # 如果收入很小且以 license 为主，判定为 biotech
            if revenue < 500:  # 百万 RMB/HKD 级别
                return True

    return False


def grade_from_score(score: float) -> str:
    """分数 -> 等级 (兼容现有 grading 逻辑)."""
    if score >= 85:
        return "A+"
    if score >= 75:
        return "A"
    if score >= 65:
        return "A-"
    if score >= 55:
        return "B+"
    if score >= 45:
        return "B"
    if score >= 35:
        return "B-"
    if score >= 25:
        return "C+"
    return "C"
