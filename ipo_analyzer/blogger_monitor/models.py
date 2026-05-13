from pydantic import BaseModel, Field
from typing import Dict, List, Literal, Optional


class SearchResultModel(BaseModel):
    title: str = ""
    url: str = ""
    snippet: str = ""
    content: str = ""
    published_at: Optional[str] = None
    source_domain: str = ""


class RelevanceResultModel(BaseModel):
    is_relevant: bool = False
    contains_opinion: bool = False
    relevance_score: float = Field(ge=0, le=1, default=0.0)
    reason: str = ""


class BloggerOpinionModel(BaseModel):
    stock_code: str = ""
    company_name: str = ""
    source: str = ""
    author: str = ""
    author_type: str = "blogger"
    title: str = ""
    published_at: Optional[str] = None
    stance: Literal["positive", "neutral", "negative"] = "neutral"
    stance_score: int = Field(ge=0, le=100, default=50)
    apply_suggestion: str = ""
    suggested_capital_ratio: str = ""
    main_reasons: List[str] = Field(default_factory=list)
    risk_points: List[str] = Field(default_factory=list)
    valuation_comment: str = ""
    summary: str = ""
    confidence_score: int = Field(ge=0, le=100, default=50)
    evidence_quotes: List[str] = Field(default_factory=list)
    is_actionable: bool = False


class ConsensusResultModel(BaseModel):
    stock_code: str = ""
    total_posts: int = 0
    positive_count: int = 0
    neutral_count: int = 0
    negative_count: int = 0
    consensus_score: float = Field(ge=0, le=100, default=0.0)
    top_reasons: List[str] = Field(default_factory=list)
    top_risks: List[str] = Field(default_factory=list)
    representative_posts: List[Dict] = Field(default_factory=list)
    coverage_score: float = Field(ge=0, le=100, default=0.0)
    data_quality_warning: str = ""
    failed_posts_count: int = 0
    skipped_posts_count: int = 0
    last_error_message: str = ""
    updated_at: str = ""
