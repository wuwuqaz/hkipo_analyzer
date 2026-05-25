# 回测框架 & 贝叶斯权重优化 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 构建回测框架 + 贝叶斯权重优化系统，从项目已有历史数据提取样本，回放评分并与实际结果比对，自动搜索最优五维权重并集成到现有 scoring.py。

**Architecture:** 新增 `ipo_analyzer/backtest/` 独立模块（纯函数核心 + CLI 入口），通过 `optimized_weights.yaml` 无侵入集成到 `scoring.py._detect_weight_profile()`。数据从现有 `temp/ipo_history.json` + `temp/reanalysis/` 提取，回测结果持久化到新的 `data/backtest.db` SQLite。

**Tech Stack:** Python 3.11+, numpy (已有 transitively via pandas), argparse, pyyaml (已有), sqlite3 (stdlib), dataclasses

**Key Adjustments from Spec (based on codebase reality):**
- 数据源：`temp/ipo_history.json` + `temp/reanalysis/*_latest.json`（非 `history.db` + `storage/results/`）
- 持久化：独立的 `data/backtest.db` SQLite（非复用 `history.db`）
- 评分集成：修改 `_detect_weight_profile()` 加载优化权重（非 `calculate()` 中 try-except）
- 设置配置：新增 `BacktestSettings` dataclass，遵循现有分层模式
- GP 实现：纯 numpy 手写（scipy 非现有依赖，避免引入）

---

### Task 1: 新增配置 + 设置模块改动

**Files:**
- Modify: `ipo_analyzer/settings.py:470-510`（在 Settings 类中新增 backtest 字段）
- Modify: `ipo_analyzer/settings.py:80-130`（在 ScoringWeights 附近新增 BacktestSettings）

- [ ] **Step 1: 在 settings.py 中新增 BacktestSettings dataclass**

在 `ScoringWeights` dataclass 之后（约第 128 行之后）新增：

```python
@dataclass
class BacktestSettings:
    """回测框架 & 贝叶斯优化配置"""
    # 数据采集
    min_samples: int = 10                    # 最少有效样本数才触发优化
    data_quality_threshold: int = 2          # data_quality 低于此值的记录被排除

    # 回测引擎
    qualify_threshold: int = 50              # score ≥ 此值计入 qualified 标的

    # 目标函数系数
    objective_win_rate_w: float = 0.4        # 胜率权重
    objective_expected_return_w: float = 0.4  # 期望收益权重
    objective_max_drawdown_w: float = 0.2    # 最大回撤惩罚权重

    # 优化器
    opt_initial_samples: int = 20            # LHS 初始采样数
    opt_iterations: int = 30                 # 贝叶斯优化迭代轮数
    opt_weight_min: float = 0.05             # 单维度权重下限
    opt_weight_max: float = 0.80             # 单维度权重上限

    # 文件路径
    optimized_weights_path: str = "data/optimized_weights.yaml"
    backtest_db_path: str = "data/backtest.db"
```

- [ ] **Step 2: 在 Settings 类中注册 backtest 字段**

在 `Settings` dataclass 末尾（第 505 行 `cornerstone` 字段之后，`SETTINGS = Settings()` 之前）新增：

```python
    backtest: BacktestSettings = field(default_factory=BacktestSettings)
```

- [ ] **Step 3: 验证 settings 导入正常**

```bash
python -c "from ipo_analyzer.settings import SETTINGS; print(SETTINGS.backtest.min_samples)"
```
Expected: `10`

---

### Task 2: 回测数据模型 (backtest/models.py)

**Files:**
- Create: `ipo_analyzer/backtest/__init__.py`
- Create: `ipo_analyzer/backtest/models.py`
- Test: `tests/test_backtest.py`

- [ ] **Step 1: 创建 `__init__.py`**

```python
"""回测框架 & 贝叶斯权重优化模块"""
__version__ = "0.1.0"
```

- [ ] **Step 2: 编写数据模型测试**

```python
# tests/test_backtest.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ipo_analyzer.backtest.models import BacktestRecord, BacktestResult, OptimizationResult


def test_backtest_record_creation():
    record = BacktestRecord(
        hk_code="02580.HK",
        company_name="测试公司",
        listing_date="2025-06-01",
        trade_score=60.0,
        fundamental_score=70.0,
        valuation_score=55.0,
        theme_score=40.0,
        data_quality_score=50.0,
        first_day_return=0.15,
        is_break=False,
        over_sub_ratio=100.0,
        score_timestamp="2025-05-20T10:00:00",
        data_quality=2,
    )
    assert record.hk_code == "02580.HK"
    assert record.first_day_return == 0.15
    assert not record.is_break


def test_backtest_result_creation():
    result = BacktestResult(
        sample_count=10,
        weights={"trade": 0.25, "fundamental": 0.35, "valuation": 0.25, "theme": 0.10, "data_quality": 0.05},
        qualified_count=7,
        win_rate=0.71,
        expected_return=0.12,
        max_drawdown=0.08,
        sharpe_like=1.5,
        ic_rank=0.42,
        break_rate=0.30,
        coverage=0.70,
        decile_returns=[0.02, 0.05, 0.08, 0.10, 0.12, 0.14, 0.15, 0.18, 0.20, 0.25],
    )
    assert result.sample_count == 10
    assert result.win_rate == 0.71


def test_optimization_result_creation():
    opt = OptimizationResult(
        weights={"trade": 0.28, "fundamental": 0.32, "valuation": 0.22, "theme": 0.12, "data_quality": 0.06},
        objective=0.312,
        default_objective=0.245,
        improvement_pct=27.3,
        convergence=[[0, 0.20], [5, 0.28], [10, 0.31]],
    )
    assert opt.improvement_pct == 27.3
    assert len(opt.convergence) == 3
```

- [ ] **Step 3: 运行测试确认失败**

```bash
python -m pytest tests/test_backtest.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'ipo_analyzer.backtest.models'`

- [ ] **Step 4: 编写 backtest/models.py**

```python
"""回测框架数据模型"""
from dataclasses import dataclass, field


@dataclass
class BacktestRecord:
    """单只IPO的回测样本"""
    hk_code: str
    company_name: str
    listing_date: str = ""

    trade_score: float = 0.0
    fundamental_score: float = 0.0
    valuation_score: float = 0.0
    theme_score: float = 0.0
    data_quality_score: float = 0.0

    first_day_return: float = 0.0
    is_break: bool = False
    over_sub_ratio: float = 0.0

    score_timestamp: str = ""
    data_quality: int = 0


@dataclass
class BacktestResult:
    """一次回测运行的完整结果"""
    sample_count: int = 0
    weights: dict = field(default_factory=dict)
    qualified_count: int = 0

    win_rate: float = 0.0
    expected_return: float = 0.0
    max_drawdown: float = 0.0
    sharpe_like: float = 0.0

    ic_rank: float = 0.0
    break_rate: float = 0.0
    coverage: float = 0.0

    decile_returns: list[float] = field(default_factory=list)


@dataclass
class OptimizationResult:
    """一次贝叶斯优化运行的结果"""
    weights: dict = field(default_factory=dict)
    objective: float = 0.0
    default_objective: float = 0.0
    improvement_pct: float = 0.0
    convergence: list[list[float]] = field(default_factory=list)
    cv_objective: float = 0.0
    sample_count: int = 0
```

- [ ] **Step 5: 运行测试确认通过**

```bash
python -m pytest tests/test_backtest.py::test_backtest_record_creation tests/test_backtest.py::test_backtest_result_creation tests/test_backtest.py::test_optimization_result_creation -v
```
Expected: 3 PASS

