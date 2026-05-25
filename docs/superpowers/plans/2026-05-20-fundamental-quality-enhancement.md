# 质地与基本面分析增强实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增3个独立分析器（管理层治理、资产负债、盈利可持续性），并接入现有五维评分体系

**Architecture:** 在 `ipo_analyzer/analyzers/` 目录下新增3个分析器模块，遵循现有分析器模式，通过 `parser.py` 注册调用，在 `quality_analyzer.py` 中读取新维度并计算分数

**Tech Stack:** Python 3.11+, re, 现有表格提取逻辑（`table_extraction.py`），现有分析器基线（`_shareholder.py` 作为参考模板）

---

## 文件结构映射

### 新建文件
1. `ipo_analyzer/analyzers/_management_governance.py` — 管理层与治理质量分析器
2. `ipo_analyzer/analyzers/_balance_sheet.py` — 资产负债结构分析器
3. `ipo_analyzer/analyzers/_analyzers/_profit_sustainability.py` — 盈利可持续性分析器
4. `tests/test_management_governance.py` — 管理层分析器单元测试
5. `tests/test_balance_sheet.py` — 资产负债分析器单元测试
6. `tests/test_profit_sustainability.py` — 盈利可持续性分析器单元测试

### 修改文件
7. `ipo_analyzer/analyzers/__init__.py` — 导出新分析器
8. `ipo_analyzer/parser.py` — 注册新分析器调用
9. `ipo_analyzer/quality_analyzer.py` — 读取新维度并评分
10. `ipo_analyzer/settings.py` — 新增阈值配置
11. `ipo_analyzer/models.py` — 新增数据模型

---

## 实施任务

### Task 1: 配置层 — 新增阈值和数据模型

**Files:**
- Modify: `ipo_analyzer/settings.py:59-81`
- Modify: `ipo_analyzer/models.py` (末尾添加新dataclass)

- [ ] **Step 1: 修改 settings.py 新增阈值配置**

在 `ProspectusQualityThresholds` 类中添加以下字段（在现有字段后）：

```python
@dataclass
class ProspectusQualityThresholds:
    """招股书基本面评分阈值"""
    gross_margin_excellent: float = 50.0
    gross_margin_good: float = 30.0
    gross_margin_fair: float = 20.0
    growth_strong: float = 0.30
    growth_good: float = 0.10
    gross_margin_anomaly_max: float = 100.0
    # 升级版新增：现金流质量阈值
    ocf_to_revenue_strong: float = 0.20
    ocf_to_revenue_good: float = 0.10
    ocf_to_net_profit_strong: float = 1.0
    ocf_to_net_profit_good: float = 0.5
    # 升级版新增：护城河深度阈值
    moat_score_strong: int = 7
    moat_score_moderate: int = 4
    scarcity_moat_strong: int = 7
    scarcity_moat_moderate: int = 4
    # 升级版新增：财务健康阈值
    cash_runway_strong: float = 2.5
    cash_runway_good: float = 1.5
    customer_concentration_high: float = 50.0
    customer_concentration_moderate: float = 30.0
    # === 新增：管理层与治理阈值 ===
    management_experience_strong: float = 10.0
    management_experience_good: float = 5.0
    founder_ownership_healthy_low: float = 15.0
    founder_ownership_healthy_high: float = 40.0
    independent_director_min_ratio: float = 0.33
    controlling_shareholder_warning: float = 70.0
    # === 新增：资产负债阈值 ===
    asset_liability_healthy: float = 0.50
    asset_liability_warning: float = 0.70
    interest_bearing_debt_healthy: float = 0.20
    interest_bearing_debt_warning: float = 0.40
    current_ratio_healthy: float = 2.0
    current_ratio_warning: float = 1.5
    quick_ratio_healthy: float = 1.0
    interest_coverage_healthy: float = 5.0
    interest_coverage_warning: float = 3.0
    # === 新增：盈利可持续性阈值 ===
    non_recurring_ratio_healthy: float = 0.10
    non_recurring_ratio_warning: float = 0.30
    government_subsidy_ratio_healthy: float = 0.05
    government_subsidy_ratio_warning: float = 0.15
```

- [ ] **Step 2: 修改 models.py 新增数据模型**

