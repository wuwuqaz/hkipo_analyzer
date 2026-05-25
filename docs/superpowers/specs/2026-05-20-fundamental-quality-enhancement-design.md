# 质地与基本面分析增强设计文档

**日期：** 2026-05-20  
**状态：** 待审核  
**目标：** 增强港股IPO质地分析和基本面分析能力，提升打新评分准确性

---

## 一、背景与目标

### 1.1 现状

当前系统已覆盖以下核心维度：
- 盈利能力（净利润、净利率、盈利增长）
- 成长性（收入增长、利润增长）
- 现金流质量（OCF/收入、OCF/净利润）
- 财务健康度（现金跑道、营运资本、融资依赖）
- 护城河（技术壁垒、赛道稀缺性、市场份额）
- 估值分析（PE、PS、PEG、同行对比）

### 1.2 缺失的关键维度

根据港股IPO破发案例分析和价值投资最佳实践，以下3个维度对打新评分影响重大但当前缺失：

1. **管理层与治理质量** — 管理层诚信、经验、股权结构是核心风险因素
2. **资产负债结构深度** — 高负债是港股破发的核心风险之一
3. **盈利可持续性** — 很多公司靠一次性收益实现盈利，需识别真实盈利能力

### 1.3 成功标准

- 新维度能自动从招股书PDF中提取关键指标
- 新增维度分数能接入现有五维评分体系
- 回测框架能验证新维度对胜率/期望收益的提升
- 新增代码遵循现有架构模式（分析器模块独立、可测试）

---

## 二、架构设计

### 2.1 整体架构

采用**方案A：扩展现有分析器架构**，在 `ipo_analyzer/analyzers/` 目录下新增3个独立分析器模块，完全复用现有分析器模式。

```
ipo_analyzer/
├── analyzers/
│   ├── _management_governance.py     ← 新增：管理层与治理质量
│   ├── _balance_sheet.py             ← 新增：资产负债结构
│   ├── _profit_sustainability.py     ← 新增：盈利可持续性
│   ├── _shareholder.py               ← 现有
│   ├── _valuation.py                 ← 现有
│   ├── _cashflow.py                  ← 现有
│   └── ...
├── parser.py                         ← 修改：注册新分析器
├── quality_analyzer.py               ← 修改：读取新维度并评分
├── scoring.py                        ← 修改：新维度接入五维评分
├── settings.py                       ← 修改：新增阈值配置
└── models.py                         ← 修改：新增数据模型
```

### 2.2 数据流

```
招股书PDF
  ↓
parser.parse_pdf_file()
  ↓
extract_info() ← 在此调用3个新分析器
  ↓
prospectus_info 字典
  ├── management_governance       ← 新增
  ├── balance_sheet               ← 新增
  ├── profit_sustainability       ← 新增
  ├── stock_quality               ← 读取新维度计算分数
  └── ...
  ↓
ScoringSystem.calculate()
  ↓
最终评分（五维加权）
```

---

## 三、详细设计

### 3.1 管理层与治理质量分析器

**文件：** `ipo_analyzer/analyzers/_management_governance.py`

#### 3.1.1 提取目标

| 指标 | 来源章节 | 提取方式 |
|------|---------|---------|
| 管理层行业经验年限 | 董事及高级管理人员 | 正则表达式 |
| 创始人/核心管理层持股比例 | 股本/主要股东 | 正则+表格提取 |
| 独立董事占比 | 公司治理 | 正则表达式 |
| 股权集中度（控股股东持股>50%） | 主要股东 | 复用 _shareholder.py |
| 过往争议记录 | 风险因素/诉讼 | 关键词匹配 |
| 审计机构资质 | 审计报告 | 关键词匹配（四大/非四大） |

#### 3.1.2 输出结构

```python
{
    'management_experience_years': 15.0,  # 核心管理层平均行业经验
    'founder_ownership_pct': 35.2,        # 创始人/核心团队持股%
    'independent_director_ratio': 0.50,   # 独立董事占比
    'controlling_shareholder_pct': 45.0,  # 控股股东持股%
    'governance_risk_flags': [],          # 治理风险标志
    'auditor_quality': '四大',             # 审计机构资质
    'management_score': 75,               # 0-100综合评分
    'label': '良好',                      # 优秀/良好/一般/偏弱
    'confidence': 'regex_context',
}
```