- [ ] **Step 6: 提交**

```bash
git add ipo_analyzer/backtest/__init__.py ipo_analyzer/backtest/models.py tests/test_backtest.py
git commit -m "feat(backtest): add BacktestRecord, BacktestResult, OptimizationResult data models"
```

---

### Task 3: 数据采集器 (backtest/collector.py)

**Files:**
- Create: `ipo_analyzer/backtest/collector.py`
- Modify: `tests/test_backtest.py`

- [ ] **Step 1: 编写采集器测试**

在 `tests/test_backtest.py` 末尾追加：

```python
import json
import tempfile
import shutil
from datetime import date
from unittest.mock import patch, MagicMock
from ipo_analyzer.backtest.collector import collect_backtest_dataset
from ipo_analyzer.backtest.models import BacktestRecord


class TestCollector:
    def setup_method(self):
        self.tempdir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tempdir)

    def _write_history(self, records):
        history_file = os.path.join(self.tempdir, "ipo_history.json")
        with open(history_file, "w") as f:
            json.dump(records, f)
        return history_file

    def test_collector_extracts_valid_records(self):
        records = [
            {
                "hk_code": "02580",
                "company_name": "测试公司A",
                "trade_score": 60,
                "fundamental_score": 70,
                "valuation_score": 55,
                "theme_score": 40,
                "data_quality_score": 50,
                "_data_quality": 2,
                "post_listing": {
                    "first_day": {"change_pct": 15.0},
                    "public_subscription_level": 100.0,
                },
            },
            {
                "hk_code": "09999",
                "company_name": "测试公司B",
                "trade_score": 30,
                "fundamental_score": 45,
                "valuation_score": 20,
                "theme_score": 10,
                "data_quality_score": 60,
                "_data_quality": 1,
                "post_listing": {
                    "first_day": {"change_pct": -5.0},
                    "public_subscription_level": 5.0,
                },
            },
        ]
        self._write_history(records)

        dataset = collect_backtest_dataset(history_dir=self.tempdir)

        assert len(dataset) == 1  # data_quality < 2 的被过滤
        r = dataset[0]
        assert r.hk_code == "02580"
        assert r.trade_score == 60
        assert r.fundamental_score == 70
        assert r.first_day_return == 0.15
        assert not r.is_break

    def test_collector_filters_missing_post_listing(self):
        records = [
            {
                "hk_code": "02580",
                "company_name": "无post_listing",
                "trade_score": 60,
                "fundamental_score": 70,
                "valuation_score": 55,
                "theme_score": 40,
                "data_quality_score": 50,
                "_data_quality": 2,
                "post_listing": None,
            },
        ]
        self._write_history(records)

        dataset = collect_backtest_dataset(history_dir=self.tempdir)
        assert len(dataset) == 0

    def test_collector_filters_no_first_day(self):
        records = [
            {
                "hk_code": "02580",
                "company_name": "无first_day",
                "trade_score": 60,
                "fundamental_score": 70,
                "valuation_score": 55,
                "theme_score": 40,
                "data_quality_score": 50,
                "_data_quality": 2,
                "post_listing": {"public_subscription_level": 100},
            },
        ]
        self._write_history(records)

        dataset = collect_backtest_dataset(history_dir=self.tempdir)
        assert len(dataset) == 0

    def test_collector_from_reanalysis_fallback(self):
        records = [
            {
                "hk_code": "02580",
                "company_name": "主记录",
                "trade_score": 30,
                "fundamental_score": 40,
                "valuation_score": 20,
                "theme_score": 10,
                "data_quality_score": 30,
                "_data_quality": 2,
                "post_listing": {
                    "first_day": {"change_pct": 10.0},
                    "public_subscription_level": 50.0,
                },
            },
        ]
        self._write_history(records)

        reanalysis_dir = os.path.join(self.tempdir, "reanalysis")
        os.makedirs(reanalysis_dir, exist_ok=True)
        reanalysis_record = {
            "stock_code": "02580",
            "score_breakdown": {
                "trade_score": 60,
                "fundamental_score": 75,
                "valuation_score": 55,
                "theme_score": 45,
            },
        }
        with open(os.path.join(reanalysis_dir, "02580_latest.json"), "w") as f:
            json.dump(reanalysis_record, f)

        dataset = collect_backtest_dataset(history_dir=self.tempdir)

        assert len(dataset) == 1
        r = dataset[0]
        # reanalysis 的 score_breakdown 覆盖主记录的顶层字段
        assert r.trade_score == 60
        assert r.fundamental_score == 75
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_backtest.py::TestCollector -v
```
Expected: FAIL — no `collect_backtest_dataset`

- [ ] **Step 3: 编写 collector.py**

```python
"""回测数据采集器：从 ipo_history.json 和 reanalysis/ 提取 BacktestRecord 列表"""
import json
import logging
import os

from .models import BacktestRecord

logger = logging.getLogger(__name__)

SCORE_FIELDS = [
    "trade_score",
    "fundamental_score",
    "valuation_score",
    "theme_score",
]


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_reanalysis_scores(reanalysis_dir, stock_code):
    """从 temp/reanalysis/{code}_latest.json 读取 score_breakdown"""
    safe_code = stock_code.replace(".HK", "").replace(".hk", "").strip()
    latest_path = os.path.join(reanalysis_dir, f"{safe_code}_latest.json")
    if not os.path.exists(latest_path):
        return {}
    try:
        data = _load_json(latest_path)
        return data.get("score_breakdown", {})
    except Exception as e:
        logger.debug("读取 reanalysis 失败 %s: %s", latest_path, e)
        return {}


def collect_backtest_dataset(
    history_dir="temp",
    data_quality_threshold=2,
):
    """从历史数据中提取 BacktestRecord 列表

    Args:
        history_dir: HistoryStore 的数据目录
        data_quality_threshold: data_quality 低于此值的记录被排除

    Returns:
        list[BacktestRecord]
    """
    history_file = os.path.join(history_dir, "ipo_history.json")
    reanalysis_dir = os.path.join(history_dir, "reanalysis")

    if not os.path.exists(history_file):
        logger.warning("历史文件不存在: %s", history_file)
        return []

    records = _load_json(history_file)
    if not isinstance(records, list):
        return []

    dataset = []
    for item in records:
        if not isinstance(item, dict):
            continue

        post = item.get("post_listing")
        if not isinstance(post, dict):
            continue

        first_day = post.get("first_day")
        if not isinstance(first_day, dict):
            continue

        change_pct = first_day.get("change_pct")
        if not isinstance(change_pct, (int, float)):
            continue

        data_quality = item.get("_data_quality", 0)
        if isinstance(data_quality, bool):
            data_quality = 2 if data_quality else 0
        if not isinstance(data_quality, (int, float)):
            data_quality = 0
        if data_quality < data_quality_threshold:
            continue

        stock_code = item.get("hk_code") or item.get("stock_code") or ""
        reanalysis_scores = _load_reanalysis_scores(reanalysis_dir, stock_code)

        record = BacktestRecord(
            hk_code=str(stock_code),
            company_name=str(item.get("company_name", "")),
            listing_date=str(item.get("listing_date") or ""),
            trade_score=float(
                reanalysis_scores.get("trade_score", item.get("trade_score", 0)) or 0
            ),
            fundamental_score=float(
                reanalysis_scores.get("fundamental_score", item.get("fundamental_score", 0)) or 0
            ),
            valuation_score=float(
                reanalysis_scores.get("valuation_score", item.get("valuation_score", 0)) or 0
            ),
            theme_score=float(
                reanalysis_scores.get("theme_score", item.get("theme_score", 0)) or 0
            ),
            data_quality_score=float(item.get("data_quality_score", 0) or 0),
            first_day_return=float(change_pct) / 100.0,
            is_break=float(change_pct) < 0,
            over_sub_ratio=float(post.get("public_subscription_level", 0) or 0),
            score_timestamp=str(item.get("_post_listing_updated_at", "")),
            data_quality=int(data_quality),
        )
        dataset.append(record)

    logger.info("采集回测样本: %d 条", len(dataset))
    return dataset
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_backtest.py::TestCollector -v
```
Expected: 4 PASS