在 `models.py` 文件末尾（现有dataclass之后）添加：

```python
# ---------------------------------------------------------------------------
# 新增分析结果模型 — 质地与基本面增强
# ---------------------------------------------------------------------------

@dataclass
class ManagementGovernanceResult:
    """管理层与治理质量分析结果"""
    management_experience_years: Optional[float] = None
    founder_ownership_pct: Optional[float] = None
    independent_director_ratio: Optional[float] = None
    controlling_shareholder_pct: Optional[float] = None
    governance_risk_flags: list[str] = field(default_factory=list)
    auditor_quality: Optional[str] = None
    management_score: int = 50
    label: str = "缺失"
    confidence: str = "missing"

@dataclass
class BalanceSheetResult:
    """资产负债结构分析结果"""
    asset_liability_ratio: Optional[float] = None
    interest_bearing_debt_ratio: Optional[float] = None
    current_ratio: Optional[float] = None
    quick_ratio: Optional[float] = None
    interest_coverage_ratio: Optional[float] = None
    short_term_debt: Optional[float] = None
    long_term_debt: Optional[float] = None
    total_equity: Optional[float] = None
    balance_sheet_score: int = 50
    label: str = "缺失"
    risk_flags: list[str] = field(default_factory=list)
    confidence: str = "missing"

@dataclass
class ProfitSustainabilityResult:
    """盈利可持续性分析结果"""
    net_profit: Optional[float] = None
    non_gaap_net_profit: Optional[float] = None
    non_recurring_pnl: Optional[float] = None
    non_recurring_ratio: Optional[float] = None
    government_subsidy: Optional[float] = None
    asset_disposal_gain: Optional[float] = None
    investment_income: Optional[float] = None
    sustainability_score: int = 50
    label: str = "缺失"
    quality_flags: list[str] = field(default_factory=list)
    confidence: str = "missing"
```

- [ ] **Step 3: 验证配置**

Run: `python -c "from ipo_analyzer.settings import SETTINGS; print(SETTINGS.prospectus_quality.management_experience_strong)"`
Expected: `10.0`

Run: `python -c "from ipo_analyzer.models import ManagementGovernanceResult; r = ManagementGovernanceResult(); print(r.management_score)"`
Expected: `50`

---

### Task 2: 管理层与治理质量分析器

**Files:**
- Create: `ipo_analyzer/analyzers/_management_governance.py`
- Test: `tests/test_management_governance.py`

- [ ] **Step 1: 创建分析器文件**

创建 `ipo_analyzer/analyzers/_management_governance.py`：

```python
"""管理层与治理质量分析器 — 从招股书中提取管理层经验、股权结构、治理质量等指标。"""

import re
import logging
from ..utils import _is_num, extract_text_excerpts

logger = logging.getLogger(__name__)

# --- 正则模式 ---

# 管理层经验年限（董事及高级管理人员章节）
_MANAGEMENT_EXPERIENCE_PATTERNS = [
    # 中文："拥有X年行业经验"、"在Y行业从业Z年"
    r'(?:拥有|具有|具备|在).{0,20}(?:行业|领域|从业|经验).{0,10}(\d+(?:\.\d+)?)\s*年',
    # 英文："X years of experience in"、"has been in the Y industry for Z years"
    r'(\d+(?:\.\d+)?)\s+years?\s+(?:of\s+)?experience',
    r'(?:in|working)\s+in\s+the\s+.{0,30}?(?:industry|sector|field)\s+for\s+(\d+(?:\.\d+)?)\s+years?',
    # 董事简历中的经验年限
    r'(?:joined|加入|since|自).{0,10}(\d{4})\b',
]

# 创始人持股比例
_FOUNDER_OWNERSHIP_PATTERNS = [
    # 中文："创始人X先生/女士持有X%的股份"
    r'(?:创始人|控股股东|实际控制人).{0,30}(?:持有|持股|拥有).{0,10}(\d+(?:\.\d+)?)\s*%',
    # 英文："founder owns X%"
    r'(?:founder|controlling\s+shareholder).{0,30}(?:owns?|holds?|own\s+approximately).{0,10}(\d+(?:\.\d+)?)\s*%',
    # 表格格式："Founder/CEO X%"
    r'(?:founder|创始人|控股股东)\s+.*?(\d+(?:\.\d+)?)\s*%',
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
    (r'(?:诉讼|訴訟|litigation|legal\s+proceedings).*?(?:涉及|involve).*?(?:董事|director|executive)', '董事涉及诉讼'),
    (r'(?:违规|violation|breach|penalty).*?(?:证监会|regulatory|SFC|SEC)', '监管违规'),
    (r'(?:关联交易|connected\s+transaction|related\s+party).*?(?:异常|unusual|significant)', '异常关联交易'),
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
        for pattern in _MANAGEMENT_EXPERIENCE_PATTERNS[:2]:
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
            year_pattern = _MANAGEMENT_EXPERIENCE_PATTERNS[3]
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
            matches = re.finditer(pattern, text, re.IGNORECASE)
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
```

