# 保荐人战绩 + 定价价差 设计文档

**日期：** 2026-05-20  
**状态：** 待审核  
**目标：** 补齐港股IPO分析的两个高优先级缺口——保荐人战绩分析和定价价差指标

---

## 一、背景与目标

### 1.1 现状

根据行业最佳实践对比，当前项目缺失两个高优先级维度：
1. **保荐人战绩分析** — 辉立/耀才/富途等打新平台标配展示保荐人历史破发率
2. **定价价差指标** — 华泰研究核心指标：发行价 vs 招股价区间中值偏离度

### 1.2 目标

- 保荐人战绩：创建 S/A/B/C 四级分级体系，纳入交易热度（trade_score）维度
- 定价价差：利用现有 `offer_price`、`min_price`、`max_price` 字段，计算价差衍生指标，纳入估值压力调整

### 1.3 成功标准

- 新增代码遵循现有架构模式
- 保荐人数据库模式参考 `cornerstone_investors.yaml`
- 所有新增功能有单元测试覆盖
- 不破坏现有 313 个测试

---

## 二、架构设计

### 2.1 文件结构

```
data/
├── sponsor_track_record.yaml      ← 新建：保荐人历史战绩数据库
├── cornerstone_investors.yaml     ← 现有（参考模式）

ipo_analyzer/
├── analyzers/
│   ├── _sponsor_track_record.py   ← 新建：保荐人战绩分析器
│   └── ...
├── models.py                      ← 修改：+SponsorRecord, +PricingGapResult
├── parser.py                      ← 修改：提取保荐人名称
├── scoring.py                     ← 修改：trade_score纳入保荐人分 + 价差调整
├── settings.py                    ← 修改：+SponsorThresholds

tests/
├── test_sponsor_track_record.py   ← 新建：保荐人战绩测试
├── test_pricing_gap.py            ← 新建：定价价差测试
```

### 2.2 数据流

```
招股书PDF
  ↓ parser
prospectus_info
  ├── min_price, max_price, offer_price    ← 已有字段
  ├── sponsor_name                          ← 新增提取
  └── _extracted_text                       ← 已有

scoring.py
  ├── 读取 sponsor_track_record.yaml 匹配保荐人等级
  ├── 保荐人分数 → trade_score 维度
  ├── 计算 pricing_gap = (offer - mid) / mid
  └── 定价价差 → 估值压力调整项
```

---

## 三、详细设计

### 3.1 保荐人战绩数据库

**文件：** `data/sponsor_track_record.yaml`

