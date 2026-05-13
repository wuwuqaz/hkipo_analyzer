import logging
import time
from typing import Optional
from urllib.parse import urlparse, parse_qs, urlunparse

from .config import BloggerMonitorConfig, load_config
from .models import SearchResultModel

logger = logging.getLogger(__name__)

_TRACKING_PARAMS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "fbclid",
        "gclid",
        "gclsrc",
        "dclid",
        "msclkid",
        "mc_eid",
        "_ga",
        "_gl",
        "ref",
        "referrer",
    }
)


class BloggerSearcher:
    def __init__(self, config: Optional[BloggerMonitorConfig] = None):
        self.config = config or load_config()
        self._tavily_client = None

    def _get_tavily_client(self):
        if self._tavily_client is not None:
            return self._tavily_client
        if not self.config.tavily_api_key:
            return None
        from tavily import TavilyClient
        self._tavily_client = TavilyClient(api_key=self.config.tavily_api_key)
        return self._tavily_client

    def generate_keywords(self, company_name: str, stock_code: str) -> list[str]:
        keywords = []
        for tpl in self.config.keyword_templates:
            keyword = tpl.replace("{company_name}", company_name).replace("{stock_code}", stock_code)
            keywords.append(keyword)
        return keywords

    def search(self, company_name: str, stock_code: str) -> list[SearchResultModel]:
        keywords = self.generate_keywords(company_name, stock_code)
        if not keywords:
            return []

        provider = self.config.search_provider

        seen_urls: set[str] = set()
        results: list[SearchResultModel] = []

        for i, keyword in enumerate(keywords):
            if i > 0:
                time.sleep(0.5)

            if provider == "duckduckgo":
                items = self._search_duckduckgo(keyword)
            else:
                # 默认 tavily，无 API key 时自动回退到 duckduckgo
                items = self._search_tavily(keyword)
                if not items and not self.config.tavily_api_key:
                    items = self._search_duckduckgo(keyword)

            for item in items:
                canon = self.canonicalize_url(item.url)
                if canon in seen_urls:
                    continue
                seen_urls.add(canon)
                results.append(item)

        return results

    def _search_tavily(self, keyword: str) -> list[SearchResultModel]:
        client = self._get_tavily_client()
        if client is None:
            logger.warning("TAVILY_API_KEY 未配置，跳过搜索")
            return []

        try:
            resp = client.search(
                query=keyword,
                max_results=self.config.max_results_per_keyword,
                include_raw_content=True,
                include_domains=self.config.site_filters or None,
                exclude_domains=self.config.exclude_domains or None,
            )
        except Exception:
            logger.exception("Tavily 搜索失败，关键词: %s", keyword)
            return []

        items: list[SearchResultModel] = []
        for r in resp.get("results", []):
            url = r.get("url", "")
            items.append(
                SearchResultModel(
                    title=r.get("title", ""),
                    url=url,
                    snippet=r.get("content", ""),
                    content=r.get("raw_content", "") or r.get("content", ""),
                    published_at=r.get("published_date"),
                    source_domain=self.extract_domain(url),
                )
            )
        return items

    def _search_duckduckgo(self, keyword: str) -> list[SearchResultModel]:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            logger.warning("DuckDuckGo 搜索未安装，请运行: pip install duckduckgo-search")
            return []

        items: list[SearchResultModel] = []
        try:
            with DDGS() as ddgs:
                for r in ddgs.text(
                    keyword,
                    max_results=self.config.max_results_per_keyword,
                ):
                    url = r.get("href", "") or r.get("url", "")
                    items.append(
                        SearchResultModel(
                            title=r.get("title", ""),
                            url=url,
                            snippet=r.get("body", ""),
                            content=r.get("body", ""),
                            published_at=None,
                            source_domain=self.extract_domain(url),
                        )
                    )
        except Exception:
            logger.exception("DuckDuckGo 搜索失败，关键词: %s", keyword)
            return []

        return items

    @staticmethod
    def canonicalize_url(url: str) -> str:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        host = parsed.hostname.lower() if parsed.hostname else ""
        if host.startswith("www."):
            host = host[4:]
        path = parsed.path.rstrip("/")
        query = parse_qs(parsed.query, keep_blank_values=True)
        cleaned = {k: v for k, v in query.items() if k not in _TRACKING_PARAMS}
        cleaned_qs = "&".join(f"{k}={v[0]}" for k in sorted(cleaned) for v in [cleaned[k]])
        return urlunparse((scheme, host, path, parsed.params, cleaned_qs, ""))

    @staticmethod
    def extract_domain(url: str) -> str:
        host = urlparse(url).hostname or ""
        if host.startswith("www."):
            host = host[4:]
        return host.lower()
