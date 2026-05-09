"""解析结果校验层 — 对 parser 输出做 schema + range + 一致性校验。

与 `financial_data_quality_flags` 兼容：校验发现的异常直接追加到 flags 列表。
"""

from datetime import datetime
from typing import Any, Optional

from .utils import _is_num
from .settings import SETTINGS


def _parse_date(date_str: str) -> Optional[datetime]:
    """尝试解析多种日期格式。"""
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def _safe_get(data: dict, key: str, default: Any = None) -> Any:
    return data.get(key, default)


class ProspectusValidator:
    """招股书解析结果校验器。

    用法:
        validator = ProspectusValidator()
        result = validator.validate(info)
        # result['valid'] -> bool
        # result['errors'] -> list[str]
        # result['warnings'] -> list[str]
    """

    # 数值阈值（百万港元口径）
    REVENUE_MAX_SANE = 1_000_000.0  # 100 万亿港元，超过则疑似单位错误
    REVENUE_MIN_SANE = 0.001        # 小于 1,000 港元，疑似解析错误
    NET_PROFIT_MAX_SANE = 500_000.0
    MARKET_CAP_MAX_SANE = 10_000_000.0  # 1000 万亿港元
    MARKET_CAP_MIN_SANE = 10.0
    OFFER_PRICE_MAX_SANE = 10_000.0
    GROSS_MARGIN_MAX_SANE = 100.0

    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def _add_error(self, msg: str):
        self.errors.append(msg)

    def _add_warning(self, msg: str):
        self.warnings.append(msg)

    # ------------------------------------------------------------------
    # 字段级校验
    # ------------------------------------------------------------------

    def _check_revenue(self, info: dict) -> None:
        revenue = info.get('revenue')
        if not _is_num(revenue):
            return
        if revenue > self.REVENUE_MAX_SANE:
            self._add_error(f"收入 {revenue:.1f} 百万港元超出合理范围，疑似单位错误（应为 billion 级别）")
        elif revenue < self.REVENUE_MIN_SANE:
            self._add_warning(f"收入 {revenue:.4f} 百万港元过小，疑似解析错误")

    def _check_net_profit(self, info: dict) -> None:
        net_profit = info.get('net_profit')
        if not _is_num(net_profit):
            return
        if abs(net_profit) > self.NET_PROFIT_MAX_SANE:
            self._add_error(f"净利润 {net_profit:.1f} 百万港元超出合理范围，疑似单位错误")
        revenue = info.get('revenue')
        if _is_num(revenue) and revenue > 0:
            margin = net_profit / revenue
            if abs(margin) > 10:
                self._add_warning(f"净利率 {margin*100:.1f}% 异常高，请核对净利润或收入口径")

    def _check_market_cap(self, info: dict) -> None:
        mc = info.get('market_cap_hkd_million')
        if not _is_num(mc):
            return
        if mc > self.MARKET_CAP_MAX_SANE:
            self._add_error(f"市值 {mc:.1f} 百万港元超出合理范围，疑似单位错误")
        elif mc < self.MARKET_CAP_MIN_SANE:
            self._add_warning(f"市值 {mc:.1f} 百万港元过小，疑似解析错误")

    def _check_offer_price(self, info: dict) -> None:
        price = info.get('offer_price')
        if not _is_num(price):
            return
        if price > self.OFFER_PRICE_MAX_SANE:
            self._add_error(f"发行价 {price:.2f} 港元超出合理范围，疑似解析错误")
        if price <= 0:
            self._add_error("发行价必须大于 0")

    def _check_gross_margin(self, info: dict) -> None:
        gm = info.get('gross_margin')
        if not _is_num(gm):
            return
        if gm > self.GROSS_MARGIN_MAX_SANE:
            self._add_error(f"毛利率 {gm:.1f}% 超出 100%，疑似解析错误")
        if gm < -100:
            self._add_error(f"毛利率 {gm:.1f}% 过低，疑似解析错误")

    def _check_dates(self, info: dict) -> None:
        """校验日期一致性：start < end < listing"""
        start = _parse_date(info.get('apply_start_date', ''))
        end = _parse_date(info.get('apply_end_date', ''))
        listing = _parse_date(info.get('listing_date', ''))

        if start and end and start > end:
            self._add_error("招股开始日期晚于结束日期")
        if end and listing and end > listing:
            self._add_warning("招股结束日期晚于上市日期，请核实")

    def _check_currency_consistency(self, info: dict) -> None:
        """校验币种/单位标记一致性。"""
        currency = info.get('financial_currency')
        if currency and currency not in ('RMB', 'HKD', 'USD'):
            self._add_warning(f"财务币种 '{currency}' 不在预期列表（RMB/HKD/USD），请核实")

    def _check_cross_field_consistency(self, info: dict) -> None:
        """跨字段一致性校验。"""
        revenue = info.get('revenue')
        net_profit = info.get('net_profit')
        market_cap = info.get('market_cap_hkd_million')
        offer_price = info.get('offer_price')
        shares = info.get('shares_in_issue_post_listing')

        # 市值 vs 股价 × 股数 一致性（允许 50% 误差）
        if _is_num(market_cap) and _is_num(offer_price) and _is_num(shares) and shares > 0:
            implied_mc = offer_price * shares / 1_000_000  # 转为百万港元
            if market_cap > 0 and (implied_mc / market_cap > 2 or market_cap / implied_mc > 2):
                self._add_warning(
                    f"市值({market_cap:.0f}M) 与 股价×股数({implied_mc:.0f}M) 差异超过 2 倍，请核实"
                )

        # PE 合理性检查
        if _is_num(market_cap) and _is_num(net_profit) and net_profit > 0:
            pe = market_cap / net_profit
            if pe > 500:
                self._add_warning(f"PE {pe:.1f}x 极高，请核对净利润单位或市值")
            if pe < 1:
                self._add_warning(f"PE {pe:.1f}x 低于 1，请核对净利润是否被高估")

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def validate(self, info: Optional[dict]) -> dict:
        """对招股书解析结果执行完整校验。

        Returns:
            {
                'valid': bool,      # 无 error 时为 True
                'errors': [str],    # 严重异常（可能阻断使用）
                'warnings': [str],  # 轻微异常（建议复核）
            }
        """
        self.errors = []
        self.warnings = []

        if not info or not isinstance(info, dict):
            self._add_error("输入为空或非字典类型")
            return {'valid': False, 'errors': self.errors, 'warnings': self.warnings}

        self._check_revenue(info)
        self._check_net_profit(info)
        self._check_market_cap(info)
        self._check_offer_price(info)
        self._check_gross_margin(info)
        self._check_dates(info)
        self._check_currency_consistency(info)
        self._check_cross_field_consistency(info)

        return {
            'valid': len(self.errors) == 0,
            'errors': self.errors,
            'warnings': self.warnings,
        }


def validate_ipo_data(ipo_data: Optional[dict]) -> dict:
    """快捷函数：对完整的 IPOData dict 执行校验（含 prospectus_info 嵌套）。"""
    if not ipo_data:
        return {'valid': False, 'errors': ['IPO数据为空'], 'warnings': []}

    validator = ProspectusValidator()

    # 校验顶层字段
    top_result = validator.validate(ipo_data)

    # 校验嵌套的 prospectus_info
    pi = ipo_data.get('prospectus_info')
    if isinstance(pi, dict):
        pi_result = validator.validate(pi)
        top_result['errors'].extend(pi_result['errors'])
        top_result['warnings'].extend(pi_result['warnings'])

    top_result['valid'] = len(top_result['errors']) == 0
    return top_result