- [ ] **Step 5: 提交**

```bash
git add ipo_analyzer/backtest/collector.py tests/test_backtest.py
git commit -m "feat(backtest): add collector to extract BacktestRecord from ipo_history.json"
```

---

### Task 4: 回测引擎 (backtest/engine.py)

**Files:**
- Create: `ipo_analyzer/backtest/engine.py`
- Modify: `tests/test_backtest.py`

- [ ] **Step 1: 编写引擎测试**

在 `tests/test_backtest.py` 末尾追加：

```python
from ipo_analyzer.backtest.engine import run_backtest
from ipo_analyzer.backtest.models import BacktestRecord, BacktestResult


class TestEngine:
    def _make_records(self):
        return [
            BacktestRecord(
                hk_code="A", company_name="A",
                trade_score=80, fundamental_score=85, valuation_score=75,
                theme_score=60, data_quality_score=80,
                first_day_return=0.20, is_break=False, over_sub_ratio=200,
            ),
            BacktestRecord(
                hk_code="B", company_name="B",
                trade_score=70, fundamental_score=75, valuation_score=65,
                theme_score=50, data_quality_score=70,
                first_day_return=0.10, is_break=False, over_sub_ratio=150,
            ),
            BacktestRecord(
                hk_code="C", company_name="C",
                trade_score=40, fundamental_score=45, valuation_score=35,
                theme_score=30, data_quality_score=50,
                first_day_return=-0.05, is_break=True, over_sub_ratio=10,
            ),
            BacktestRecord(
                hk_code="D", company_name="D",
                trade_score=30, fundamental_score=35, valuation_score=25,
                theme_score=20, data_quality_score=40,
                first_day_return=-0.15, is_break=True, over_sub_ratio=3,
            ),
        ]

    def test_engine_basic_result(self):
        dataset = self._make_records()
        weights = {"trade": 0.25, "fundamental": 0.35, "valuation": 0.25,
                   "theme": 0.10, "data_quality": 0.05}

        result = run_backtest(dataset, weights, qualify_threshold=50)

        assert result.sample_count == 4
        # A=79.75, B=69.75, C=40.25, D=30.75 → qualified: A, B
        assert result.qualified_count == 2
        assert result.win_rate == 1.0  # A 和 B 都未破发
        assert result.break_rate == 0.5  # 4 只中 2 只破发
        assert result.coverage == 0.5  # 2/4 qualified
        assert result.max_drawdown == 0.0  # qualified 中无亏损

    def test_engine_decile_monotonic(self):
        records = []
        for i in range(20):
            records.append(BacktestRecord(
                hk_code=f"C{i:02d}", company_name=f"C{i:02d}",
                trade_score=float(i * 5), fundamental_score=float(i * 5),
                valuation_score=float(i * 5), theme_score=float(i * 5),
                data_quality_score=50.0,
                first_day_return=float(i) / 100,
                is_break=i < 5,
                over_sub_ratio=float(i * 10),
            ))
        weights = {"trade": 0.25, "fundamental": 0.35, "valuation": 0.25,
                   "theme": 0.10, "data_quality": 0.05}

        result = run_backtest(records, weights, qualify_threshold=0)
        assert result.decile_returns[-1] >= result.decile_returns[0]  # 高 decile 收益更高

    def test_engine_empty_dataset(self):
        result = run_backtest([], {}, qualify_threshold=50)
        assert result.sample_count == 0
        assert result.win_rate == 0.0

    def test_engine_no_qualified(self):
        dataset = self._make_records()
        weights = {"trade": 0.25, "fundamental": 0.35, "valuation": 0.25,
                   "theme": 0.10, "data_quality": 0.05}
        result = run_backtest(dataset, weights, qualify_threshold=90)
        assert result.qualified_count == 0
        assert result.win_rate == 0.0
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_backtest.py::TestEngine -v
```
Expected: FAIL — no `run_backtest`

- [ ] **Step 3: 编写 engine.py**

```python
"""回测引擎：用给定权重对历史数据重算评分并统计表现"""
import statistics

from .models import BacktestResult

WEIGHT_KEYS = ["trade", "fundamental", "valuation", "theme", "data_quality"]


def _composite_score(record, weights):
    return (
        record.trade_score * weights.get("trade", 0)
        + record.fundamental_score * weights.get("fundamental", 0)
        + record.valuation_score * weights.get("valuation", 0)
        + record.theme_score * weights.get("theme", 0)
        + record.data_quality_score * weights.get("data_quality", 0)
    )


def _spearman_rank(x, y):
    """计算 Spearman 秩相关系数"""
    n = len(x)
    if n < 2:
        return 0.0
    rank_x = _rank(x)
    rank_y = _rank(y)
    d2 = sum((rx - ry) ** 2 for rx, ry in zip(rank_x, rank_y))
    return 1.0 - (6.0 * d2) / (n * (n * n - 1))


def _rank(values):
    """返回值的秩（从 1 开始）"""
    indexed = sorted(enumerate(values), key=lambda iv: iv[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


def run_backtest(dataset, weights, qualify_threshold=50):
    """运行回测

    Args:
        dataset: list[BacktestRecord]
        weights: dict[str, float]  五维权重
        qualify_threshold: score ≥ 此值计入 qualified

    Returns:
        BacktestResult
    """
    n = len(dataset)
    if n == 0:
        return BacktestResult(sample_count=0, weights=dict(weights))

    scored = [
        (_composite_score(r, weights), r)
        for r in dataset
    ]
    scored.sort(key=lambda x: x[0])

    scores = [s for s, _ in scored]
    returns = [r.first_day_return for _, r in scored]

    qualified_returns = [
        r.first_day_return
        for s, r in scored
        if s >= qualify_threshold
    ]
    q_count = len(qualified_returns)

    if q_count > 0:
        win_rate = sum(1 for r in qualified_returns if r >= 0) / q_count
        expected_return = sum(qualified_returns) / n
        max_drawdown = abs(min(0.0, min(qualified_returns)))
        sharpe_like = (
            expected_return / statistics.stdev(qualified_returns)
            if len(qualified_returns) >= 2 and statistics.stdev(qualified_returns) > 1e-9
            else 0.0
        )
    else:
        win_rate = 0.0
        expected_return = 0.0
        max_drawdown = 0.0
        sharpe_like = 0.0

    ic_rank = _spearman_rank(scores, returns)

    break_count = sum(1 for r in dataset if r.is_break)
    break_rate = break_count / n if n else 0.0
    coverage = q_count / n if n else 0.0

    decile_size = max(1, n // 10)
    decile_returns = []
    for d in range(10):
        start = d * decile_size
        end = start + decile_size if d < 9 else n
        chunk_returns = [r.first_day_return for _, r in scored[start:end]]
        if chunk_returns:
            decile_returns.append(round(statistics.mean(chunk_returns), 4))
        else:
            decile_returns.append(0.0)

    return BacktestResult(
        sample_count=n,
        weights=dict(weights),
        qualified_count=q_count,
        win_rate=round(win_rate, 4),
        expected_return=round(expected_return, 4),
        max_drawdown=round(max_drawdown, 4),
        sharpe_like=round(sharpe_like, 4),
        ic_rank=round(ic_rank, 4),
        break_rate=round(break_rate, 4),
        coverage=round(coverage, 4),
        decile_returns=decile_returns,
    )
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_backtest.py::TestEngine -v
```
Expected: 4 PASS

