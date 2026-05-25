"""管理层与治理质量分析器 — 从招股书中提取管理层经验、股权结构、治理质量等指标。"""

import re
import logging

logger = logging.getLogger(__name__)

# --- 正则模式 ---

# 管理层经验年限（董事及高级管理人员章节）
_MANAGEMENT_EXPERIENCE_PATTERNS = [
    # 中文："拥有X年行业经验"
    r'拥有(\d+(?:\.\d+)?)年.{0,10}(?:行业|领域|从业|经验)',
    r'具有(\d+(?:\.\d+)?)年.{0,10}(?:行业|领域|从业|经验)',
    r'具备(\d+(?:\.\d+)?)年.{0,10}(?:行业|领域|从业|经验)',
    # 英文："X years of experience in"
    r'(\d+(?:\.\d+)?)\s+years?\s+(?:of\s+)?experience',
    # 董事简历中的经验年限
    r'(?:joined|加入|since|自).{0,40}(\d{4})\b',
]

# 创始人持股比例
_FOUNDER_OWNERSHIP_PATTERNS = [
    # 中文："创始人...持有...X%"
    r'创始人.*?持有.*?(\d+(?:\.\d+)?)%',
    r'创始人.*?持股.*?(\d+(?:\.\d+)?)%',
    # 英文："founder owns X%"
    r'(?:founder|controlling\s+shareholder).*?(?:owns?|holds?).*?(\d+(?:\.\d+)?)\s*%',
]

# 独立董事占比
_INDEPENDENT_DIRECTOR_PATTERNS = [
    # 中文："董事会由X名成员组成，其中包括Y名独立非执行董事"
    r'(?:董事会).{0,30}(?:包括|组成).{0,30}(\d+)\s*名.*?(?:独立非执行董事|独立非執行董事|独立董事)',
    # 英文："The Board consists of X directors, including Y independent non-executive directors"
    r'(?:board|董事會).{0,50}(?:including|其中包括).{0,10}(\d+)\s+(?:independent\s+non-executive|独立非(?:执行|執行))\s+director',
    # 通用："X名独立非执行董事"
    r'(\d+)\s*(?:名)?\s*(?:独立非执行董事|独立非執行董事|independent\s+non-executive\s+directors?)',
]

# 审计机构识别（四大/非四大）
_AUDITOR_BIG4_PATTERNS = [
    # 四大：普华永道、德勤、安永、毕马威
    r'(?:普华永道|普華永道|PricewaterhouseCoopers|PwC)',
    r'(?:德勤|Deloitte|Deloitte\s+Touche)',
    r'(?:安永|Ernst\s+&\s+Young|EY|EY\.com)',
    r'(?:毕马威|畢馬威|KPMG)',
]

# 治理风险标志
_GOVERNANCE_RISK_PATTERNS = [
    (r'(?:董事|director|executive).{0,20}(?:涉及|involve).{0,20}(?:诉讼|訴訟|litigation)', '董事涉及诉讼'),
    (r'(?:诉讼|訴訟|litigation).{0,20}(?:涉及|involve).{0,20}(?:董事|director|executive)', '董事涉及诉讼'),
    (r'(?:违规|violation|breach|penalty).{0,20}(?:证监会|regulatory|SFC|SEC)', '监管违规'),
    (r'(?:关联交易|connected\s+transaction|related\s+party).{0,20}(?:异常|unusual|significant)', '异常关联交易'),
    (r'(?:内部控制缺陷|internal\s+control\s+deficiency|material\s+weakness)', '内部控制缺陷'),
    (r'(?:财务造假|fraud|misstatement|irregularities)', '财务舞弊风险'),
]


