# 评分系统管道化重构设计

> 日期: 2026-05-22  
> 范围: 后端评分逻辑 (scoring.py) + 整体数据流 (分析器 → 评分 → 输出) + 前端展示对接  
> 方案: 方案 A — 管道化 + 类型契约重构

---

## 1. 背景与动机

当前 `ScoringSystem` 已膨胀至 ~1200 行，承担了维度评分、策略评分（long-term / strict IPO）、调整项计算（peer/valuation/pricing gap/risk/cornerstone）、推荐生成、权重检测等过多职责。随着新增分析维度（管理层治理、资产负债、盈利可持续性）的引入，以及回测框架对评分组件细粒度调优的需求，现有结构已难以维护和扩展。

本次重构的核心目标：**将评分从「一个巨型类」转变为「类型安全、职责清晰、可观测的管道」**。

---

## 2. 当前问题分析

| 问题 | 影响 | 严重程度 |
|------|------|---------|
| `ScoringSystem` ~1200 行，职责混杂 | 任何分数调整都需要阅读整份文件；单测难以覆盖分支 | 🔴 高 |
| 分析器输出为 untyped dict，评分直接读取 | 字段缺失/类型错误在运行时才发现；重构时无 IDE 支持 | 🔴 高 |
| 调整项（peer_adj、val_penalty、risk_penalty、cornerstone_penalty）分散在不同方法中 | 难以验证最终分数的完整调整链路；score_trace 是事后手动追加 | 🔴 高 |
| `_build_strategy_scores` 既算分又做推荐 | 推荐逻辑与分数计算耦合，无法独立测试 | 🟡 中 |
| Biotech 特殊处理散落在 valuation、scoring、quality、signal 四个模块 | 判断标准不一致（有的看行业代码，有的看收入结构），维护困难 | 🟡 中 |
| 阈值（heat tier、long-term 权重等）部分 hardcoded | 回测框架目前只优化五维权重，无法优化内部阈值 | 🟡 中 |

---

## 3. 设计目标

1. **职责单一化**：每个评分组件只做一件事，输入输出通过强类型契约定义。
2. **管道可观测**：评分每一步的中间结果自动记录，score_trace 不再是事后补录的字符串。
3. **向后兼容**：现有 `ScoringSystem.calculate()` 接口保留为薄层，内部委托新管道，现有调用方零改动。
4. **回测友好**：DimensionScorer / AdjustmentEngine / StrategyScorer 可以独立被回测框架调用，无需跑完整 pipeline。
5. **阈值可配置**：将散落在代码中的评分阈值统一收拢到 `settings.py`，为后续回测优化阈值铺路。

---

## 4. 架构设计

### 4.1 整体数据流

```
Analyzer Outputs (flat dicts from 9+ analyzers)
    ↓
AnalyzerOutputAdapter  (dict → ScoringInput dataclass)
    ↓
ScoringPipeline
    ├── Step 1: DimensionScorer
    │   → DimensionScores (trade, fundamental, valuation, theme, data_quality)
    ├── Step 2: AdjustmentEngine
    │   → Adjustments (peer_adj, val_penalty, pricing_gap_adj,
    │                   risk_penalty, cornerstone_penalty)
    ├── Step 3: StrategyScorer
    │   → StrategyScores (long_term_score, strict_ipo_score)
    └── Step 4: Recommender
        → Recommendation (recommendation, reasons, dimension_grades)
    ↓
ScoringResult (typed dataclass, 内含完整 ScoreTrace)
    ↓
IPODataNormalizer → IPOData / API Response
```

### 4.2 类型契约

#### `ScoringInput`

评分管道的唯一输入。由 `AnalyzerOutputAdapter` 从分析器 dict 映射而来。

