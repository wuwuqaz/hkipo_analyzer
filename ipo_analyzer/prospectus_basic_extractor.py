"""招股书基础信息提取模块 — 发行信息、市值、日期等"""

import re
import logging
from datetime import datetime
from typing import Optional

from .settings import SETTINGS
from .utils import _is_num, _infer_sector

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 通用提取工具
# ---------------------------------------------------------------------------

def extract_int_after_label(text: str, patterns: list[str]) -> Optional[int]:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        groups = match.groups()
        if not groups:
            continue
        number_text = groups[0].replace(',', '').strip()
        try:
            return int(float(number_text))
        except Exception:
            continue
    return None


def extract_float_after_label(text: str, patterns: list[str]) -> Optional[float]:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        groups = match.groups()
        if not groups:
            continue
        number_text = groups[0].replace(',', '').strip()
        try:
            return float(number_text)
        except Exception:
            continue
    return None


def extract_hkd_amounts_after_label(text: str, label_pattern: str, window_size: int = 900) -> list[float]:
    match = re.search(label_pattern, text, re.IGNORECASE | re.DOTALL)
    if not match:
        return []
    window = text[match.end():match.end() + window_size]
    values = []
    # million
    for amount in re.findall(r'HK\$\s*([0-9,]+(?:\.[0-9]+)?)\s*million', window, re.IGNORECASE):
        try:
            values.append(float(amount.replace(',', '')))
        except Exception:
            continue
    # billion → 转为 million
    for amount in re.findall(r'HK\$\s*([0-9,]+(?:\.[0-9]+)?)\s*billion', window, re.IGNORECASE):
        try:
            values.append(float(amount.replace(',', '')) * 1000)
        except Exception:
            continue
    return values


def extract_market_cap_table_value(text: str, label_pattern: str, window_size: int = 1200) -> Optional[float]:
    """Extract HK$'million table values where the currency unit is in the header."""
    match = re.search(label_pattern, text, re.IGNORECASE | re.DOTALL)
    if not match:
        return None

    header_window = text[max(0, match.start() - 400):match.start()]
    if not re.search(r"HK\$[’'‘`]?\s*million|HK\$\s*['’]?\s*000", header_window, re.IGNORECASE):
        return None

    value_window = text[match.end():match.end() + window_size]
    value_match = re.search(r'\(?\d+\)?\s*\n\s*([0-9,]+(?:\.[0-9]+)?)', value_window)
    if not value_match:
        value_match = re.search(r'^\s*([0-9,]+(?:\.[0-9]+)?)\b', value_window)
    if not value_match:
        return None

    try:
        return float(value_match.group(1).replace(',', ''))
    except Exception:
        return None


