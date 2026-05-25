"""资产负债结构分析器 — 从招股书中提取资产负债率、流动比率、有息负债等指标。"""

import re
import logging
from ..utils import _is_num

logger = logging.getLogger(__name__)

# --- 正则模式 ---

# 资产负债率
_ASSET_LIABILITY_RATIO_PATTERNS = [
    r'资产负债率为(\d+(?:\.\d+)?)\s*%',
    r'资产负债率=(\d+(?:\.\d+)?)\s*%',
    r'资产负债率：(\d+(?:\.\d+)?)\s*%',
]

# 流动比率
_CURRENT_RATIO_PATTERNS = [
    r'流动比率为(\d+(?:\.\d+)?)',
    r'流动比率=(\d+(?:\.\d+)?)',
    r'流动比率：(\d+(?:\.\d+)?)',
]

# 有息负债（短期借款+长期借款）
_SHORT_TERM_DEBT_PATTERNS = [
    r'(?:短期借款|短期借款|short[- ]term\s+debt|short[- ]term\s+borrowings).{0,10}([\d,]+(?:\.\d+)?)',
]
_LONG_TERM_DEBT_PATTERNS = [
    r'(?:长期借款|長期借款|long[- ]term\s+debt|long[- ]term\s+borrowings).{0,10}([\d,]+(?:\.\d+)?)',
]

# 利息保障倍数
_INTEREST_COVERAGE_PATTERNS = [
    r'(?:利息保障倍数|利息保障倍數|interest\s+coverage\s+ratio).{0,10}(\d+(?:\.\d+)?)',
]

# 股东权益
_TOTAL_EQUITY_PATTERNS = [
    r'(?:股东权益|股東權益|total\s+equity|shareholders\'\s+equity|shareholders\'\s+funds).{0,10}([\d,]+(?:\.\d+)?)',
]