```python
@dataclass
class ScoringInput:
    # 标识
    stock_code: str
    company_name: str
    industry: Optional[str]
    is_biotech: bool  # 统一判断，不再各自为政

    # 交易信号 (from SignalComponentAnalyzer)
    heat_score: float          # 0-45
    scale_score: float         # 0-10
    cornerstone_score: float   # 0-20
    real_money_signal: float
    float_structure_score: float
    sponsor_score: Optional[float]
    greenshoe_score: Optional[float]
    clawback_score: Optional[float]

    # 基本面 (from ProspectusQualityAnalyzer)
    stock_quality_score: float  # 0-100
    quality_dimensions: QualityDimensions  # nested dataclass

    # 估值 (from ValuationAnalyzer + PeerComparableAnalyzer)
    valuation_framework_score: float
    peer_adj_label: Optional[str]  # "excellent", "fair", "overvalued" 等
    pricing_gap_adj: float
    valuation_label: Optional[str]

    # 主题 (from SectorAnalyzer + macro/sentiment)
    mainline_beta_score: float
    stock_connect_path_score: float
    scarcity_score: float
    sentiment_bonus: float
    macro_bonus: float

    # 数据质量
    data_quality_score: float

    # 风险 (from RiskFactorAnalyzer)
    risk_penalty: float
    risk_categories: dict[str, list[str]]

    # 基石 (from CornerstoneAnalyzer)
    cornerstone_pct: Optional[float]
    cornerstone_investors: list[CornerstoneInvestorInput]
    cornerstone_red_flags: list[str]

    # 原始数据引用（用于调试和追溯）
    raw_prospectus_info: dict  # 保留原始 dict，供 adapter 无法映射的字段 fallback
```

#### `DimensionScores`

五维原始分，不含任何调整。

```python
@dataclass
class DimensionScores:
    trade: float        # 0-100
    fundamental: float  # 0-100
    valuation: float    # 0-100
    theme: float        # 0-100
    data_quality: float # 0-100

    # 子组件明细（用于 score_trace 和前端 drill-down）
    trade_components: dict[str, float]
    fundamental_components: dict[str, float]
```

#### `Adjustments`

所有调整项集中管理。

```python
@dataclass
class Adjustments:
    peer_adj: float
    val_penalty: float
    pricing_gap_adj: float
    risk_penalty: float
    cornerstone_penalty: float

    @property
    def total(self) -> float:
        return self.peer_adj + self.val_penalty + self.pricing_gap_adj \
               - self.risk_penalty - self.cornerstone_penalty
```

#### `StrategyScores`

```python
@dataclass
class StrategyScores:
    long_term_score: float
    strict_ipo_score: float

    # 子组件明细
    long_term_components: dict[str, float]
```

#### `ScoreTrace`

管道化自动记录，不再是字符串拼接。

```python
@dataclass
class ScoreTraceStep:
    step_name: str
    input_data: dict[str, Any]
    output_data: dict[str, Any]
    metadata: dict[str, Any]  # 如权重配置、阈值版本等

@dataclass
class ScoreTrace:
    steps: list[ScoreTraceStep]

    def to_flat_dict(self) -> dict:
        """兼容现有前端格式"""
```

#### `ScoringResult`

评分管道的最终输出。

```python
@dataclass
class ScoringResult:
    # 核心分数
    score: float
    final_score: float

    # 五维分
    trade_score: float
    fundamental_score: float
    valuation_score: float
    theme_score: float
    data_quality_score: float

    # 策略分
    long_term_score: float
    strict_ipo_score: float
    ipo_trade_score: float

    # 推荐
    recommendation: str
    reasons: list[str]
    dimension_grades: dict[str, str]

    # 可观测性
    score_trace: ScoreTrace
    weight_profile: str
    debug_info: dict[str, Any]
```

### 4.3 各组件设计

#### `AnalyzerOutputAdapter`

**职责**：将 `core.py` 中收集的扁平分析器输出（`prospectus_info` dict）映射为 `ScoringInput`。字段缺失/类型错误在此层统一处理，评分组件不再接触原始 dict。

**关键行为**：
- 对 `is_biotech` 使用统一判断逻辑（提取自当前散落在各处的判断规则）。
- 字段缺失时填充安全默认值，并记录 `debug_info`。
- 保留 `raw_prospectus_info` 引用，供 `ScoreTrace` 完整追溯。

#### `DimensionScorer`

**职责**：只计算五维原始分，不处理任何调整项。

```python
class DimensionScorer:
    def __init__(self, thresholds: DimensionThresholds): ...

    def calculate(self, input: ScoringInput) -> DimensionScores:
        trade = self._calc_trade(input)
        fundamental = self._calc_fundamental(input)
        valuation = self._calc_valuation(input)
        theme = self._calc_theme(input)
        data_quality = self._calc_data_quality(input)
        return DimensionScores(...)
```

#### `AdjustmentEngine`

**职责**：集中计算所有调整项。当前散落在 `_calc_valuation_adjustments`、`_calculate_risk_penalty`、cornerstone penalty 等处的逻辑统一迁移至此。

