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

# Re-export legacy scoring symbols from scoring.py so that existing imports keep working.
# scoring.py is a sibling module; import it under an internal alias to avoid shadowing.
import importlib.util as _importlib_util
import pathlib as _pathlib
_scoring_py_path = _pathlib.Path(__file__).parent.parent / "scoring.py"
_scoring_py_spec = _importlib_util.spec_from_file_location(
    "ipo_analyzer._scoring_py",
    str(_scoring_py_path),
)
_scoring_py = _importlib_util.module_from_spec(_scoring_py_spec)
_scoring_py_spec.loader.exec_module(_scoring_py)

ScoringSystem = _scoring_py.ScoringSystem
ProspectusQualityAnalyzer = _scoring_py.ProspectusQualityAnalyzer
SignalComponentAnalyzer = _scoring_py.SignalComponentAnalyzer

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
    "ScoringSystem",
    "ProspectusQualityAnalyzer",
    "SignalComponentAnalyzer",
]