- [ ] **Step 2: 创建单元测试**

创建 `tests/test_management_governance.py`：

```python
"""管理层与治理质量分析器单元测试。"""

from ipo_analyzer.analyzers._management_governance import ManagementGovernanceAnalyzer


def test_extract_management_experience_direct_match():
    """测试直接匹配管理层经验年限。"""
    text = """
    张先生拥有15年半导体行业经验。
    李女士在医疗器械行业从业12年。
    """
    result = ManagementGovernanceAnalyzer().analyze({}, text)
    assert result['management_experience_years'] is not None
    assert result['management_experience_years'] >= 10


def test_extract_founder_ownership():
    """测试提取创始人持股比例。"""
    text = """
    本公司创始人王明先生持有公司35.2%的股份。
    """
    result = ManagementGovernanceAnalyzer().analyze({}, text)
    assert result['founder_ownership_pct'] is not None
    assert 30 <= result['founder_ownership_pct'] <= 40


def test_auditor_big4_detection():
    """测试识别四大会计师事务所。"""
    text = """
    申报会计师：普华永道中天会计师事务所
    """
    result = ManagementGovernanceAnalyzer().analyze({}, text)
    assert result['auditor_quality'] == '四大'


def test_governance_risk_detection():
    """测试识别治理风险。"""
    text = """
    本公司董事涉及未决诉讼，可能对公司声誉造成不利影响。
    """
    result = ManagementGovernanceAnalyzer().analyze({}, text)
    assert len(result['governance_risk_flags']) > 0
    assert any('诉讼' in f for f in result['governance_risk_flags'])


def test_score_calculation_with_good_governance():
    """测试良好治理情况下评分较高。"""
    text = """
    张先生拥有12年行业经验。
    创始人持有公司30%的股份。
    申报会计师：德勤华永会计师事务所
    """
    analyzer = ManagementGovernanceAnalyzer()
    result = analyzer.analyze({}, text)
    assert result['management_score'] >= 60
    assert result['label'] in ('良好', '优秀')


def test_score_calculation_with_risks():
    """测试存在治理风险时评分较低。"""
    text = """
    本公司涉及财务造假指控。
    董事涉及诉讼。
    """
    result = ManagementGovernanceAnalyzer().analyze({}, text)
    assert result['management_score'] < 50
    assert result['label'] in ('偏弱', '一般')


def test_missing_data_returns_default():
    """测试数据缺失时返回默认值。"""
    result = ManagementGovernanceAnalyzer().analyze({}, '')
    assert result['management_experience_years'] is None
    assert result['management_score'] == 50
    assert result['label'] == '缺失'
    assert result['confidence'] == 'missing'
```

- [ ] **Step 3: 运行测试验证**

Run: `cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer && pytest tests/test_management_governance.py -v`
Expected: 7 tests pass

---

### Task 3: 资产负债结构分析器

**Files:**
- Create: `ipo_analyzer/analyzers/_balance_sheet.py`
- Test: `tests/test_balance_sheet.py`

- [ ] **Step 1: 创建分析器文件**

创建 `ipo_analyzer/analyzers/_balance_sheet.py`：

