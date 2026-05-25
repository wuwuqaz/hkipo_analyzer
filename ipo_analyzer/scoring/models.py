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
    weight_profile: dict[str, Any] = field(default_factory=dict)
    debug_info: dict[str, Any] = field(default_factory=dict)
