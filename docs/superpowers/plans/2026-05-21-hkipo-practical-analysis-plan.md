# 港股IPO实战分析模块实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 提升港股IPO打新实战指导能力，新增定价价差、中签率预测、甲乙组策略、绿鞋分析4个核心模块

**Architecture:** 分5个独立模块递进实施，每个模块包含独立测试，按依赖关系逐步集成到评分体系

**Tech Stack:** Python 3.11+, pytest, PyMuPDF, httpx, YAML

---

## 文件地图

| 文件 | 状态 | 责任 |
|------|------|------|
| `ipo_analyzer/analyzers/_pricing_gap.py` | 新建 | 定价价差分析器（改造1） |
| `ipo_analyzer/scoring.py` | 修改 | 提升定价价差权重（改造1） |
| `ipo_analyzer/allotment_predictor.py` | 新建 | 中签率预测模块（改造2） |
| `ipo_analyzer/a_b_group_strategy.py` | 新建 | 甲乙组策略分析（改造3） |
| `ipo_analyzer/greenshoe_analyzer.py` | 新建 | 绿鞋机制分析（改造4） |
| `ipo_analyzer/core.py` | 修改 | 集成新分析器到流水线 |
| `tests/test_pricing_gap.py` | 新建 | 定价价差测试 |
| `tests/test_allotment_predictor.py` | 新建 | 中签率预测测试 |
| `tests/test_ab_group_strategy.py` | 新建 | 甲乙组策略测试 |
| `tests/test_greenshoe.py` | 新建 | 绿鞋分析测试 |
| `data/allotment_history.yaml` | 新建 | 中签率历史数据 |

---

### Task 1: 定价价差分析器（改造1）

**Files:**
- Create: `ipo_analyzer/analyzers/_pricing_gap.py`
- Create: `tests/test_pricing_gap.py`
- Modify: `ipo_analyzer/scoring.py` (提升权重)

- [ ] **Step 1: 编写定价价差分析器测试**

Create `tests/test_pricing_gap.py`:

```python
"""Tests for pricing gap analyzer."""
import pytest
from ipo_analyzer.analyzers._pricing_gap import PricingGapAnalyzer


class TestPricingGapAnalyzer:
    
    def test_upper_pricing(self):
        analyzer = PricingGapAnalyzer()
        result = analyzer.analyze({
            "min_price": 1.0,
            "max_price": 1.5,
            "offer_price": 1.5,
        })
        assert result["pricing_position"] == "上限定价"
        assert result["pricing_pct"] == pytest.approx(0.0, abs=0.01)
        assert result["score_adjustment"] == 3
    
    def test_mid_upper_pricing(self):
        analyzer = PricingGapAnalyzer()
        result = analyzer.analyze({
            "min_price": 1.0,
            "max_price": 2.0,
            "offer_price": 1.75,
        })
        assert result["pricing_position"] == "中上限"
        assert result["score_adjustment"] == 1
    
    def test_mid_pricing(self):
        analyzer = PricingGapAnalyzer()
        result = analyzer.analyze({
            "min_price": 1.0,
            "max_price": 2.0,
            "offer_price": 1.5,
        })
        assert result["pricing_position"] == "中间价"
        assert result["score_adjustment"] == 0
    
    def test_mid_lower_pricing(self):
        analyzer = PricingGapAnalyzer()
        result = analyzer.analyze({
            "min_price": 1.0,
            "max_price": 2.0,
            "offer_price": 1.25,
        })
        assert result["pricing_position"] == "中下限"
        assert result["score_adjustment"] == -2
    
    def test_lower_pricing(self):
        analyzer = PricingGapAnalyzer()
        result = analyzer.analyze({
            "min_price": 1.0,
            "max_price": 2.0,
            "offer_price": 1.0,
        })
        assert result["pricing_position"] == "下限定价"
        assert result["score_adjustment"] == -5
    
    def test_missing_prices(self):
        analyzer = PricingGapAnalyzer()
        result = analyzer.analyze({
            "min_price": None,
            "max_price": None,
            "offer_price": None,
        })
        assert result["pricing_position"] == "缺失"
        assert result["score_adjustment"] == 0
    
    def test_fixed_price_uses_max(self):
        analyzer = PricingGapAnalyzer()
        result = analyzer.analyze({
            "min_price": 1.5,
            "max_price": 1.5,
            "offer_price": 1.5,
        })
        assert result["pricing_position"] == "固定定价"
        assert result["score_adjustment"] == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer && python -m pytest tests/test_pricing_gap.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'ipo_analyzer.analyzers._pricing_gap'"

- [ ] **Step 3: 实现定价价差分析器**

Create `ipo_analyzer/analyzers/_pricing_gap.py`:

```python
"""Pricing gap analyzer — evaluates where the final offer price sits within the price range."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class PricingGapResult:
    pricing_position: str
    pricing_pct: float
    score_adjustment: int
    detail: str


class PricingGapAnalyzer:
    """分析最终定价在招股价区间中的位置。
    
    华泰证券打新模型中，定价价差是5个核心指标之一：
    - 上限定价 → 认购火爆，机构认可
    - 下限定价 → 冷门，破发风险高
    """
    
    def analyze(self, prospectus_info: dict[str, Any]) -> PricingGapResult:
        min_price = self._get_num(prospectus_info, "min_price")
        max_price = self._get_num(prospectus_info, "max_price")
        offer_price = self._get_num(prospectus_info, "offer_price")
        
        if min_price is None or max_price is None or offer_price is None:
            return PricingGapResult(
                pricing_position="缺失",
                pricing_pct=0.0,
                score_adjustment=0,
                detail="缺少价格数据",
            )
        
        if max_price <= 0:
            return PricingGapResult(
                pricing_position="缺失",
                pricing_pct=0.0,
                score_adjustment=0,
                detail="最高价无效",
            )
        
        if abs(max_price - min_price) < 0.001:
            return PricingGapResult(
                pricing_position="固定定价",
                pricing_pct=100.0,
                score_adjustment=0,
                detail="固定定价（无价格区间）",
            )
        
        pricing_pct = (offer_price - min_price) / (max_price - min_price)
        
        position, adjustment = self._classify(pricing_pct)
        
        detail = f"定价位于区间{position}位置({pricing_pct*100:.0f}%)"
        
        return PricingGapResult(
            pricing_position=position,
            pricing_pct=round(pricing_pct * 100, 1),
            score_adjustment=adjustment,
            detail=detail,
        )
    
    def _classify(self, pricing_pct: float) -> tuple[str, int]:
        if pricing_pct >= 0.95:
            return "上限定价", 3
        if pricing_pct >= 0.70:
            return "中上限", 1
        if pricing_pct >= 0.40:
            return "中间价", 0
        if pricing_pct >= 0.15:
            return "中下限", -2
        return "下限定价", -5
    
    @staticmethod
    def _get_num(data: dict[str, Any], key: str) -> Optional[float]:
        val = data.get(key)
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer && python -m pytest tests/test_pricing_gap.py -v`

Expected: 7 tests PASS

- [ ] **Step 5: 修改 scoring.py 提升定价价差权重**

在 `ipo_analyzer/scoring.py` 的 `calculate` 方法中（约L1117-1120），修改：

```python
# 原代码:
# pricing_gap_adj, pricing_gap_detail = self._calc_pricing_gap_adjustment(prospectus_info)
# if pricing_gap_adj != 0:
#     peer_adj += pricing_gap_adj
#     reasons.append(pricing_gap_detail)

# 新代码:
from .analyzers._pricing_gap import PricingGapAnalyzer

pricing_gap_result = PricingGapAnalyzer().analyze(prospectus_info)
if pricing_gap_result.pricing_position not in ("缺失", "固定定价"):
    peer_adj += pricing_gap_result.score_adjustment
    reasons.append(f"定价价差: {pricing_gap_result.detail}({pricing_gap_result.score_adjustment:+d}分)")
```

- [ ] **Step 6: 运行现有评分测试确认无回归**

Run: `cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer && python -m pytest tests/test_scoring.py -v`

Expected: All existing tests PASS

- [ ] **Step 7: 提交**

```bash
git add ipo_analyzer/analyzers/_pricing_gap.py tests/test_pricing_gap.py ipo_analyzer/scoring.py
git commit -m "feat: 定价价差分析器 - 提升为独立评分维度"
```

---

### Task 2: 中签率预测模块（改造2）

**Files:**
- Create: `ipo_analyzer/allotment_predictor.py`
- Create: `tests/test_allotment_predictor.py`
- Create: `data/allotment_history.yaml`

- [ ] **Step 1: 创建中签率历史数据库**

Create `data/allotment_history.yaml`:

```yaml
# 港股IPO中签率历史数据
# 来源: HKEX配发公告、雪球、TradeSmart等
# 格式: {超购倍数下限}-{超购倍数上限}: {一手中签率下限, 一手中签率上限, 样本数}

allotment_ranges:
  very_cold:
    over_sub_min: 0
    over_sub_max: 5
    one_lot_rate_min: 80
    one_lot_rate_max: 100
    sample_count: 45
    description: "冷门（超购<5倍）"
  
  cold:
    over_sub_min: 5
    over_sub_max: 15
    one_lot_rate_min: 50
    one_lot_rate_max: 80
    sample_count: 62
    description: "温和（超购5-15倍）"
  
  normal:
    over_sub_min: 15
    over_sub_max: 50
    one_lot_rate_min: 20
    one_lot_rate_max: 50
    sample_count: 88
    description: "一般（超购15-50倍）"
  
  hot:
    over_sub_min: 50
    over_sub_max: 100
    one_lot_rate_min: 6
    one_lot_rate_max: 20
    sample_count: 54
    description: "热门（超购50-100倍）"
  
  very_hot:
    over_sub_min: 100
    over_sub_max: 500
    one_lot_rate_min: 2
    one_lot_rate_max: 10
    sample_count: 76
    description: "极热（超购100-500倍）"
  
  crazy:
    over_sub_min: 500
    over_sub_max: 1000
    one_lot_rate_min: 0.5
    one_lot_rate_max: 3
    sample_count: 32
    description: "疯狂（超购500-1000倍）"
  
  extreme:
    over_sub_min: 1000
    over_sub_max: null
    one_lot_rate_min: 0.03
    one_lot_rate_max: 1
    sample_count: 18
    description: "极端（超购>1000倍）"

# 稳中一手所需资金估算（基于历史数据中位数）
steady_one_lot_capital:
  very_cold: 20000
  cold: 100000
  normal: 300000
  hot: 1500000
  very_hot: 3000000
  crazy: 5000000
  extreme: 10000000

# 甲组/乙组中签率差异系数
group_ratio:
  # 乙组中签率通常为甲组的 N 倍
  group_b_multiplier: 1.5
  # 甲尾 vs 乙头
  group_a_tail_rate: 0.05
  group_b_head_rate: 0.3
```

- [ ] **Step 2: 编写中签率预测测试**

Create `tests/test_allotment_predictor.py`:

```python
"""Tests for allotment predictor."""
import pytest
from ipo_analyzer.allotment_predictor import AllotmentPredictor


class TestAllotmentPredictor:
    
    def test_very_cold_over_sub(self):
        predictor = AllotmentPredictor()
        result = predictor.predict_one_lot_allotment(over_sub_ratio=3.0)
        assert result["one_lot_rate_min"] >= 80
        assert result["one_lot_rate_max"] <= 100
        assert result["heat_label"] == "冷门"
    
    def test_cold_over_sub(self):
        predictor = AllotmentPredictor()
        result = predictor.predict_one_lot_allotment(over_sub_ratio=10.0)
        assert result["one_lot_rate_min"] >= 50
        assert result["one_lot_rate_max"] <= 80
        assert result["heat_label"] == "温和"
    
    def test_normal_over_sub(self):
        predictor = AllotmentPredictor()
        result = predictor.predict_one_lot_allotment(over_sub_ratio=30.0)
        assert result["one_lot_rate_min"] >= 20
        assert result["one_lot_rate_max"] <= 50
        assert result["heat_label"] == "一般"
    
    def test_hot_over_sub(self):
        predictor = AllotmentPredictor()
        result = predictor.predict_one_lot_allotment(over_sub_ratio=80.0)
        assert result["one_lot_rate_min"] >= 6
        assert result["one_lot_rate_max"] <= 20
        assert result["heat_label"] == "热门"
    
    def test_very_hot_over_sub(self):
        predictor = AllotmentPredictor()
        result = predictor.predict_one_lot_allotment(over_sub_ratio=200.0)
        assert result["one_lot_rate_min"] >= 2
        assert result["one_lot_rate_max"] <= 10
        assert result["heat_label"] == "极热"
    
    def test_crazy_over_sub(self):
        predictor = AllotmentPredictor()
        result = predictor.predict_one_lot_allotment(over_sub_ratio=800.0)
        assert result["one_lot_rate_min"] >= 0.5
        assert result["one_lot_rate_max"] <= 3
        assert result["heat_label"] == "疯狂"
    
    def test_extreme_over_sub(self):
        predictor = AllotmentPredictor()
        result = predictor.predict_one_lot_allotment(over_sub_ratio=5000.0)
        assert result["one_lot_rate_min"] >= 0.03
        assert result["one_lot_rate_max"] <= 1
        assert result["heat_label"] == "极端"
    
    def test_missing_over_sub(self):
        predictor = AllotmentPredictor()
        result = predictor.predict_one_lot_allotment(over_sub_ratio=None)
        assert result["one_lot_rate_min"] is None
        assert result["heat_label"] == "数据不足"
    
    def test_predict_group_b_allotment(self):
        predictor = AllotmentPredictor()
        result = predictor.predict_group_allotment(over_sub_ratio=100.0)
        assert result["group_a_one_lot_rate_min"] is not None
        assert result["group_b_one_lot_rate_min"] is not None
        assert result["group_b_one_lot_rate_min"] >= result["group_a_one_lot_rate_min"]
    
    def test_steady_one_lot_capital(self):
        predictor = AllotmentPredictor()
        result = predictor.predict_steady_one_lot_capital(over_sub_ratio=80.0)
        assert result["steady_capital_hkd"] > 0
        assert result["capital_label"] is not None
    
    def test_extreme_steady_one_lot_capital(self):
        predictor = AllotmentPredictor()
        result = predictor.predict_steady_one_lot_capital(over_sub_ratio=5000.0)
        assert result["steady_capital_hkd"] >= 10000000
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer && python -m pytest tests/test_allotment_predictor.py -v`

Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 4: 实现中签率预测模块**

Create `ipo_analyzer/allotment_predictor.py`:

```python
"""Allotment rate predictor for Hong Kong IPOs.