class ManagementGovernanceAnalyzer:
    """管理层与治理质量分析器"""

    def analyze(self, prospectus_info, text=''):
        result = {
            'management_experience_years': None,
            'founder_ownership_pct': None,
            'independent_director_ratio': None,
            'controlling_shareholder_pct': prospectus_info.get('shareholder', {}).get('controlling_shareholder_pct'),
            'governance_risk_flags': [],
            'auditor_quality': None,
            'management_score': 50,
            'label': '缺失',
            'confidence': 'missing',
        }

        try:
            text_content = text or prospectus_info.get('_extracted_text', '')
            if not text_content:
                return result

            # 提取管理层经验
            result['management_experience_years'] = self._extract_management_experience(text_content)

            # 提取创始人持股
            result['founder_ownership_pct'] = self._extract_founder_ownership(text_content)

            # 提取独董占比
            result['independent_director_ratio'] = self._extract_independent_director_ratio(text_content)

            # 识别审计机构
            result['auditor_quality'] = self._identify_auditor(text_content)

            # 识别治理风险
            result['governance_risk_flags'] = self._identify_governance_risks(text_content)

            # 计算评分
            result['management_score'] = self._calculate_score(result)
            result['label'] = self._calculate_label(result['management_score'])
            result['confidence'] = 'regex_context'

        except Exception as e:
            logger.warning("%s: %s", type(self).__name__, e)
            result['_error'] = str(e)

        return result

    def _extract_management_experience(self, text):
        """提取管理层平均行业经验年限。"""
        experiences = []

        # 方法1：直接匹配年限数字
        for pattern in _MANAGEMENT_EXPERIENCE_PATTERNS[:-1]:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for m in matches:
                try:
                    years = float(m)
                    if 1 <= years <= 50:
                        experiences.append(years)
                except ValueError:
                    continue

        # 方法2：通过年份计算（如"自2010年加入"）
        if not experiences:
            years_found = []
            year_pattern = _MANAGEMENT_EXPERIENCE_PATTERNS[-1]
            for m in re.finditer(year_pattern, text, re.IGNORECASE):
                try:
                    year = int(m.group(1))
                    if 1990 <= year <= 2025:
                        from datetime import datetime
                        exp = datetime.now().year - year
                        if 1 <= exp <= 40:
                            years_found.append(exp)
                except ValueError:
                    continue
            if years_found:
                experiences = years_found[:5]  # 最多取5个

        if experiences:
            return round(sum(experiences) / len(experiences), 1)
        return None

    def _extract_founder_ownership(self, text):
        """提取创始人/核心团队持股比例。"""
        for pattern in _FOUNDER_OWNERSHIP_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE | re.DOTALL)
            for m in matches:
                try:
                    pct = float(m.group(1))
                    if 5 <= pct <= 80:
                        return pct
                except ValueError:
                    continue
        return None

    def _extract_independent_director_ratio(self, text):
        """提取独立董事占比。"""
        for pattern in _INDEPENDENT_DIRECTOR_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for m in matches:
                try:
                    independent_count = int(m.group(1))
                    # 尝试提取董事会总人数
                    total_match = re.search(r'董事会.*?(\d+)\s*名', text, re.IGNORECASE)
                    if total_match:
                        total_count = int(total_match.group(1))
                        if total_count > 0 and independent_count <= total_count:
                            return round(independent_count / total_count, 2)
                except ValueError:
                    continue
        return None

    def _identify_auditor(self, text):
        """识别审计机构资质（四大/非四大）。"""
        for pattern in _AUDITOR_BIG4_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return '四大'
        # 检查是否有审计师信息但非四大
        if re.search(r'(?:auditor|核数师|申报会计师|审计师)', text, re.IGNORECASE):
            return '非四大'
        return None

    def _identify_governance_risks(self, text):
        """识别治理风险标志。"""
        flags = []
        for pattern, flag_label in _GOVERNANCE_RISK_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                flags.append(flag_label)
        return flags

    def _calculate_score(self, result):
        """计算管理层治理综合评分（0-100）。"""
        from ..settings import SETTINGS
        qt = SETTINGS.prospectus_quality
        score = 50  # 基础分

        # 管理层经验
        exp = result.get('management_experience_years')
        if exp is not None:
            if exp >= qt.management_experience_strong:
                score += 25
            elif exp >= qt.management_experience_good:
                score += 15
            else:
                score += 5

        # 创始人持股（利益绑定）
        founder_pct = result.get('founder_ownership_pct')
        if founder_pct is not None:
            if qt.founder_ownership_healthy_low <= founder_pct <= qt.founder_ownership_healthy_high:
                score += 20
            elif founder_pct < qt.founder_ownership_healthy_low:
                score += 10
            else:
                score += 15

        # 独董占比
        ind_ratio = result.get('independent_director_ratio')
        if ind_ratio is not None:
            if ind_ratio >= qt.independent_director_min_ratio:
                score += 15
            else:
                score -= 10

        # 审计机构
        auditor = result.get('auditor_quality')
        if auditor == '四大':
            score += 15
        elif auditor == '非四大':
            score -= 5

        # 治理风险扣分
        risk_flags = result.get('governance_risk_flags', [])
        score -= len(risk_flags) * 15

        # 控股股东集中度检查
        ctrl_pct = result.get('controlling_shareholder_pct')
        if ctrl_pct is not None and ctrl_pct > qt.controlling_shareholder_warning:
            score -= 10

        return max(0, min(100, score))

    def _calculate_label(self, score):
        """根据评分计算标签。"""
        if score >= 75:
            return '优秀'
        elif score >= 60:
            return '良好'
        elif score >= 40:
            return '一般'
        else:
            return '偏弱'
