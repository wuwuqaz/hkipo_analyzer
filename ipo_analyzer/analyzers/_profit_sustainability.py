"""盈利可持续性分析器 — 从招股书中提取非经常性损益、政府补贴等指标，评估盈利质量。"""

import re
import logging
from ..utils import _is_num, extract_text_excerpts

logger = logging.getLogger(__name__)

# --- 正则模式 ---

# 非经常性损益
_NON_RECURRING_PNL_PATTERNS = [
    r'(?:非经常性损益|非經常性損益|non[- ]recurring\s+profit\s+and\s+loss|non[- ]recurring\s+items).*?(-?[\d,]+(?:\.\d+)?)',
    r'(?:非经常.*?损益|非經常.*?損益).*?(-?[\d,]+(?:\.\d+)?)',
]

# 扣非净利润
_NON_GAAP_NET_PROFIT_PATTERNS = [
    r'(?:扣非净利润|扣除非經常性損益後淨利潤|non[- ]GAAP\s+net\s+profit).*?(-?[\d,]+(?:\.\d+)?)',
    r'(?:调整后净利润|經調整淨利潤|adjusted\s+net\s+profit).*?(-?[\d,]+(?:\.\d+)?)',
]

# 政府补贴
_GOVERNMENT_SUBSIDY_PATTERNS = [
    r'政府补助人民币([\d,]+(?:\.\d+)?)',
    r'政府补贴人民币([\d,]+(?:\.\d+)?)',
    r'政府补助为([\d,]+(?:\.\d+)?)',
    r'政府补贴为([\d,]+(?:\.\d+)?)',
]

# 资产处置收益
_ASSET_DISPOSAL_PATTERNS = [
    r'(?:资产处置收益|資產處置收益|gain\s+on\s+disposal\s+of\s+assets).{0,10}([\d,]+(?:\.\d+)?)',
]

# 投资收益
_INVESTMENT_INCOME_PATTERNS = [
    r'(?:投资收益|投資收益|investment\s+income).{0,10}([\d,]+(?:\.\d+)?)',
]