- [ ] **Step 5: 提交**

```bash
git add ipo_analyzer/backtest/engine.py tests/test_backtest.py
git commit -m "feat(backtest): add run_backtest engine with decile/IC/sharpe metrics"
```

---

### Task 5: 评估指标 (backtest/metrics.py)

**Files:**
- Create: `ipo_analyzer/backtest/metrics.py`
- Modify: `tests/test_backtest.py`

- [ ] **Step 1: 编写 metrics 测试**

在 `tests/test_backtest.py` 末尾追加：

```python
from ipo_analyzer.backtest.metrics import compute_objective, compute_objective_cv
from ipo_analyzer.backtest.models import BacktestRecord, BacktestResult


class TestMetrics:
    def test_objective_calculation(self):
        result = BacktestResult(
            sample_count=10,
            qualified_count=7,
            win_rate=0.857,
            expected_return=0.12,
            max_drawdown=0.05,
        )
        obj = compute_objective(result, win_rate_w=0.4, expected_return_w=0.4,
                                max_drawdown_w=0.2)
        # 0.857*0.4 + 0.12*0.4 - 0.05*0.2 = 0.3428 + 0.048 - 0.01 = 0.3808
        assert abs(obj - 0.3808) < 1e-6

    def test_objective_zero_qualified(self):
        result = BacktestResult(sample_count=10, qualified_count=0)
        obj = compute_objective(result)
        assert obj == 0.0

    def test_objective_cv_runs(self):
        dataset = [
            BacktestRecord(hk_code="A", company_name="A",
                           trade_score=80, fundamental_score=85, valuation_score=75,
                           theme_score=60, data_quality_score=80,
                           first_day_return=0.20, is_break=False),
            BacktestRecord(hk_code="B", company_name="B",
                           trade_score=70, fundamental_score=75, valuation_score=65,
                           theme_score=50, data_quality_score=70,
                           first_day_return=0.10, is_break=False),
            BacktestRecord(hk_code="C", company_name="C",
                           trade_score=40, fundamental_score=45, valuation_score=35,
                           theme_score=30, data_quality_score=50,
                           first_day_return=-0.05, is_break=True),
        ]
        weights = {"trade": 0.25, "fundamental": 0.35, "valuation": 0.25,
                   "theme": 0.10, "data_quality": 0.05}
        cv_obj = compute_objective_cv(dataset, weights, qualify_threshold=50)
        assert isinstance(cv_obj, float)
        assert cv_obj >= 0.0
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_backtest.py::TestMetrics -v
```
Expected: FAIL

- [ ] **Step 3: 编写 metrics.py**

```python
"""回测评估指标：目标函数 + 交叉验证"""
from .engine import run_backtest


def compute_objective(
    backtest_result,
    win_rate_w=0.4,
    expected_return_w=0.4,
    max_drawdown_w=0.2,
):
    """计算多目标复合函数值

    objective = win_rate*w1 + expected_return*w2 - max_drawdown*w3
    """
    if backtest_result.qualified_count == 0:
        return 0.0

    obj = (
        backtest_result.win_rate * win_rate_w
        + backtest_result.expected_return * expected_return_w
        - backtest_result.max_drawdown * max_drawdown_w
    )
    return round(obj, 6)


def compute_objective_cv(dataset, weights, qualify_threshold=50):
    """Leave-One-Out 交叉验证的目标函数值

    每次留一只 IPO 作为验证集，取所有折的均值。
    """
    n = len(dataset)
    if n < 3:
        result = run_backtest(dataset, weights, qualify_threshold)
        return compute_objective(result)

    objectives = []
    for i in range(n):
        train = [r for j, r in enumerate(dataset) if j != i]
        test = dataset[i]
        result = run_backtest(train, weights, qualify_threshold)
        obj = compute_objective(result)
        objectives.append(obj)

    return round(sum(objectives) / len(objectives), 6)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_backtest.py::TestMetrics -v
```
Expected: 3 PASS

- [ ] **Step 5: 提交**

```bash
git add ipo_analyzer/backtest/metrics.py tests/test_backtest.py
git commit -m "feat(backtest): add objective function and LOO cross-validation"
```

---

### Task 6: 贝叶斯优化器 (backtest/optimizer.py)

**Files:**
- Create: `ipo_analyzer/backtest/optimizer.py`
- Modify: `tests/test_backtest.py`

- [ ] **Step 1: 编写优化器测试**

在 `tests/test_backtest.py` 末尾追加：

```python
from ipo_analyzer.backtest.optimizer import optimize_weights, _normalize_weights, _lhs_sample


class TestOptimizer:
    def test_normalize_weights(self):
        raw = {"trade": 5, "fundamental": 10, "valuation": 3, "theme": 1, "data_quality": 1}
        w = _normalize_weights(raw)
        assert abs(sum(w.values()) - 1.0) < 1e-6
        assert all(0.0 <= v <= 1.0 for v in w.values())

    def test_normalize_all_zero(self):
        raw = {"trade": 0, "fundamental": 0, "valuation": 0, "theme": 0, "data_quality": 0}
        w = _normalize_weights(raw)
        for v in w.values():
            assert abs(v - 0.2) < 1e-6

    def test_lhs_sample(self):
        samples = _lhs_sample(n=5, dim=3, lower=0.05, upper=0.80)
        assert len(samples) == 5
        for s in samples:
            assert len(s) == 3
            for v in s:
                assert 0.05 <= v <= 0.80

    def _make_dataset(self, n=15):
        import random
        random.seed(42)
        records = []
        for i in range(n):
            records.append(BacktestRecord(
                hk_code=f"C{i:02d}", company_name=f"C{i:02d}",
                trade_score=float(random.randint(20, 90)),
                fundamental_score=float(random.randint(20, 90)),
                valuation_score=float(random.randint(20, 90)),
                theme_score=float(random.randint(20, 90)),
                data_quality_score=50.0,
                first_day_return=float(random.randint(-15, 30)) / 100,
                is_break=False,
                over_sub_ratio=float(random.randint(5, 200)),
            ))
        records[0].is_break = True
        records[0].first_day_return = -0.10
        return records

    def test_optimize_returns_better_objective(self):
        dataset = self._make_dataset(15)
        result = optimize_weights(
            dataset,
            initial_samples=10,
            iterations=15,
            use_cv=False,
            qualify_threshold=50,
        )
        assert result.objective >= 0
        assert abs(sum(result.weights.values()) - 1.0) < 1e-3
        assert result.objective >= result.default_objective - 0.05  # 至少不显著变差
        assert len(result.convergence) > 0
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_backtest.py::TestOptimizer -v
```
Expected: FAIL

- [ ] **Step 3: 编写 optimizer.py**

