# 回测框架 & 贝叶斯权重优化 — 设计规范

> 版本: v1.0  
> 日期: 2026-05-20  
> 状态: 待审阅

## 1. 背景与目标

### 1.1 背景

当前项目通过五维加权评分（交易热度25%、基本面35%、估值25%、主题10%、数据质量5%）对港股IPO进行打分。这些权重是基于经验设定的，缺少历史数据回测验证。对比华泰证券等专业机构的做法，其模型经过了跨年份系统回测，筛选后的标的收益率可提升约15个百分点。

### 1.2 目标

- **回测框架**：基于项目已积累的IPO历史数据（`storage/results/*.json` + `history.db`），对现有评分体系进行回测，计算胜率、期望收益、IC Rank等指标
- **权重优化**：用贝叶斯优化自动搜索最优五维权重，最大化多目标函数（胜率+期望收益-最大回撤）
- **无侵入集成**：通过 `optimized_weights.yaml` 配置文件与现有 `scoring.py` 集成，不改动评分核心逻辑

### 1.3 范围

- ✅ 从项目已有数据中提取回测样本
- ✅ 用当前/自定义权重回放评分并对比实际结果
- ✅ 贝叶斯优化搜索最优权重
- ✅ CLI 驱动（`python -m ipo_analyzer.backtest`）
- ✅ 结果持久化到 SQLite
- ❌ 不涉及新增外部数据源
- ❌ 不在前端展示（预留 API 端点接口，但不实现 UI）
- ❌ 不自动触发（需手动执行 CLI）

---

## 2. 架构设计

### 2.1 方案选择：独立模块 + CLI（方案A）

**理由**：数据量尚小（~几十只IPO），最小侵入、可渐进演化。核心回测逻辑以纯函数实现，未来可自然升级为 API 或前端可视化。

### 2.2 模块结构

```
ipo_analyzer/backtest/          # 新增模块（6个文件）
├── __init__.py
├── engine.py                   # 回测核心：重算评分 → 比对实际收益
├── metrics.py                  # 评估指标：胜率/期望收益/夏普/回撤/IC
├── optimizer.py                # 贝叶斯优化：GP surrogate + EI acquisition
├── collector.py                # 数据采集：history.db + storage/results/
├── store.py                    # 结果持久化：SQLite 表
└── cli.py                      # CLI 入口

ipo_analyzer/scoring.py         # 改动: +1 方法 load_optimized_weights()
ipo_analyzer/settings.py         # 改动: +1 配置 optimized_weights_path
data/optimized_weights.yaml     # 新增: 优化器输出，scoring.py 读取
```

### 2.3 数据流

```
collector.py  →  BacktestDataset  →  engine.py  →  BacktestResult  →  metrics.py  →  objective
                                              ↕ (被 optimizer.py 调用 30-50 轮)
                                              
optimizer.py  →  optimal_weights  →  optimized_weights.yaml  →  scoring.py (下次分析自动生效)
```

### 2.4 内部边界

- **collector/engine/metrics/optimizer** 均为纯函数，不依赖数据库连接、不依赖 FastAPI
- **store.py** 负责 SQLite 读写，使用 `aiosqlite` 异步接口（与现有 `db_pool.py` 风格一致）
- **cli.py** 是唯一的入口编排层

---

## 3. 数据模型

### 3.1 BacktestRecord（回测样本）

```python
@dataclass
class BacktestRecord:
    # 标识
    hk_code: str              # "02580.HK"
    company_name: str         # "宁德时代"
    listing_date: date        # 上市日期

    # 五维分项分（来自历史评分记录）
    trade_score: float        # 0-100
    fundamental_score: float  # 0-100
    valuation_score: float    # 0-100
    theme_score: float        # 0-100
    data_quality_score: float # 0-100

    # 实际结果（事后已知）
    first_day_return: float   # 首日涨跌幅 %
    is_break: bool            # 是否破发
    over_sub_ratio: float     # 实际超购倍数

    # 元数据
    score_timestamp: datetime # 评分时间
    data_quality: int         # 数据完整度 0/1/2
```

### 3.2 数据来源映射

| 字段 | 来源 |
|------|------|
| trade_score | `storage/results/{code}.json` → `score_breakdown.trade_score` |
| fundamental_score | `storage/results/{code}.json` → `score_breakdown.fundamental_score` |
| valuation_score | `storage/results/{code}.json` → `score_breakdown.valuation_score` |
| theme_score | `storage/results/{code}.json` → `score_breakdown.theme_score` |
| data_quality_score | `storage/results/{code}.json` → `score_breakdown.data_quality_score` |
| first_day_return | `history.db` post_listing 表 → (first_day_close - offer_price) / offer_price |
| is_break | `history.db` post_listing 表 → first_day_close < offer_price |
| over_sub_ratio | `history.db` post_listing 表 → actual_over_sub_ratio |

