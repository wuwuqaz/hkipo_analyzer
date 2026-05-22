"""将分析器输出的扁平 dict 映射为强类型 ScoringInput."""

from __future__ import annotations

from typing import Any

from .models import ScoringInput, CornerstoneInvestorInput, QualityDimensions
from ._utils import is_biotech


class AnalyzerOutputAdapter:
    """统一适配器: prospectus_info dict -> ScoringInput."""

    def adapt(self, stock_code: str, company_name: str, prospectus_info: dict[str, Any]) -> ScoringInput:
        return ScoringInput(stock_code=stock_code, company_name=company_name)