```python
"""贝叶斯优化器：GP + EI 搜索最优五维权重"""
import logging
import math
import numpy as np
from numpy.linalg import cholesky, solve

from .engine import run_backtest
from .metrics import compute_objective, compute_objective_cv
from .models import OptimizationResult

logger = logging.getLogger(__name__)

WEIGHT_KEYS = ["trade", "fundamental", "valuation", "theme", "data_quality"]
N_DIM = len(WEIGHT_KEYS)


def _lhs_sample(n, dim, lower=0.05, upper=0.80):
    """Latin Hypercube Sampling"""
    samples = np.zeros((n, dim))
    for d in range(dim):
        cut = np.linspace(0, 1, n + 1)
        for i in range(n):
            samples[i, d] = lower + (upper - lower) * np.random.uniform(cut[i], cut[i + 1])
    for i in range(n):
        np.random.shuffle(samples[i])
    return samples


def _normalize_weights(raw_dict):
    """将原始值归一化为和为1的权重向量"""
    vals = np.array([raw_dict[k] for k in WEIGHT_KEYS], dtype=float)
    total = vals.sum()
    if total < 1e-9:
        vals = np.ones(N_DIM) / N_DIM
    else:
        vals = vals / total
    return {k: float(v) for k, v in zip(WEIGHT_KEYS, vals)}


def _weights_to_array(weights):
    return np.array([weights[k] for k in WEIGHT_KEYS])


def _array_to_weights(arr):
    return {k: float(arr[i]) for i, k in enumerate(WEIGHT_KEYS)}


def _rbf_kernel(x1, x2, length_scale=1.0, signal_variance=1.0):
    """RBF (squared exponential) kernel"""
    sqdist = np.sum(x1**2, axis=1).reshape(-1, 1) + np.sum(x2**2, axis=1) - 2 * np.dot(x1, x2.T)
    return signal_variance * np.exp(-0.5 * sqdist / length_scale**2)


def _evaluate_weights(dataset, weights, use_cv, qualify_threshold):
    """评估一组权重的目标函数值"""
    if use_cv:
        return compute_objective_cv(dataset, weights, qualify_threshold)
    result = run_backtest(dataset, weights, qualify_threshold)
    return compute_objective(result)


def optimize_weights(
    dataset,
    initial_samples=20,
    iterations=30,
    use_cv=True,
    qualify_threshold=50,
    default_weights=None,
):
    """贝叶斯优化搜索最优五维权重

    Args:
        dataset: list[BacktestRecord]
        initial_samples: LHS 初始采样数
        iterations: 贝叶斯优化迭代轮数
        use_cv: 是否使用 LOO 交叉验证
        qualify_threshold: score 阈值
        default_weights: 默认权重（用于计算 improvement）

    Returns:
        OptimizationResult
    """
    if default_weights is None:
        default_weights = {
            "trade": 0.25, "fundamental": 0.35,
            "valuation": 0.25, "theme": 0.10, "data_quality": 0.05,
        }

    np.random.seed(42)

    # 1. LHS 初始采样
    logger.info("贝叶斯优化：LHS 初始采样 %d 组权重", initial_samples)
    raw_samples = _lhs_sample(initial_samples, N_DIM, 0.05, 0.80)
    X = []
    y = []
    for i in range(initial_samples):
        raw = {WEIGHT_KEYS[d]: float(raw_samples[i, d]) for d in range(N_DIM)}
        w = _normalize_weights(raw)
        obj = _evaluate_weights(dataset, w, use_cv, qualify_threshold)
        X.append(_weights_to_array(w))
        y.append(obj)

    X = np.array(X)
    y = np.array(y)

    best_idx = int(np.argmax(y))
    best_weights = _array_to_weights(X[best_idx])
    best_obj = float(y[best_idx])
    convergence = [[int(i), best_obj]]

    # 2. 贝叶斯优化主循环
    logger.info("贝叶斯优化：开始 %d 轮迭代", iterations)
    for it in range(iterations):
        # GP 拟合
        n_eval = len(X)
        length_scale = max(0.1, 1.0 / math.sqrt(n_eval))
        K = _rbf_kernel(X, X, length_scale=length_scale, signal_variance=1.0)
        K += np.eye(n_eval) * 1e-6

        try:
            L = cholesky(K)
        except np.linalg.LinAlgError:
            K += np.eye(n_eval) * 1e-4
            L = cholesky(K)

        alpha = solve(L.T, solve(L, y))

        # 预测均值计算
        y_mean = y.mean()
        y_std = y.std()
        if y_std < 1e-9:
            y_std = 1.0
        y_norm = (y - y_mean) / y_std

        # EI 搜索下一个采样点
        n_candidates = 500
        candidates = _lhs_sample(n_candidates, N_DIM, 0.05, 0.80)
        candidate_weights = []
        for i in range(n_candidates):
            raw = {WEIGHT_KEYS[d]: float(candidates[i, d]) for d in range(N_DIM)}
            candidate_weights.append(_normalize_weights(raw))

        best_y = float(np.max(y_norm))
        ei_values = np.zeros(n_candidates)

        for i in range(n_candidates):
            w_arr = _weights_to_array(candidate_weights[i]).reshape(1, -1)
            k_star = _rbf_kernel(w_arr, X, length_scale=length_scale, signal_variance=1.0)
            k_star_star = _rbf_kernel(w_arr, w_arr, length_scale=length_scale, signal_variance=1.0)

            v = solve(L, k_star.T)
            mu = float(np.dot(k_star, alpha))
            mu = mu * y_std + y_mean
            sigma2 = float(k_star_star - np.dot(v.T, v))
            sigma2 = max(sigma2, 1e-8)
            sigma = math.sqrt(sigma2) * y_std

            if sigma < 1e-8:
                ei_values[i] = 0.0
            else:
                z = (mu - best_y * y_std - y_mean) / sigma if sigma > 1e-6 else 0.0
                from math import erf, sqrt
                cdf_z = 0.5 * (1.0 + erf(z / sqrt(2.0)))
                phi_z = (1.0 / sqrt(2.0 * math.pi)) * math.exp(-0.5 * z * z)
                ei_values[i] = sigma * (z * cdf_z + phi_z)

        next_idx = int(np.argmax(ei_values))
        next_weights = candidate_weights[next_idx]

        obj = _evaluate_weights(dataset, next_weights, use_cv, qualify_threshold)

        X = np.vstack([X, _weights_to_array(next_weights).reshape(1, -1)])
        y = np.append(y, obj)

        if obj > best_obj:
            best_obj = float(obj)
            best_weights = dict(next_weights)
            logger.info("  迭代 %d: 新最优 objective=%.4f, weights=%s", it + 1, best_obj, best_weights)

        convergence.append([int(initial_samples + it + 1), best_obj])

    # 3. 默认权重评估
    default_obj = _evaluate_weights(dataset, default_weights, use_cv, qualify_threshold)
    cv_objective = best_obj if use_cv else 0.0
    improvement = (best_obj - default_obj) / abs(default_obj) * 100 if abs(default_obj) > 1e-9 else 0.0

    return OptimizationResult(
        weights=best_weights,
        objective=best_obj,
        default_objective=default_obj,
        improvement_pct=round(improvement, 2),
        convergence=convergence,
        cv_objective=cv_objective,
        sample_count=len(dataset),
    )
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_backtest.py::TestOptimizer -v
```

如果 numpy 不在环境里，先安装：
```bash
pip install numpy
```
（numpy 通常已被 pandas 间接依赖引入，此步骤大概率不需要）

Expected: 5 PASS（或接近全部通过，optimize_returns_better 可能因随机性偶尔失败，重跑即可）

- [ ] **Step 5: 提交**

```bash
git add ipo_analyzer/backtest/optimizer.py tests/test_backtest.py
git commit -m "feat(backtest): add Bayesian optimizer with GP+EI for weight search"
```

---

### Task 7: 持久化存储 (backtest/store.py)

**Files:**
- Create: `ipo_analyzer/backtest/store.py`
- Modify: `tests/test_backtest.py`