class BalanceSheetAnalyzer:
    """资产负债结构分析器"""

    def analyze(self, prospectus_info, text=''):
        result = {
            'asset_liability_ratio': None,
            'interest_bearing_debt_ratio': None,
            'current_ratio': None,
            'quick_ratio': None,
            'interest_coverage_ratio': None,
            'short_term_debt': None,
            'long_term_debt': None,
            'total_equity': None,
            'balance_sheet_score': 50,
            'label': '缺失',
            'risk_flags': [],
            'confidence': 'missing',
        }

        try:
            text_content = text or prospectus_info.get('_extracted_text', '')
            if not text_content:
                return result

            # 提取资产负债率
            result['asset_liability_ratio'] = self._extract_asset_liability_ratio(text_content)

            # 提取流动比率
            result['current_ratio'] = self._extract_current_ratio(text_content)

            # 提取短期借款和长期借款
            result['short_term_debt'] = self._extract_short_term_debt(text_content)
            result['long_term_debt'] = self._extract_long_term_debt(text_content)

            # 计算有息负债率
            total_equity = self._extract_total_equity(text_content)
            result['total_equity'] = total_equity
            if result['short_term_debt'] is not None and result['long_term_debt'] is not None and total_equity is not None and total_equity > 0:
                total_debt = result['short_term_debt'] + result['long_term_debt']
                result['interest_bearing_debt_ratio'] = round(total_debt / total_equity, 2)

            # 提取利息保障倍数
            result['interest_coverage_ratio'] = self._extract_interest_coverage(text_content)

            # 估算速动比率（如果有存货数据）
            inventory = prospectus_info.get('cashflow', {}).get('inventory_turnover_days_latest')
            if result['current_ratio'] is not None and inventory is not None and _is_num(inventory):
                # 简化估算：如果存货周转天数高，速动比率降低
                inventory_factor = min(1.0, 200 / max(inventory, 200))
                result['quick_ratio'] = round(result['current_ratio'] * inventory_factor, 2)

            # 识别风险标志
            result['risk_flags'] = self._identify_risks(result)

            # 计算评分
            result['balance_sheet_score'] = self._calculate_score(result)
            result['label'] = self._calculate_label(result['balance_sheet_score'])
            result['confidence'] = 'regex_context'

        except Exception as e:
            logger.warning("%s: %s", type(self).__name__, e)
            result['_error'] = str(e)

        return result

    def _extract_asset_liability_ratio(self, text):
        """提取资产负债率（转为小数，如55% -> 0.55）。"""
        for pattern in _ASSET_LIABILITY_RATIO_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    ratio = float(match.group(1)) / 100.0
                    if 0.1 <= ratio <= 0.95:
                        return ratio
                except ValueError:
                    continue
        return None

    def _extract_current_ratio(self, text):
        """提取流动比率。"""
        for pattern in _CURRENT_RATIO_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    ratio = float(match.group(1))
                    if 0.5 <= ratio <= 10.0:
                        return ratio
                except ValueError:
                    continue
        return None

    def _extract_short_term_debt(self, text):
        """提取短期借款（百万）。"""
        for pattern in _SHORT_TERM_DEBT_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    value = float(match.group(1).replace(',', ''))
                    if 0 < value <= 100000:
                        return value
                except ValueError:
                    continue
        return None

    def _extract_long_term_debt(self, text):
        """提取长期借款（百万）。"""
        for pattern in _LONG_TERM_DEBT_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    value = float(match.group(1).replace(',', ''))
                    if 0 < value <= 100000:
                        return value
                except ValueError:
                    continue
        return None

    def _extract_total_equity(self, text):
        """提取股东权益（百万）。"""
        for pattern in _TOTAL_EQUITY_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    value = float(match.group(1).replace(',', ''))
                    if 10 <= value <= 500000:
                        return value
                except ValueError:
                    continue
        return None

    def _extract_interest_coverage(self, text):
        """提取利息保障倍数。"""
        for pattern in _INTEREST_COVERAGE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    ratio = float(match.group(1))
                    if 0.5 <= ratio <= 100.0:
                        return ratio
                except ValueError:
                    continue
        return None

    def _identify_risks(self, result):
        """识别资产负债风险标志。"""
        from ..settings import SETTINGS
        qt = SETTINGS.prospectus_quality
        flags = []

        # 资产负债率过高
        if result.get('asset_liability_ratio') is not None:
            if result['asset_liability_ratio'] > qt.asset_liability_warning:
                flags.append(f"资产负债率偏高({result['asset_liability_ratio']*100:.1f}%)")
            elif result['asset_liability_ratio'] > qt.asset_liability_healthy:
                flags.append(f"资产负债率{result['asset_liability_ratio']*100:.1f}%，需关注")

        # 有息负债率过高
        if result.get('interest_bearing_debt_ratio') is not None:
            if result['interest_bearing_debt_ratio'] > qt.interest_bearing_debt_warning:
                flags.append(f"有息负债率偏高({result['interest_bearing_debt_ratio']*100:.1f}%)")

        # 流动比率过低
        if result.get('current_ratio') is not None:
            if result['current_ratio'] < qt.current_ratio_warning:
                flags.append(f"流动比率偏低({result['current_ratio']:.1f})")

        # 速动比率过低
        if result.get('quick_ratio') is not None:
            if result['quick_ratio'] < qt.quick_ratio_healthy:
                flags.append(f"速动比率偏低({result['quick_ratio']:.1f})")

        # 利息保障倍数过低
        if result.get('interest_coverage_ratio') is not None:
            if result['interest_coverage_ratio'] < qt.interest_coverage_warning:
                flags.append(f"利息保障倍数不足({result['interest_coverage_ratio']:.1f}x)")

        return flags

    def _calculate_score(self, result):
        """计算资产负债综合评分（0-100）。"""
        from ..settings import SETTINGS
        qt = SETTINGS.prospectus_quality
        score = 50  # 基础分

        # 资产负债率
        alr = result.get('asset_liability_ratio')
        if alr is not None:
            if alr < qt.asset_liability_healthy:
                score += 25
            elif alr < qt.asset_liability_warning:
                score += 15
            else:
                score += 5

        # 有息负债率
        ibdr = result.get('interest_bearing_debt_ratio')
        if ibdr is not None:
            if ibdr < qt.interest_bearing_debt_healthy:
                score += 20
            elif ibdr < qt.interest_bearing_debt_warning:
                score += 10
            else:
                score -= 5

        # 流动比率
        cr = result.get('current_ratio')
        if cr is not None:
            if cr > qt.current_ratio_healthy:
                score += 20
            elif cr > qt.current_ratio_warning:
                score += 10
            else:
                score -= 10

        # 速动比率
        qr = result.get('quick_ratio')
        if qr is not None:
            if qr > qt.quick_ratio_healthy:
                score += 15
            else:
                score -= 10

        # 利息保障倍数
        icr = result.get('interest_coverage_ratio')
        if icr is not None:
            if icr > qt.interest_coverage_healthy:
                score += 20
            elif icr > qt.interest_coverage_warning:
                score += 10
            else:
                score -= 15

        return max(0, min(100, score))

    def _calculate_label(self, score):
        """根据评分计算标签。"""
        if score >= 75:
            return '稳健'
        elif score >= 60:
            return '可控'
        elif score >= 40:
            return '偏紧'
        else:
            return '高风险'