class ProfitSustainabilityAnalyzer:
    """盈利可持续性分析器"""

    def analyze(self, prospectus_info, text=''):
        result = {
            'net_profit': prospectus_info.get('net_profit'),
            'non_gaap_net_profit': None,
            'non_recurring_pnl': None,
            'non_recurring_ratio': None,
            'government_subsidy': None,
            'asset_disposal_gain': None,
            'investment_income': None,
            'sustainability_score': 50,
            'label': '缺失',
            'quality_flags': [],
            'confidence': 'missing',
        }

        try:
            text_content = text or prospectus_info.get('_extracted_text', '')
            if not text_content:
                return result

            # 提取扣非净利润
            result['non_gaap_net_profit'] = self._extract_non_gaap_net_profit(text_content)

            # 提取非经常性损益
            result['non_recurring_pnl'] = self._extract_non_recurring_pnl(text_content)

            # 计算非经常性损益占比
            if result['net_profit'] is not None and _is_num(result['net_profit']) and result['net_profit'] != 0:
                if result['non_gaap_net_profit'] is not None:
                    result['non_recurring_ratio'] = round(
                        abs(result['net_profit'] - result['non_gaap_net_profit']) / abs(result['net_profit']),
                        2
                    )
                elif result['non_recurring_pnl'] is not None:
                    result['non_recurring_ratio'] = round(
                        abs(result['non_recurring_pnl']) / abs(result['net_profit']),
                        2
                    )

            # 提取政府补贴
            result['government_subsidy'] = self._extract_government_subsidy(text_content)

            # 提取资产处置收益
            result['asset_disposal_gain'] = self._extract_asset_disposal_gain(text_content)

            # 提取投资收益
            result['investment_income'] = self._extract_investment_income(text_content)

            # 识别质量标志
            result['quality_flags'] = self._identify_quality_flags(result)

            # 计算评分
            result['sustainability_score'] = self._calculate_score(result, prospectus_info)
            result['label'] = self._calculate_label(result['sustainability_score'])
            result['confidence'] = 'regex_context'

        except Exception as e:
            logger.warning("%s: %s", type(self).__name__, e)
            result['_error'] = str(e)

        return result

    def _extract_non_recurring_pnl(self, text):
        """提取非经常性损益（百万）。"""
        for pattern in _NON_RECURRING_PNL_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                try:
                    value = float(match.group(1).replace(',', ''))
                    if abs(value) <= 50000:
                        return value
                except ValueError:
                    continue
        return None

    def _extract_non_gaap_net_profit(self, text):
        """提取扣非净利润（百万）。"""
        for pattern in _NON_GAAP_NET_PROFIT_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                try:
                    value = float(match.group(1).replace(',', ''))
                    if abs(value) <= 50000:
                        return value
                except ValueError:
                    continue
        return None

    def _extract_government_subsidy(self, text):
        """提取政府补贴（百万）。"""
        for pattern in _GOVERNMENT_SUBSIDY_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    value = float(match.group(1).replace(',', ''))
                    if 0 <= value <= 10000:
                        return value
                except ValueError:
                    continue
        return None

    def _extract_asset_disposal_gain(self, text):
        """提取资产处置收益（百万）。"""
        for pattern in _ASSET_DISPOSAL_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    value = float(match.group(1).replace(',', ''))
                    if abs(value) <= 10000:
                        return value
                except ValueError:
                    continue
        return None

    def _extract_investment_income(self, text):
        """提取投资收益（百万）。"""
        for pattern in _INVESTMENT_INCOME_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    value = float(match.group(1).replace(',', ''))
                    if abs(value) <= 10000:
                        return value
                except ValueError:
                    continue
        return None

    def _identify_quality_flags(self, result):
        """识别盈利质量标志。"""
        from ..settings import SETTINGS
        qt = SETTINGS.prospectus_quality
        flags = []

        # 非经常性损益占比过高
        if result.get('non_recurring_ratio') is not None:
            if result['non_recurring_ratio'] > qt.non_recurring_ratio_warning:
                flags.append(f"非经常性损益占比{result['non_recurring_ratio']*100:.1f}%，盈利可持续性存疑")
            elif result['non_recurring_ratio'] > qt.non_recurring_ratio_healthy:
                flags.append(f"非经常性损益占比{result['non_recurring_ratio']*100:.1f}%")

        # 政府补贴依赖
        if result.get('government_subsidy') is not None and result.get('net_profit') is not None and result['net_profit'] > 0:
            subsidy_ratio = result['government_subsidy'] / result['net_profit']
            if subsidy_ratio > qt.government_subsidy_ratio_warning:
                flags.append(f"政府补贴依赖度高(占净利润{subsidy_ratio*100:.1f}%)")
            elif subsidy_ratio > qt.government_subsidy_ratio_healthy:
                flags.append(f"政府补贴占净利润{subsidy_ratio*100:.1f}%")

        # 扣非净利润与净利润反向
        if result.get('non_gaap_net_profit') is not None and result.get('net_profit') is not None:
            if result['net_profit'] > 0 and result['non_gaap_net_profit'] < 0:
                flags.append("扣非净利润为负，实际经营亏损")
            elif result['net_profit'] < 0 and result['non_gaap_net_profit'] > 0:
                flags.append("非经常性损失导致账面亏损")

        return flags

    def _calculate_score(self, result, prospectus_info):
        """计算盈利可持续性评分（0-100）。"""
        from ..settings import SETTINGS
        qt = SETTINGS.prospectus_quality
        score = 50  # 基础分

        # 非经常性损益占比
        nrr = result.get('non_recurring_ratio')
        if nrr is not None:
            if nrr < qt.non_recurring_ratio_healthy:
                score += 30
            elif nrr < 0.20:
                score += 20
            elif nrr < qt.non_recurring_ratio_warning:
                score += 10
            else:
                score -= 10

        # 政府补贴依赖
        if result.get('government_subsidy') is not None and result.get('net_profit') is not None and result['net_profit'] > 0:
            subsidy_ratio = result['government_subsidy'] / result['net_profit']
            if subsidy_ratio < qt.government_subsidy_ratio_healthy:
                score += 20
            elif subsidy_ratio < qt.government_subsidy_ratio_warning:
                score += 10
            else:
                score -= 10

        # 扣非净利润与净利润同向
        if result.get('non_gaap_net_profit') is not None and result.get('net_profit') is not None:
            if (result['net_profit'] > 0 and result['non_gaap_net_profit'] > 0) or \
               (result['net_profit'] < 0 and result['non_gaap_net_profit'] < 0):
                score += 20
            else:
                score -= 20

        # 盈利状态（Biotech豁免）
        from ..industry_router import classify_company
        profile = classify_company(prospectus_info, prospectus_info.get('_extracted_text', ''))
        if profile.is_biotech and not profile.is_profitable:
            # Biotech未盈利是正常现象，不扣分
            score += 10
        elif result.get('net_profit') is not None and result['net_profit'] > 0:
            score += 20  # 已盈利
        elif result.get('net_profit') is not None:
            score -= 10  # 亏损（非Biotech）

        return max(0, min(100, score))

    def _calculate_label(self, score):
        """根据评分计算标签。"""
        if score >= 75:
            return '可持续'
        elif score >= 60:
            return '基本可持续'
        elif score >= 40:
            return '依赖非经常'
        else:
            return '不可持续'