```python
"""资产负债结构分析器 — 从招股书中提取资产负债率、流动比率、有息负债等指标。"""

import re
import logging
from ..utils import _is_num, extract_text_excerpts

logger = logging.getLogger(__name__)

# --- 正则模式 ---

# 资产负债率
_ASSET_LIABILITY_RATIO_PATTERNS = [
    r'(?:资产负债率|資產負債率|asset[- ]liability\s+ratio|debt\s+to\s+asset).{0,10}(\d+(?:\.\d+)?)\s*%',
    r'(?:资产负债率|資產負債率).{0,5}(\d+(?:\.\d+)?)\s*%',
]

# 流动比率
_CURRENT_RATIO_PATTERNS = [
    r'(?:流动比率|流動比率|current\s+ratio).{0,10}(\d+(?:\.\d+)?)',
    r'(?:流动资产/流动负债|流動資產/流動負債).{0,10}(\d+(?:\.\d+)?)',
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
```

- [ ] **Step 2: 创建单元测试**

创建 `tests/test_balance_sheet.py`：

```python
"""资产负债结构分析器单元测试。"""

from ipo_analyzer.analyzers._balance_sheet import BalanceSheetAnalyzer


def test_extract_asset_liability_ratio():
    """测试提取资产负债率。"""
    text = """
    截至2023年12月31日，本公司资产负债率为55.2%。
    """
    result = BalanceSheetAnalyzer().analyze({}, text)
    assert result['asset_liability_ratio'] is not None
    assert 0.50 <= result['asset_liability_ratio'] <= 0.60


def test_extract_current_ratio():
    """测试提取流动比率。"""
    text = """
    流动比率：2.1
    """
    result = BalanceSheetAnalyzer().analyze({}, text)
    assert result['current_ratio'] is not None
    assert 2.0 <= result['current_ratio'] <= 2.2


def test_good_balance_sheet_score():
    """测试健康资产负债表评分较高。"""
    text = """
    资产负债率为45.0%。
    流动比率为2.5。
    利息保障倍数为8.5。
    """
    result = BalanceSheetAnalyzer().analyze({}, text)
    assert result['balance_sheet_score'] >= 70
    assert result['label'] == '稳健'


def test_risky_balance_sheet_flags():
    """测试高风险资产负债表识别风险标志。"""
    text = """
    资产负债率为75.0%。
    流动比率为1.2。
    利息保障倍数为2.0。
    """
    result = BalanceSheetAnalyzer().analyze({}, text)
    assert len(result['risk_flags']) > 0
    assert result['balance_sheet_score'] < 50


def test_missing_data_returns_default():
    """测试数据缺失时返回默认值。"""
    result = BalanceSheetAnalyzer().analyze({}, '')
    assert result['asset_liability_ratio'] is None
    assert result['balance_sheet_score'] == 50
    assert result['label'] == '缺失'
    assert result['confidence'] == 'missing'
```

- [ ] **Step 3: 运行测试验证**

Run: `cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer && pytest tests/test_balance_sheet.py -v`
Expected: 5 tests pass

---

### Task 4: 盈利可持续性分析器

**Files:**
- Create: `ipo_analyzer/analyzers/_profit_sustainability.py`
- Test: `tests/test_profit_sustainability.py`

- [ ] **Step 1: 创建分析器文件**

创建 `ipo_analyzer/analyzers/_profit_sustainability.py`：

```python
"""盈利可持续性分析器 — 从招股书中提取非经常性损益、政府补贴等指标，评估盈利质量。"""

import re
import logging
from ..utils import _is_num, extract_text_excerpts

logger = logging.getLogger(__name__)

# --- 正则模式 ---

# 非经常性损益
_NON_RECURRING_PNL_PATTERNS = [
    r'(?:非经常性损益|非經常性損益|non[- ]recurring\s+profit\s+and\s+loss|non[- ]recurring\s+items).{0,10}([\d,]+(?:\.\d+)?)',
    r'(?:非经常.*?损益|非經常.*?損益).{0,10}([\d,]+(?:\.\d+)?)',
]

# 扣非净利润
_NON_GAAP_NET_PROFIT_PATTERNS = [
    r'(?:扣非净利润|扣除非經常性損益後淨利潤|non[- ]GAAP\s+net\s+profit).{0,10}([\d,]+(?:\.\d+)?)',
    r'(?:调整后净利润|經調整淨利潤|adjusted\s+net\s+profit).{0,10}([\d,]+(?:\.\d+)?)',
]

# 政府补贴
_GOVERNMENT_SUBSIDY_PATTERNS = [
    r'(?:政府补助|政府補貼|government\s+grants|government\s+subsidies).{0,10}([\d,]+(?:\.\d+)?)',
    r'(?:政府.*?补助|政府.*?補貼).{0,10}([\d,]+(?:\.\d+)?)',
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
            match = re.search(pattern, text, re.IGNORECASE)
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
            match = re.search(pattern, text, re.IGNORECASE)
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
```