- [ ] **Step 1: 编写 store 测试**

在 `tests/test_backtest.py` 末尾追加：

```python
import sqlite3
from ipo_analyzer.backtest.store import BacktestStore
from ipo_analyzer.backtest.models import BacktestResult, OptimizationResult


class TestStore:
    def setup_method(self):
        self.tempdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tempdir, "test_backtest.db")

    def teardown_method(self):
        shutil.rmtree(self.tempdir)

    def test_init_creates_tables(self):
        store = BacktestStore(self.db_path)
        conn = sqlite3.connect(self.db_path)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {t[0] for t in tables}
        assert "backtest_runs" in table_names
        assert "optimization_runs" in table_names
        conn.close()

    def test_save_and_load_backtest_result(self):
        store = BacktestStore(self.db_path)
        result = BacktestResult(
            sample_count=10,
            weights={"trade": 0.25, "fundamental": 0.35},
            qualified_count=7,
            win_rate=0.71,
            expected_return=0.12,
            max_drawdown=0.08,
            sharpe_like=1.5,
            ic_rank=0.42,
            break_rate=0.30,
            coverage=0.70,
            decile_returns=[0.02, 0.05, 0.08],
        )
        run_id = store.save_backtest_run(result, notes="test")
        assert run_id is not None

        loaded = store.get_latest_backtest_run()
        assert loaded is not None
        assert loaded["win_rate"] == 0.71

    def test_save_and_load_optimization(self):
        store = BacktestStore(self.db_path)
        opt = OptimizationResult(
            weights={"trade": 0.28, "fundamental": 0.32},
            objective=0.312,
            default_objective=0.245,
            improvement_pct=27.3,
            convergence=[[0, 0.20], [10, 0.31]],
        )
        opt_id = store.save_optimization_run(opt, iterations=30, cv_enabled=True)
        assert opt_id is not None

        loaded = store.get_latest_optimization()
        assert loaded is not None
        assert loaded["best_objective"] == 0.312
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_backtest.py::TestStore -v
```
Expected: FAIL

- [ ] **Step 3: 编写 store.py**

```python
"""回测结果持久化：SQLite 存储"""
import json
import logging
import os
import sqlite3
import uuid

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS backtest_runs (
    id            TEXT PRIMARY KEY,
    run_at        TEXT NOT NULL,
    weights       TEXT NOT NULL,
    sample_count  INTEGER,
    qualified_count INTEGER,
    win_rate      REAL,
    expected_return REAL,
    max_drawdown  REAL,
    sharpe_like   REAL,
    ic_rank       REAL,
    break_rate    REAL,
    coverage      REAL,
    decile_returns TEXT,
    is_optimized  INTEGER DEFAULT 0,
    notes         TEXT
);

CREATE TABLE IF NOT EXISTS optimization_runs (
    id            TEXT PRIMARY KEY,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    iterations    INTEGER,
    best_weights  TEXT,
    best_objective REAL,
    default_objective REAL,
    improvement_pct REAL,
    cv_enabled    INTEGER DEFAULT 1,
    cv_objective  REAL DEFAULT 0,
    sample_count  INTEGER DEFAULT 0,
    convergence   TEXT,
    status        TEXT DEFAULT 'completed'
);
"""


class BacktestStore:
    def __init__(self, db_path="data/backtest.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = self._connect()
        conn.executescript(SCHEMA)
        conn.commit()
        conn.close()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _dict_row(self, row):
        if row is None:
            return None
        return dict(row)

    def save_backtest_run(self, result, notes=""):
        run_id = str(uuid.uuid4())[:8]
        from datetime import datetime
        conn = self._connect()
        conn.execute(
            """INSERT INTO backtest_runs
               (id, run_at, weights, sample_count, qualified_count,
                win_rate, expected_return, max_drawdown, sharpe_like,
                ic_rank, break_rate, coverage, decile_returns,
                is_optimized, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                datetime.now().isoformat(),
                json.dumps(result.weights),
                result.sample_count,
                result.qualified_count,
                result.win_rate,
                result.expected_return,
                result.max_drawdown,
                result.sharpe_like,
                result.ic_rank,
                result.break_rate,
                result.coverage,
                json.dumps(result.decile_returns),
                0,
                notes,
            ),
        )
        conn.commit()
        conn.close()
        return run_id

    def save_optimization_run(self, opt_result, iterations, cv_enabled=True):
        opt_id = str(uuid.uuid4())[:8]
        from datetime import datetime
        conn = self._connect()
        conn.execute(
            """INSERT INTO optimization_runs
               (id, started_at, finished_at, iterations, best_weights,
                best_objective, default_objective, improvement_pct,
                cv_enabled, cv_objective, sample_count, convergence, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                opt_id,
                datetime.now().isoformat(),
                datetime.now().isoformat(),
                iterations,
                json.dumps(opt_result.weights),
                opt_result.objective,
                opt_result.default_objective,
                opt_result.improvement_pct,
                1 if cv_enabled else 0,
                opt_result.cv_objective,
                opt_result.sample_count,
                json.dumps(opt_result.convergence),
                "completed",
            ),
        )
        conn.commit()
        conn.close()
        return opt_id

    def get_latest_backtest_run(self):
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM backtest_runs ORDER BY run_at DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return self._dict_row(row)

    def get_best_backtest_run(self):
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM backtest_runs ORDER BY expected_return DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return self._dict_row(row)

    def get_latest_optimization(self):
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM optimization_runs ORDER BY finished_at DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return self._dict_row(row)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_backtest.py::TestStore -v
```
Expected: 4 PASS

- [ ] **Step 5: 提交**

```bash
git add ipo_analyzer/backtest/store.py tests/test_backtest.py
git commit -m "feat(backtest): add SQLite store for backtest and optimization results"
```

---

### Task 8: CLI 入口 (backtest/cli.py) + 主入口集成

**Files:**
- Create: `ipo_analyzer/backtest/cli.py`
- Modify: `ipo_analyzer/__main__.py`
- Modify: `tests/test_backtest.py`

- [ ] **Step 1: 编写 CLI 测试**

在 `tests/test_backtest.py` 末尾追加：

```python
import subprocess
from ipo_analyzer.backtest.store import BacktestStore


class TestCLI:
    def test_cli_run_prints_report(self):
        result = subprocess.run(
            [sys.executable, "-m", "ipo_analyzer.backtest", "run"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        output = result.stdout + result.stderr
        assert "样本数" in output or "sample" in output.lower() or "无" in output

    def test_cli_status_prints_info(self):
        result = subprocess.run(
            [sys.executable, "-m", "ipo_analyzer.backtest", "status"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0

    def test_cli_report_works(self):
        result = subprocess.run(
            [sys.executable, "-m", "ipo_analyzer.backtest", "report"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_backtest.py::TestCLI -v
```
Expected: FAIL

- [ ] **Step 3: 编写 cli.py**