```python
class AdjustmentEngine:
    def __init__(self, thresholds: AdjustmentThresholds): ...

    def calculate(self, input: ScoringInput,
                  dimensions: DimensionScores) -> Adjustments:
        peer_adj = self._calc_peer_adj(input, dimensions)
        val_penalty = self._calc_val_penalty(input)
        pricing_gap_adj = self._calc_pricing_gap_adj(input)
        risk_penalty = self._calc_risk_penalty(input)
        cornerstone_penalty = self._calc_cornerstone_penalty(input)
        return Adjustments(...)
```

#### `StrategyScorer`

**职责**：基于 raw_score + 基本面信号计算 long_term_score 和 strict_ipo_score。推荐逻辑已剥离到 `Recommender`。

```python
class StrategyScorer:
    def calculate(self, input: ScoringInput,
                  raw_score: float,
                  dimensions: DimensionScores) -> StrategyScores:
        long_term = self._calc_long_term(input, dimensions)
        strict_ipo = self._calc_strict_ipo(raw_score, long_term, input)
        return StrategyScores(...)
```

#### `Recommender`

**职责**：纯映射逻辑，将分数映射为推荐标签、原因列表、等级评定。

```python
class Recommender:
    def recommend(self, final_score: float,
                  strategy_scores: StrategyScores,
                  adjustments: Adjustments,
                  dimensions: DimensionScores) -> RecommendationResult:
        ...
```

#### `ScoringPipeline`

**职责**：串联以上组件，管理 `ScoreTrace`。

```python
class ScoringPipeline:
    def __init__(self,
                 dimension_scorer: DimensionScorer,
                 adjustment_engine: AdjustmentEngine,
                 strategy_scorer: StrategyScorer,
                 recommender: Recommender,
                 weight_detector: WeightProfileDetector): ...

    def run(self, input: ScoringInput) -> ScoringResult:
        trace = ScoreTrace()

        # Step 1: DimensionScores
        dims = self.dimension_scorer.calculate(input)
        trace.record("dimension", input, dims)

        # Step 2: Adjustments
        adj = self.adjustment_engine.calculate(input, dims)
        trace.record("adjustment", {"dimensions": dims}, adj)

        # Step 3: Weighted raw score
        profile = self.weight_detector.detect(input)
        weights = profile.weights
        raw_score = sum(dims[d] * weights[d] for d in dims)
        trace.record("weighting", {"profile": profile}, {"raw_score": raw_score})

        # Step 4: Apply adjustments
        score = raw_score + adj.total
        trace.record("apply_adjustments", {"raw_score": raw_score}, {"score": score})

        # Step 5: Strategy scores
        strat = self.strategy_scorer.calculate(input, score, dims)
        trace.record("strategy", {"score": score}, strat)

        # Step 6: Final score (after strategy caps)
        final_score = self._apply_caps(score, strat, input)
        trace.record("final", {"score": score}, {"final_score": final_score})

        # Step 7: Recommendation
        rec = self.recommender.recommend(final_score, strat, adj, dims)
        trace.record("recommendation", {"final_score": final_score}, rec)

        return ScoringResult(
            score=score,
            final_score=final_score,
            trade_score=dims.trade,
            fundamental_score=dims.fundamental,
            ...,
            score_trace=trace,
            weight_profile=profile.name,
        )
```

---

## 5. 文件重组

新建目录 `ipo_analyzer/scoring/`，将现有 `scoring.py` 中的逻辑迁移至以下文件：

```
ipo_analyzer/scoring/
├── __init__.py              # 导出 ScoringPipeline, ScoringResult, ScoreTrace
├── pipeline.py              # ScoringPipeline 主类
├── input_adapter.py         # AnalyzerOutputAdapter
├── models.py                # 所有 scoring 相关的 dataclass
├── dimension_scorer.py      # DimensionScorer
├── adjustment_engine.py     # AdjustmentEngine
├── strategy_scorer.py       # StrategyScorer
├── recommender.py           # Recommender
├── weight_detector.py       # WeightProfileDetector（从现有 _detect_weight_profile 提取）
└── _utils.py                # is_biotech(), threshold helpers, caps logic
```

保留 `ipo_analyzer/scoring.py` 作为兼容薄层：