```yaml
meta:
  version: '1.0'
  last_updated: '2026-05-20'
  description: 港股保荐人历史战绩数据库
  scoring_window_months: 24
  total_sponsors: 25

sponsors:
  - name: 中金公司
    tier: S
    aliases:
      - CICC
      - 中国国际金融
      - 中国国际金融股份有限公司
    recent_ipo_count: 45
    break_rate: 0.22
    avg_first_day_return: 4.5
    avg_oversub_ratio: 120
    sector_strength:
      - biotech
      - technology
    note: 头部中资投行，投行项目最多

  - name: 摩根士丹利
    tier: S
    aliases:
      - Morgan Stanley
      - 摩根士丹利亚洲
      - Morgan Stanley Asia
    recent_ipo_count: 38
    break_rate: 0.18
    avg_first_day_return: 5.8
    avg_oversub_ratio: 150
    sector_strength:
      - technology
      - consumer
    note: 顶级外资，科技消费领域强势

  - name: 高盛
    tier: S
    aliases:
      - Goldman Sachs
      - 高盛亚洲
      - Goldman Sachs Asia
    recent_ipo_count: 32
    break_rate: 0.20
    avg_first_day_return: 5.2
    avg_oversub_ratio: 140

  - name: 中信证券
    tier: A
    aliases:
      - 中信证券国际
      - CITIC Securities
      - 中信里昂
      - CLSA
    recent_ipo_count: 30
    break_rate: 0.28
    avg_first_day_return: 3.5
    avg_oversub_ratio: 90
    note: 中资头部，项目多但破发率偏高

  - name: 华泰国际
    tier: A
    aliases:
      - 华泰金融
      - Huatai International
    recent_ipo_count: 25
    break_rate: 0.25
    avg_first_day_return: 3.8

  - name: 招银国际
    tier: A
    aliases:
      - CMB International
      - 招商银行国际
    recent_ipo_count: 28
    break_rate: 0.24
    avg_first_day_return: 3.6
    note: 银行系投行，中高评级

  - name: 建银国际
    tier: A
    aliases:
      - CCB International
      - 建设银行国际
    recent_ipo_count: 22
    break_rate: 0.30
    avg_first_day_return: 2.8
    note: 银行系，破发率较高

  - name: 农银国际
    tier: B
    aliases:
      - ABC International
      - 农业银行国际
    recent_ipo_count: 18
    break_rate: 0.35
    avg_first_day_return: 2.0

  - name: 海通国际
    tier: B
    aliases:
      - Haitong International
      - 海通证券
    recent_ipo_count: 20
    break_rate: 0.38
    avg_first_day_return: 1.8

  - name: 申万宏源
    tier: B
    aliases:
      - 申万宏源国际
      - Shenwan Hongyuan
    recent_ipo_count: 12
    break_rate: 0.42
    avg_first_day_return: 0.5

  - name: 国泰君安
    tier: B
    aliases:
      - 国泰君安国际
      - Guotai Junan
    recent_ipo_count: 16
    break_rate: 0.40
    avg_first_day_return: 1.2

  - name: UBS
    tier: A
    aliases:
      - 瑞银
      - 瑞士银行
      - UBS AG
    recent_ipo_count: 25
    break_rate: 0.26
    avg_first_day_return: 3.2

  - name: 美林
    tier: A
    aliases:
      - Merrill Lynch
      - BofA Securities
    recent_ipo_count: 18
    break_rate: 0.22
    avg_first_day_return: 4.0

  - name: 招商证券
    tier: B
    aliases:
      - 招商证券国际
      - China Merchants Securities
    recent_ipo_count: 15
    break_rate: 0.40
    avg_first_day_return: 1.0

  - name: 光大证券
    tier: B
    aliases:
      - 光大证券国际
      - Everbright Securities
    recent_ipo_count: 10
    break_rate: 0.45
    avg_first_day_return: 0.0

  - name: 工银国际
    tier: A
    aliases:
      - ICBC International
      - 工商银行国际
    recent_ipo_count: 20
    break_rate: 0.28
    avg_first_day_return: 2.5

  - name: 中信建投
    tier: A
    aliases:
      - 中信建投国际
      - China Securities International
    recent_ipo_count: 15
    break_rate: 0.30
    avg_first_day_return: 2.2

  - name: 法国巴黎银行
    tier: A
    aliases:
      - BNP Paribas
      - 法巴
    recent_ipo_count: 12
    break_rate: 0.25
    avg_first_day_return: 3.0

  - name: 花旗
    tier: A
    aliases:
      - Citigroup
      - Citi
      - 花旗银行
    recent_ipo_count: 15
    break_rate: 0.22
    avg_first_day_return: 4.2

  - name: 瑞士信贷
    tier: B
    aliases:
      - Credit Suisse
      - 瑞信
    recent_ipo_count: 10
    break_rate: 0.38
    avg_first_day_return: 1.5
    note: 已被瑞银收购，历史数据保留

  - name: 星展银行
    tier: B
    aliases:
      - DBS
      - 星展
    recent_ipo_count: 8
    break_rate: 0.42
    avg_first_day_return: 1.0

  - name: 平安证券
    tier: B
    aliases:
      - 平安证券国际
      - Ping An Securities
    recent_ipo_count: 8
    break_rate: 0.45
    avg_first_day_return: -0.5

  - name: 银河国际
    tier: B
    aliases:
      - 银河证券国际
      - Galaxy International
    recent_ipo_count: 6
    break_rate: 0.50
    avg_first_day_return: -1.0

  - name: 广发证券
    tier: C
    aliases:
      - 广发国际
      - GF Securities
    recent_ipo_count: 5
    break_rate: 0.55
    avg_first_day_return: -2.0

  - name: 未知保荐人
    tier: C
    aliases: []
    recent_ipo_count: 0
    break_rate: 0.50
    avg_first_day_return: 0.0
    note: 兜底默认值，用于未匹配到的保荐人
```

**分级体系（S/A/B/C 四级）：**

| 等级 | 条件 | 含义 |
|------|------|------|
| **S级** | 胜率 > 80% + 平均收益 > 3% | 顶级保荐人，机构认可度极高 |
| **A级** | 胜率 60-80% | 可靠保荐人，中等偏上 |
| **B级** | 胜率 40-60% | 一般保荐人，需结合其他因素 |
| **C级** | 胜率 < 40% 或 项目 < 5 个 | 弱保荐人或数据不足 |

---

### 3.2 保荐人战绩分析器

**文件：** `ipo_analyzer/analyzers/_sponsor_track_record.py`

```
class SponsorTrackRecordAnalyzer:
    def analyze(self, prospectus_info, text=''):
        - 从招股书文本提取保荐人名称（正则：sponsor/保荐人/联席保荐人模式）
        - 加载 sponsor_track_record.yaml 数据库
        - 名称匹配（精确+别名）
        - 返回: {sponsor_name, tier, break_rate, avg_return, ...}
```

---

### 3.3 定价价差指标

**无新分析器**，直接在 `scoring.py` 中计算：