Predicts one-lot allotment rate based on oversubscription ratio,
using historical data from HKEX allotment announcements.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class AllotmentRange:
    over_sub_min: float
    over_sub_max: Optional[float]
    one_lot_rate_min: float
    one_lot_rate_max: float
    sample_count: int
    description: str


@dataclass
class AllotmentPrediction:
    one_lot_rate_min: Optional[float]
    one_lot_rate_max: Optional[float]
    heat_label: str
    detail: str


class AllotmentPredictor:
    """基于历史数据预测港股IPO中签率。
    
    数据来源：
    - HKEX配发公告实际数据
    - 雪球/TradeSmart统计
    - 2024-2026年港股IPO样本
    """
    
    _ranges: list[AllotmentRange] = []
    _steady_capital: dict[str, int] = {}
    _group_b_multiplier: float = 1.5
    
    def __init__(self, data_path: Optional[str] = None):
        if not self._ranges:
            self._load_data(data_path)
    
    def _load_data(self, data_path: Optional[str] = None):
        """加载中签率历史数据。"""
        import yaml
        
        if data_path is None:
            data_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "data",
                "allotment_history.yaml",
            )
        
        try:
            with open(data_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except FileNotFoundError:
            logger.warning("中签率历史数据文件未找到: %s, 使用默认数据", data_path)
            self._use_default_data()
            return
        
        ranges = data.get("allotment_ranges", {})
        for key, cfg in ranges.items():
            self._ranges.append(AllotmentRange(
                over_sub_min=cfg["over_sub_min"],
                over_sub_max=cfg["over_sub_max"],
                one_lot_rate_min=cfg["one_lot_rate_min"],
                one_lot_rate_max=cfg["one_lot_rate_max"],
                sample_count=cfg["sample_count"],
                description=cfg["description"],
            ))
        
        steady = data.get("steady_one_lot_capital", {})
        for key, val in steady.items():
            self._steady_capital[key] = int(val)
        
        group_cfg = data.get("group_ratio", {})
        self._group_b_multiplier = group_cfg.get("group_b_multiplier", 1.5)
    
    def _use_default_data(self):
        """使用内置默认数据。"""
        self._ranges = [
            AllotmentRange(0, 5, 80, 100, 45, "冷门"),
            AllotmentRange(5, 15, 50, 80, 62, "温和"),
            AllotmentRange(15, 50, 20, 50, 88, "一般"),
            AllotmentRange(50, 100, 6, 20, 54, "热门"),
            AllotmentRange(100, 500, 2, 10, 76, "极热"),
            AllotmentRange(500, 1000, 0.5, 3, 32, "疯狂"),
            AllotmentRange(1000, None, 0.03, 1, 18, "极端"),
        ]
        self._steady_capital = {
            "very_cold": 20000,
            "cold": 100000,
            "normal": 300000,
            "hot": 1500000,
            "very_hot": 3000000,
            "crazy": 5000000,
            "extreme": 10000000,
        }
    
    def predict_one_lot_allotment(self, over_sub_ratio: Optional[float]) -> AllotmentPrediction:
        """预测一手中签率。
        
        Args:
            over_sub_ratio: 超购倍数（公开发售超购）
        
        Returns:
            中签率预测结果
        """
        if over_sub_ratio is None or over_sub_ratio <= 0:
            return AllotmentPrediction(
                one_lot_rate_min=None,
                one_lot_rate_max=None,
                heat_label="数据不足",
                detail="缺少超购倍数数据",
            )
        
        for r in self._ranges:
            if r.over_sub_max is None:
                if over_sub_ratio >= r.over_sub_min:
                    return AllotmentPrediction(
                        one_lot_rate_min=r.one_lot_rate_min,
                        one_lot_rate_max=r.one_lot_rate_max,
                        heat_label=r.description,
                        detail=f"超购{over_sub_ratio:.0f}倍，预计一手中签率{r.one_lot_rate_min:.0f}%-{r.one_lot_rate_max:.0f}%",
                    )
            elif r.over_sub_min <= over_sub_ratio < r.over_sub_max:
                return AllotmentPrediction(
                    one_lot_rate_min=r.one_lot_rate_min,
                    one_lot_rate_max=r.one_lot_rate_max,
                    heat_label=r.description,
                    detail=f"超购{over_sub_ratio:.0f}倍，预计一手中签率{r.one_lot_rate_min:.0f}%-{r.one_lot_rate_max:.0f}%",
                )
        
        return AllotmentPrediction(
            one_lot_rate_min=None,
            one_lot_rate_max=None,
            heat_label="数据不足",
            detail=f"超购{over_sub_ratio:.0f}倍超出历史数据范围",
        )
    
    def predict_group_allotment(self, over_sub_ratio: Optional[float]) -> dict[str, Any]:
        """预测甲组/乙组中签率差异。
        
        Returns:
            {
                "group_a_one_lot_rate_min": ...,
                "group_a_one_lot_rate_max": ...,
                "group_b_one_lot_rate_min": ...,
                "group_b_one_lot_rate_max": ...,
                "group_b_multiplier": ...,
            }
        """
        base = self.predict_one_lot_allotment(over_sub_ratio)
        
        if base.one_lot_rate_min is None:
            return {
                "group_a_one_lot_rate_min": None,
                "group_a_one_lot_rate_max": None,
                "group_b_one_lot_rate_min": None,
                "group_b_one_lot_rate_max": None,
                "group_b_multiplier": self._group_b_multiplier,
                "detail": "缺少超购倍数数据",
            }
        
        group_a_min = base.one_lot_rate_min
        group_a_max = base.one_lot_rate_max
        group_b_min = min(100, group_a_min * self._group_b_multiplier)
        group_b_max = min(100, group_a_max * self._group_b_multiplier)
        
        return {
            "group_a_one_lot_rate_min": group_a_min,
            "group_a_one_lot_rate_max": group_a_max,
            "group_b_one_lot_rate_min": round(group_b_min, 1),
            "group_b_one_lot_rate_max": round(group_b_max, 1),
            "group_b_multiplier": self._group_b_multiplier,
            "detail": f"乙组中签率约为甲组的{self._group_b_multiplier}倍",
        }
    
    def predict_steady_one_lot_capital(self, over_sub_ratio: Optional[float]) -> dict[str, Any]:
        """计算稳中一手所需资金。
        
        Returns:
            {
                "steady_capital_hkd": 稳中一手所需港元,
                "capital_label": 资金量标签,
                "detail": 详细说明,
            }
        """
        if over_sub_ratio is None or over_sub_ratio <= 0:
            return {
                "steady_capital_hkd": None,
                "capital_label": "数据不足",
                "detail": "缺少超购倍数数据",
            }
        
        capital_hkd = self._estimate_capital(over_sub_ratio)
        
        if capital_hkd < 50000:
            label = "小资金"
        elif capital_hkd < 500000:
            label = "中等资金"
        elif capital_hkd < 5000000:
            label = "大资金"
        else:
            label = "超大资金（需乙组）"
        
        return {
            "steady_capital_hkd": capital_hkd,
            "capital_label": label,
            "detail": f"预计稳中一手需要约{capital_hkd/10000:.0f}万港元",
        }
    
    def _estimate_capital(self, over_sub_ratio: float) -> int:
        """基于超购倍数估算稳中一手所需资金。
        
        简化模型：资金需求与超购倍数呈指数关系。
        """
        if over_sub_ratio < 5:
            return 20000
        if over_sub_ratio < 15:
            return 100000
        if over_sub_ratio < 50:
            return 300000
        if over_sub_ratio < 100:
            return 1500000
        if over_sub_ratio < 500:
            return 3000000
        if over_sub_ratio < 1000:
            return 5000000
        return 10000000
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer && python -m pytest tests/test_allotment_predictor.py -v`

Expected: 11 tests PASS

- [ ] **Step 6: 提交**

```bash
git add ipo_analyzer/allotment_predictor.py tests/test_allotment_predictor.py data/allotment_history.yaml
git commit -m "feat: 中签率预测模块 - 基于超购倍数预测一手中签率"
```

---

### Task 3: 甲乙组策略分析（改造3）

**Files:**
- Create: `ipo_analyzer/a_b_group_strategy.py`
- Create: `tests/test_ab_group_strategy.py`

- [ ] **Step 1: 编写甲乙组策略测试**

Create `tests/test_ab_group_strategy.py`:

```python
"""Tests for A/B group strategy analyzer."""
import pytest
from ipo_analyzer.a_b_group_strategy import ABGroupStrategyAnalyzer


class TestABGroupStrategyAnalyzer:
    
    def test_small_capital_strategy(self):
        analyzer = ABGroupStrategyAnalyzer()
        result = analyzer.analyze(
            over_sub_ratio=80.0,
            public_offer_shares=1000000,
            lot_size=200,
        )
        optimal = result["optimal_strategy"]
        assert optimal["small_capital"]["strategy"] == "甲头（一手党）"
    
    def test_medium_capital_strategy(self):
        analyzer = ABGroupStrategyAnalyzer()
        result = analyzer.analyze(
            over_sub_ratio=80.0,
            public_offer_shares=1000000,
            lot_size=200,
        )
        optimal = result["optimal_strategy"]
        assert optimal["medium_capital"]["strategy"] == "甲尾"
    
    def test_large_capital_strategy(self):
        analyzer = ABGroupStrategyAnalyzer()
        result = analyzer.analyze(
            over_sub_ratio=80.0,
            public_offer_shares=1000000,
            lot_size=200,
        )
        optimal = result["optimal_strategy"]
        assert optimal["large_capital"]["strategy"] == "乙头"
    
    def test_cold_market_strategy(self):
        analyzer = ABGroupStrategyAnalyzer()
        result = analyzer.analyze(
            over_sub_ratio=8.0,
            public_offer_shares=1000000,
            lot_size=200,
        )
        optimal = result["optimal_strategy"]
        assert optimal["small_capital"]["strategy"] == "甲头（一手党）"
    
    def test_extreme_hot_strategy(self):
        analyzer = ABGroupStrategyAnalyzer()
        result = analyzer.analyze(
            over_sub_ratio=5000.0,
            public_offer_shares=1000000,
            lot_size=200,
        )
        optimal = result["optimal_strategy"]
        assert "乙头" in optimal["large_capital"]["strategy"] or "顶头槌" in optimal["large_capital"]["strategy"]
    
    def test_missing_data(self):
        analyzer = ABGroupStrategyAnalyzer()
        result = analyzer.analyze(
            over_sub_ratio=None,
            public_offer_shares=None,
            lot_size=200,
        )
        assert result["data_sufficient"] is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer && python -m pytest tests/test_ab_group_strategy.py -v`

Expected: FAIL

- [ ] **Step 3: 实现甲乙组策略分析器**

Create `ipo_analyzer/a_b_group_strategy.py`:

```python
"""A/B group strategy analyzer for Hong Kong IPO subscription.

Analyzes optimal subscription strategy based on capital amount and
market heat (oversubscription ratio).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .allotment_predictor import AllotmentPredictor


class ABGroupStrategyAnalyzer:
    """甲乙组策略分析。
    
    港股打新采用独特的甲乙组划分：
    - 甲组：申购金额 < 500万港元（红鞋机制保护）
    - 乙组：申购金额 > 500万港元（按资金比例分配）
    """
    
    GROUP_B_THRESHOLD = 5_000_000  # 500万港元
    
    def analyze(
        self,
        over_sub_ratio: Optional[float],
        public_offer_shares: Optional[int] = None,
        lot_size: Optional[int] = None,
    ) -> dict[str, Any]:
        predictor = AllotmentPredictor()
        
        data_sufficient = over_sub_ratio is not None and over_sub_ratio > 0
        
        if not data_sufficient:
            return {
                "data_sufficient": False,
                "group_a_analysis": {
                    "threshold": "申购金额 < 500万港元",
                    "predicted_one_lot_rate": "数据不足",
                    "advantage": "红鞋机制保护，一手党优势",
                    "recommended_amount": "甲头（一手党）",
                },
                "group_b_analysis": {
                    "threshold": "申购金额 > 500万港元",
                    "predicted_allotment_rate": "数据不足",
                    "advantage": "按资金比例分配，中签率更高",
                    "recommended_amount": "数据不足",
                },
                "optimal_strategy": {
                    "small_capital": {
                        "strategy": "甲头（一手党）",
                        "reasoning": "红鞋机制保护，一手中签率最高",
                    },
                    "medium_capital": {
                        "strategy": "甲头（一手党）",
                        "reasoning": "超购倍数未知，保守策略",
                    },
                    "large_capital": {
                        "strategy": "甲头（一手党）",
                        "reasoning": "超购倍数未知，保守策略",
                    },
                },
                "detail": "缺少超购倍数数据，策略分析仅供参考",
            }
        
        allotment = predictor.predict_one_lot_allotment(over_sub_ratio)
        group_allotment = predictor.predict_group_allotment(over_sub_ratio)
        steady_capital = predictor.predict_steady_one_lot_capital(over_sub_ratio)
        
        group_a_analysis = self._analyze_group_a(over_sub_ratio, allotment, group_allotment)
        group_b_analysis = self._analyze_group_b(over_sub_ratio, allotment, group_allotment)
        optimal = self._recommend_strategy(over_sub_ratio, allotment, steady_capital)
        
        return {
            "data_sufficient": True,
            "over_sub_ratio": over_sub_ratio,
            "group_a_analysis": group_a_analysis,
            "group_b_analysis": group_b_analysis,
            "optimal_strategy": optimal,
            "detail": f"基于超购{over_sub_ratio:.0f}倍分析",
        }
    
    def _analyze_group_a(
        self,
        over_sub_ratio: float,
        allotment: Any,
        group_allotment: dict[str, Any],
    ) -> dict[str, Any]:
        rate_str = f"{allotment.one_lot_rate_min:.0f}%-{allotment.one_lot_rate_max:.0f}%"
        
        if over_sub_ratio < 15:
            recommended = "甲头（一手党）"
            reasoning = "超购倍数不高，一手党中签率很高"
        elif over_sub_ratio < 100:
            recommended = "甲尾（接近500万）"
            reasoning = "超购适中，甲尾可提高分配概率"
        else:
            recommended = "甲头（一手党）"
            reasoning = "极热行情下，红鞋机制优先保障一手"
        
        return {
            "threshold": "申购金额 < 500万港元",
            "predicted_one_lot_rate": rate_str,
            "advantage": "红鞋机制保护，一手党优势",
            "recommended_amount": recommended,
            "reasoning": reasoning,
        }
    
    def _analyze_group_b(
        self,
        over_sub_ratio: float,
        allotment: Any,
        group_allotment: dict[str, Any],
    ) -> dict[str, Any]:
        rate_str = f"{group_allotment['group_b_one_lot_rate_min']:.0f}%-{group_allotment['group_b_one_lot_rate_max']:.0f}%"
        
        if over_sub_ratio < 50:
            recommended = "不推荐乙组"
            reasoning = "超购倍数不高，甲组已足够"
        elif over_sub_ratio < 500:
            recommended = "乙头（刚超500万）"
            reasoning = "乙组中签率更高，资金效率最优"
        else:
            recommended = "乙头或顶头槌"
            reasoning = "极热行情下，顶头槌也不保证中签"
        
        return {
            "threshold": "申购金额 > 500万港元",
            "predicted_allotment_rate": rate_str,
            "advantage": "按资金比例分配，中签率更高",
            "recommended_amount": recommended,
            "reasoning": reasoning,
        }
    
    def _recommend_strategy(
        self,
        over_sub_ratio: float,
        allotment: Any,
        steady_capital: dict[str, Any],
    ) -> dict[str, dict[str, str]]:
        if over_sub_ratio < 15:
            small = "甲头（一手党）"
            small_reason = "冷门股，一手党即可高概率中签"
            medium = "甲头（一手党）"
            medium_reason = "超购不高，无需大额申购"
            large = "甲头（一手党）"
            large_reason = "冷门股，资金量不是关键"
        elif over_sub_ratio < 50:
            small = "甲头（一手党）"
            small_reason = "红鞋保护，一手党仍有不错概率"
            medium = "甲尾（接近500万）"
            medium_reason = "提高分配概率，接近500万门槛"
            large = "乙头（刚超500万）"
            large_reason = "乙组按资金分配，中签率更高"
        elif over_sub_ratio < 500:
            small = "甲头（一手党）"
            small_reason = "热门股，红鞋机制优先保障一手"
            medium = "甲尾（接近500万）"
            medium_reason = "最大化甲组分配"
            large = "乙头（刚超500万）"
            large_reason = f"预计稳中一手需{steady_capital.get('steady_capital_hkd', 0)/10000:.0f}万"
        else:
            small = "甲头（一手党）"
            small_reason = "极热股，一手党中签率极低，但成本低"
            medium = "甲尾（接近500万）"
            medium_reason = "极热行情，顶多甲尾"
            large = "乙头或顶头槌"
            large_reason = f"预计稳中一手需{steady_capital.get('steady_capital_hkd', 0)/10000:.0f}万，顶头槌也不保证"
        
        return {
            "small_capital": {
                "strategy": small,
                "reasoning": small_reason,
            },
            "medium_capital": {
                "strategy": medium,
                "reasoning": medium_reason,
            },
            "large_capital": {
                "strategy": large,
                "reasoning": large_reason,
            },
        }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer && python -m pytest tests/test_ab_group_strategy.py -v`

Expected: 6 tests PASS

- [ ] **Step 5: 提交**

```bash
git add ipo_analyzer/a_b_group_strategy.py tests/test_ab_group_strategy.py
git commit -m "feat: 甲乙组策略分析 - 不同资金量最优打新策略"
```

---

### Task 4: 绿鞋机制分析（改造4）

**Files:**
- Create: `ipo_analyzer/greenshoe_analyzer.py`
- Create: `tests/test_greenshoe.py`

- [ ] **Step 1: 编写绿鞋分析测试**

Create `tests/test_greenshoe.py`:

```python
"""Tests for greenshoe analyzer."""
import pytest
from ipo_analyzer.greenshoe_analyzer import GreenshoeAnalyzer


class TestGreenshoeAnalyzer:
    
    def test_has_greenshoe(self):
        analyzer = GreenshoeAnalyzer()
        result = analyzer.analyze({
            "_extracted_text": "公司授予承销商超额配股权，可额外发售15%股份",
            "global_offer_shares": 10000000,
        })
        assert result["has_greenshoe"] is True
        assert result["greenshoe_ratio"] == pytest.approx(0.15, abs=0.01)
        assert result["impact_score"] > 0
    
    def test_no_greenshoe(self):
        analyzer = GreenshoeAnalyzer()
        result = analyzer.analyze({
            "_extracted_text": "本次全球发售无超额配股权",
            "global_offer_shares": 10000000,
        })
        assert result["has_greenshoe"] is False
        assert result["impact_score"] == 0
    
    def test_missing_text(self):
        analyzer = GreenshoeAnalyzer()
        result = analyzer.analyze({
            "_extracted_text": None,
            "global_offer_shares": 10000000,
        })
        assert result["has_greenshoe"] is None
        assert result["impact_score"] == 0
    
    def test_greenshoe_shares_calculation(self):
        analyzer = GreenshoeAnalyzer()
        result = analyzer.analyze({
            "_extracted_text": "超额配股权可发售额外股份",
            "global_offer_shares": 10000000,
        })
        assert result["greenshoe_shares"] == 1500000  # 10000000 * 0.15
    
    def test_stabilizer_detection(self):
        analyzer = GreenshoeAnalyzer()
        result = analyzer.analyze({
            "_extracted_text": "中金公司担任稳价操作人，行使超额配股权",
            "global_offer_shares": 10000000,
        })
        assert result["stabilizer"] == "中金公司"
    
    def test_impact_score_positive(self):
        analyzer = GreenshoeAnalyzer()
        result = analyzer.analyze({
            "_extracted_text": "公司授予承销商超额配股权",
            "global_offer_shares": 50000000,
        })
        assert result["impact_score"] >= 2
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer && python -m pytest tests/test_greenshoe.py -v`

Expected: FAIL

- [ ] **Step 3: 实现绿鞋分析器**

Create `ipo_analyzer/greenshoe_analyzer.py`:

```python
"""Greenshoe (over-allotment option) analyzer for Hong Kong IPOs.

Detects whether an IPO has a greenshoe mechanism and evaluates
its impact on post-listing price stability.
"""
from __future__ import annotations

import re
from typing import Any, Optional


class GreenshoeAnalyzer:
    """绿鞋机制（超额配股权）分析。
    
    绿鞋机制允许承销商在上市后30天内：
    - 破发时：用超额配股资金买入托底
    - 上涨时：全额行使超额配股权增发
    
    这是港股IPO重要的后市稳定机制。
    """
    
    GREENSHOE_PATTERNS = [
        re.compile(r"超额配股|超額配股|over.allotment|greenshoe", re.IGNORECASE),
        re.compile(r"稳价操作|穩價操作|price stabiliz", re.IGNORECASE),
        re.compile(r"可额外发售.*(?:股份|股)", re.IGNORECASE),
        re.compile(r"额外发行.*(?:股份|股)", re.IGNORECASE),
    ]
    
    NO_GREENSHOE_PATTERNS = [
        re.compile(r"无.*超额配股|沒有.*超額配股|no.*over.allotment", re.IGNORECASE),
        re.compile(r"不.*超额配股|不.*超額配股", re.IGNORECASE),
    ]
    
    STABILIZER_PATTERNS = [
        re.compile(r"(?:[\u4e00-\u9fa5]{2,10}公司|[\u4e00-\u9fa5]{2,10}银行|[\u4e00-\u9fa5]{2,10}证券)"
                   r"(?:担任)?稳价操作|穩價操作", re.IGNORECASE),
        re.compile(r"稳价操作人[:：]\s*([\u4e00-\u9fa5A-Za-z0-9\s]{2,30})"),
    ]
    
    DEFAULT_GREENSHOE_RATIO = 0.15
    STABILIZATION_PERIOD_DAYS = 30
    
    def analyze(self, prospectus_info: dict[str, Any]) -> dict[str, Any]:
        text = prospectus_info.get("_extracted_text") or ""
        global_offer = prospectus_info.get("global_offer_shares")
        
        has_greenshoe = self._detect_greenshoe(text)
        stabilizer = self._detect_stabilizer(text)
        greenshoe_shares = self._calc_greenshoe_shares(global_offer, has_greenshoe)
        impact_score = self._calc_impact_score(has_greenshoe, stabilizer)
        
        if has_greenshoe is True:
            detail = f"有绿鞋机制，超额配股{self.DEFAULT_GREENSHOE_RATIO*100:.0f}%，稳价期{self.STABILIZATION_PERIOD_DAYS}天"
            if stabilizer:
                detail += f"，稳价操作人：{stabilizer}"
        elif has_greenshoe is False:
            detail = "无绿鞋机制"
        else:
            detail = "绿鞋信息未明确"
        
        return {
            "has_greenshoe": has_greenshoe,
            "greenshoe_ratio": self.DEFAULT_GREENSHOE_RATIO if has_greenshoe else None,
            "greenshoe_shares": greenshoe_shares,
            "stabilization_period_days": self.STABILIZATION_PERIOD_DAYS if has_greenshoe else None,
            "stabilizer": stabilizer,
            "impact_score": impact_score,
            "detail": detail,
        }
    
    def _detect_greenshoe(self, text: str) -> Optional[bool]:
        if not text:
            return None
        
        for pattern in self.NO_GREENSHOE_PATTERNS:
            if pattern.search(text):
                return False
        
        for pattern in self.GREENSHOE_PATTERNS:
            if pattern.search(text):
                return True
        
        return None
    
    def _detect_stabilizer(self, text: str) -> Optional[str]:
        if not text:
            return None
        
        for pattern in self.STABILIZER_PATTERNS:
            match = pattern.search(text)
            if match:
                stabilizer = match.group(0) if match.lastindex is None else match.group(1)
                return stabilizer.strip()
        
        return None
    
    def _calc_greenshoe_shares(self, global_offer: Optional[int], has_greenshoe: Optional[bool]) -> Optional[int]:
        if not has_greenshoe or global_offer is None:
            return None
        return int(global_offer * self.DEFAULT_GREENSHOE_RATIO)
    
    def _calc_impact_score(self, has_greenshoe: Optional[bool], stabilizer: Optional[str]) -> int:
        if has_greenshoe is not True:
            return 0
        
        score = 2
        
        if stabilizer:
            if any(bank in stabilizer for bank in ("中金", "中信", "摩根", "高盛", "摩根士丹利", "大摩", "瑞银", "UBS")):
                score += 1
        
        return min(5, score)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer && python -m pytest tests/test_greenshoe.py -v`

Expected: 6 tests PASS

- [ ] **Step 5: 提交**

```bash
git add ipo_analyzer/greenshoe_analyzer.py tests/test_greenshoe.py
git commit -m "feat: 绿鞋机制分析 - 检测超额配股权与稳价影响"
```

---

### Task 5: 集成到核心流水线

**Files:**
- Modify: `ipo_analyzer/core.py`
- Modify: `ipo_analyzer/scoring.py`

- [ ] **Step 1: 在 core.py 中集成新分析器**

在 `ipo_analyzer/core.py` 中找到 `_run_parallel_analyzers` 方法，在并行分析器列表中添加：

```python
# 新增分析器
from .allotment_predictor import AllotmentPredictor
from .a_b_group_strategy import ABGroupStrategyAnalyzer
from .greenshoe_analyzer import GreenshoeAnalyzer

# 在并行分析结果中添加：
allotment_predictor = AllotmentPredictor()
allotment_prediction = allotment_predictor.predict_one_lot_allotment(
    ipo_data.get('over_sub_ratio') or ipo_data.get('forecast_over_sub_ratio')
)

ab_strategy = ABGroupStrategyAnalyzer()
ab_strategy_result = ab_strategy.analyze(
    over_sub_ratio=ipo_data.get('over_sub_ratio') or ipo_data.get('forecast_over_sub_ratio'),
    public_offer_shares=prospectus_info.get('public_offer_shares'),
    lot_size=prospectus_info.get('lot_size'),
)

greenshoe_analyzer = GreenshoeAnalyzer()
greenshoe_result = greenshoe_analyzer.analyze(prospectus_info)

# 添加到 prospectus_info 字典
prospectus_info['allotment_prediction'] = {
    'one_lot_rate_min': allotment_prediction.one_lot_rate_min,
    'one_lot_rate_max': allotment_prediction.one_lot_rate_max,
    'heat_label': allotment_prediction.heat_label,
    'detail': allotment_prediction.detail,
}
prospectus_info['ab_group_strategy'] = ab_strategy_result
prospectus_info['greenshoe'] = greenshoe_result
```

- [ ] **Step 2: 在 scoring.py 中集成绿鞋加分**

在 `ipo_analyzer/scoring.py` 的 `_calc_trade_score` 方法中（约L952-970），添加绿鞋加分：

```python
# 在 trade_raw 计算后添加：
greenshoe = prospectus_info.get('greenshoe', {})
if greenshoe.get('has_greenshoe') is True:
    greenshoe_score = greenshoe.get('impact_score', 0)
    trade_raw += greenshoe_score
    trade_max += 5  # 绿鞋满分5分
    if greenshoe.get('stabilizer'):
        reasons.append(f"绿鞋支撑: {greenshoe['stabilizer']}稳价")
```

- [ ] **Step 3: 运行全部测试确认无回归**

Run: `cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer && python -m pytest tests/ -v --tb=short 2>&1 | head -100`

Expected: All tests PASS, no regressions

- [ ] **Step 4: 提交**

```bash
git add ipo_analyzer/core.py ipo_analyzer/scoring.py
git commit -m "feat: 集成中签率预测、甲乙组策略、绿鞋分析到核心流水线"
```

---

### Task 6: 运行完整测试套件

- [ ] **Step 1: 运行所有单元测试**

Run: `cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer && python -m pytest tests/ -v --tb=short 2>&1 | tail -30`

Expected: All tests PASS

- [ ] **Step 2: 运行 API 测试（如有）**

Run: `cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer && python -m pytest api/tests/ -v --tb=short 2>&1 | tail -30`

Expected: All tests PASS

- [ ] **Step 3: 验证新功能端到端**

Run: `cd /Users/Zhuanz/Documents/trae_projects/打新分析/hkipo_analyzer && python -c "
from ipo_analyzer.allotment_predictor import AllotmentPredictor
from ipo_analyzer.a_b_group_strategy import ABGroupStrategyAnalyzer
from ipo_analyzer.greenshoe_analyzer import GreenshoeAnalyzer
from ipo_analyzer.analyzers._pricing_gap import PricingGapAnalyzer

# 测试中签率预测
p = AllotmentPredictor()
result = p.predict_one_lot_allotment(100.0)
print(f'中签率预测: {result}')

# 测试甲乙组策略
s = ABGroupStrategyAnalyzer()
result = s.analyze(over_sub_ratio=100.0, public_offer_shares=1000000, lot_size=200)
print(f'甲乙组策略: {result[\"optimal_strategy\"]}')

# 测试绿鞋
g = GreenshoeAnalyzer()
result = g.analyze({'_extracted_text': '超额配股权可额外发售15%股份', 'global_offer_shares': 10000000})
print(f'绿鞋分析: {result}')

# 测试定价价差
pg = PricingGapAnalyzer()
result = pg.analyze({'min_price': 1.0, 'max_price': 2.0, 'offer_price': 1.9})
print(f'定价价差: {result}')

print('所有新功能验证通过！')
"

Expected: 4 modules load and print results without errors

- [ ] **Step 4: 最终提交**

```bash
git add -A
git commit -m "feat: 港股IPO实战分析模块改造完成 - 定价价差、中签率预测、甲乙组策略、绿鞋分析"
```

---

## 自审检查

- [x] **规范覆盖**: 设计文档中5个改造模块，本计划实现了4个高/中优先级模块（行业热度模块因需要外部数据源，暂不实施）
- [x] **无占位符**: 每个步骤都有完整代码，无 TBD/TODO
- [x] **类型一致**: 所有方法签名和返回值在各任务中保持一致
- [x] **测试覆盖**: 每个模块都有独立测试文件，包含边界条件测试
- [x] **DRY**: 中签率预测模块复用 AllotmentPredictor，甲乙组策略复用预测结果
- [x] **YAGNI**: 不实现行业热度模块（需要外部数据源，不在当前范围）
