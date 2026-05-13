from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

import yaml
from dotenv import load_dotenv
import os


_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_SOURCES_FILE = _DATA_DIR / "sources.yaml"


@dataclass
class BloggerMonitorConfig:
    tavily_api_key: str = ""
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    search_provider: str = "tavily"
    max_results_per_keyword: int = 5
    site_filters: list[str] = field(default_factory=list)
    exclude_domains: list[str] = field(default_factory=list)
    keyword_templates: list[str] = field(default_factory=list)
    source_weights: dict[str, float] = field(default_factory=dict)
    max_article_age_months: int = 6
    min_content_length: int = 200
    ipo_keywords: list[str] = field(default_factory=list)
    opinion_keywords: list[str] = field(default_factory=list)


def load_config(sources_path: Optional[Union[str, Path]] = None) -> BloggerMonitorConfig:
    load_dotenv()

    path = Path(sources_path) if sources_path else _SOURCES_FILE
    if not path.exists():
        return BloggerMonitorConfig(
            tavily_api_key=os.getenv("TAVILY_API_KEY", ""),
            llm_api_key=os.getenv("LLM_API_KEY", ""),
            llm_base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
            llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        )

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    search_cfg = raw.get("search", {})
    keywords_cfg = raw.get("keywords", {})
    weights_cfg = raw.get("source_weights", {})
    relevance_cfg = raw.get("relevance", {})

    return BloggerMonitorConfig(
        tavily_api_key=os.getenv("TAVILY_API_KEY", ""),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        search_provider=search_cfg.get("provider", "tavily"),
        max_results_per_keyword=search_cfg.get("max_results_per_keyword", 5),
        site_filters=search_cfg.get("site_filters", []),
        exclude_domains=search_cfg.get("exclude_domains", []),
        keyword_templates=keywords_cfg.get("templates", []),
        source_weights=weights_cfg,
        max_article_age_months=relevance_cfg.get("max_article_age_months", 6),
        min_content_length=relevance_cfg.get("min_content_length", 200),
        ipo_keywords=relevance_cfg.get("ipo_keywords", []),
        opinion_keywords=relevance_cfg.get("opinion_keywords", []),
    )