- [ ] **Step 2: 创建单元测试**

创建 `tests/test_profit_sustainability.py`：

```python
"""盈利可持续性分析器单元测试。"""

from ipo_analyzer.analyzers._profit_sustainability import ProfitSustainabilityAnalyzer


def test_extract_government_subsidy():
    """测试提取政府补贴。"""
    text = """
    本公司收到政府补助人民币15.5百万元。
    """
    result = ProfitSustainabilityAnalyzer().analyze({}, text)
    assert result['government_subsidy'] is not None
    assert 10 <= result['government_subsidy'] <= 20


def test_high_non_recurring_ratio_detection():
    """测试高非经常性损益占比识别。"""
    text = """
    非经常性损益为50百万元。
    扣非净利润为30百万元。
    """
    prospectus_info = {'net_profit': 80.0, '_extracted_text': text}
    result = ProfitSustainabilityAnalyzer().analyze(prospectus_info, text)
    assert result['non_recurring_ratio'] is not None
    assert result['non_recurring_ratio'] > 0.3
    assert len(result['quality_flags']) > 0


def test_sustainable_profit_score():
    """测试可持续盈利情况下评分较高。"""
    text = """
    扣非净利润为50百万元。
    """
    prospectus_info = {'net_profit': 52.0, '_extracted_text': text}
    result = ProfitSustainabilityAnalyzer().analyze(prospectus_info, text)
    assert result['sustainability_score'] >= 70
    assert result['label'] in ('可持续', '基本可持续')


def test_biotech_unprofitable_exempt():
    """测试Biotech未盈利情况不扣分。"""
    text = """
    本公司仍在研发阶段，尚未商业化。
    """
    prospectus_info = {
        'net_profit': -50.0,
        'sector': 'healthcare',
        'listing_suffix': 'B',
        '_extracted_text': text,
    }
    result = ProfitSustainabilityAnalyzer().analyze(prospectus_info, text)
    # Biotech未盈利应该不扣分，评分不应过低
    assert result['sustainability_score'] >= 40


def test_profit_quality_flag_opposite_direction():
    """测试扣非与净利润反向时识别风险。"""
    text = """
    扣非净利润为-10百万元。
    """
    prospectus_info = {'net_profit': 20.0, '_extracted_text': text}
    result = ProfitSustainabilityAnalyzer().analyze(prospectus_info, text)
    assert any('扣非' in f for f in result['quality_flags'])
    assert result['sustainability_score'] < 50


def test_missing_data_returns_default():
    """测试数据缺失时返回默认值。"""
    result = ProfitSustainabilityAnalyzer().analyze({}, '')
    assert result['non_recurring_ratio'] is None
    assert result['sustainability_score'] == 50
    assert result['label'] == '缺失'
    assert result['confidence'] == 'missing'
```

- [ ] **Step 3: 运行测试验证**

Run: `cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer && pytest tests/test_profit_sustainability.py -v`
Expected: 6 tests pass

---

### Task 5: 注册新分析器到 parser.py

**Files:**
- Modify: `ipo_analyzer/analyzers/__init__.py`
- Modify: `ipo_analyzer/parser.py`

- [ ] **Step 1: 修改 __init__.py 导出新分析器**

在 `ipo_analyzer/analyzers/__init__.py` 中添加：