```python
# 第一步：计算价差
mid_price = (min_price + max_price) / 2 if min_price and max_price else None

if mid_price and mid_price > 0 and offer_price:
    pricing_gap = (offer_price - mid_price) / mid_price

    # 第二步：融入估值压力调整
    if pricing_gap < -0.20:
        gap_score = +5    # 折价发行
        gap_label = "折价发行"
    elif pricing_gap < 0.10:
        gap_score = 0     # 中性
        gap_label = "定价中性"
    elif pricing_gap < 0.20:
        gap_score = -3    # 偏激进
        gap_label = "定价偏激进"
    else:
        gap_score = -8    # 定价激进
        gap_label = "定价激进"
```

**融入方式：** 作为 `_calc_valuation_adjustments()` 返回值的组成部分，与现有估值调整合并。

---

### 3.4 接入 scoring.py

**保荐人接入 trade_score 维度：**

在 `_compute_raw_scores()` 方法中，trade_score 计算新增 sponsor 成分：

```python
# 现有：trade_raw = heat + scale + cornerstone + real_money + float_structure
# 新增：如果保荐人匹配成功，追加 sponsor 分
if sponsor_result and sponsor_result.get('tier') != 'C':
    sponsor_score = sponsor_tier_score.get(sponsor_result['tier'], 0)
    trade_raw += sponsor_score
    trade_max += SPONSOR_SCORE_MAX  # = 10
```

**保荐人分级分数映射：**
| Tier | 分数 | 说明 |
|------|------|------|
| S级 | +10 | 顶级保荐人 |
| A级 | +7 | 可靠保荐人 |
| B级 | +3 | 一般保荐人 |
| C级 | 0 | 不额外加分 |

---

### 3.5 配置项

**settings.py 新增：**

```python
@dataclass
class SponsorThresholds:
    """保荐人战绩评分阈值"""
    tier_s_score: int = 10
    tier_s_condition_break_rate: float = 0.20
    tier_a_score: int = 7
    tier_a_condition_break_rate: float = 0.40
    tier_b_score: int = 3
    tier_b_condition_break_rate: float = 0.60
    max_score: int = 10
    min_project_count: int = 5
```

---

### 3.6 数据模型

**models.py 新增：**

```python
@dataclass
class SponsorRecord:
    """保荐人战绩记录"""
    name: str
    tier: str = "C"
    aliases: list[str] = field(default_factory=list)
    recent_ipo_count: int = 0
    break_rate: float = 0.50
    avg_first_day_return: float = 0.0
    avg_oversub_ratio: float = 0.0
    sector_strength: list[str] = field(default_factory=list)

@dataclass
class PricingGapResult:
    """定价价差分析结果"""
    mid_price: Optional[float] = None
    pricing_gap: Optional[float] = None
    gap_score: int = 0
    gap_label: str = "数据不足"
    confidence: str = "missing"
```

---

## 四、测试策略

### 4.1 保荐人战绩测试

- `test_load_sponsor_database()` — 验证数据库加载
- `test_match_sponsor_by_name_exact()` — 精确名称匹配
- `test_match_sponsor_by_alias()` — 别名匹配
- `test_unknown_sponsor_returns_default()` — 未知保荐人返回兜底
- `test_tier_s_sponsor_score()` — S级保荐人得分
- `test_tier_c_sponsor_no_bonus()` — C级保荐人不加分

### 4.2 定价价差测试

- `test_pricing_gap_discount_positive()` — 折价发行+5分
- `test_pricing_gap_neutral()` — 中性定价
- `test_pricing_gap_aggressive_negative()` — 激进定价-8分
- `test_pricing_gap_missing_data()` — 数据缺失返回None
- `test_pricing_gap_zero_mid_price()` — 分母为0的处理

---

## 五、实施步骤

1. 创建 `data/sponsor_track_record.yaml` 保荐人数据库
2. 创建 `ipo_analyzer/analyzers/_sponsor_track_record.py` 分析器
3. 修改 `ipo_analyzer/models.py` 新增数据模型
4. 修改 `ipo_analyzer/settings.py` 新增阈值
5. 修改 `ipo_analyzer/parser.py` 提取保荐人名称
6. 修改 `ipo_analyzer/scoring.py` 融入保荐人分 + 定价价差
7. 创建测试文件并验证
8. 运行全量测试确认无回归

---

## 六、验收标准

- [ ] 保荐人分级数据库覆盖 ≥ 20 家港股主流保荐人
- [ ] 名称匹配支持精确+别名匹配
- [ ] 未知保荐人使用兜底默认值
- [ ] 定价价差正确融入估值调整
- [ ] 所有新增代码有单元测试覆盖
- [ ] 不破坏现有 313 个测试
- [ ] 代码风格与现有分析器一致