def extract_chinese_market_cap_table_value(text: str) -> Optional[float]:
    """提取中文/繁体全球发售统计表中的公司股份市值（百万元港元）。"""
    patterns = [
        r'股份市值(?:\(\d+\))?[\s\S]{0,220}?([0-9,]+(?:\.[0-9]+)?)\s*百萬港元',
        r'股份市值(?:\(\d+\))?[\s\S]{0,220}?([0-9,]+(?:\.[0-9]+)?)\s*百万港元',
        r'本公司市值(?:\(\d+\))?[\s\S]{0,220}?([0-9,]+(?:\.[0-9]+)?)\s*百萬港元',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        try:
            return float(match.group(1).replace(',', ''))
        except Exception:
            continue
    return None


def parse_text_date(date_text: str) -> Optional[str]:
    if not date_text:
        return None
    date_text = date_text.strip().rstrip('.')
    for fmt in ("%A, %B %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(date_text, fmt).date().isoformat()
        except Exception:
            continue
    return None


def extract_date_after_phrase(text: str, patterns: list[str]) -> Optional[str]:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        groups = [group for group in match.groups() if group]
        for group in groups:
            parsed = parse_text_date(group)
            if parsed:
                return parsed
            date_match = re.search(
                r'((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+[A-Za-z]+\s+\d{1,2},\s+\d{4})',
                group,
                re.IGNORECASE,
            )
            if date_match:
                parsed = parse_text_date(date_match.group(1))
                if parsed:
                    return parsed
    return None


def infer_sector_label(text: str) -> str:
    return _infer_sector(text)


def is_chapter_18c_ipo(text: str) -> bool:
    """Detect HKEX Chapter 18C / specialist technology issuers."""
    patterns = [
        r'\bChapter\s*18C\b',
        r'\bCh(?:apter)?\.?\s*18C\b',
        r'\b18C\s+(?:of\s+the\s+)?(?:Listing\s+Rules|Main\s+Board\s+Listing\s+Rules)\b',
        r'specialist\s+technology\s+(?:company|companies|issuer)',
        r'特[專专]科技(?:公司|發行人|发行人)?',
    ]
    return any(re.search(pattern, text or '', re.IGNORECASE) for pattern in patterns)


# ---------------------------------------------------------------------------
# 招股书基础信息提取
# ---------------------------------------------------------------------------

def extract_prospectus_basic_info(text: str, info: dict) -> None:
    """从招股书文本中提取发行基本信息，直接写入 info dict（原地修改）。"""
    if is_chapter_18c_ipo(text):
        info['is_chapter_18c'] = True
        info['public_offer_clawback_max_pct'] = 20.0
        info['public_offer_clawback_note'] = '18C/特专科技：公开发售可回拨至20%'

    offer_shares = extract_int_after_label(text, [
        r'Number of Offer Shares under\s*the Global\s*Offering\s*[:：]?\s*\n?\s*([0-9,]+)',
        r'Number of Offer Shares under\s*the Global\s*Offering\s*([0-9,]+)\s*H Shares',
        # 中文招股书全球发售股份（冒号可能在下一行）
        r'全球發售.*?發售股份數目\s*[：:]\s*([0-9,]+)',
        r'全球發售.*?發售股份總數\s*[：:]\s*([0-9,]+)',
        r'全球發售發行\s*([0-9,]+)\s*股',
        r'全球发售发行\s*([0-9,]+)\s*股',
    ])
    hk_offer_shares = extract_int_after_label(text, [
        r'Number of Hong Kong Offer Shares\s*[:：]?\s*\n?\s*([0-9,]+)',
        r'Number of Hong Kong Offer Shares\s*([0-9,]+)\s*H Shares',
        # 中文香港发售股份（冒号可能在下一行，允许中间有其他字符）
        r'香港發售股份數目\s*[：:]\s*([0-9,]+)',
        r'香港公開發售.*?股份數目\s*[：:]\s*([0-9,]+)',
        r'香港公開發售\s*[:：]\s*\n?\s*([0-9,]+)',
        r'香港發售\s*[:：]\s*\n?\s*([0-9,]+)',
        # 表格格式：香港发售股份可能在表格中
        r'香港\s*(?:公開)?\s*發售\s*股份\s*[:：]?\s*\n?\s*([0-9,]+)',
    ])
    intl_offer_shares = extract_int_after_label(text, [
        r'Number of International Offer Shares\s*[:：]?\s*\n?\s*([0-9,]+)',
        r'Number of International Offer Shares\s*([0-9,]+)\s*H Shares',
        # 中文国际发售股份（冒号可能在下一行）
        r'國際發售股份數目\s*[：:]\s*([0-9,]+)',
        r'國際發售.*?股份數目\s*[：:]\s*([0-9,]+)',
    ])
    offer_price = extract_float_after_label(text, [
        r'Offer Price\s*:\s*HK\$([0-9,]+(?:\.[0-9]+)?)',
        r'Maximum Offer Price\s*HK\$([0-9,]+(?:\.[0-9]+)?)',
        r'Offer Price\s*HK\$([0-9,]+(?:\.[0-9]+)?)',
        # 中文发售價（冒号可能在下一行）
        r'發售價\s*[：:]\s*(?:每股H股)?\s*(?:HK\$|港元)?\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:港元|HKD)',
        r'發售價[^0-9\n]*(?:每股.*?)?(?:HK\$|港元)?\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:港元|HKD)',
    ])
    board_lot = info.get('lot_size')
    if board_lot is None:
        board_lot = extract_int_after_label(text, [
            r'board\s+lot\s+size[^\d]*?(\d[\d,]*)',
            r'each\s+board\s+lot[^\d]*?(\d[\d,]*)',
            # 中文每手股数
            r'每\s*手[^\d]*?(\d[\d,]*)\s*股',
            r'每\s*手\s*買\s*賣\s*單\s*位[^\d]*?(\d[\d,]*)\s*股',
            r'買\s*賣\s*單\s*位\s*每\s*手[^\d]*?(\d[\d,]*)\s*股',
            r'每\s*手[^\d]*?(\d[\d,]*)',
            r'買\s*賣\s*單\s*位\s*[:：][^\d]*?(\d[\d,]*)\s*股',
        ])
        if board_lot is not None:
            info['lot_size'] = board_lot
    # 同时存储 board_lot 字段，供 core.py 使用
    if board_lot is not None:
        info['board_lot'] = board_lot

    post_listing_shares = extract_int_after_label(text, [
        r'([0-9,]+)\s*(?:H\s*)?Shares expected to be in issue immediately\s+(?:after|upon)\s+(?:the\s+)?completion of the Global Offering',
        r'([0-9,]+)\s*(?:H\s*)?Shares in\s*issue immediately\s+(?:following|after)\s+(?:the\s+)?completion of the Global Offering',
        r'([0-9,]+)\s*(?:Offer\s*)?Shares(?:\s*are)?\s*issued and outstanding\s+(?:following|after)\s+(?:the\s+)?completion of the Global Offering',
        r'([0-9,]+)\s*(?:H\s*)?Shares will be in issue and outstanding immediately\s+(?:following|after)\s+(?:the\s+)?completion of the Global Offering',
        r'([0-9,]+)\s*(?:H\s*)?Shares in issue immediately upon completion of the Global Offering',
        # 中文：紧随全球发售完成后已发行股份
        r'緊隨全球發售完成後.*?已發行.*?([0-9,]+)\s*股',
        r'全球發售完成後.*?已發行股份[^0-9]*?([0-9,]+)\s*股',
        r'已發行及發行在外.*?([0-9,]+)\s*股',
    ])

    # --- 多口径市值提取 ---
    # 优先级：公司总市值 > 发行H股市值 > 预期表述 > 股数×股价计算
    market_cap_million = None
    market_cap_low = None
    market_cap_high = None
    market_cap_mid = None
    market_cap_source = None

    # 1. 公司总市值（our Company / our Shares）— 最准确
    cap_company = extract_hkd_amounts_after_label(
        text,
        r'Market capitalization of\s*(?:our\s*)?(?:Company|Shares)',
    )
    if cap_company and len(cap_company) > 0:
        cap_company = sorted(cap_company)
        market_cap_low = cap_company[0]
        market_cap_high = cap_company[-1]
        market_cap_million = market_cap_high
        market_cap_source = 'company_shares_table'
    else:
        cap_table_value = extract_market_cap_table_value(
            text,
            r'Market capitalization of\s*(?:our\s*)?(?:Company|Shares)\b',
        )
        if cap_table_value is not None:
            market_cap_low = cap_table_value
            market_cap_high = cap_table_value
            market_cap_million = cap_table_value
            market_cap_source = 'company_shares_table'
        else:
            cap_table_value_zh = extract_chinese_market_cap_table_value(text)
            if cap_table_value_zh is not None:
                market_cap_low = cap_table_value_zh
                market_cap_high = cap_table_value_zh
                market_cap_million = cap_table_value_zh
                market_cap_source = 'company_shares_table_zh'

    # 2. 发行H股市值（仅当未找到公司总市值时 fallback）
    if market_cap_million is None:
        mc_h_shares = extract_hkd_amounts_after_label(
            text,
            r'Market capitalization of\s+(?:the\s+)?H Shares',
        )
        if mc_h_shares and len(mc_h_shares) > 0:
            mc_h_shares = sorted(mc_h_shares)
            market_cap_low = mc_h_shares[0]
            market_cap_high = mc_h_shares[-1]
            market_cap_million = market_cap_high
            market_cap_source = 'h_shares_table'

    # 3. 预期市值表述
    if market_cap_million is None:
        mc_expected = re.findall(
            r'(?:expected\s+)?market\s+capitalization[^.]*?approximately\s+HK\$([0-9,]+(?:\.[0-9]+)?)\s*(million|billion)',
            text, re.IGNORECASE,
        )
        if mc_expected:
            vals = []
            for v, unit in mc_expected:
                val = float(v.replace(',', ''))
                if unit.lower() == 'billion':
                    val *= 1000
                vals.append(val)
            market_cap_million = max(vals)
            market_cap_mid = vals[len(vals) // 2] if len(vals) > 2 else max(vals)
            market_cap_source = 'expected_market_cap'

    # 4. 股数 × 股价 计算（兜底）
    if market_cap_million is None and post_listing_shares is not None:
        prices = []
        for pm in re.finditer(r'HK\$([0-9]+(?:\.[0-9]+)?)\s*per\s*(?:Offer\s*)?(?:H\s*)?Share', text, re.IGNORECASE):
            try:
                prices.append(float(pm.group(1)))
            except ValueError:
                continue
        max_price = max(prices) if prices else (offer_price or info.get('max_price'))
        if max_price and max_price > 0:
            market_cap_million = round(post_listing_shares * max_price / 1_000_000, 2)
            market_cap_source = 'shares_x_offer_price'

    # 5. 交叉校验：如果提取到的市值与 股数×股价 差异超过2倍，优先相信股数×股价
    if (
        market_cap_million is not None
        and post_listing_shares is not None
        and market_cap_source not in ('company_shares_table', 'company_shares_table_zh')
    ):
        prices = []
        for pm in re.finditer(r'HK\$([0-9]+(?:\.[0-9]+)?)\s*per\s*(?:Offer\s*)?(?:H\s*)?Share', text, re.IGNORECASE):
            try:
                prices.append(float(pm.group(1)))
            except ValueError:
                continue
        calc_price = max(prices) if prices else (offer_price or info.get('max_price'))
        if calc_price and calc_price > 0:
            implied_mc = round(post_listing_shares * calc_price / 1_000_000, 2)
            if market_cap_million > 0 and (implied_mc / market_cap_million > 2 or market_cap_million / implied_mc > 2):
                market_cap_million = implied_mc
                market_cap_source = 'shares_x_offer_price(cross_check)'

    if market_cap_million is not None and offer_price and offer_price > 0:
        inferred_total_shares = round(market_cap_million * 1_000_000 / offer_price)
        if (
            post_listing_shares is None
            or (
                offer_shares is not None
                and post_listing_shares <= offer_shares * 1.5
                and inferred_total_shares > offer_shares * 2
            )
        ):
            post_listing_shares = inferred_total_shares

    if market_cap_low is not None:
        info['market_cap_hkd_million_low'] = market_cap_low
    if market_cap_high is not None:
        info['market_cap_hkd_million_high'] = market_cap_high
    if market_cap_mid is not None:
        info['market_cap_hkd_million_mid'] = market_cap_mid
    if market_cap_source:
        info['market_cap_source'] = market_cap_source

    net_proceeds_million = extract_float_after_label(text, [
        r'receive net proceeds of approximately HK\$([0-9,.]+)\s*million',
    ])
    if offer_price is None and info.get('max_price') is not None:
        offer_price = info.get('max_price')
    results_date = extract_date_after_phrase(text, [
        r'Results of allocations in the Hong Kong Public Offering.*?((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+[A-Za-z]+\s+\d{1,2},\s+\d{4})',
        r'Result(s)? of balloting.*?((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+[A-Za-z]+\s+\d{1,2},\s+\d{4})',
    ])
    listing_date = extract_date_after_phrase(text, [
        r'Dealings in the H Shares on the Stock Exchange.*?((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+[A-Za-z]+\s+\d{1,2},\s+\d{4})',
        r'Dealings in the Shares.*?((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+[A-Za-z]+\s+\d{1,2},\s+\d{4})',
    ])
    if listing_date:
        info['listing_date'] = listing_date
    if results_date:
        info['results_date'] = results_date

    if offer_shares is not None:
        info['global_offer_shares'] = offer_shares
    if hk_offer_shares is not None:
        info['hk_offer_shares'] = hk_offer_shares
    if intl_offer_shares is not None:
        info['international_offer_shares'] = intl_offer_shares
    if offer_price is not None:
        info['offer_price'] = offer_price
    if post_listing_shares is not None:
        info['shares_in_issue_post_listing'] = post_listing_shares
    if market_cap_million is not None:
        info['market_cap_hkd_million'] = market_cap_million
    if net_proceeds_million is not None:
        info['net_proceeds_hkd_million'] = net_proceeds_million

    if offer_price is not None and board_lot is not None:
        info['entry_fee_hkd'] = offer_price * board_lot * (1 + SETTINGS.fx.entry_fee_rate)

    if offer_shares and post_listing_shares:
        info['issuance_ratio_pct'] = offer_shares / post_listing_shares * 100

    if hk_offer_shares and offer_shares:
        info['public_offer_ratio_pct'] = hk_offer_shares / offer_shares * 100
    if intl_offer_shares and offer_shares:
        info['international_offer_ratio_pct'] = intl_offer_shares / offer_shares * 100

    # 从招股书估算公开集资额与总集资额（亿港元，供 pre-IPO 评分使用）
    if _is_num(offer_price) and hk_offer_shares:
        info['public_offer'] = round(offer_price * hk_offer_shares / 100_000_000, 2)
    if _is_num(offer_price) and offer_shares:
        info['total_fund'] = round(offer_price * offer_shares / 100_000_000, 2)

    if info.get('cornerstone_analysis', {}).get('cornerstone_investors'):
        cornerstone_rows = info['cornerstone_analysis']['cornerstone_investors']
        cornerstone_offer_shares = sum(int(row.get('offer_shares') or 0) for row in cornerstone_rows)
        cornerstone_investment_hkd = 0
        cornerstone_investment_usd = 0
        for row in cornerstone_rows:
            hkd_amount = row.get('investment_amount_hkd_m')
            usd_amount = row.get('investment_amount_usd_m')
            if _is_num(hkd_amount):
                cornerstone_investment_hkd += hkd_amount
            elif _is_num(usd_amount):
                cornerstone_investment_hkd += usd_amount * 7.8344
            if _is_num(usd_amount):
                cornerstone_investment_usd += usd_amount
        info['cornerstone_total_offer_shares'] = cornerstone_offer_shares
        if cornerstone_investment_hkd:
            info['cornerstone_investment_hkd_million'] = cornerstone_investment_hkd
        if cornerstone_investment_usd:
            info['cornerstone_investment_usd_million'] = cornerstone_investment_usd
        if offer_shares:
            info['cornerstone_offer_ratio_pct'] = cornerstone_offer_shares / offer_shares * 100

    sector = infer_sector_label(text)
    if sector:
        info['sector'] = sector

    if info.get('lot_size') and not info.get('board_lot'):
        info['board_lot'] = info['lot_size']
