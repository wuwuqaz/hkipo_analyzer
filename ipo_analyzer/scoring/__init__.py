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
