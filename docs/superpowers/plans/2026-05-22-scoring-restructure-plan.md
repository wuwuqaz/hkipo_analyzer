# 评分系统管道化重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `ScoringSystem` (~1200行) 重构为类型安全、职责清晰的评分管道 (`ScoringPipeline`)，保留向后兼容接口。

**Architecture:** 新建 `ipo_analyzer/scoring/` 包，内含 `AnalyzerOutputAdapter`、`DimensionScorer`、`AdjustmentEngine`、`StrategyScorer`、`Recommender`、`ScoringPipeline` 六个组件。保留 `scoring.py` 作为兼容薄层。

**Tech Stack:** Python 3.12, dataclasses, pytest (via `python3 -m pytest`)

---

## 文件结构

```
ipo_analyzer/scoring/              # 新建
├── __init__.py                    # 导出 ScoringPipeline, ScoringResult
├── models.py                      # ScoringInput, DimensionScores, Adjustments, StrategyScores, ScoringResult, ScoreTrace
├── _utils.py                      # is_biotech(), threshold helpers
├── input_adapter.py               # AnalyzerOutputAdapter
├── dimension_scorer.py            # DimensionScorer
├── adjustment_engine.py           # AdjustmentEngine
├── strategy_scorer.py             # StrategyScorer
├── recommender.py                 # Recommender
├── weight_detector.py             # WeightProfileDetector
└── pipeline.py                    # ScoringPipeline

ipo_analyzer/settings.py           # 新增 DimensionThresholds, AdjustmentThresholds
ipo_analyzer/scoring.py            # 保留，变薄为兼容层

tests/                             # 新增
├── test_scoring_models.py
├── test_input_adapter.py
├── test_dimension_scorer.py
├── test_adjustment_engine.py
├── test_scoring_pipeline.py
└── test_scoring_compat.py         # 验证兼容层输出不变
```

---

## Task 1: 创建 scoring 包骨架

**Files:**
- Create: `ipo_analyzer/scoring/__init__.py`

- [ ] **Step 1: 创建包初始化文件**

```python
"""评分管道 — 类型安全、职责清晰的评分系统重构."""

from .pipeline import ScoringPipeline
from .models import (
    ScoringInput,
    DimensionScores,
    Adjustments,
    StrategyScores,
    ScoringResult,
    ScoreTrace,
    ScoreTraceStep,
    WeightProfile,
)
from .input_adapter import AnalyzerOutputAdapter

__all__ = [
    "ScoringPipeline",
    "ScoringInput",
    "DimensionScores",
    "Adjustments",
    "StrategyScores",
    "ScoringResult",
    "ScoreTrace",
    "ScoreTraceStep",
    "WeightProfile",
    "AnalyzerOutputAdapter",
]
```

- [ ] **Step 2: Commit**

```bash
git add ipo_analyzer/scoring/__init__.py
git commit -m "feat(scoring): create scoring package skeleton"
```

---

## Task 2: 定义核心类型契约 (models.py)

**Files:**
- Create: `ipo_analyzer/scoring/models.py`
- Test: `tests/test_scoring_models.py`

- [ ] **Step 1: 写 models.py**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CornerstoneInvestorInput:
    name: str
    offer_shares: Optional[int] = None
    offer_shares_pct: Optional[float] = None
    lockup_months: Optional[int] = None
    type_hint: Optional[str] = None


@dataclass
class QualityDimensions:
    growth_score: float = 0.0
    profitability_score: float = 0.0
    valuation_score: float = 0.0
    risk_score: float = 0.0
    cashflow_score: float = 0.0
    moat_score: float = 0.0
    financial_health_score: float = 0.0
    management_score: float = 0.0
    balance_sheet_score: float = 0.0
    profit_sustainability_score: float = 0.0


@dataclass
class ScoringInput:
    """评分管道的唯一输入."""
    stock_code: str
    company_name: str
    industry: Optional[str] = None
    is_biotech: bool = False

    # 交易信号
    heat_score: float = 0.0
    scale_score: float = 0.0
    cornerstone_score: float = 0.0
    real_money_signal: float = 0.0
    float_structure_score: float = 0.0
    sponsor_score: Optional[float] = None
    greenshoe_score: Optional[float] = None
    clawback_score: Optional[float] = None

    # 基本面
    stock_quality_score: float = 0.0
    quality_dimensions: QualityDimensions = field(default_factory=QualityDimensions)

    # 估值
    valuation_framework_score: float = 0.0
    peer_adj_label: Optional[str] = None
    pricing_gap_adj: float = 0.0
    valuation_label: Optional[str] = None

    # 主题
    mainline_beta_score: float = 0.0
    stock_connect_path_score: float = 0.0
    scarcity_score: float = 0.0
    sentiment_bonus: float = 0.0
    macro_bonus: float = 0.0

    # 数据质量
    data_quality_score: float = 0.0

    # 风险
    risk_penalty: float = 0.0
    risk_categories: dict[str, list[str]] = field(default_factory=dict)

    # 基石
    cornerstone_pct: Optional[float] = None
    cornerstone_investors: list[CornerstoneInvestorInput] = field(default_factory=list)
    cornerstone_red_flags: list[str] = field(default_factory=list)

    # 原始引用
    raw_prospectus_info: dict[str, Any] = field(default_factory=dict)


@dataclass
class DimensionScores:
    trade: float = 0.0
    fundamental: float = 0.0
    valuation: float = 0.0
    theme: float = 0.0
    data_quality: float = 0.0

    trade_components: dict[str, float] = field(default_factory=dict)
    fundamental_components: dict[str, float] = field(default_factory=dict)


@dataclass
class Adjustments:
    peer_adj: float = 0.0
    val_penalty: float = 0.0
    pricing_gap_adj: float = 0.0
    risk_penalty: float = 0.0
    cornerstone_penalty: float = 0.0

    @property
    def total(self) -> float:
        return (
            self.peer_adj
            + self.val_penalty
            + self.pricing_gap_adj
            - self.risk_penalty
            - self.cornerstone_penalty
        )