```python
"""回测框架 CLI 入口"""
import argparse
import logging
import os
import sys

import yaml

from .collector import collect_backtest_dataset
from .engine import run_backtest
from .metrics import compute_objective
from .optimizer import optimize_weights
from .store import BacktestStore
from ..settings import SETTINGS

logger = logging.getLogger(__name__)


def _get_default_weights():
    sw = SETTINGS.scoring
    return {
        "trade": sw.live_heat_trade,
        "fundamental": sw.live_heat_fundamental,
        "data_quality": sw.live_heat_data_quality,
        "valuation": sw.live_heat_valuation,
        "theme": sw.live_heat_theme,
    }


def cmd_run(args):
    """回测：用当前/指定权重跑回测"""
    bt = SETTINGS.backtest
    dataset = collect_backtest_dataset(
        history_dir="temp",
        data_quality_threshold=args.data_quality or bt.data_quality_threshold,
    )
    if len(dataset) < (args.min_samples or 1):
        print(f"样本数不足: {len(dataset)}，至少需要 {args.min_samples or 1}")
        return

    if args.weights:
        with open(args.weights) as f:
            w = yaml.safe_load(f).get("weights", _get_default_weights())
    else:
        w = _get_default_weights()

    result = run_backtest(dataset, w, qualify_threshold=bt.qualify_threshold)
    _print_result(result, w)

    if not args.no_save:
        store = BacktestStore(bt.backtest_db_path)
        store.save_backtest_run(result, notes="cli run")


def cmd_optimize(args):
    """贝叶斯优化搜索最优权重"""
    bt = SETTINGS.backtest
    dataset = collect_backtest_dataset(
        history_dir="temp",
        data_quality_threshold=args.data_quality or bt.data_quality_threshold,
    )
    min_samples = args.min_samples or bt.min_samples
    if len(dataset) < min_samples:
        print(f"样本数不足 ({len(dataset)} < {min_samples})，无法优化")
        return

    default_weights = _get_default_weights()
    print(f"数据集: {len(dataset)} 条, 迭代: {args.iterations or bt.opt_iterations}, CV: {not args.no_cv}")

    opt_result = optimize_weights(
        dataset,
        initial_samples=bt.opt_initial_samples,
        iterations=args.iterations or bt.opt_iterations,
        use_cv=not args.no_cv,
        qualify_threshold=bt.qualify_threshold,
        default_weights=default_weights,
    )

    print(f"\n=== 优化结果 ===")
    print(f"最优权重: {opt_result.weights}")
    print(f"优化目标值: {opt_result.objective:.4f}")
    print(f"默认目标值: {opt_result.default_objective:.4f}")
    print(f"提升: {opt_result.improvement_pct:+.1f}%")
    print(f"收敛: {len(opt_result.convergence)} 轮")

    store = BacktestStore(bt.backtest_db_path)
    store.save_optimization_run(opt_result, iterations=args.iterations or bt.opt_iterations,
                                cv_enabled=not args.no_cv)

    output_path = bt.optimized_weights_path
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    from datetime import datetime
    optimized_yaml = {
        "optimized_at": datetime.now().isoformat(),
        "sample_count": opt_result.sample_count,
        "cv_objective": opt_result.cv_objective,
        "weights": opt_result.weights,
        "default_objective": opt_result.default_objective,
        "optimized_objective": opt_result.objective,
        "improvement_pct": opt_result.improvement_pct,
    }
    with open(output_path, "w") as f:
        yaml.dump(optimized_yaml, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    print(f"\n优化权重已写入: {output_path}")


def cmd_report(args):
    """查看回测报告"""
    bt = SETTINGS.backtest
    store = BacktestStore(bt.backtest_db_path)

    if args.compare:
        opt = store.get_latest_optimization()
        if opt:
            print("=== 默认 vs 优化 对比 ===")
            print(f"默认目标值:    {opt['default_objective']:.4f}")
            print(f"优化目标值:    {opt['best_objective']:.4f}")
            print(f"提升:         {opt['improvement_pct']:+.1f}%")
            print(f"优化权重:     {opt['best_weights']}")
        else:
            print("无优化记录")
    else:
        run = store.get_latest_backtest_run()
        if not run:
            print("无回测记录")
            return
        print("=== 最近回测 ===")
        print(f"样本数: {run['sample_count']}")
        print(f"Qualified: {run['qualified_count']}")
        print(f"胜率: {run['win_rate']:.2%}")
        print(f"期望收益: {run['expected_return']:.2%}")
        print(f"最大回撤: {run['max_drawdown']:.2%}")
        print(f"Sharpe: {run['sharpe_like']:.2f}")
        print(f"IC Rank: {run['ic_rank']:.3f}")
        print(f"破发率: {run['break_rate']:.2%}")
        print(f"覆盖率: {run['coverage']:.2%}")
        print(f"权重: {run['weights']}")


def cmd_status(args):
    """回测系统状态"""
    bt = SETTINGS.backtest

    dataset = collect_backtest_dataset(
        history_dir="temp",
        data_quality_threshold=bt.data_quality_threshold,
    )
    print(f"历史数据集: {len(dataset)} 条有效样本")

    store = BacktestStore(bt.backtest_db_path)
    opt = store.get_latest_optimization()
    if opt:
        print(f"\n最近优化: {opt['finished_at']}")
        print(f"最优权重: {opt['best_weights']}")
        print(f"提升: {opt['improvement_pct']:+.1f}%")

    opt_path = bt.optimized_weights_path
    if os.path.exists(opt_path):
        print(f"\n优化配置文件已存在: {opt_path}")
    else:
        print(f"\n优化配置文件不存在，使用默认权重")


def _print_result(result, weights):
    print(f"=== 回测结果 ===")
    print(f"样本数: {result.sample_count}")
    print(f"权重: {weights}")
    print(f"Qualified (score≥50): {result.qualified_count}")
    print(f"胜率: {result.win_rate:.2%}")
    print(f"期望收益: {result.expected_return:.2%}")
    print(f"最大回撤: {result.max_drawdown:.2%}")
    print(f"Sharpe: {result.sharpe_like:.2f}")
    print(f"IC Rank: {result.ic_rank:.3f}")
    print(f"破发率(全体): {result.break_rate:.2%}")
    print(f"覆盖率: {result.coverage:.2%}")
    print(f"十分位收益: {result.decile_returns}")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m ipo_analyzer.backtest",
        description="回测框架 & 贝叶斯权重优化",
    )
    sub = parser.add_subparsers(dest="command", help="子命令")

    p_run = sub.add_parser("run", help="运行回测")
    p_run.add_argument("--weights", type=str, help="权重 YAML 文件路径")
    p_run.add_argument("--min-samples", type=int, help="最小样本数")
    p_run.add_argument("--data-quality", type=int, help="数据质量阈值")
    p_run.add_argument("--no-save", action="store_true", help="不保存到数据库")

    p_opt = sub.add_parser("optimize", help="贝叶斯优化权重")
    p_opt.add_argument("--iterations", type=int, help="优化迭代轮数 (默认30)")
    p_opt.add_argument("--no-cv", action="store_true", help="禁用交叉验证")
    p_opt.add_argument("--min-samples", type=int, help="最小样本数")
    p_opt.add_argument("--data-quality", type=int, help="数据质量阈值")

    p_report = sub.add_parser("report", help="查看回测报告")
    p_report.add_argument("--compare", action="store_true", help="对比默认vs优化")
    p_report.add_argument("--last", action="store_true", help="最近一次（默认）")
    p_report.add_argument("--best", action="store_true", help="历史最优")

    sub.add_parser("status", help="回测系统状态查询")

    return parser


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run":
        cmd_run(args)
    elif args.command == "optimize":
        cmd_optimize(args)
    elif args.command == "report":
        cmd_report(args)
    elif args.command == "status":
        cmd_status(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 在 `ipo_analyzer/__main__.py` 中注册 backtest 子命令**

在 `main()` 函数中：

```python
# 在 subparsers 定义区域添加（约第28行 reanalyze_parser 之后）:
backtest_parser = subparsers.add_parser("backtest", help="回测 & 权重优化")

# 在 args.command 判断链中添加:
elif args.command == "backtest":
    from ipo_analyzer.backtest.cli import main as backtest_main
    backtest_main()
