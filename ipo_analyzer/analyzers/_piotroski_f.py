"""Piotroski F-Score 升级版财务质量评分（针对港股IPO优化）。

基于 InvestSkill 的 Piotroski 框架，但针对港股IPO公司进行优化：
- 原版 9 分制（盈利能力 3 + 杠杆 3 + 运营 3）
- 港股版扩展 IPO 特殊维度（现金跑道 + 收入增速）
"""

from __future__ import annotations

from ..models import PiotroskiFResult
from ..utils import _is_num


class PiotroskiFAnalyzer:
    """Piotroski F-Score 升级版财务质量评分"""

    @staticmethod
    def analyze(prospectus_info: dict) -> PiotroskiFResult:
        """分析招股书数据，返回 Piotroski F-Score 结果。"""
        result = PiotroskiFResult()

        # 1. 盈利能力分析 (0-3)
        profit_score = 0
        profit_reasons = []

        # 1.1 ROA > 0?
        net_profit = prospectus_info.get('net_profit')
        if _is_num(net_profit) and net_profit > 0:
            profit_score += 1
            result.profit_roa = True
            profit_reasons.append("净利润为正")
        else:
            profit_reasons.append("净利润为负或未披露")

        # 1.2 OCF > 0?
        cf = prospectus_info.get('cashflow', {}) or {}
        ocf = cf.get('operating_cash_flow')
        if _is_num(ocf) and ocf > 0:
            profit_score += 1
            result.profit_ocf_positive = True
            profit_reasons.append("经营现金流为正")
        else:
            profit_reasons.append("经营现金流为负或未披露")

        # 1.3 ROA 改善？
        net_profit_y1 = prospectus_info.get('net_profit_y1')
        if _is_num(net_profit) and _is_num(net_profit_y1):
            if net_profit > net_profit_y1:
                profit_score += 1
                result.profit_roa_improvement = True
                profit_reasons.append("净利润同比增长")
            else:
                profit_reasons.append("净利润同比下滑")

        result.profit_score = profit_score

        # 2. 杠杆/流动性/融资分析 (0-3)
        leverage_score = 0
        leverage_reasons = []

        # 2.1 资产负债率下降？
        cf_data = cf.get('receivables_amount')  # 暂用应收作为代理指标
        if cf_data is not None:
            leverage_score += 1
            result.leverage_debt_ratio_drop = True
            leverage_reasons.append("营运资本结构健康")
        else:
            leverage_reasons.append("资产负债数据不足")

        # 2.2 流动比率改善？
        current_ratio = cf.get('working_capital_pressure_score')
        if _is_num(current_ratio) and current_ratio < 40:
            leverage_score += 1
            result.leverage_current_ratio_improve = True
            leverage_reasons.append("营运资本压力低")

        # 2.3 无新股增发（IPO本身不适用，给1分）
        leverage_score += 1
        result.leverage_no_new_shares = True
        leverage_reasons.append("IPO融资后暂无进一步稀释风险")

        result.leverage_score = leverage_score

        # 3. 运营效率分析 (0-2)
        operations_score = 0
        operations_reasons = []

        # 3.1 毛利率改善？
        gm = prospectus_info.get('gross_margin')
        gm_y1 = prospectus_info.get('gross_margin_y1')
        if _is_num(gm) and _is_num(gm_y1):
            if gm >= gm_y1:
                operations_score += 1
                result.operations_gm_improve = True
                operations_reasons.append("毛利率同比持平或改善")
            else:
                operations_reasons.append("毛利率同比下滑")

        # 3.2 应收周转改善？
        rec_days = cf.get('receivables_turnover_days_latest')
        if _is_num(rec_days) and rec_days < 150:
            operations_score += 1
            result.operations_at_improve = True
            operations_reasons.append("应收周转天数合理(<150天)")
        elif not _is_num(rec_days):
            operations_score += 1
            operations_reasons.append("应收周转数据不足，按中性评估")

        result.operations_score = operations_score

        # 4. IPO特殊维度 (0-2)
        ipo_special_score = 0
        ipo_reasons = []

        # 4.1 现金跑道 > 1年?
        cash_runway = cf.get('cash_runway_years')
        if _is_num(cash_runway) and cash_runway >= 1.5:
            ipo_special_score += 1
            result.ipo_cash_runway_ok = True
            ipo_reasons.append(f"现金跑道充裕({cash_runway:.1f}年)")
        elif _is_num(cash_runway) and cash_runway >= 1:
            ipo_special_score += 0
            ipo_reasons.append(f"现金跑道一般({cash_runway:.1f}年)")
        else:
            ipo_reasons.append("现金跑道不足1年或数据缺失")

        # 4.2 收入增长 > 10%?
        revenue = prospectus_info.get('revenue')
        revenue_y1 = prospectus_info.get('revenue_y1')
        if _is_num(revenue) and _is_num(revenue_y1) and revenue_y1 > 0:
            growth = (revenue - revenue_y1) / revenue_y1
            if growth >= 0.10:
                ipo_special_score += 1
                result.ipo_revenue_growth = True
                ipo_reasons.append(f"收入增长强劲({growth*100:.1f}%)")
            else:
                ipo_reasons.append(f"收入增长偏弱({growth*100:.1f}%)")

        result.ipo_special_score = ipo_special_score

        # 计算总分
        total = profit_score + leverage_score + operations_score + ipo_special_score
        result.total_score = total

        # 评级
        if total >= 9:
            result.grade = "优秀"
        elif total >= 7:
            result.grade = "良好"
        elif total >= 5:
            result.grade = "中等"
        elif total >= 3:
            result.grade = "偏弱"
        else:
            result.grade = "较弱"

        # 风险红旗
        if _is_num(net_profit) and net_profit < 0 and _is_num(ocf) and ocf < 0:
            result.red_flags.append("净利润和经营现金流均为负，持续经营能力存疑")
        if _is_num(cash_runway) and cash_runway < 1:
            result.red_flags.append(f"现金跑道不足1年({cash_runway:.1f}年)，融资紧迫")

        # 汇总原因
        result.reasons = profit_reasons + leverage_reasons + operations_reasons + ipo_reasons

        # 置信度
        data_count = sum(1 for v in [net_profit, ocf, gm, revenue] if _is_num(v))
        if data_count >= 3:
            result.confidence = "high"
        elif data_count >= 2:
            result.confidence = "medium"
        else:
            result.confidence = "low"

        return result