```python
# ipo_analyzer/scoring.py (保留，变薄)
from ipo_analyzer.scoring import ScoringPipeline, ScoringResult

class ScoringSystem:
    def __init__(self, settings: Optional[ScoringSettings] = None):
        self.pipeline = ScoringPipeline.from_settings(settings or SETTINGS)

    def calculate(self, ipo, prospectus_info, signal_components=None) -> dict:
        # 1. 用旧逻辑构建 input dict（兼容现有调用方）
        # 2. Adapter 转换
        # 3. Pipeline 执行
        # 4. 将 ScoringResult 映射回现有 dict 格式
        ...
```

---

## 6. 迁移策略

**阶段 1：类型契约先行（不改动评分逻辑）**
1. 创建 `ipo_analyzer/scoring/models.py`，定义所有 dataclass。
2. 创建 `AnalyzerOutputAdapter`，只写映射逻辑，不改动现有评分计算。
3. 单测：验证 adapter 能正确将现有 `prospectus_info` 映射为 `ScoringInput`。

**阶段 2：组件拆解（保持输出不变）**
1. 将 `ScoringSystem` 中的 `_calc_trade`、`_calc_fundamental` 等方法逐一提取为 `DimensionScorer` 的私有方法。
2. 将调整项逻辑提取为 `AdjustmentEngine`。
3. 将策略评分提取为 `StrategyScorer`。
4. 将推荐逻辑提取为 `Recommender`。
5. 每一步都通过现有测试确保输出不变。

**阶段 3：管道组装**
1. 实现 `ScoringPipeline`，将上述组件串联。
2. 实现 `ScoreTrace` 自动记录。
3. `ScoringSystem.calculate()` 内部改为调用 `ScoringPipeline`。

**阶段 4：阈值外部化**
1. 将 hardcoded 阈值迁移至 `settings.py` 的 `DimensionThresholds`、`AdjustmentThresholds`。
2. 更新回测框架，使其能优化这些阈值。

**阶段 5：清理**
1. 删除 `ScoringSystem` 中已迁移的旧方法。
2. 更新 API 层，可选择直接返回 `ScoringResult` 而非 dict。

---

## 7. 缺失补充

| 缺失项 | 补充方案 | 优先级 |
|--------|---------|--------|
| Biotech 统一判断 | 提取 `_utils.is_biotech()`，标准：行业代码属于 biotech/18C，或收入结构以 license upfront 为主 | 高 |
| ScoreTrace 结构化 | 从字符串拼接改为 `list[ScoreTraceStep]`，前端可渲染为可折叠的评分步骤树 | 高 |
| 阈值配置外部化 | `DimensionThresholds`、`AdjustmentThresholds` 收拢至 `settings.py`，支持 YAML 覆盖 | 中 |
| 评分组件独立单测 | 每个 Scorer 可独立实例化和测试，无需构造完整的 `prospectus_info` | 中 |
| 回测对接 | 回测框架可直接调用 `DimensionScorer` / `AdjustmentEngine` 进行组件级 A/B 测试 | 低 |

---

## 8. 测试策略

1. **回归测试**：重构期间，现有 `test_scoring.py` 的全部断言必须持续通过。任何测试修改都必须是输出格式兼容性的调整，而非分数逻辑变化。
2. **组件单测**：为每个 Scorer 编写独立单元测试，使用最小化的 `ScoringInput` fixture。
3. **管道集成测试**：验证 `ScoringPipeline.run()` 的 `ScoreTrace` 包含所有预期步骤。
4. **Adapter 测试**：使用真实的 `prospectus_info` dict 验证映射完整性。

---

## 9. 前端对接

当前前端通过 API 获取评分 dict。重构后：

- **短期**：`ScoringSystem.calculate()` 返回的 dict 格式不变，前端零改动。
- **中期**：API 层可直接序列化 `ScoringResult`，前端可利用 `score_trace` 渲染更丰富的评分溯源 UI。
- **长期**：`DimensionScores.trade_components` 等子组件明细可支持前端 drill-down（如点击「交易分」展开 heat/scale/cornerstone 子项）。

---

## 10. 回测兼容性

当前回测框架优化的是五维权重。重构后：

- `WeightProfileDetector` 可被回测框架直接替换为自定义权重配置。
- `DimensionScorer` / `AdjustmentEngine` 的阈值可被回测框架覆盖，为后续「阈值级优化」铺路。
- `ScoreTrace` 使回测结果可解释性更强——不仅知道最终分数，还能对比每一步的中间差异。