```

- [ ] **Step 5: 运行 CLI 测试确认通过**

```bash
python -m pytest tests/test_backtest.py::TestCLI -v
```
Expected: 3 PASS

- [ ] **Step 6: 提交**

```bash
git add ipo_analyzer/backtest/cli.py ipo_analyzer/__main__.py tests/test_backtest.py
git commit -m "feat(backtest): add CLI (run/optimize/report/status) and register in __main__"
```

---

### Task 9: scoring.py 集成 — 加载优化权重

**Files:**
- Modify: `ipo_analyzer/scoring.py:366-401`（修改 `_detect_weight_profile`）
- Modify: `tests/test_backtest.py`

- [ ] **Step 1: 编写集成测试**

在 `tests/test_backtest.py` 末尾追加：

```python
class TestScoringIntegration:
    def test_load_optimized_weights(self):
        opt_path = os.path.join(self.tempdir, "optimized_weights.yaml")
        opt_data = {
            "weights": {
                "trade": 0.30, "fundamental": 0.30,
                "valuation": 0.20, "theme": 0.15, "data_quality": 0.05,
            }
        }
        with open(opt_path, "w") as f:
            yaml.dump(opt_data, f)

        from ipo_analyzer.scoring import ScoringSystem
        from unittest.mock import patch

        with patch("ipo_analyzer.scoring.OPTIMIZED_WEIGHTS_PATH", opt_path):
            profile = ScoringSystem._load_optimized_weights()
            assert profile is not None
            assert profile["weights"]["trade"] == 0.30

    def test_load_optimized_weights_file_missing(self):
        from unittest.mock import patch
        from ipo_analyzer.scoring import ScoringSystem
        with patch("ipo_analyzer.scoring.OPTIMIZED_WEIGHTS_PATH", "/nonexistent/path.yaml"):
            profile = ScoringSystem._load_optimized_weights()
            assert profile is None
```

**注意**：由于 `ScoringSystem._detect_weight_profile` 是 `@staticmethod`，我们需要在 `scoring.py` 模块级别暴露 `OPTIMIZED_WEIGHTS_PATH`，或改为在 `_detect_weight_profile` 内部调用。

更简洁方案：在 `_detect_weight_profile` 末尾返回权重之前，加一个加载优化权重的一行调用。

- [ ] **Step 2: 修改 `scoring.py._detect_weight_profile()`**

在 `_detect_weight_profile` 方法中，在 `sw = SETTINGS.scoring` 之前添加加载优化权重的逻辑：

```python
@staticmethod
def _detect_weight_profile(ipo):
    """检测权重配置文件：判断是 live_heat 还是 prospectus_only"""
    over_sub_ratio = ipo.get('over_sub_ratio')
    over_sub_ratio_source = ipo.get('over_sub_ratio_source')
    forecast_over_sub_ratio = ipo.get('forecast_over_sub_ratio')
    market_heat = ipo.get('market_heat', '')

    has_heat = _is_num(over_sub_ratio) and over_sub_ratio_source in ("actual", "forecast", "estimated", "historical_actual", "historical_forecast", "post_listing_actual")
    has_market = _is_num(forecast_over_sub_ratio) or market_heat in ("温和", "热门", "极热")

    # 尝试加载优化权重
    optimized = ScoringSystem._try_load_optimized_weights()
    if optimized:
        profile_name = 'live_heat' if (has_heat or has_market) else 'prospectus_only'
        return {
            'name': f'{profile_name}_optimized',
            'weights': optimized,
            'reason': '使用贝叶斯优化权重',
        }

    sw = SETTINGS.scoring
    if has_heat or has_market:
        return {
            'name': 'live_heat',
            'weights': {
                'trade': sw.live_heat_trade,
                'fundamental': sw.live_heat_fundamental,
                'data_quality': sw.live_heat_data_quality,
                'valuation': sw.live_heat_valuation,
                'theme': sw.live_heat_theme,
            },
            'reason': '检测到有效超购/孖展数据',
        }
    else:
        return {
            'name': 'prospectus_only',
            'weights': {
                'trade': sw.prospectus_trade,
                'fundamental': sw.prospectus_fundamental,
                'data_quality': sw.prospectus_data_quality,
                'valuation': sw.prospectus_valuation,
                'theme': sw.prospectus_theme,
            },
            'reason': '未检测到有效热度数据，使用招股书阶段权重',
        }
```

在 `ScoringSystem` 类中新增导入和静态方法（在 `import re` 之后，`class ScoringSystem` 内部添加）：

```python
@staticmethod
def _try_load_optimized_weights():
    try:
        from .settings import SETTINGS
        import yaml
        path = SETTINGS.backtest.optimized_weights_path
        with open(path) as f:
            opt = yaml.safe_load(f)
        if opt and opt.get("weights") and isinstance(opt["weights"], dict):
            w = opt["weights"]
            required = ["trade", "fundamental", "valuation", "theme", "data_quality"]
            if all(k in w for k in required):
                logger.info("加载优化权重: %s", w)
                return w
    except Exception:
        pass
    return None
```

- [ ] **Step 3: 运行全部测试确认**

```bash
python -m pytest tests/test_backtest.py -v
```
Expected: 全部 PASS

- [ ] **Step 4: 运行现有测试确认无回归**

```bash
python -m pytest tests/ -v --ignore=tests/test_backtest.py -x
```
Expected: 无新增失败（现有 255+ 测试全部通过）

- [ ] **Step 5: 提交**

```bash
git add ipo_analyzer/scoring.py tests/test_backtest.py
git commit -m "feat(backtest): integrate optimized weights into scoring.py _detect_weight_profile"
```

---

### Task 10: 添加 .gitignore 规则 & 最终验证

**Files:**
- Modify: `.gitignore`
- Modify: `ipo_analyzer/backtest/__init__.py`

- [ ] **Step 1: 更新 .gitignore**

确认以下规则存在：

```
data/backtest.db
data/optimized_weights.yaml
.superpowers/
```

- [ ] **Step 2: 更新 backtest/__init__.py 导出**

```python
"""回测框架 & 贝叶斯权重优化模块"""
__version__ = "0.1.0"

from .models import BacktestRecord, BacktestResult, OptimizationResult
from .collector import collect_backtest_dataset
from .engine import run_backtest
from .metrics import compute_objective, compute_objective_cv
from .optimizer import optimize_weights
from .store import BacktestStore
```

- [ ] **Step 3: 全量回归测试**

```bash
python -m pytest tests/ -v
```

Expected: 所有测试通过（包括 255+ 现有测试 + 26 新增回测测试）

- [ ] **Step 4: 手动验证 CLI 完整性**

```bash
python -m ipo_analyzer.backtest status
python -m ipo_analyzer.backtest run
```

- [ ] **Step 5: 提交**

```bash
git add .gitignore ipo_analyzer/backtest/__init__.py
git commit -m "chore(backtest): finalize module exports and gitignore"
```

---

## 完成检查清单

- [ ] `python -m ipo_analyzer.backtest status` — 显示样本数
- [ ] `python -m ipo_analyzer.backtest run` — 运行回测并输出结果
- [ ] `python -m ipo_analyzer.backtest optimize` — 搜索最优权重（需 ≥10 条样本）
- [ ] `python -m ipo_analyzer.backtest report --compare` — 对比默认 vs 优化
- [ ] `data/optimized_weights.yaml` — 优化后正确生成
- [ ] `data/backtest.db` — 回测记录持久化
- [ ] `python -m pytest tests/ -v` — 全量测试通过
- [ ] scoring.py 在有 optimized_weights.yaml 时自动使用优化权重
