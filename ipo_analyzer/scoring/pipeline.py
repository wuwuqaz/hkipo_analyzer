"""评分管道主类 — 串联所有评分组件."""

from __future__ import annotations

from .models import ScoringInput, ScoringResult, ScoreTrace


class ScoringPipeline:
    """评分管道 — 将在后续 Task 中实现完整逻辑."""

    def run(self, inp: ScoringInput) -> ScoringResult:
        # 占位实现，避免导入循环
        return ScoringResult()