```python
# 找到现有导入部分（约在27-33行），添加以下导入：
from ._management_governance import ManagementGovernanceAnalyzer  # noqa: E402
from ._balance_sheet import BalanceSheetAnalyzer  # noqa: E402
from ._profit_sustainability import ProfitSustainabilityAnalyzer  # noqa: E402

# 在 __all__ 列表中添加：
__all__ = [
    "ValuationAnalyzer",
    "BusinessBreakdownAnalyzer",
    "GeographicExpansionAnalyzer",
    "CustomerSupplierAnalyzer",
    "WorkingCapitalCashFlowAnalyzer",
    "ProductionCapacityAnalyzer",
    "RnDPipelineAnalyzer",
    "RiskFactorAnalyzer",
    "ShareholderAnalyzer",
    "OrderBacklogAnalyzer",
    # InvestSkill 集成框架
    "PiotroskiFAnalyzer",
    "DCFValuationAnalyzer",
    "SectorAnalyzer",
    "CompanyProfileAnalyzer",
    # 质地增强分析器
    "ManagementGovernanceAnalyzer",
    "BalanceSheetAnalyzer",
    "ProfitSustainabilityAnalyzer",
]
```

- [ ] **Step 2: 修改 parser.py 注册新分析器调用**

在 `ipo_analyzer/parser.py` 中，找到 `extract_info` 方法末尾（约在现有分析器调用之后），添加：

```python
# 先添加导入（在文件顶部，约13行附近）：
from .analyzers._management_governance import ManagementGovernanceAnalyzer
from .analyzers._balance_sheet import BalanceSheetAnalyzer
from .analyzers._profit_sustainability import ProfitSustainabilityAnalyzer

# 然后在 extract_info 方法末尾（找到现有最后一个分析器调用后）添加：
# ... 现有代码：info['risk_factors'] = RiskFactorAnalyzer().analyze(text, info) ...

# 新增：管理层与治理质量分析
info['management_governance'] = ManagementGovernanceAnalyzer().analyze(info, text)

# 新增：资产负债结构分析
info['balance_sheet'] = BalanceSheetAnalyzer().analyze(info, text)

# 新增：盈利可持续性分析
info['profit_sustainability'] = ProfitSustainabilityAnalyzer().analyze(info, text)
```

注意：实际文件位置需根据现有代码结构调整。查找 `extract_info` 方法中最后一个分析器调用的位置（通常是 `RiskFactorAnalyzer` 或 `OrderBacklogAnalyzer`）。

---

### Task 6: 接入 quality_analyzer.py 评分体系

**Files:**
- Modify: `ipo_analyzer/quality_analyzer.py:212-627`

- [ ] **Step 1: 在 analyze 方法中添加新维度评分**

在 `quality_analyzer.py` 的 `ProspectusQualityAnalyzer.analyze` 方法中，找到计算 `fisher_label` 和 `lynch_label` 之前的位置（约在580-590行附近），添加以下代码：

```python
# 新增：管理层治理维度评分
mg = prospectus_info.get('management_governance', {})
if mg.get('management_score') and mg.get('confidence') != 'missing':
    mg_score = mg['management_score']
    score += round(mg_score * 0.15)  # 权重15%
    if mg.get('label') == '优秀':
        reasons.append(f"管理层治理优秀(经验{mg.get('management_experience_years')}年)")
    elif mg.get('label') == '良好':
        reasons.append(f"管理层治理良好")
    dimensions['management_governance'] = {
        'label': mg.get('label', '缺失'),
        'detail': f"核心经验{mg.get('management_experience_years')}年，创始人持股{mg.get('founder_ownership_pct')}%",
    }

# 新增：资产负债维度评分
bs = prospectus_info.get('balance_sheet', {})
if bs.get('balance_sheet_score') and bs.get('confidence') != 'missing':
    bs_score = bs['balance_sheet_score']
    score += round(bs_score * 0.15)  # 权重15%
    if bs.get('risk_flags'):
        for flag in bs['risk_flags'][:2]:
            reasons.append(f"资产负债风险: {flag}")
    dimensions['balance_sheet'] = {
        'label': bs.get('label', '缺失'),
        'detail': f"资产负债率{bs.get('asset_liability_ratio')*100:.1f}%" if bs.get('asset_liability_ratio') else "资产负债率--",
    }

# 新增：盈利可持续性维度评分
ps = prospectus_info.get('profit_sustainability', {})
if ps.get('sustainability_score') and ps.get('confidence') != 'missing':
    ps_score = ps['sustainability_score']
    score += round(ps_score * 0.10)  # 权重10%
    if ps.get('non_recurring_ratio', 0) > 0.3:
        reasons.append(f"非经常性损益占比{ps['non_recurring_ratio']*100:.1f}%，盈利可持续性存疑")
    elif ps.get('non_recurring_ratio') is not None:
        reasons.append(f"非经常性占比{ps['non_recurring_ratio']*100:.1f}%")
    dimensions['profit_sustainability'] = {
        'label': ps.get('label', '缺失'),
        'detail': f"非经常性占比{ps.get('non_recurring_ratio')*100:.1f}%" if ps.get('non_recurring_ratio') is not None else "非经常性占比--",
    }
```