### 3.3 过滤规则

1. 排除 `data_quality < 2` 的记录（数据不完整）
2. 排除缺少 `first_day_return` 的记录（未上市或数据缺失）
3. 有效样本数 ≥ 10 才触发优化（`settings.MIN_BACKTEST_SAMPLES`）

### 3.4 SQLite 持久化（store.py）

复用现有 `history.db`，新增两张表：

```sql
CREATE TABLE IF NOT EXISTS backtest_runs (
    id            TEXT PRIMARY KEY,          -- UUID
    run_at        TEXT NOT NULL,             -- ISO datetime
    weights       TEXT NOT NULL,             -- JSON: {"trade":0.28,...}
    sample_count  INTEGER,
    win_rate      REAL,
    expected_return REAL,
    max_drawdown  REAL,
    sharpe_like   REAL,
    ic_rank       REAL,
    decile_returns TEXT,                     -- JSON: [0.05, 0.08, ...]
    is_optimized  INTEGER DEFAULT 0,         -- 0=手动权重, 1=优化结果
    notes         TEXT
);

CREATE TABLE IF NOT EXISTS optimization_runs (
    id            TEXT PRIMARY KEY,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    iterations    INTEGER,
    best_weights  TEXT,                      -- JSON
    best_objective REAL,
    default_objective REAL,
    improvement_pct REAL,
    cv_enabled    INTEGER DEFAULT 1,
    convergence   TEXT,                      -- JSON: [[iter, obj], ...]
    status        TEXT DEFAULT 'running'     -- running|completed|failed
);
```

---

## 4. 回测引擎 (engine.py)

### 4.1 核心逻辑

```python
def run_backtest(dataset: list[BacktestRecord], weights: dict[str, float]) -> BacktestResult:
```

对每只IPO计算加权总分，然后按分分析实际表现：

```
composite_score = w1*trade + w2*fundamental + w3*valuation + w4*theme + w5*data_quality

统计：
- overall: 全体样本的破发率、平均收益
- qualified (score ≥ QUALIFY_THRESHOLD): 推荐标的的胜率、期望收益、最大回撤
- deciles: 按评分分为10组，每组平均收益
```

### 4.2 QUALIFY_THRESHOLD

默认 50，通过 `settings.BACKTEST_QUALIFY_THRESHOLD` 配置。模拟用户只看高分推荐的场景。

---

## 5. 评估指标 (metrics.py)

### 5.1 目标函数（多目标复合）

```
objective = win_rate × 0.4 + expected_return × 0.4 - max_drawdown × 0.2
```

其中：
- `win_rate` = qualified 中未破发数 / qualified 总数
- `expected_return` = qualified 样本的 first_day_return 均值（含所有样本，不仅仅是qualified的均值，而是将qualified收益求和除以全部样本数以反映覆盖率）
- `max_drawdown` = |min(0, qualified 中最差收益)|

目标函数系数可通过 `settings.OBJECTIVE_WEIGHTS` 配置：`{"win_rate": 0.4, "expected_return": 0.4, "max_drawdown": 0.2}`。

### 5.2 辅助诊断指标

| 指标 | 含义 |
|------|------|
| `sharpe_like` | expected_return / std(qualified_returns) |
| `ic_rank` | Spearman 秩相关（评分排序 vs 实际收益排序） |
| `break_rate` | 全体破发率（对照基准） |
| `coverage` | qualified 数量 / 全体数量 |
| `decile_returns` | 十分位收益分布，检验单调性 |

---

## 6. 贝叶斯优化器 (optimizer.py)

### 6.1 搜索空间

```
w_i ∈ [0.05, 0.80],  i ∈ {trade, fundamental, valuation, theme, data_quality}
Σw_i = 1.0
```

### 6.2 算法

使用 `scipy.optimize` + 自行实现约200行的 GP（高斯过程）+ EI（Expected Improvement），无需引入 Optuna/Botorch 等重型依赖。

**备选方案**：如 `scikit-optimize`（skopt）可用，优先使用其 `gp_minimize`。

### 6.3 流程

1. LHS 初始采样 20 组权重
2. 每组权重 → `engine.run()` → `metrics.objective()` → 目标值
3. GP 拟合 (weights, objective) 映射
4. EI 选择下一个最有希望的采样点
5. 迭代 30-50 轮直到收敛
6. 输出最优权重 → `optimized_weights.yaml`

### 6.4 过拟合防护

- **LOO 交叉验证**：object 计算时每次留一只 IPO 验证，取均值
- 可通过 `--no-cv` 关闭（样本量大时提速）
- GP 自动输出 posterior std，大不确定性时发出警告

