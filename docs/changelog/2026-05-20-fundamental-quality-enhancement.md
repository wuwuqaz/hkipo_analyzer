# 质地与基本面分析增强 - 变更日志

**日期：** 2026-05-20  
**Commit：** 8b5f63f  
**类型：** Feature  
**分支：** main  

---

## 概述

增强港股IPO打新分析系统的质地评估能力，新增3个核心分析维度，提升对高风险破发标的的识别准确度。

---

## 新增功能

### 1. 管理层与治理质量分析

**文件：** `ipo_analyzer/analyzers/_management_governance.py`

**提取指标：**
- 管理层行业经验年限（年）
- 创始人/核心团队持股比例（%）
- 独立董事占比
- 控股股东持股比例
- 审计机构资质（四大/非四大）
- 治理风险标志（诉讼、违规、关联交易、内控缺陷、财务舞弊）

**评分逻辑（0-100分）：**
| 指标 | 条件 | 分数 |
|------|------|------|
| 管理层经验 | ≥10年 | +25 |
|  | 5-10年 | +15 |
| 创始人持股 | 15-40%（利益绑定适中） | +20 |
| 独董占比 | ≥1/3 | +15 |
| 审计机构 | 四大 | +15 |
| 无治理风险 | 无风险标志 | +15 |
| 控股股东集中度 | 30-60% | +10 |

**风险扣分：**
- 控股股东持股 >70% → -10分
- 独董占比 <1/3 → -10分
- 有争议/诉讼记录 → -15分/项
- 审计机构非四大 → -5分

**标签：** 优秀（≥75）、良好（≥60）、一般（≥40）、偏弱（<40）

---

### 2. 资产负债结构分析

**文件：** `ipo_analyzer/analyzers/_balance_sheet.py`

**提取指标：**
- 资产负债率
- 有息负债率（短期借款+长期借款）/股东权益
- 流动比率（流动资产/流动负债）
- 速动比率（扣除存货）
- 利息保障倍数（EBIT/利息支出）

**评分逻辑（0-100分）：**
| 指标 | 条件 | 分数 |
|------|------|------|
| 资产负债率 | <50% | +25 |
|  | 50-70% | +15 |
|  | >70% | +5 |
| 有息负债率 | <20% | +20 |
|  | 20-40% | +10 |
|  | >40% | -5 |
| 流动比率 | >2.0 | +20 |
|  | 1.5-2.0 | +10 |
|  | <1.5 | -10 |
| 速动比率 | >1.0 | +15 |
|  | <1.0 | -10 |
| 利息保障倍数 | >5 | +20 |
|  | 3-5 | +10 |
|  | <3 | -15 |

**标签：** 稳健（≥75）、可控（≥60）、偏紧（≥40）、高风险（<40）

---

### 3. 盈利可持续性分析

**文件：** `ipo_analyzer/analyzers/_profit_sustainability.py`

**提取指标：**
- 净利润
- 扣非净利润（Non-GAAP Net Profit）
- 非经常性损益及占比
- 政府补贴及占比
- 资产处置收益
- 投资收益

**评分逻辑（0-100分）：**
| 指标 | 条件 | 分数 |
|------|------|------|
| 非经常性损益占比 | <10% | +30 |
|  | 10-20% | +20 |
|  | 20-30% | +10 |
|  | >30% | -10 |
| 政府补贴占比 | <5% | +20 |
|  | 5-15% | +10 |
|  | >15% | -10 |
| 扣非vs净利润 | 同向 | +20 |
|  | 反向 | -20 |
| 盈利状态 | 已盈利（非Biotech） | +20 |
|  | 亏损（非Biotech） | -10 |
| Biotech未盈利 | 豁免 | +10 |

**标签：** 可持续（≥75）、基本可持续（≥60）、依赖非经常（≥40）、不可持续（<40）

---

## 权重分配

新维度在质地评分中的权重：
- 管理层与治理质量：**15%**
- 资产负债结构：**15%**
- 盈利可持续性：**10%**

合计新增权重：**40%**

---

## 配置项

在 `ipo_analyzer/settings.py` 的 `ProspectusQualityThresholds` 中新增：

```python
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

## 测试覆盖

**新增18个单元测试：**

| 测试文件 | 测试数量 | 覆盖范围 |
|---------|---------|---------|
| `tests/test_management_governance.py` | 7 | 管理层经验、创始人持股、四大识别、治理风险、评分逻辑 |
| `tests/test_balance_sheet.py` | 5 | 资产负债率、流动比率、健康/高风险场景、默认值 |
| `tests/test_profit_sustainability.py` | 6 | 政府补贴、非经常性损益、可持续盈利、Biotech豁免、反向风险 |

**测试结果：** ✅ 313个测试全部通过（18新增 + 295现有）

---

## 修改文件清单

| 文件 | 更改类型 | 说明 |
|------|---------|------|
| `ipo_analyzer/analyzers/_management_governance.py` | 新建 | 管理层治理分析器 |
| `ipo_analyzer/analyzers/_balance_sheet.py` | 新建 | 资产负债分析器 |
| `ipo_analyzer/analyzers/_profit_sustainability.py` | 新建 | 盈利可持续性分析器 |
| `ipo_analyzer/analyzers/__init__.py` | 修改 | 导出新分析器 |
| `ipo_analyzer/parser.py` | 修改 | 注册分析器调用 |
| `ipo_analyzer/quality_analyzer.py` | 修改 | 接入评分体系 |
| `ipo_analyzer/settings.py` | 修改 | 新增阈值配置 |
| `ipo_analyzer/models.py` | 修改 | 新增数据模型 |
| `tests/test_management_governance.py` | 新建 | 单元测试 |
| `tests/test_balance_sheet.py` | 新建 | 单元测试 |
| `tests/test_profit_sustainability.py` | 新建 | 单元测试 |

---

## 技术细节

### 正则表达式修复

在开发过程中遇到的正则表达式问题和解决方案：

1. **贪婪匹配问题**：`.{0,10}` 会消耗数字的一部分
   - 解决：改用 `.*?` 非贪婪匹配

2. **跨行匹配问题**：测试文本包含换行符
   - 解决：添加 `re.DOTALL` 标志

3. **负数捕获问题**：扣非净利润可能为负
   - 解决：正则改为 `-?[\d,]+`

### 评分体系集成

在 `quality_analyzer.py` 中，新维度评分插入位置：
- 在财务健康分析之后
- 在 label 计算之前
- 同时更新 Fisher 和 Lynch 长期评分点

---

## 后续计划

### Phase 2 候选维度（待实施）
- 行业周期位置判断
- 收入质量深度分析
- 供应链韧性分析

### Phase 3 候选维度（需要外部数据）
- ESG风险评估

---

## 验收标准

- [x] 3个新分析器能通过所有单元测试
- [x] 新维度能正确接入现有评分体系
- [x] 招股书PDF提取成功率 >= 70%
- [x] 回测验证新维度对胜率有正向提升（或至少无负面影响）
- [x] 代码风格与现有15个分析器保持一致
- [x] 所有新增阈值可在 `settings.py` 中配置
- [x] 新增数据模型能在前端正确序列化显示
- [x] 所有313个测试通过
