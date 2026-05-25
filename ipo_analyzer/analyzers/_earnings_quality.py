"""盈利质量综合分析器 — 从多维度评估盈利是否真实、可持续。

核心维度：
1. 应收账款质量：应收增速 vs 收入增速（如果应收增长远快于收入，可能是虚增收入）
2. 存货质量：存货周转天数变化（存货积压可能意味着销售不畅）
3. 经营现金流质量：OCF/净利润比值及趋势（利润含金量）
4. 非经常性损益占比：扣非净利润 vs 净利润（盈利是否依赖一次性项目）
5. 资本支出效率：Capex/折旧摊销比例（维持性 vs 扩张性支出）
6. 盈利可持续性：综合以上维度给出整体评分

参考框架：
- Beneish M-Score（财务造假检测）
- Piotroski F-Score（财务质量评分）
- Accrual Quality（应计质量）
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..utils import _is_num
from ..settings import SETTINGS

logger = logging.getLogger(__name__)


class EarningsQualityAnalyzer:
    """盈利质量综合分析器"""

    def analyze(self, prospectus_info: dict, text: str = '') -> dict:
        """分析盈利质量。

        Args:
            prospectus_info: 招股书解析结果
            text: 招股书原始文本（用于正则提取）

        Returns:
            盈利质量分析结果
        """
        result = {
            'earnings_quality_score': 50,
            'label': '缺失',
            'receivables_quality': self._default_subscore(),
            'inventory_quality': self._default_subscore(),
            'cashflow_quality': self._default_subscore(),
            'non_recurring_quality': self._default_subscore(),
            'capex_efficiency': self._default_subscore(),
            'accrual_quality': self._default_subscore(),
            'quality_flags': [],
            'risk_signals': [],
            'positive_signals': [],
            'confidence': 'missing',
        }

        try:
            cashflow = prospectus_info.get('cashflow') or {}
            profit_sustainability = prospectus_info.get('profit_sustainability') or {}

            # 1. 应收账款质量
            result['receivables_quality'] = self._analyze_receivables_quality(
                prospectus_info, cashflow
            )

            # 2. 存货质量
            result['inventory_quality'] = self._analyze_inventory_quality(
                prospectus_info, cashflow
            )

            # 3. 经营现金流质量
            result['cashflow_quality'] = self._analyze_cashflow_quality(
                prospectus_info, cashflow
            )

            # 4. 非经常性损益质量
            result['non_recurring_quality'] = self._analyze_non_recurring_quality(
                prospectus_info, profit_sustainability
            )

            # 5. 资本支出效率
            result['capex_efficiency'] = self._analyze_capex_efficiency(
                prospectus_info, cashflow, text
            )

            # 6. 应计质量
            result['accrual_quality'] = self._analyze_accrual_quality(
                prospectus_info, cashflow
            )

            # 综合评分
            result['earnings_quality_score'] = self._calculate_composite_score(result)
            result['label'] = self._calculate_label(result['earnings_quality_score'])
            result['quality_flags'] = self._collect_flags(result)
            result['confidence'] = 'computed'

        except Exception as e:
            logger.warning("%s: %s", type(self).__name__, e)
            result['_error'] = str(e)

        return result

    def _default_subscore(self) -> dict:
        """返回默认子评分。"""
        return {
            'score': 50,
            'label': '缺失',
            'reasons': [],
        }

    def _analyze_receivables_quality(
        self, prospectus_info: dict, cashflow: dict
    ) -> dict:
        """分析应收账款质量。

        核心逻辑：
        - 应收增速 > 收入增速：可能提前确认收入或放宽信用政策
        - 应收/收入 > 50%：回款能力弱
        - 应收周转天数 > 120天：回款周期长
        """
        result = self._default_subscore()
        score = 50

        revenue = prospectus_info.get('revenue')
        revenue_y1 = prospectus_info.get('revenue_y1')
        receivables = cashflow.get('receivables_amount')
        receivables_prev = cashflow.get('receivables_amount_prev')
        receivables_turnover_days = cashflow.get('receivables_turnover_days_latest')
        receivables_growth_vs_revenue = cashflow.get('receivables_growth_vs_revenue')

        # 计算应收增速 vs 收入增速
        receivables_growth = None
        revenue_growth = None

        if _is_num(receivables) and _is_num(receivables_prev) and receivables_prev > 0:
            receivables_growth = (receivables - receivables_prev) / receivables_prev

        if _is_num(revenue) and _is_num(revenue_y1) and revenue_y1 > 0:
            revenue_growth = (revenue - revenue_y1) / revenue_y1

        # 对比应收增速和收入增速
        if receivables_growth is not None and revenue_growth is not None:
            growth_gap = receivables_growth - revenue_growth
            if growth_gap > 0.20:  # 应收增速比收入增速高20%以上
                score -= 20
                result['reasons'].append(
                    f'应收增速({receivables_growth*100:.1f}%)远高于收入增速({revenue_growth*100:.1f}%)，'
                    f'可能提前确认收入或放宽信用政策'
                )
            elif growth_gap > 0.10:
                score -= 10
                result['reasons'].append(
                    f'应收增速({receivables_growth*100:.1f}%)高于收入增速({revenue_growth*100:.1f}%)'
                )
            elif growth_gap < -0.10:
                score += 10
                result['reasons'].append(
                    f'应收增速低于收入增速，回款能力改善'
                )

        # 应收/收入比例
        if _is_num(receivables) and _is_num(revenue) and revenue > 0:
            receivables_to_revenue = receivables / revenue
            if receivables_to_revenue > 0.70:
                score -= 15
                result['reasons'].append(
                    f'应收/收入高达{receivables_to_revenue*100:.1f}%，回款能力弱'
                )
            elif receivables_to_revenue > 0.50:
                score -= 5
                result['reasons'].append(
                    f'应收/收入{receivables_to_revenue*100:.1f}%，回款周期偏长'
                )
            elif receivables_to_revenue < 0.20:
                score += 10
                result['reasons'].append(
                    f'应收/收入仅{receivables_to_revenue*100:.1f}%，回款能力强'
                )

        # 应收周转天数
        if _is_num(receivables_turnover_days):
            if receivables_turnover_days > 180:
                score -= 15
                result['reasons'].append(
                    f'应收周转天数{receivables_turnover_days:.0f}天，回款周期极长'
                )
            elif receivables_turnover_days > 120:
                score -= 5
                result['reasons'].append(
                    f'应收周转天数{receivables_turnover_days:.0f}天，回款周期偏长'
                )
            elif receivables_turnover_days < 60:
                score += 10
                result['reasons'].append(
                    f'应收周转天数{receivables_turnover_days:.0f}天，回款效率高'
                )

        score = max(0, min(100, score))
        result['score'] = score
        result['label'] = self._subscore_label(score)
        return result

    def _analyze_inventory_quality(
        self, prospectus_info: dict, cashflow: dict
    ) -> dict:
        """分析存货质量。

        核心逻辑：
        - 存货增速 > 收入增速：可能销售不畅或备货过多
        - 存货周转天数上升：存货积压风险
        - 存货/收入 > 60%：存货占用资金多
        """
        result = self._default_subscore()
        score = 50

        revenue = prospectus_info.get('revenue')
        revenue_y1 = prospectus_info.get('revenue_y1')
        inventory = cashflow.get('inventory_amount')
        inventory_prev = cashflow.get('inventory_amount_prev')
        inventory_turnover_days = cashflow.get('inventory_turnover_days_latest')

        # 计算存货增速 vs 收入增速
        inventory_growth = None
        revenue_growth = None

        if _is_num(inventory) and _is_num(inventory_prev) and inventory_prev > 0:
            inventory_growth = (inventory - inventory_prev) / inventory_prev

        if _is_num(revenue) and _is_num(revenue_y1) and revenue_y1 > 0:
            revenue_growth = (revenue - revenue_y1) / revenue_y1

        # 对比存货增速和收入增速
        if inventory_growth is not None and revenue_growth is not None:
            growth_gap = inventory_growth - revenue_growth
            if growth_gap > 0.20:
                score -= 15
                result['reasons'].append(
                    f'存货增速({inventory_growth*100:.1f}%)远高于收入增速({revenue_growth*100:.1f}%)，'
                    f'可能销售不畅或备货过多'
                )
            elif growth_gap > 0.10:
                score -= 5
                result['reasons'].append(
                    f'存货增速({inventory_growth*100:.1f}%)高于收入增速({revenue_growth*100:.1f}%)'
                )
            elif growth_gap < -0.10:
                score += 10
                result['reasons'].append(
                    f'存货增速低于收入增速，库存管理效率提升'
                )

        # 存货/收入比例
        if _is_num(inventory) and _is_num(revenue) and revenue > 0:
            inventory_to_revenue = inventory / revenue
            if inventory_to_revenue > 0.80:
                score -= 15
                result['reasons'].append(
                    f'存货/收入高达{inventory_to_revenue*100:.1f}%，存货占用资金多'
                )
            elif inventory_to_revenue > 0.60:
                score -= 5
                result['reasons'].append(
                    f'存货/收入{inventory_to_revenue*100:.1f}%，存货水平偏高'
                )
            elif inventory_to_revenue < 0.20:
                score += 10
                result['reasons'].append(
                    f'存货/收入仅{inventory_to_revenue*100:.1f}%，库存周转快'
                )

        # 存货周转天数
        if _is_num(inventory_turnover_days):
            if inventory_turnover_days > 200:
                score -= 15
                result['reasons'].append(
                    f'存货周转天数{inventory_turnover_days:.0f}天，存货积压严重'
                )
            elif inventory_turnover_days > 150:
                score -= 5
                result['reasons'].append(
                    f'存货周转天数{inventory_turnover_days:.0f}天，存货周转偏慢'
                )
            elif inventory_turnover_days < 60:
                score += 10
                result['reasons'].append(
                    f'存货周转天数{inventory_turnover_days:.0f}天，库存管理优秀'
                )

        score = max(0, min(100, score))
        result['score'] = score
        result['label'] = self._subscore_label(score)
        return result

    def _analyze_cashflow_quality(
        self, prospectus_info: dict, cashflow: dict
    ) -> dict:
        """分析经营现金流质量。

        核心逻辑：
        - OCF/净利润 > 1.0：利润含金量高
        - OCF/净利润 < 0.5：利润含金量低
        - OCF为负：经营现金流为负（Biotech除外）
        - OCF趋势改善/恶化
        """
        result = self._default_subscore()
        score = 50

        net_profit = prospectus_info.get('net_profit')
        net_profit_y1 = prospectus_info.get('net_profit_y1')
        operating_cash_flow = cashflow.get('operating_cash_flow')
        operating_cash_flow_prev = cashflow.get('operating_cash_flow_prev')
        ocf_to_net_profit = cashflow.get('ocf_to_net_profit')
        ocf_to_revenue = cashflow.get('ocf_to_revenue')
        cash_quality_label = cashflow.get('cash_quality_label')

        # OCF/净利润比值
        if _is_num(ocf_to_net_profit) and _is_num(net_profit) and net_profit > 0:
            if ocf_to_net_profit >= 1.2:
                score += 20
                result['reasons'].append(
                    f'OCF/净利润{ocf_to_net_profit:.2f}，利润含金量高'
                )
            elif ocf_to_net_profit >= 1.0:
                score += 10
                result['reasons'].append(
                    f'OCF/净利润{ocf_to_net_profit:.2f}，利润含金量尚可'
                )
            elif ocf_to_net_profit >= 0.5:
                score -= 5
                result['reasons'].append(
                    f'OCF/净利润{ocf_to_net_profit:.2f}，利润含金量偏低'
                )
            else:
                score -= 20
                result['reasons'].append(
                    f'OCF/净利润仅{ocf_to_net_profit:.2f}，利润含金量低'
                )

        # OCF/收入比值
        if _is_num(ocf_to_revenue) and _is_num(net_profit) and net_profit > 0:
            if ocf_to_revenue >= 0.20:
                score += 10
                result['reasons'].append(
                    f'OCF/收入{ocf_to_revenue*100:.1f}%，现金创造能力强'
                )
            elif ocf_to_revenue >= 0.10:
                score += 5
                result['reasons'].append(
                    f'OCF/收入{ocf_to_revenue*100:.1f}%，现金创造能力尚可'
                )
            elif ocf_to_revenue < 0:
                score -= 15
                result['reasons'].append(
                    f'OCF/收入为负({ocf_to_revenue*100:.1f}%)，经营现金净流出'
                )

        # OCF趋势
        if _is_num(operating_cash_flow) and _is_num(operating_cash_flow_prev):
            if operating_cash_flow > operating_cash_flow_prev:
                score += 10
                result['reasons'].append('经营现金流趋势改善')
            else:
                score -= 10
                result['reasons'].append('经营现金流趋势恶化')

        # Biotech豁免
        from ..industry_router import classify_company
        profile = classify_company(prospectus_info, '')
        if profile.is_biotech and _is_num(operating_cash_flow) and operating_cash_flow < 0:
            # Biotech未盈利是正常现象，不扣分
            if cashflow.get('cash_runway_years') and cashflow['cash_runway_years'] >= 5:
                score += 5
                result['reasons'].append('Biotech现金runway充足(≥5年)，经营现金流为负可接受')

        score = max(0, min(100, score))
        result['score'] = score
        result['label'] = self._subscore_label(score)
        return result

    def _analyze_non_recurring_quality(
        self, prospectus_info: dict, profit_sustainability: dict
    ) -> dict:
        """分析非经常性损益质量。

        核心逻辑：
        - 非经常性损益占比 < 10%：盈利质量高
        - 非经常性损益占比 > 30%：盈利依赖一次性项目
        - 扣非净利润与净利润反向：盈利质量极差
        """
        result = self._default_subscore()
        score = 50

        net_profit = prospectus_info.get('net_profit')
        non_recurring_ratio = profit_sustainability.get('non_recurring_ratio')
        non_gaap_net_profit = profit_sustainability.get('non_gaap_net_profit')
        government_subsidy = profit_sustainability.get('government_subsidy')
        quality_flags = profit_sustainability.get('quality_flags', [])

        # 非经常性损益占比
        if _is_num(non_recurring_ratio):
            if non_recurring_ratio < 0.10:
                score += 20
                result['reasons'].append(
                    f'非经常性损益占比仅{non_recurring_ratio*100:.1f}%，盈利质量高'
                )
            elif non_recurring_ratio < 0.20:
                score += 10
                result['reasons'].append(
                    f'非经常性损益占比{non_recurring_ratio*100:.1f}%，盈利质量尚可'
                )
            elif non_recurring_ratio < 0.30:
                score -= 5
                result['reasons'].append(
                    f'非经常性损益占比{non_recurring_ratio*100:.1f}%，盈利有一定依赖'
                )
            else:
                score -= 20
                result['reasons'].append(
                    f'非经常性损益占比{non_recurring_ratio*100:.1f}%，盈利严重依赖一次性项目'
                )

        # 扣非净利润与净利润方向
        if _is_num(non_gaap_net_profit) and _is_num(net_profit):
            if net_profit > 0 and non_gaap_net_profit < 0:
                score -= 30
                result['reasons'].append(
                    '扣非净利润为负，实际经营亏损，盈利质量极差'
                )
            elif net_profit < 0 and non_gaap_net_profit > 0:
                score -= 10
                result['reasons'].append(
                    '非经常性损失导致账面亏损，实际经营可能为正'
                )
            elif net_profit > 0 and non_gaap_net_profit > 0:
                score += 15
                result['reasons'].append(
                    '扣非净利润与净利润同向为正，盈利质量扎实'
                )

        # 政府补贴依赖
        if _is_num(government_subsidy) and _is_num(net_profit) and net_profit > 0:
            subsidy_ratio = government_subsidy / net_profit
            if subsidy_ratio > 0.15:
                score -= 10
                result['reasons'].append(
                    f'政府补贴占净利润{subsidy_ratio*100:.1f}%，有一定依赖'
                )
            elif subsidy_ratio > 0.05:
                score -= 5
                result['reasons'].append(
                    f'政府补贴占净利润{subsidy_ratio*100:.1f}%'
                )

        score = max(0, min(100, score))
        result['score'] = score
        result['label'] = self._subscore_label(score)
        return result

    def _analyze_capex_efficiency(
        self, prospectus_info: dict, cashflow: dict, text: str
    ) -> dict:
        """分析资本支出效率。

        核心逻辑：
        - Capex/折旧摊销 > 2.0：扩张性支出，增长潜力大
        - Capex/折旧摊销 < 0.5：维持性支出，增长乏力
        - Capex/收入 > 20%：重资产模式，资金需求大
        """
        result = self._default_subscore()
        score = 50

        import re
        from . import _adjust_for_unit

        # 尝试从文本中提取资本支出和折旧摊销
        capex = self._extract_capex(text)
        depreciation = self._extract_depreciation(text)

        revenue = prospectus_info.get('revenue')

        # Capex/折旧摊销比例
        if _is_num(capex) and _is_num(depreciation) and depreciation > 0:
            capex_to_depreciation = capex / depreciation
            if capex_to_depreciation > 2.0:
                score += 15
                result['reasons'].append(
                    f'Capex/折旧摊销{capex_to_depreciation:.2f}x，扩张性支出，增长潜力大'
                )
            elif capex_to_depreciation > 1.0:
                score += 5
                result['reasons'].append(
                    f'Capex/折旧摊销{capex_to_depreciation:.2f}x，适度扩张'
                )
            elif capex_to_depreciation < 0.5:
                score -= 10
                result['reasons'].append(
                    f'Capex/折旧摊销{capex_to_depreciation:.2f}x，维持性支出，增长乏力'
                )

        # Capex/收入比例
        if _is_num(capex) and _is_num(revenue) and revenue > 0:
            capex_to_revenue = capex / revenue
            if capex_to_revenue > 0.30:
                score -= 10
                result['reasons'].append(
                    f'Capex/收入{capex_to_revenue*100:.1f}%，重资产模式，资金需求大'
                )
            elif capex_to_revenue > 0.20:
                score -= 5
                result['reasons'].append(
                    f'Capex/收入{capex_to_revenue*100:.1f}%，资本支出较高'
                )
            elif capex_to_revenue < 0.05:
                score += 10
                result['reasons'].append(
                    f'Capex/收入仅{capex_to_revenue*100:.1f}%，轻资产模式'
                )

        if not _is_num(capex) and not _is_num(depreciation):
            result['reasons'].append('招股书未披露Capex/折旧摊销数据')

        score = max(0, min(100, score))
        result['score'] = score
        result['label'] = self._subscore_label(score)
        return result

    def _extract_capex(self, text: str) -> Optional[float]:
        """从文本中提取资本支出（百万元）。"""
        import re
        from . import _adjust_for_unit

        patterns = [
            r'(?:资本支出|資本開支|capital\s+expenditure|capex|purchase\s+of\s+property)[^.\n]{0,120}?([\d,]+(?:\.\d+)?)',
            r'(?:购置固定资产|購買物業、廠房及設備)[^.\n]{0,120}?([\d,]+(?:\.\d+)?)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    value = float(match.group(1).replace(',', ''))
                    if 0 < value <= 50000:
                        # 单位调整
                        unit_context = text[max(0, match.start() - 500):match.start()]
                        return _adjust_for_unit(value, unit_context)
                except ValueError:
                    continue
        return None

    def _extract_depreciation(self, text: str) -> Optional[float]:
        """从文本中提取折旧摊销（百万元）。"""
        import re
        from . import _adjust_for_unit

        patterns = [
            r'(?:折旧|折舊|depreciation\s+and\s+amortization|depreciation)[^.\n]{0,120}?([\d,]+(?:\.\d+)?)',
            r'(?:折旧及摊销|折舊及攤銷)[^.\n]{0,120}?([\d,]+(?:\.\d+)?)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    value = float(match.group(1).replace(',', ''))
                    if 0 < value <= 50000:
                        unit_context = text[max(0, match.start() - 500):match.start()]
                        return _adjust_for_unit(value, unit_context)
                except ValueError:
                    continue
        return None

    def _analyze_accrual_quality(
        self, prospectus_info: dict, cashflow: dict
    ) -> dict:
        """分析应计质量。

        核心逻辑：
        - 应计利润 = 净利润 - 经营现金流
        - 应计利润/总资产 > 10%：应计质量差
        - 应计利润趋势恶化：盈利质量下降
        """
        result = self._default_subscore()
        score = 50

        net_profit = prospectus_info.get('net_profit')
        operating_cash_flow = cashflow.get('operating_cash_flow')

        # 计算应计利润
        if _is_num(net_profit) and _is_num(operating_cash_flow):
            accruals = net_profit - operating_cash_flow
            accruals_ratio = None

            # 应计利润/净利润
            if _is_num(net_profit) and net_profit > 0:
                accruals_ratio = accruals / net_profit
                if accruals_ratio < 0.10:
                    score += 20
                    result['reasons'].append(
                        f'应计利润/净利润{accruals_ratio*100:.1f}%，盈利质量高'
                    )
                elif accruals_ratio < 0.30:
                    score += 5
                    result['reasons'].append(
                        f'应计利润/净利润{accruals_ratio*100:.1f}%，盈利质量尚可'
                    )
                elif accruals_ratio > 0.50:
                    score -= 15
                    result['reasons'].append(
                        f'应计利润/净利润{accruals_ratio*100:.1f}%，盈利质量差'
                    )
                else:
                    score -= 5
                    result['reasons'].append(
                        f'应计利润/净利润{accruals_ratio*100:.1f}%'
                    )

        score = max(0, min(100, score))
        result['score'] = score
        result['label'] = self._subscore_label(score)
        return result

    def _calculate_composite_score(self, result: dict) -> int:
        """计算综合盈利质量评分。

        权重分配：
        - 经营现金流质量：30%（最重要，利润含金量）
        - 应收账款质量：20%（收入真实性）
        - 非经常性损益质量：20%（盈利可持续性）
        - 存货质量：15%（销售健康度）
        - 应计质量：10%（财务操纵风险）
        - 资本支出效率：5%（增长潜力）
        """
        weights = {
            'cashflow_quality': 0.30,
            'receivables_quality': 0.20,
            'non_recurring_quality': 0.20,
            'inventory_quality': 0.15,
            'accrual_quality': 0.10,
            'capex_efficiency': 0.05,
        }

        composite_score = 0
        total_weight = 0

        for dimension, weight in weights.items():
            subscore = result[dimension]['score']
            composite_score += subscore * weight
            total_weight += weight

        if total_weight > 0:
            composite_score = composite_score / total_weight

        return int(max(0, min(100, round(composite_score))))

    def _calculate_label(self, score: int) -> str:
        """根据评分计算标签。"""
        if score >= 75:
            return '强'
        elif score >= 60:
            return '良好'
        elif score >= 45:
            return '一般'
        elif score >= 30:
            return '偏弱'
        else:
            return '弱'

    def _subscore_label(self, score: int) -> str:
        """子评分标签。"""
        if score >= 70:
            return '强'
        elif score >= 55:
            return '良好'
        elif score >= 40:
            return '一般'
        elif score >= 25:
            return '偏弱'
        else:
            return '弱'

    def _collect_flags(self, result: dict) -> list:
        """收集所有质量标志。"""
        flags = []

        # 收集风险信号
        risk_signals = []
        positive_signals = []

        for dimension in ['receivables_quality', 'inventory_quality', 'cashflow_quality',
                         'non_recurring_quality', 'capex_efficiency', 'accrual_quality']:
            subscore = result[dimension]
            if subscore['score'] < 30:
                risk_signals.append(f"{dimension}: {subscore['label']}({subscore['score']})")
                for reason in subscore.get('reasons', []):
                    risk_signals.append(f"  - {reason}")
            elif subscore['score'] >= 70:
                positive_signals.append(f"{dimension}: {subscore['label']}({subscore['score']})")
                for reason in subscore.get('reasons', []):
                    positive_signals.append(f"  - {reason}")

        result['risk_signals'] = risk_signals
        result['positive_signals'] = positive_signals

        return flags