### 6.5 optimized_weights.yaml 格式

```yaml
optimized_at: "2026-05-20T15:30:00"
sample_count: 31
cv_objective: 0.312          # LOO 交叉验证的目标值
weights:
  trade: 0.28
  fundamental: 0.32
  valuation: 0.22
  theme: 0.12
  data_quality: 0.06
default_objective: 0.245     # 默认权重的目标值（对照）
optimized_objective: 0.312
improvement_pct: 27.3        # 相对提升
```

---

## 7. CLI 设计 (cli.py)

```bash
# 回测（用当前默认权重或指定权重）
python -m ipo_analyzer.backtest run
python -m ipo_analyzer.backtest run --weights path/to/weights.yaml
python -m ipo_analyzer.backtest run --min-samples 5

# 优化（贝叶斯搜索最优权重）
python -m ipo_analyzer.backtest optimize
python -m ipo_analyzer.backtest optimize --iterations 50
python -m ipo_analyzer.backtest optimize --no-cv
python -m ipo_analyzer.backtest optimize --apply    # 自动写入配置生效

# 查看报告
python -m ipo_analyzer.backtest report              # 最近一次
python -m ipo_analyzer.backtest report --last        # 同上
python -m ipo_analyzer.backtest report --best        # 历史最优
python -m ipo_analyzer.backtest report --compare     # default vs optimized

# 状态查询
python -m ipo_analyzer.backtest status
```

---

## 8. scoring.py 集成

### 8.1 改动点

在 `ScoringSystem.calculate()` 的权重加载处增加：

```python
try:
    from ipo_analyzer.settings import OPTIMIZED_WEIGHTS_PATH
    import yaml
    with open(OPTIMIZED_WEIGHTS_PATH) as f:
        opt = yaml.safe_load(f)
    if opt and opt.get("weights"):
        weights = opt["weights"]
        logger.info("使用优化权重: %s", weights)
except FileNotFoundError:
    pass  # 文件不存在 → 使用默认权重
```

### 8.2 向后兼容

- `optimized_weights.yaml` 不存在 → 自动使用默认权重
- `optimized_weights.yaml` 存在但格式错误 → 记录警告，回退默认权重
- 不影响任何现有功能

---

## 9. 测试策略

### 9.1 测试文件

`tests/test_backtest.py`，独立于现有 255+ 测试。

### 9.2 测试用例

| 分类 | 用例 | 验证内容 |
|------|------|---------|
| collector | `test_collector_from_mock_results` | 从模拟JSON生成正确BacktestRecord |
| collector | `test_collector_filters_low_quality` | data_quality<2被排除 |
| collector | `test_collector_min_samples` | 样本不足时返回空+警告 |
| engine | `test_engine_basic_run` | 已知权重+数据，指标计算正确 |
| engine | `test_engine_decile_order` | 高评分分位收益>低评分分位收益 |
| metrics | `test_metrics_objective_calculation` | 目标函数值正确 |
| metrics | `test_metrics_ic_rank` | Spearman边界情况 |
| optimizer | `test_optimizer_converges` | 20条模拟数据，opt_obj > default_obj |
| optimizer | `test_optimizer_respects_sum_one` | 权重向量和≈1.0 |
| CLI | `test_cli_run_prints_report` | stdout包含关键指标 |
| CLI | `test_cli_optimize_writes_yaml` | optimized_weights.yaml正确生成 |
| integration | `test_scoring_loads_optimized_weights` | scoring.py正确读取 |
| integration | `test_scoring_falls_back_to_default` | 文件不存在时自动回退 |

---

## 10. 依赖

- **现有依赖**：pyyaml（已有）、aiosqlite（已有）
- **新增依赖**：scipy（贝叶斯优化的GP基础）— 或 skopt（scikit-optimize）
- **首选方案**：尝试 scipy.optimize + numpy 手写 GP（零新依赖），备选 skopt

---

## 11. 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| 样本量小导致过拟合 | LOO交叉验证；输出uncertainty区间；N<10不触发优化 |
| 优化权重与未来市场脱节 | 保留默认权重作为fallback；定期重新优化 |
| scoring.py集成引入bug | 仅try-except包装，核心逻辑不动；回退测试覆盖 |
| GP收敛慢或陷入局部最优 | LHS初始化+EI探索/利用平衡；多次运行对比 |

---

## 12. 未来扩展路径

- 阶段2（数据100+）：`--auto` 标志，分析完新股后触增量回测
- 阶段3（数据300+）：FastAPI端点 `/api/backtest/report` + 前端面板
- 阶段4（数据1000+）：A/B对比、滚动窗口回测、保荐人因子纳入评分