#### 3.1.3 评分逻辑

```
管理层经验 >= 10年        → +25分
创始人持股 15-40%         → +20分（利益绑定适中）
独董占比 >= 1/3           → +15分
审计机构为四大            → +15分
无治理风险标志            → +15分
控股股东持股 30-60%       → +10分（控制权合理）

风险扣分：
控股股东持股 > 70%        → -10分（过度集中）
独董占比 < 1/3            → -10分
有争议/诉讼记录           → -15分/项
审计机构非四大            → -5分
```

---

### 3.2 资产负债结构分析器

**文件：** `ipo_analyzer/analyzers/_balance_sheet.py`

#### 3.2.1 提取目标

| 指标 | 来源章节 | 提取方式 |
|------|---------|---------|
| 资产负债率 | 财务状况/资产负债表 | 表格提取 |
| 有息负债率 | 资产负债表+附注 | 表格+正则 |
| 流动比率 | 资产负债表 | 表格提取 |
| 速动比率 | 资产负债表 | 计算（扣除存货） |
| 利息保障倍数 | 利润表+附注 | 表格+计算 |
| 短期借款/长期借款 | 资产负债表 | 表格提取 |
| 股东权益 | 资产负债表 | 表格提取 |

#### 3.2.2 输出结构

```python
{
    'asset_liability_ratio': 0.55,        # 资产负债率
    'interest_bearing_debt_ratio': 0.25,  # 有息负债率
    'current_ratio': 2.1,                 # 流动比率
    'quick_ratio': 1.8,                   # 速动比率
    'interest_coverage_ratio': 8.5,       # 利息保障倍数
    'short_term_debt': 150.0,             # 短期借款（百万）
    'long_term_debt': 300.0,              # 长期借款（百万）
    'total_equity': 800.0,                # 股东权益（百万）
    'balance_sheet_score': 70,            # 0-100综合评分
    'label': '稳健',                      # 稳健/可控/偏紧/高风险
    'risk_flags': [],                     # 风险标志
    'confidence': 'table_extraction',
}
```

#### 3.2.3 评分逻辑

```
资产负债率 < 50%          → +25分
资产负债率 50-70%         → +15分
资产负债率 > 70%          → +5分（高风险）

有息负债率 < 20%          → +20分
有息负债率 20-40%         → +10分
有息负债率 > 40%          → -5分

流动比率 > 2.0            → +20分
流动比率 1.5-2.0          → +10分
流动比率 < 1.5            → -10分

速动比率 > 1.0            → +15分
速动比率 < 1.0            → -10分

利息保障倍数 > 5          → +20分
利息保障倍数 3-5          → +10分
利息保障倍数 < 3          → -15分（危险）
```

---

### 3.3 盈利可持续性分析器

**文件：** `ipo_analyzer/analyzers/_profit_sustainability.py`

#### 3.3.1 提取目标

| 指标 | 来源章节 | 提取方式 |
|------|---------|---------|
| 净利润 | 综合损益表 | 表格提取（已有） |
| 扣非净利润 | 利润表附注 | 表格+正则 |
| 非经常性损益 | 非经常性损益表 | 表格提取 |
| 政府补贴 | 政府补助附注 | 正则+表格 |
| 资产处置收益 | 附注 | 正则匹配 |
| 投资收益 | 附注 | 正则匹配 |
| 非经常性损益占比 | 计算 | (净利润-扣非净利润)/净利润 |

#### 3.3.2 输出结构

```python
{
    'net_profit': 50.0,                   # 净利润（百万）
    'non_gaap_net_profit': 40.0,          # 扣非净利润（百万）
    'non_recurring_pnl': 10.0,            # 非经常性损益（百万）
    'non_recurring_ratio': 0.20,          # 非经常性损益占比
    'government_subsidy': 8.0,            # 政府补贴（百万）
    'asset_disposal_gain': 2.0,           # 资产处置收益（百万）
    'investment_income': 0.0,             # 投资收益（百万）
    'sustainability_score': 65,           # 0-100综合评分
    'label': '可持续',                    # 可持续/基本可持续/依赖非经常/不可持续
    'quality_flags': [],                  # 质量标志
    'confidence': 'table_extraction',
}
```

#### 3.3.3 评分逻辑