---

### Task 7: 运行全部测试并修复问题

**Files:**
- All test files

- [ ] **Step 1: 运行所有新增测试**

Run: `cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer && pytest tests/test_management_governance.py tests/test_balance_sheet.py tests/test_profit_sustainability.py -v`
Expected: 18 tests pass (7 + 5 + 6)

- [ ] **Step 2: 运行现有测试确保未破坏**

Run: `cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer && pytest tests/ -v --tb=short`
Expected: All existing tests pass

- [ ] **Step 3: 验证导入无错误**

Run: `cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer && python -c "from ipo_analyzer.analyzers import ManagementGovernanceAnalyzer, BalanceSheetAnalyzer, ProfitSustainabilityAnalyzer; print('导入成功')"`
Expected: `导入成功`

- [ ] **Step 4: 验证评分集成**

Run: `cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer && python -c "
from ipo_analyzer.quality_analyzer import ProspectusQualityAnalyzer
result = ProspectusQualityAnalyzer().analyze({
    'gross_margin': 45.0,
    'profitable': True,
    'revenue': 500.0,
    'revenue_y1': 400.0,
    'management_governance': {
        'management_score': 75,
        'label': '良好',
        'confidence': 'regex_context',
    },
    'balance_sheet': {
        'balance_sheet_score': 70,
        'label': '稳健',
        'confidence': 'regex_context',
    },
    'profit_sustainability': {
        'sustainability_score': 80,
        'label': '可持续',
        'confidence': 'regex_context',
    },
})
print(f'质地分: {result[\"score\"]}')
print(f'标签: {result[\"label\"]}')
"
Expected: 质地分应高于基础分（因新增维度加分）

---

### Task 8: 提交代码

- [ ] **Step: 提交所有更改**

```bash
cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer
git add ipo_analyzer/analyzers/_management_governance.py
git add ipo_analyzer/analyzers/_balance_sheet.py
git add ipo_analyzer/analyzers/_profit_sustainability.py
git add ipo_analyzer/analyzers/__init__.py
git add ipo_analyzer/parser.py
git add ipo_analyzer/quality_analyzer.py
git add ipo_analyzer/settings.py
git add ipo_analyzer/models.py
git add tests/test_management_governance.py
git add tests/test_balance_sheet.py
git add tests/test_profit_sustainability.py
git commit -m "feat: 新增管理层治理、资产负债、盈利可持续性三个分析维度

- 新增 ManagementGovernanceAnalyzer 分析管理层经验、股权结构、治理质量
- 新增 BalanceSheetAnalyzer 分析资产负债率、流动比率、有息负债
- 新增 ProfitSustainabilityAnalyzer 分析非经常性损益、政府补贴依赖
- 接入现有五维评分体系（权重15%+15%+10%）
- 新增18个单元测试，全部通过
- 所有阈值可在 settings.py 中配置"
```

---

## 自查清单

### 1. 规范覆盖检查
- [x] 3个新分析器已实现 → Task 2, 3, 4
- [x] 数据模型已添加 → Task 1
- [x] 阈值配置已添加 → Task 1
- [x] parser.py 已注册新分析器 → Task 5
- [x] quality_analyzer.py 已接入评分 → Task 6
- [x] 单元测试已编写 → Task 2, 3, 4
- [x] settings.py 已扩展 → Task 1

### 2. 占位符扫描
- [x] 无 TBD/TODO
- [x] 无 "implement later"
- [x] 所有步骤包含实际代码
- [x] 所有测试包含实际测试代码

### 3. 类型一致性
- [x] 数据模型字段名与分析器返回值一致
- [x] settings.py 阈值字段名与分析器中使用一致
- [x] 评分权重分配（15%+15%+10%）与设计文档一致