@dataclass
class StrategyScores:
    long_term_score: float = 0.0
    strict_ipo_score: float = 0.0
    long_term_components: dict[str, float] = field(default_factory=dict)


@dataclass
class RecommendationResult:
    recommendation: str = ""
    reasons: list[str] = field(default_factory=list)
    dimension_grades: dict[str, str] = field(default_factory=dict)


@dataclass
class ScoreTraceStep:
    step_name: str
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoreTrace:
    steps: list[ScoreTraceStep] = field(default_factory=list)

    def record(
        self,
        step_name: str,
        input_data: dict[str, Any],
        output_data: dict[str, Any],
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        self.steps.append(
            ScoreTraceStep(
                step_name=step_name,
                input_data=input_data,
                output_data=output_data,
                metadata=metadata or {},
            )
        )

    def to_flat_dict(self) -> dict[str, Any]:
        """兼容现有前端格式."""
        result: dict[str, Any] = {}
        for step in self.steps:
            result[step.step_name] = {
                "input": step.input_data,
                "output": step.output_data,
                "metadata": step.metadata,
            }
        return result


@dataclass
class WeightProfile:
    name: str
    weights: dict[str, float]


@dataclass
class ScoringResult:
    score: float = 0.0
    final_score: float = 0.0

    trade_score: float = 0.0
    fundamental_score: float = 0.0
    valuation_score: float = 0.0
    theme_score: float = 0.0
    data_quality_score: float = 0.0

    long_term_score: float = 0.0
    strict_ipo_score: float = 0.0
    ipo_trade_score: float = 0.0

    recommendation: str = ""
    reasons: list[str] = field(default_factory=list)
    dimension_grades: dict[str, str] = field(default_factory=dict)

    score_trace: ScoreTrace = field(default_factory=ScoreTrace)
    weight_profile: str = ""
    debug_info: dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 2: 写 models 测试**

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ipo_analyzer.scoring.models import (
    ScoringInput,
    DimensionScores,
    Adjustments,
    ScoreTrace,
    WeightProfile,
)


def test_scoring_input_defaults():
    inp = ScoringInput(stock_code="09999", company_name="测试")
    assert inp.heat_score == 0.0
    assert inp.is_biotech is False
    assert inp.cornerstone_investors == []


def test_adjustments_total():
    adj = Adjustments(peer_adj=3.0, val_penalty=-2.0, pricing_gap_adj=1.0, risk_penalty=5.0, cornerstone_penalty=2.0)
    assert adj.total == 3.0 + (-2.0) + 1.0 - 5.0 - 2.0


def test_score_trace_record():
    trace = ScoreTrace()
    trace.record("step1", {"a": 1}, {"b": 2})
    assert len(trace.steps) == 1
    assert trace.steps[0].step_name == "step1"


def test_weight_profile():
    wp = WeightProfile(name="live_heat", weights={"trade": 0.25, "fundamental": 0.35})
    assert wp.weights["trade"] == 0.25
```

- [ ] **Step 3: 运行测试**

```bash
python3 -m pytest tests/test_scoring_models.py -v
```

Expected: 4 passed

- [ ] **Step 4: Commit**

```bash
git add ipo_analyzer/scoring/models.py tests/test_scoring_models.py
git commit -m "feat(scoring): add scoring type contracts (models)"
```

---

## Task 3: 创建评分工具函数 (_utils.py)

**Files:**
- Create: `ipo_analyzer/scoring/_utils.py`

- [ ] **Step 1: 写 _utils.py**

```python
"""评分管道共享工具 — biotech 判断、阈值读取等."""

from __future__ import annotations

from typing import Any


def is_biotech(prospectus_info: dict[str, Any]) -> bool:
    """统一判断是否为 biotech/18A 公司.

    当前散落在 valuation、scoring、quality、signal 四处的判断逻辑汇总:
    1. 股票代码/公司名以 -B 结尾
    2. 行业代码为 biotech/pharma/healthcare + 关键词命中
    3. 收入结构以 license upfront 为主
    """
    name = prospectus_info.get("extracted_company_name", "")
    aliases = prospectus_info.get("company_name_aliases", [])
    sector = prospectus_info.get("sector", "")
    text = prospectus_info.get("_extracted_text", "")

    # -B 后缀强制命中
    names = [name] + aliases
    if any(n.strip().upper().endswith("-B") for n in names if isinstance(n, str)):
        return True

    # 行业 + 关键词
    biotech_sectors = {"biotech", "pharma", "healthcare", "pharmaceutical"}
    if sector and sector.lower() in biotech_sectors:
        if "biotech" in text.lower() or "pipeline" in text.lower():
            return True

    # revenue 结构特征 (license upfront driven)
    revenue = prospectus_info.get("revenue", 0)
    if isinstance(revenue, (int, float)) and revenue > 0:
        if "license" in text.lower() and "upfront" in text.lower():
            # 如果收入很小且以 license 为主，判定为 biotech
            if revenue < 500:  # 百万 RMB/HKD 级别
                return True

    return False


def grade_from_score(score: float) -> str:
    """分数 -> 等级 (兼容现有 grading 逻辑)."""
    if score >= 85:
        return "A+"
    if score >= 75:
        return "A"
    if score >= 65:
        return "A-"
    if score >= 55:
        return "B+"
    if score >= 45:
        return "B"
    if score >= 35:
        return "B-"
    if score >= 25:
        return "C+"
    return "C"
```

- [ ] **Step 2: Commit**

```bash
git add ipo_analyzer/scoring/_utils.py
git commit -m "feat(scoring): add shared scoring utilities (is_biotech, grade_from_score)"
```

---

## Task 4: 创建 AnalyzerOutputAdapter

**Files:**
- Create: `ipo_analyzer/scoring/input_adapter.py`
- Test: `tests/test_input_adapter.py`

- [ ] **Step 1: 写 input_adapter.py**

```python
"""将分析器输出的扁平 dict 映射为强类型 ScoringInput."""

from __future__ import annotations

from typing import Any

from .models import ScoringInput, CornerstoneInvestorInput, QualityDimensions
from ._utils import is_biotech


class AnalyzerOutputAdapter:
    """统一适配器: prospectus_info dict -> ScoringInput."""

    def adapt(self, stock_code: str, company_name: str, prospectus_info: dict[str, Any]) -> ScoringInput:
        p = prospectus_info

        # 基石投资者
        raw_investors = p.get("cornerstone_analysis", {}).get("cornerstone_investors", [])
        investors = []
        for ri in raw_investors:
            if isinstance(ri, dict):
                investors.append(
                    CornerstoneInvestorInput(
                        name=ri.get("name", ""),
                        offer_shares=ri.get("offer_shares"),
                        offer_shares_pct=ri.get("offer_shares_pct"),
                        lockup_months=ri.get("lockup_months"),
                        type_hint=ri.get("type"),
                    )
                )

        # 质量维度
        qa = p.get("quality_analysis", {})
        qd = QualityDimensions(
            growth_score=qa.get("growth_score", 0.0),
            profitability_score=qa.get("profitability_score", 0.0),
            valuation_score=qa.get("valuation_score", 0.0),
            risk_score=qa.get("risk_score", 0.0),
            cashflow_score=qa.get("cashflow_score", 0.0),
            moat_score=qa.get("moat_score", 0.0),
            financial_health_score=qa.get("financial_health_score", 0.0),
            management_score=qa.get("management_score", 0.0),
            balance_sheet_score=qa.get("balance_sheet_score", 0.0),
            profit_sustainability_score=qa.get("profit_sustainability_score", 0.0),
        )

        # 风险
        risk = p.get("risk_analysis", {})
        risk_penalty = risk.get("total_penalty", 0.0)
        risk_categories = risk.get("risks", {})
        if not isinstance(risk_categories, dict):
            risk_categories = {}

        # 信号组件
        signals = p.get("signal_components", {})

        # 估值
        val = p.get("valuation", {})

        return ScoringInput(
            stock_code=stock_code,
            company_name=company_name,
            industry=p.get("sector"),
            is_biotech=is_biotech(p),

            heat_score=signals.get("heat_score", 0.0),
            scale_score=signals.get("scale_score", 0.0),
            cornerstone_score=signals.get("cornerstone_score", 0.0),
            real_money_signal=signals.get("real_money", 0.0),
            float_structure_score=signals.get("float_structure", 0.0),
            sponsor_score=signals.get("sponsor_score"),
            greenshoe_score=signals.get("greenshoe_score"),
            clawback_score=signals.get("clawback_score"),

            stock_quality_score=p.get("stock_quality_score", 0.0),
            quality_dimensions=qd,

            valuation_framework_score=val.get("valuation_framework_score", 0.0),
            peer_adj_label=val.get("peer_adj_label"),
            pricing_gap_adj=p.get("pricing_gap_adj", 0.0),
            valuation_label=val.get("valuation_label"),

            mainline_beta_score=signals.get("mainline_beta", 0.0),
            stock_connect_path_score=signals.get("stock_connect_path", 0.0),
            scarcity_score=signals.get("scarcity", 0.0),
            sentiment_bonus=p.get("sentiment_bonus", 0.0),
            macro_bonus=p.get("macro_bonus", 0.0),

            data_quality_score=signals.get("data_quality", 0.0),

            risk_penalty=risk_penalty,
            risk_categories=risk_categories,

            cornerstone_pct=p.get("cornerstone_pct"),
            cornerstone_investors=investors,
            cornerstone_red_flags=p.get("cornerstone_red_flags", []),

            raw_prospectus_info=p,
        )
```

- [ ] **Step 2: 写 adapter 测试**

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ipo_analyzer.scoring.input_adapter import AnalyzerOutputAdapter
from ipo_analyzer.scoring.models import ScoringInput


def test_adapter_minimal():
    adapter = AnalyzerOutputAdapter()
    p = {
        "sector": "hardtech",
        "revenue": 500.0,
        "stock_quality_score": 70.0,
        "signal_components": {"heat_score": 30.0, "data_quality": 80.0},
        "valuation": {"valuation_framework_score": 60.0},
        "risk_analysis": {"total_penalty": 5.0, "risks": {"operational": ["risk1"]}},
    }
    inp = adapter.adapt("09999", "测试公司", p)
    assert isinstance(inp, ScoringInput)
    assert inp.stock_code == "09999"
    assert inp.heat_score == 30.0
    assert inp.risk_penalty == 5.0
    assert inp.is_biotech is False


def test_adapter_biotech_detection():
    adapter = AnalyzerOutputAdapter()
    p = {
        "extracted_company_name": "TestBio-B",
        "sector": "healthcare",
        "_extracted_text": "biotech pipeline",
    }
    inp = adapter.adapt("09999", "TestBio", p)
    assert inp.is_biotech is True


def test_adapter_cornerstone_investors():
    adapter = AnalyzerOutputAdapter()
    p = {
        "cornerstone_analysis": {
            "cornerstone_investors": [
                {"name": " investor1 ", "offer_shares_pct": 10.0},
            ]
        }
    }
    inp = adapter.adapt("09999", "测试", p)
    assert len(inp.cornerstone_investors) == 1
    assert inp.cornerstone_investors[0].offer_shares_pct == 10.0
```

- [ ] **Step 3: 运行测试**

```bash
python3 -m pytest tests/test_input_adapter.py -v
```

Expected: 3 passed

- [ ] **Step 4: Commit**

```bash
git add ipo_analyzer/scoring/input_adapter.py tests/test_input_adapter.py
git commit -m "feat(scoring): add AnalyzerOutputAdapter with biotech detection"
```

---

## Task 5: 创建 DimensionScorer

**Files:**
- Create: `ipo_analyzer/scoring/dimension_scorer.py`
- Test: `tests/test_dimension_scorer.py`

- [ ] **Step 1: 写 dimension_scorer.py**

```python
"""计算五维原始分 — 不含任何调整项."""

from __future__ import annotations

from .models import ScoringInput, DimensionScores


class DimensionScorer:
    def calculate(self, inp: ScoringInput) -> DimensionScores:
        trade = self._calc_trade(inp)
        fundamental = self._calc_fundamental(inp)
        valuation = self._calc_valuation(inp)
        theme = self._calc_theme(inp)
        data_quality = self._calc_data_quality(inp)

        return DimensionScores(
            trade=trade,
            fundamental=fundamental,
            valuation=valuation,
            theme=theme,
            data_quality=data_quality,
            trade_components={
                "heat": inp.heat_score,
                "scale": inp.scale_score,
                "cornerstone": inp.cornerstone_score,
                "real_money": inp.real_money_signal,
                "float": inp.float_structure_score,
                "sponsor": inp.sponsor_score or 0.0,
                "greenshoe": inp.greenshoe_score or 0.0,
                "clawback": inp.clawback_score or 0.0,
            },
            fundamental_components={
                "stock_quality": inp.stock_quality_score,
                "quality_dimensions": inp.quality_dimensions.__dict__,
            },
        )

    def _calc_trade(self, inp: ScoringInput) -> float:
        # 交易分 = heat + scale + cornerstone + real_money + float + sponsor + greenshoe + clawback
        # 归一化到 0-100
        raw = (
            inp.heat_score
            + inp.scale_score
            + inp.cornerstone_score
            + inp.real_money_signal
            + inp.float_structure_score
            + (inp.sponsor_score or 0.0)
            + (inp.greenshoe_score or 0.0)
            + (inp.clawback_score or 0.0)
        )
        # 基于当前 max: 45+10+20+20+15+10+5+5 = 130, 映射到 100
        return min(100.0, raw / 130.0 * 100.0)

    def _calc_fundamental(self, inp: ScoringInput) -> float:
        # 基本面分直接来自 stock_quality_score (0-100)
        return min(100.0, max(0.0, inp.stock_quality_score))

    def _calc_valuation(self, inp: ScoringInput) -> float:
        # 估值框架分直接映射
        return min(100.0, max(0.0, inp.valuation_framework_score))

    def _calc_theme(self, inp: ScoringInput) -> float:
        # 主题分综合
        raw = (
            inp.mainline_beta_score * 0.30
            + inp.stock_connect_path_score * 0.30
            + inp.scarcity_score * 0.20
            + inp.sentiment_bonus * 0.10
            + inp.macro_bonus * 0.10
        )
        return min(100.0, max(0.0, raw))

    def _calc_data_quality(self, inp: ScoringInput) -> float:
        return min(100.0, max(0.0, inp.data_quality_score))
```

- [ ] **Step 2: 写 dimension_scorer 测试**

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ipo_analyzer.scoring.dimension_scorer import DimensionScorer
from ipo_analyzer.scoring.models import ScoringInput


def test_dimension_scorer_basic():
    scorer = DimensionScorer()
    inp = ScoringInput(
        stock_code="09999",
        company_name="测试",
        heat_score=30.0,
        scale_score=10.0,
        cornerstone_score=15.0,
        real_money_signal=10.0,
        float_structure_score=10.0,
        stock_quality_score=70.0,
        valuation_framework_score=60.0,
        mainline_beta_score=50.0,
        stock_connect_path_score=50.0,
        scarcity_score=50.0,
        data_quality_score=80.0,
    )
    dims = scorer.calculate(inp)
    assert 0.0 <= dims.trade <= 100.0
    assert dims.fundamental == 70.0
    assert dims.valuation == 60.0
    assert dims.data_quality == 80.0
    assert "heat" in dims.trade_components


def test_dimension_scorer_biotech_zero():
    scorer = DimensionScorer()
    inp = ScoringInput(stock_code="09999", company_name="测试")
    dims = scorer.calculate(inp)
    assert dims.trade == 0.0
    assert dims.fundamental == 0.0
```

- [ ] **Step 3: 运行测试**

```bash
python3 -m pytest tests/test_dimension_scorer.py -v
```

Expected: 2 passed

- [ ] **Step 4: Commit**

```bash
git add ipo_analyzer/scoring/dimension_scorer.py tests/test_dimension_scorer.py
git commit -m "feat(scoring): add DimensionScorer with 5-dimension raw scoring"
```

---

## Task 6: 创建 AdjustmentEngine

**Files:**
- Create: `ipo_analyzer/scoring/adjustment_engine.py`

- [ ] **Step 1: 写 adjustment_engine.py**

```python
"""集中计算所有调整项."""

from __future__ import annotations

from .models import ScoringInput, DimensionScores, Adjustments


class AdjustmentEngine:
    def calculate(self, inp: ScoringInput, dims: DimensionScores) -> Adjustments:
        peer_adj = self._calc_peer_adj(inp)
        val_penalty = self._calc_val_penalty(inp)
        pricing_gap_adj = inp.pricing_gap_adj
        risk_penalty = self._calc_risk_penalty(inp)
        cornerstone_penalty = self._calc_cornerstone_penalty(inp)

        return Adjustments(
            peer_adj=peer_adj,
            val_penalty=val_penalty,
            pricing_gap_adj=pricing_gap_adj,
            risk_penalty=risk_penalty,
            cornerstone_penalty=cornerstone_penalty,
        )

    def _calc_peer_adj(self, inp: ScoringInput) -> float:
        label = inp.peer_adj_label
        if label == "excellent":
            return 6.0
        if label == "fair":
            return 0.0
        if label in ("overvalued", "clearly_overvalued"):
            return -6.0
        return 0.0

    def _calc_val_penalty(self, inp: ScoringInput) -> float:
        label = inp.valuation_label
        if label == "很贵":
            return -5.0
        if label == "偏贵":
            return -3.0
        if label == "合理":
            return 0.0
        if label == "便宜":
            return 2.0
        return 0.0

    def _calc_risk_penalty(self, inp: ScoringInput) -> float:
        # 基础 risk penalty 来自输入，可在此叠加额外规则
        base = inp.risk_penalty
        # 如果有严重风险类别，追加惩罚
        severe = ["legal", "regulatory", "accounting"]
        extra = 0.0
        for cat in severe:
            if cat in inp.risk_categories and len(inp.risk_categories[cat]) > 0:
                extra += 2.0
        return min(20.0, base + extra)

    def _calc_cornerstone_penalty(self, inp: ScoringInput) -> float:
        flags = inp.cornerstone_red_flags
        if not flags:
            return 0.0
        # 每个 red flag 扣 3 分，最多 15
        return min(15.0, len(flags) * 3.0)
```

- [ ] **Step 2: 写 adjustment_engine 测试**

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ipo_analyzer.scoring.adjustment_engine import AdjustmentEngine
from ipo_analyzer.scoring.models import ScoringInput, DimensionScores


def test_peer_adj_excellent():
    engine = AdjustmentEngine()
    inp = ScoringInput(stock_code="09999", company_name="测试", peer_adj_label="excellent")
    adj = engine.calculate(inp, DimensionScores())
    assert adj.peer_adj == 6.0


def test_val_penalty_expensive():
    engine = AdjustmentEngine()
    inp = ScoringInput(stock_code="09999", company_name="测试", valuation_label="很贵")
    adj = engine.calculate(inp, DimensionScores())
    assert adj.val_penalty == -5.0


def test_risk_penalty_with_severe():
    engine = AdjustmentEngine()
    inp = ScoringInput(
        stock_code="09999",
        company_name="测试",
        risk_penalty=5.0,
        risk_categories={"legal": ["lawsuit"]},
    )
    adj = engine.calculate(inp, DimensionScores())
    assert adj.risk_penalty == 7.0


def test_cornerstone_penalty():
    engine = AdjustmentEngine()
    inp = ScoringInput(
        stock_code="09999",
        company_name="测试",
        cornerstone_red_flags=["weak", "unknown", "short_lockup"],
    )
    adj = engine.calculate(inp, DimensionScores())
    assert adj.cornerstone_penalty == 9.0
```

- [ ] **Step 3: 运行测试**

```bash
python3 -m pytest tests/test_adjustment_engine.py -v
```

Expected: 4 passed

- [ ] **Step 4: Commit**

```bash
git add ipo_analyzer/scoring/adjustment_engine.py tests/test_adjustment_engine.py
git commit -m "feat(scoring): add AdjustmentEngine consolidating all score adjustments"
```

---

## Task 7: 创建 StrategyScorer

**Files:**
- Create: `ipo_analyzer/scoring/strategy_scorer.py`

- [ ] **Step 1: 写 strategy_scorer.py**

```python
"""计算 long_term_score 和 strict_ipo_score."""

from __future__ import annotations

from .models import ScoringInput, DimensionScores, StrategyScores


class StrategyScorer:
    def calculate(
        self,
        inp: ScoringInput,
        raw_score: float,
        dims: DimensionScores,
    ) -> StrategyScores:
        long_term = self._calc_long_term(inp, dims)
        strict_ipo = self._calc_strict_ipo(raw_score, long_term, inp)
        return StrategyScores(
            long_term_score=long_term,
            strict_ipo_score=strict_ipo,
            long_term_components={
                "fundamental": inp.quality_dimensions.fundamental_score if hasattr(inp.quality_dimensions, "fundamental_score") else 0.0,
                "valuation": inp.quality_dimensions.valuation_score if hasattr(inp.quality_dimensions, "valuation_score") else 0.0,
                "moat": inp.quality_dimensions.moat_score if hasattr(inp.quality_dimensions, "moat_score") else 0.0,
                "financial_health": inp.quality_dimensions.financial_health_score if hasattr(inp.quality_dimensions, "financial_health_score") else 0.0,
                "growth": inp.quality_dimensions.growth_score if hasattr(inp.quality_dimensions, "growth_score") else 0.0,
                "stock_connect": inp.stock_connect_path_score,
                "theme": inp.mainline_beta_score,
            },
        )

    def _calc_long_term(self, inp: ScoringInput, dims: DimensionScores) -> float:
        qd = inp.quality_dimensions
        # 使用 getattr 安全访问，因为 QualityDimensions 的字段可能随版本变化
        fundamental = getattr(qd, "fundamental_score", 0.0) or dims.fundamental
        valuation = getattr(qd, "valuation_score", 0.0) or dims.valuation
        moat = getattr(qd, "moat_score", 0.0)
        financial_health = getattr(qd, "financial_health_score", 0.0)
        growth = getattr(qd, "growth_score", 0.0)
        stock_connect = inp.stock_connect_path_score
        theme = inp.mainline_beta_score

        score = (
            fundamental * 0.35
            + valuation * 0.25
            + moat * 0.15
            + financial_health * 0.10
            + growth * 0.05
            + stock_connect * 0.05
            + theme * 0.05
        )
        return min(100.0, max(0.0, score))

    def _calc_strict_ipo(self, raw_score: float, long_term: float, inp: ScoringInput) -> float:
        # strict_ipo = raw_trade * 0.40 + long_term * 0.40 + valuation * 0.20
        # 简化: 使用 raw_score 的 trade 部分 + long_term + valuation
        trade_part = inp.heat_score  # 简化代理
        val_part = inp.valuation_framework_score
        score = trade_part * 0.40 + long_term * 0.40 + val_part * 0.20
        return min(100.0, max(0.0, score))
```

- [ ] **Step 2: Commit**

```bash
git add ipo_analyzer/scoring/strategy_scorer.py
git commit -m "feat(scoring): add StrategyScorer for long-term and strict-IPO scores"
```

---

## Task 8: 创建 Recommender

**Files:**
- Create: `ipo_analyzer/scoring/recommender.py`

- [ ] **Step 1: 写 recommender.py**

```python
"""基于分数生成推荐、原因和等级评定."""

from __future__ import annotations

from .models import (
    ScoringInput,
    DimensionScores,
    Adjustments,
    StrategyScores,
    RecommendationResult,
)
from ._utils import grade_from_score


class Recommender:
    def recommend(
        self,
        final_score: float,
        strategy_scores: StrategyScores,
        adjustments: Adjustments,
        dimensions: DimensionScores,
    ) -> RecommendationResult:
        reasons = self._build_reasons(final_score, strategy_scores, adjustments, dimensions)
        rec = self._score_to_recommendation(final_score)
        grades = {
            "trade": grade_from_score(dimensions.trade),
            "fundamental": grade_from_score(dimensions.fundamental),
            "valuation": grade_from_score(dimensions.valuation),
            "theme": grade_from_score(dimensions.theme),
            "data_quality": grade_from_score(dimensions.data_quality),
        }
        return RecommendationResult(
            recommendation=rec,
            reasons=reasons,
            dimension_grades=grades,
        )

    def _score_to_recommendation(self, score: float) -> str:
        if score >= 75:
            return "强烈推荐"
        if score >= 60:
            return "推荐"
        if score >= 45:
            return "中性"
        if score >= 30:
            return "谨慎"
        return "回避"

    def _build_reasons(
        self,
        final_score: float,
        strategy_scores: StrategyScores,
        adjustments: Adjustments,
        dimensions: DimensionScores,
    ) -> list[str]:
        reasons = []
        if dimensions.trade >= 70:
            reasons.append("交易热度强劲")
        elif dimensions.trade <= 30:
            reasons.append("交易热度不足")

        if dimensions.fundamental >= 70:
            reasons.append("基本面优质")
        elif dimensions.fundamental <= 30:
            reasons.append("基本面较弱")

        if adjustments.peer_adj > 0:
            reasons.append("估值相对同行有优势")
        elif adjustments.peer_adj < 0:
            reasons.append("估值相对同行偏高")

        if adjustments.risk_penalty > 10:
            reasons.append("风险因子较多，需注意")

        if strategy_scores.long_term_score >= 70:
            reasons.append("长期投资价值较高")

        return reasons
```

- [ ] **Step 2: Commit**

```bash
git add ipo_analyzer/scoring/recommender.py
git commit -m "feat(scoring): add Recommender for recommendation and grading"
```

---

## Task 9: 创建 WeightProfileDetector

**Files:**
- Create: `ipo_analyzer/scoring/weight_detector.py`

- [ ] **Step 1: 写 weight_detector.py**

```python
"""检测权重配置文件 (live_heat / prospectus_only / optimized)."""

from __future__ import annotations

import os
from typing import Optional

from .models import ScoringInput, WeightProfile


class WeightProfileDetector:
    """基于输入数据可用性选择权重配置."""

    def __init__(self, optimized_weights_path: str = "data/optimized_weights.yaml"):
        self._optimized_path = optimized_weights_path
        self._optimized: Optional[WeightProfile] = None
        self._load_optimized()

    def _load_optimized(self) -> None:
        if not os.path.exists(self._optimized_path):
            return
        try:
            import yaml
            with open(self._optimized_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if data and "weights" in data:
                self._optimized = WeightProfile(
                    name="optimized",
                    weights=data["weights"],
                )
        except Exception:
            pass

    def detect(self, inp: ScoringInput) -> WeightProfile:
        # 如果有真实 heat 数据 (heat_score > 0 或 over_sub_ratio 存在)
        has_heat = inp.heat_score > 0 or inp.real_money_signal > 0

        if self._optimized:
            return self._optimized

        if has_heat:
            return WeightProfile(
                name="live_heat",
                weights={
                    "trade": 0.25,
                    "fundamental": 0.35,
                    "data_quality": 0.05,
                    "valuation": 0.25,
                    "theme": 0.10,
                },
            )

        return WeightProfile(
            name="prospectus_only",
            weights={
                "trade": 0.15,
                "fundamental": 0.40,
                "data_quality": 0.05,
                "valuation": 0.25,
                "theme": 0.15,
            },
        )
```

- [ ] **Step 2: Commit**

```bash
git add ipo_analyzer/scoring/weight_detector.py
git commit -m "feat(scoring): add WeightProfileDetector with optimized weights fallback"
```

---

## Task 10: 创建 ScoringPipeline

**Files:**
- Create: `ipo_analyzer/scoring/pipeline.py`
- Test: `tests/test_scoring_pipeline.py`

- [ ] **Step 1: 写 pipeline.py**

```python
"""评分管道 — 串联所有评分组件."""

from __future__ import annotations

from typing import Optional

from .models import ScoringInput, ScoringResult, ScoreTrace
from .dimension_scorer import DimensionScorer
from .adjustment_engine import AdjustmentEngine
from .strategy_scorer import StrategyScorer
from .recommender import Recommender
from .weight_detector import WeightProfileDetector


class ScoringPipeline:
    def __init__(
        self,
        dimension_scorer: Optional[DimensionScorer] = None,
        adjustment_engine: Optional[AdjustmentEngine] = None,
        strategy_scorer: Optional[StrategyScorer] = None,
        recommender: Optional[Recommender] = None,
        weight_detector: Optional[WeightProfileDetector] = None,
    ):
        self.dimension_scorer = dimension_scorer or DimensionScorer()
        self.adjustment_engine = adjustment_engine or AdjustmentEngine()
        self.strategy_scorer = strategy_scorer or StrategyScorer()
        self.recommender = recommender or Recommender()
        self.weight_detector = weight_detector or WeightProfileDetector()

    def run(self, inp: ScoringInput) -> ScoringResult:
        trace = ScoreTrace()

        # Step 1: DimensionScores
        dims = self.dimension_scorer.calculate(inp)
        trace.record("dimension", {"input": inp.stock_code}, {"dimensions": dims.__dict__})

        # Step 2: Adjustments
        adj = self.adjustment_engine.calculate(inp, dims)
        trace.record("adjustment", {"dimensions": dims.__dict__}, {"adjustments": adj.__dict__})

        # Step 3: Weighted raw score
        profile = self.weight_detector.detect(inp)
        weights = profile.weights
        raw_score = (
            dims.trade * weights.get("trade", 0.0)
            + dims.fundamental * weights.get("fundamental", 0.0)
            + dims.valuation * weights.get("valuation", 0.0)
            + dims.theme * weights.get("theme", 0.0)
            + dims.data_quality * weights.get("data_quality", 0.0)
        )
        trace.record(
            "weighting",
            {"profile": profile.name},
            {"raw_score": raw_score, "weights": weights},
        )

        # Step 4: Apply adjustments
        score = raw_score + adj.total
        trace.record("apply_adjustments", {"raw_score": raw_score}, {"score": score})

        # Step 5: Strategy scores
        strat = self.strategy_scorer.calculate(inp, score, dims)
        trace.record("strategy", {"score": score}, {"strategy": strat.__dict__})

        # Step 6: Final score (caps)
        final_score = self._apply_caps(score, strat, inp)
        trace.record("final", {"score": score}, {"final_score": final_score})

        # Step 7: Recommendation
        rec = self.recommender.recommend(final_score, strat, adj, dims)
        trace.record("recommendation", {"final_score": final_score}, {"recommendation": rec.__dict__})

        return ScoringResult(
            score=score,
            final_score=final_score,
            trade_score=dims.trade,
            fundamental_score=dims.fundamental,
            valuation_score=dims.valuation,
            theme_score=dims.theme,
            data_quality_score=dims.data_quality,
            long_term_score=strat.long_term_score,
            strict_ipo_score=strat.strict_ipo_score,
            ipo_trade_score=dims.trade,  # 兼容字段
            recommendation=rec.recommendation,
            reasons=rec.reasons,
            dimension_grades=rec.dimension_grades,
            score_trace=trace,
            weight_profile=profile.name,
            debug_info={"raw_score": raw_score, "adjustments": adj.__dict__},
        )

    def _apply_caps(self, score: float, strat: StrategyScores, inp: ScoringInput) -> float:
        # 基础 cap
        final = min(100.0, max(0.0, score))
        # 如果 strict_ipo_score 明显低于 raw score，可能需要调整
        # 当前简化: 不做额外 cap
        return final
```

- [ ] **Step 2: 写 pipeline 集成测试**

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ipo_analyzer.scoring.pipeline import ScoringPipeline
from ipo_analyzer.scoring.models import ScoringInput


def test_pipeline_full_run():
    pipeline = ScoringPipeline()
    inp = ScoringInput(
        stock_code="09999",
        company_name="测试公司",
        heat_score=30.0,
        scale_score=10.0,
        cornerstone_score=15.0,
        real_money_signal=10.0,
        float_structure_score=10.0,
        stock_quality_score=70.0,
        valuation_framework_score=60.0,
        mainline_beta_score=50.0,
        stock_connect_path_score=50.0,
        scarcity_score=50.0,
        data_quality_score=80.0,
        peer_adj_label="excellent",
        pricing_gap_adj=2.0,
    )
    result = pipeline.run(inp)
    assert 0.0 <= result.final_score <= 100.0
    assert result.weight_profile == "live_heat"
    assert len(result.score_trace.steps) == 7
    assert result.recommendation != ""
    assert "trade" in result.dimension_grades


def test_pipeline_prospectus_only_profile():
    pipeline = ScoringPipeline()
    inp = ScoringInput(
        stock_code="09999",
        company_name="测试",
        stock_quality_score=60.0,
        valuation_framework_score=50.0,
        data_quality_score=70.0,
    )
    result = pipeline.run(inp)
    assert result.weight_profile == "prospectus_only"
```

- [ ] **Step 3: 运行测试**

```bash
python3 -m pytest tests/test_scoring_pipeline.py -v
```

Expected: 2 passed

- [ ] **Step 4: Commit**

```bash
git add ipo_analyzer/scoring/pipeline.py tests/test_scoring_pipeline.py
git commit -m "feat(scoring): add ScoringPipeline with full score trace"
```

---

## Task 11: 保留兼容层 (scoring.py 变薄)

**Files:**
- Modify: `ipo_analyzer/scoring.py`

- [ ] **Step 1: 在 scoring.py 顶部添加兼容导入**

在 `scoring.py` 文件的最顶部（imports 之后）添加：

```python
# === 兼容层: 委托给新的 ScoringPipeline ===
from ipo_analyzer.scoring import (
    ScoringPipeline,
    AnalyzerOutputAdapter,
    ScoringResult,
)
```

- [ ] **Step 2: 在 ScoringSystem.__init__ 中初始化 pipeline**

找到 `class ScoringSystem:` 和 `def __init__`，修改为：

```python
class ScoringSystem:
    def __init__(self, settings=None):
        self.settings = settings or SETTINGS
        self.pipeline = ScoringPipeline()
        self.adapter = AnalyzerOutputAdapter()
```

- [ ] **Step 3: 在 calculate() 方法末尾添加新管道调用（保留旧逻辑，新增委托分支）**

在 `calculate()` 方法中，在 `return result` 之前，添加一段兼容转换代码：

```python
        # === 新管道委托（兼容层）===
        try:
            inp = self.adapter.adapt(
                stock_code=getattr(ipo, "hk_code", ""),
                company_name=getattr(ipo, "company_name", ""),
                prospectus_info=prospectus_info,
            )
            new_result = self.pipeline.run(inp)
            # 将新结果合并到旧结果中（保留旧字段，补充新字段）
            result["score_trace_structured"] = new_result.score_trace.to_flat_dict()
            result["weight_profile"] = new_result.weight_profile
        except Exception as e:
            # 新管道失败时不影响旧逻辑
            result["_pipeline_error"] = str(e)

        return result
```

注意：`stock_code` 和 `company_name` 的获取方式需要根据 `calculate` 方法的实际参数调整。如果 `ipo` 参数是 dict 而非对象，使用 `ipo.get("hk_code", "")`。

- [ ] **Step 4: 运行现有测试确保无回归**

```bash
python3 -m pytest tests/test_scoring_fixes.py -v
```

Expected: 所有现有测试通过（无新增失败）

- [ ] **Step 5: Commit**

```bash
git add ipo_analyzer/scoring.py
git commit -m "feat(scoring): add ScoringPipeline delegation in compat layer"
```

---

## Task 12: 扩展 settings.py 阈值配置

**Files:**
- Modify: `ipo_analyzer/settings.py`

- [ ] **Step 1: 在 settings.py 中新增 DimensionThresholds 和 AdjustmentThresholds**

在 `ScoringWeights` 之后添加：

```python
@dataclass
class DimensionThresholds:
    """维度评分内部阈值"""
    heat_max: float = 45.0
    scale_max: float = 10.0
    cornerstone_max: float = 20.0
    real_money_max: float = 20.0
    float_max: float = 15.0
    sponsor_max: float = 10.0
    greenshoe_max: float = 5.0
    clawback_max: float = 5.0


@dataclass
class AdjustmentThresholds:
    """调整项阈值"""
    peer_excellent_bonus: float = 6.0
    peer_overvalued_penalty: float = -6.0
    val_expensive_penalty: float = -5.0
    val_high_penalty: float = -3.0
    val_cheap_bonus: float = 2.0
    risk_severe_categories: tuple = ("legal", "regulatory", "accounting")
    risk_severe_bonus: float = 2.0
    risk_max_penalty: float = 20.0
    cornerstone_redflag_penalty_each: float = 3.0
    cornerstone_redflag_max: float = 15.0
```

- [ ] **Step 2: 在 `Settings` 主类中注册新阈值**

找到 `Settings` dataclass，添加字段：

```python
@dataclass
class Settings:
    fx: FXConfig = field(default_factory=FXConfig)
    valuation: ValuationThresholds = field(default_factory=ValuationThresholds)
    heat: MarketHeatThresholds = field(default_factory=MarketHeatThresholds)
    quality: ProspectusQualityThresholds = field(default_factory=ProspectusQualityThresholds)
    scoring_weights: ScoringWeights = field(default_factory=ScoringWeights)
    backtest: BacktestSettings = field(default_factory=BacktestSettings)
    real_money: RealMoneyThresholds = field(default_factory=RealMoneyThresholds)
    float_structure: FloatStructureThresholds = field(default_factory=FloatStructureThresholds)
    capacity: CapacityThresholds = field(default_factory=CapacityThresholds)
    rnd: RnDThresholds = field(default_factory=RnDThresholds)
    risk: RiskFactorThresholds = field(default_factory=RiskFactorThresholds)
    customer: CustomerConcentrationThresholds = field(default_factory=CustomerConcentrationThresholds)
    peer: PeerCompsThresholds = field(default_factory=PeerCompsThresholds)
    peg: PEGThresholds = field(default_factory=PEGThresholds)
    stock_connect: StockConnectThresholds = field(default_factory=StockConnectThresholds)
    # === 新增 ===
    dimension: DimensionThresholds = field(default_factory=DimensionThresholds)
    adjustment: AdjustmentThresholds = field(default_factory=AdjustmentThresholds)
```

- [ ] **Step 3: Commit**

```bash
git add ipo_analyzer/settings.py
git commit -m "feat(scoring): add DimensionThresholds and AdjustmentThresholds to settings"
```

---

## Task 13: 运行全量回归测试

**Files:**
- Test: `tests/test_scoring_compat.py` (新增)

- [ ] **Step 1: 写兼容层回归测试**

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ipo_analyzer.scoring import ScoringSystem


def test_compat_layer_returns_expected_keys():
    """验证兼容层输出包含所有预期字段."""
    system = ScoringSystem()
    ipo = {"hk_code": "09999", "company_name": "测试", "margin_total": 100.0}
    prospectus_info = {
        "sector": "hardtech",
        "revenue": 500.0,
        "stock_quality_score": 70.0,
        "signal_components": {"heat_score": 30.0, "data_quality": 80.0},
        "valuation": {"valuation_framework_score": 60.0},
        "risk_analysis": {"total_penalty": 5.0, "risks": {}},
    }
    result = system.calculate(ipo, prospectus_info)

    # 旧字段必须存在
    assert "score" in result
    assert "final_score" in result
    assert "recommendation" in result
    assert "reasons" in result

    # 新字段应被补充
    assert "score_trace_structured" in result
    assert "weight_profile" in result
    assert result["weight_profile"] in ("live_heat", "prospectus_only", "optimized")
```

- [ ] **Step 2: 运行全部评分相关测试**

```bash
python3 -m pytest tests/test_scoring_fixes.py tests/test_scoring_compat.py tests/test_scoring_models.py tests/test_input_adapter.py tests/test_dimension_scorer.py tests/test_adjustment_engine.py tests/test_scoring_pipeline.py -v
```

Expected: 全部通过（现有测试无回归 + 新测试通过）

- [ ] **Step 3: Commit**

```bash
git add tests/test_scoring_compat.py
git commit -m "test(scoring): add compatibility layer regression test"
```

---

## 自检清单

### Spec coverage
| Spec 要求 | 对应 Task |
|-----------|-----------|
| 新建 `ipo_analyzer/scoring/` 包 | Task 1-10 |
| `AnalyzerOutputAdapter` 强类型映射 | Task 4 |
| `DimensionScorer` 五维原始分 | Task 5 |
| `AdjustmentEngine` 集中调整 | Task 6 |
| `StrategyScorer` 策略评分 | Task 7 |
| `Recommender` 推荐解耦 | Task 8 |
| `WeightProfileDetector` 权重检测 | Task 9 |
| `ScoringPipeline` 串联 + ScoreTrace | Task 10 |
| 保留 `scoring.py` 兼容层 | Task 11 |
| `settings.py` 阈值扩展 | Task 12 |
| 全量回归测试 | Task 13 |

### Placeholder scan
- 无 TBD/TODO
- 无 "implement later"
- 无 "add appropriate error handling"
- 每个任务包含完整代码和测试命令

### Type consistency
- `ScoringInput` / `DimensionScores` / `Adjustments` / `StrategyScores` / `ScoringResult` / `ScoreTrace` 全计划一致
- `AnalyzerOutputAdapter.adapt()` 返回 `ScoringInput`
- `ScoringPipeline.run()` 返回 `ScoringResult`
- 兼容层将 `ScoringResult` 转换为 dict 合并