```
非经常性损益占比 < 10%    → +30分（高质量盈利）
非经常性损益占比 10-20%   → +20分
非经常性损益占比 20-30%   → +10分
非经常性损益占比 > 30%    → -10分（依赖非经常性收益）

政府补贴占比 < 5%         → +20分
政府补贴占比 5-15%        → +10分
政府补贴占比 > 15%        → -10分（补贴依赖）

扣非净利润与净利润同向    → +20分
扣非净利润 vs 净利润反向  → -20分（盈利质量存疑）

连续两年盈利（如有数据）  → +20分
仅一年盈利                → +10分
亏损                      → -10分（但Biotech豁免）
```

---

### 3.4 接入现有评分体系

#### 3.4.1 修改 `parser.py`

在 `extract_info()` 方法末尾注册新分析器：

```python
# 现有代码
prospectus_info['risk_factors'] = RiskFactorAnalyzer().analyze(text, prospectus_info)

# 新增
prospectus_info['management_governance'] = ManagementGovernanceAnalyzer().analyze(prospectus_info, text)
prospectus_info['balance_sheet'] = BalanceSheetAnalyzer().analyze(prospectus_info, text)
prospectus_info['profit_sustainability'] = ProfitSustainabilityAnalyzer().analyze(prospectus_info, text)
```

#### 3.4.2 修改 `quality_analyzer.py`

在 `ProspectusQualityAnalyzer.analyze()` 方法中读取新维度：

```python
# 新增：管理层治理维度
mg = prospectus_info.get('management_governance', {})
if mg.get('management_score'):
    mg_score = mg['management_score']
    score += round(mg_score * 0.15)  # 权重15%
    if mg.get('label') == '优秀':
        reasons.append(f"管理层治理优秀(经验{mg.get('management_experience_years')}年)")
    dimensions['management_governance'] = {
        'label': mg.get('label', '缺失'),
        'detail': f"核心经验{mg.get('management_experience_years')}年，创始人持股{mg.get('founder_ownership_pct')}%",
    }

# 新增：资产负债维度
bs = prospectus_info.get('balance_sheet', {})
if bs.get('balance_sheet_score'):
    bs_score = bs['balance_sheet_score']
    score += round(bs_score * 0.15)  # 权重15%
    if bs.get('risk_flags'):
        for flag in bs['risk_flags'][:2]:
            reasons.append(f"资产负债风险: {flag}")
    dimensions['balance_sheet'] = {
        'label': bs.get('label', '缺失'),
        'detail': f"资产负债率{bs.get('asset_liability_ratio')*100:.1f}%，流动比率{bs.get('current_ratio'):.1f}",
    }

# 新增：盈利可持续性维度
ps = prospectus_info.get('profit_sustainability', {})
if ps.get('sustainability_score'):
    ps_score = ps['sustainability_score']
    score += round(ps_score * 0.10)  # 权重10%
    if ps.get('non_recurring_ratio', 0) > 0.3:
        reasons.append(f"非经常性损益占比{ps['non_recurring_ratio']*100:.1f}%，盈利可持续性存疑")
    dimensions['profit_sustainability'] = {
        'label': ps.get('label', '缺失'),
        'detail': f"非经常性占比{ps.get('non_recurring_ratio')*100:.1f}%，扣非净利润{ps.get('non_gaap_net_profit')}m",
    }
```

#### 3.4.3 修改 `settings.py`

在 `ProspectusQualityThresholds` 中新增阈值：

```python
@dataclass
class ProspectusQualityThresholds:
    # ... 现有字段 ...
    
    # 管理层与治理阈值
    management_experience_strong: float = 10.0
    management_experience_good: float = 5.0
    founder_ownership_healthy_low: float = 15.0
    founder_ownership_healthy_high: float = 40.0
    independent_director_min_ratio: float = 0.33
    controlling_shareholder_warning: float = 70.0
    
    # 资产负债阈值
    asset_liability_healthy: float = 0.50
    asset_liability_warning: float = 0.70
    interest_bearing_debt_healthy: float = 0.20
    interest_bearing_debt_warning: float = 0.40
    current_ratio_healthy: float = 2.0
    current_ratio_warning: float = 1.5
    quick_ratio_healthy: float = 1.0
    interest_coverage_healthy: float = 5.0
    interest_coverage_warning: float = 3.0
    
    # 盈利可持续性阈值
    non_recurring_ratio_healthy: float = 0.10
    non_recurring_ratio_warning: float = 0.30
    government_subsidy_ratio_healthy: float = 0.05
    government_subsidy_ratio_warning: float = 0.15
```

