"""DCF 估值模型（基于 InvestSkill 框架）。

港股IPO DCF估值特点：
- 新股缺乏历史数据，使用简化模型
- 支持三情景分析：悲观/基准/乐观
- 结合港股市场特征调整WACC
"""

from __future__ import annotations

from ..models import DCFValuationResult
from ..utils import _is_num


class DCFValuationAnalyzer:
    """DCF 估值分析器"""

    # 港股IPO默认WACC参数
    DEFAULT_WACC_PCT = 12.0  # 港股小盘IPO通常WACC较高
    DEFAULT_TERMINAL_GROWTH_PCT = 2.5  # 永续增长率

    @staticmethod
    def analyze(prospectus_info: dict) -> DCFValuationResult:
        """分析招股书数据，返回DCF估值结果。"""
        result = DCFValuationResult()

        # 获取基础数据
        net_profit = prospectus_info.get('net_profit')
        revenue = prospectus_info.get('revenue')
        revenue_y1 = prospectus_info.get('revenue_y1')
        market_cap = prospectus_info.get('market_cap_hkd_million')
        offer_price = prospectus_info.get('offer_price')
        sector = prospectus_info.get('sector', 'unknown')

        # 检查是否有足够数据进行DCF
        has_data = _is_num(net_profit) or _is_num(revenue)
        if not has_data:
            result.valuation_label = "数据不足"
            result.confidence = "low"
            result.reasons.append("净利润和收入数据均缺失，无法进行DCF估值")
            return result

        # 1. 计算增长率
        growth_rate = 0.05  # 默认5%
        if _is_num(revenue) and _is_num(revenue_y1) and revenue_y1 > 0:
            growth_rate = (revenue - revenue_y1) / revenue_y1
            growth_rate = max(0.0, min(growth_rate, 0.50))  # 限制在0-50%

        # 2. 根据行业调整WACC
        wacc = DCFValuationAnalyzer._get_wacc_for_sector(sector, growth_rate)
        terminal_growth = DCFValuationAnalyzer._get_terminal_growth(sector)

        result.wacc_pct = wacc
        result.terminal_growth_pct = terminal_growth

        # 3. 计算内在价值（简化版DCF）
        if _is_num(net_profit) and net_profit > 0:
            # 使用净利润作为FCF代理（简化模型）
            base_value = DCFValuationAnalyzer._calculate_dcf(
                fcf=net_profit,
                growth_rate=growth_rate,
                wacc=wacc / 100,
                terminal_growth=terminal_growth / 100,
                years=5
            )
        elif _is_num(revenue) and revenue > 0:
            # 使用收入×净利率估算（假设净利率10%）
            net_margin = 0.10
            if sector in ('biotech', 'healthcare'):
                net_margin = 0.05  # Biotech净利率较低
            elif sector in ('consumer', 'retail'):
                net_margin = 0.15  # 消费类净利率较高

            estimated_fcf = revenue * net_margin
            base_value = DCFValuationAnalyzer._calculate_dcf(
                fcf=estimated_fcf,
                growth_rate=growth_rate,
                wacc=wacc / 100,
                terminal_growth=terminal_growth / 100,
                years=5
            )
        else:
            result.valuation_label = "数据不足"
            result.confidence = "low"
            result.reasons.append("无可用财务数据进行DCF估值")
            return result

        result.base_value_hkd = base_value

        # 4. 三情景分析
        bear_growth = max(0.0, growth_rate - 0.05)
        bull_growth = min(0.50, growth_rate + 0.05)

        if _is_num(net_profit) and net_profit > 0:
            result.bear_value_hkd = DCFValuationAnalyzer._calculate_dcf(
                fcf=net_profit * 0.8,  # 悲观情景：FCF降低20%
                growth_rate=bear_growth,
                wacc=wacc / 100,
                terminal_growth=terminal_growth / 100,
                years=5
            )
            result.bull_value_hkd = DCFValuationAnalyzer._calculate_dcf(
                fcf=net_profit * 1.2,  # 乐观情景：FCF提高20%
                growth_rate=bull_growth,
                wacc=wacc / 100,
                terminal_growth=terminal_growth / 100,
                years=5
            )
        elif _is_num(revenue) and revenue > 0:
            estimated_fcf = revenue * net_margin
            result.bear_value_hkd = DCFValuationAnalyzer._calculate_dcf(
                fcf=estimated_fcf * 0.8,
                growth_rate=bear_growth,
                wacc=wacc / 100,
                terminal_growth=terminal_growth / 100,
                years=5
            )
            result.bull_value_hkd = DCFValuationAnalyzer._calculate_dcf(
                fcf=estimated_fcf * 1.2,
                growth_rate=bull_growth,
                wacc=wacc / 100,
                terminal_growth=terminal_growth / 100,
                years=5
            )

        # 5. 计算上行空间
        if _is_num(market_cap) and market_cap > 0:
            result.intrinsic_value_hkd = base_value
            result.upside_pct = (base_value - market_cap) / market_cap * 100

            if _is_num(result.bear_value_hkd):
                result.bear_upside_pct = (result.bear_value_hkd - market_cap) / market_cap * 100
            if _is_num(result.bull_value_hkd):
                result.bull_upside_pct = (result.bull_value_hkd - market_cap) / market_cap * 100

            # 6. 估值结论
            upside = result.upside_pct
            if upside >= 30:
                result.valuation_label = "低估"
                result.reasons.append(f"DCF内在价值高于市值{upside:.1f}%")
            elif upside >= 10:
                result.valuation_label = "合理偏低"
                result.reasons.append(f"DCF内在价值高于市值{upside:.1f}%，估值合理偏低")
            elif upside >= -10:
                result.valuation_label = "合理"
                result.reasons.append(f"DCF内在价值与市值基本一致(差异{abs(upside):.1f}%)")
            elif upside >= -30:
                result.valuation_label = "合理偏高"
                result.reasons.append(f"DCF内在价值低于市值{abs(upside):.1f}%，估值偏高")
            else:
                result.valuation_label = "高估"
                result.reasons.append(f"DCF内在价值低于市值{abs(upside):.1f}%，估值偏高")

            # 三情景结论
            if _is_num(result.bear_upside_pct):
                result.reasons.append(f"悲观情景：{result.bear_upside_pct:.1f}%")
            if _is_num(result.bull_upside_pct):
                result.reasons.append(f"乐观情景：{result.bull_upside_pct:.1f}%")
        else:
            result.valuation_label = "无法对比"
            result.reasons.append("市值数据缺失，无法计算上行空间")

        result.offer_price_hkd = offer_price
        result.confidence = "medium" if _is_num(base_value) else "low"

        return result

    @staticmethod
    def _calculate_dcf(
        fcf: float,
        growth_rate: float,
        wacc: float,
        terminal_growth: float,
        years: int = 5
    ) -> float:
        """简化DCF计算。

        Args:
            fcf: 自由现金流
            growth_rate: 增长率
            wacc: 加权平均资本成本
            terminal_growth: 永续增长率
            years: 预测年限
        """
        pv = 0.0
        current_fcf = fcf

        # 预测期现金流折现
        for year in range(1, years + 1):
            current_fcf *= (1 + growth_rate)
            pv += current_fcf / ((1 + wacc) ** year)

        # 终值计算（Gordon Growth Model）
        terminal_value = current_fcf * (1 + terminal_growth) / (wacc - terminal_growth)
        pv_terminal = terminal_value / ((1 + wacc) ** years)

        return pv + pv_terminal

    @staticmethod
    def _get_wacc_for_sector(sector: str, growth_rate: float) -> float:
        """根据行业和增长率获取WACC。"""
        base_wacc = DCFValuationAnalyzer.DEFAULT_WACC_PCT

        # 行业调整
        if sector in ('biotech', 'healthcare'):
            base_wacc += 2.0  # Biotech风险高，WACC更高
        elif sector in ('technology', 'hardtech'):
            base_wacc += 1.0  # 科技股风险中等
        elif sector in ('consumer', 'retail'):
            base_wacc -= 0.5  # 消费股相对稳定
        elif sector in ('financial', 'banking'):
            base_wacc -= 1.0  # 金融股最稳定

        # 增长率调整（高增长公司风险更高）
        if growth_rate > 0.30:
            base_wacc += 1.0
        elif growth_rate > 0.20:
            base_wacc += 0.5

        return base_wacc

    @staticmethod
    def _get_terminal_growth(sector: str) -> float:
        """根据行业获取永续增长率。"""
        if sector in ('biotech', 'healthcare'):
            return 3.0  # Biotech长期增长潜力高
        elif sector in ('technology', 'hardtech'):
            return 3.0
        elif sector in ('consumer', 'retail'):
            return 2.5
        else:
            return DCFValuationAnalyzer.DEFAULT_TERMINAL_GROWTH_PCT