---

### 3.5 数据模型扩展

在 `models.py` 中新增3个数据类：

```python
@dataclass
class ManagementGovernanceResult:
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

---

## 四、测试策略

### 4.1 单元测试

为每个分析器创建独立测试文件：

- `tests/test_management_governance.py`
- `tests/test_balance_sheet.py`
- `tests/test_profit_sustainability.py`

测试覆盖：
1. **数据提取准确性** — 使用已知招股书验证提取结果
2. **边界条件** — 数据缺失、格式异常、极端值
3. **评分逻辑** — 各维度分数计算是否正确
4. **风险标志** — 是否正确识别高风险场景

### 4.2 集成测试

修改现有 `tests/test_quality_analyzer.py`，验证：
1. 新维度分数能正确接入总评分
2. 新维度原因能正确显示在评分理由中
3. 五维权重配置能正确影响最终评分

### 4.3 回测验证

运行回测框架验证新维度对以下指标的提升：
- 胜率（win_rate）
- 期望收益（expected_return）
- IC Rank（信息系数排名）

---

## 五、实施步骤

### Phase 1: 数据提取层（优先级最高）

1. 创建 `ipo_analyzer/analyzers/_management_governance.py`
   - 实现管理层经验年限提取
   - 实现创始人持股比例提取
   - 实现独董占比提取
   - 实现审计机构识别

2. 创建 `ipo_analyzer/analyzers/_balance_sheet.py`
   - 实现资产负债率提取（复用表格提取逻辑）
   - 实现流动比率/速动比率计算
   - 实现有息负债率提取
   - 实现利息保障倍数计算

3. 创建 `ipo_analyzer/analyzers/_profit_sustainability.py`
   - 实现非经常性损益提取
   - 实现政府补贴识别
   - 实现扣非净利润vs净利润对比
   - 实现盈利可持续性评分

### Phase 2: 评分接入层

4. 修改 `ipo_analyzer/analyzers/__init__.py` — 导出新分析器
5. 修改 `ipo_analyzer/parser.py` — 注册新分析器调用
6. 修改 `ipo_analyzer/quality_analyzer.py` — 读取新维度并计算分数
7. 修改 `ipo_analyzer/settings.py` — 添加新阈值配置
8. 修改 `ipo_analyzer/models.py` — 添加新数据模型

### Phase 3: 测试与验证

9. 编写单元测试（3个测试文件）
10. 修改集成测试
11. 运行回测验证
12. 修复发现的问题

---

## 六、风险与约束

### 6.1 技术风险

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 招股书格式差异大 | 提取成功率低 | 使用多正则模式+表格提取回退 |
| 表格解析错误 | 数据错误 | 添加数据合理性校验 |
| 中文/英文混合 | 正则匹配失败 | 同时支持中英文模式 |
| 数据缺失 | 评分不准确 | 设置合理默认值并降低置信度 |

### 6.2 业务约束

- **Biotech公司特殊处理** — 未盈利Biotech的盈利可持续性豁免
- **金融行业特殊处理** — 银行/保险不适用流动比率标准
- **数据缺失降级** — 当关键数据缺失时，使用中性默认分（50分）并标记置信度

---

## 七、后续扩展（Phase 2/3）

### Phase 2 候选维度

5. **行业周期位置判断** — 需要外部行业数据源
6. **收入质量深度分析** — 需要应收账款账龄等详细数据
7. **供应链韧性分析** — 需要供应商地域分布数据

### Phase 3 候选维度

8. **ESG风险评估** — 需要外部ESG评级数据或LLM分析

---

## 八、验收标准

- [ ] 3个新分析器能通过所有单元测试
- [ ] 新维度能正确接入现有评分体系
- [ ] 招股书PDF提取成功率 >= 70%
- [ ] 回测验证新维度对胜率有正向提升（或至少无负面影响）
- [ ] 代码风格与现有15个分析器保持一致
- [ ] 所有新增阈值可在 `settings.py` 中配置
- [ ] 新增数据模型能在前端正确序列化显示
