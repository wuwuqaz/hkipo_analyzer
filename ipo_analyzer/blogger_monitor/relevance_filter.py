from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from .config import BloggerMonitorConfig, load_config
from .models import RelevanceResultModel, SearchResultModel

logger = logging.getLogger(__name__)


class RelevanceFilter:
    def __init__(self, config: Optional[BloggerMonitorConfig] = None):
        self.config = config or load_config()

    def filter(self, article: SearchResultModel, stock_code: str, company_name: str) -> RelevanceResultModel:
        content = f"{article.title} {article.snippet} {article.content}"

        ipo_relevant, relevance_score, ipo_reason = self._check_ipo_relevance(content, stock_code, company_name)
        contains_opinion, opinion_reason = self._check_opinion(content)
        is_fresh, freshness_reason = self._check_freshness(article.published_at)
        is_quality, quality_reason = self._check_content_quality(content)

        is_relevant = ipo_relevant and is_fresh and is_quality

        reasons = []
        if not ipo_relevant:
            reasons.append(ipo_reason)
        if not is_fresh:
            reasons.append(freshness_reason)
        if not is_quality:
            reasons.append(quality_reason)
        reason = "; ".join(reasons) if reasons else "通过所有过滤条件"

        if contains_opinion:
            relevance_score += 0.1
        if is_quality:
            relevance_score += 0.1
        relevance_score = max(0.0, min(1.0, relevance_score))

        logger.debug(
            "文章过滤结果: is_relevant=%s, score=%.2f, opinion=%s, reason=%s",
            is_relevant,
            relevance_score,
            contains_opinion,
            reason,
        )

        return RelevanceResultModel(
            is_relevant=is_relevant,
            contains_opinion=contains_opinion,
            relevance_score=relevance_score,
            reason=reason,
        )

    def _check_ipo_relevance(self, content: str, stock_code: str, company_name: str) -> tuple[bool, float, str]:
        has_company = company_name in content
        has_stock_code = stock_code in content

        if not has_company and not has_stock_code:
            return False, 0.5, "未包含公司名或股票代码"

        matched_ipo_keywords = [kw for kw in self.config.ipo_keywords if kw in content]

        if not matched_ipo_keywords:
            if has_company and not has_stock_code:
                return (
                    False,
                    0.6,
                    "仅包含公司名但无IPO关键词，可能是同名公司",
                )
            return False, 0.6, "未包含IPO关键词"

        score = 0.5
        if has_company:
            score += 0.1
        if has_stock_code:
            score += 0.1
        if len(matched_ipo_keywords) >= 2:
            score += 0.1

        return True, score, ""

    def _check_opinion(self, content: str) -> tuple[bool, str]:
        matched = [kw for kw in self.config.opinion_keywords if kw in content]
        if matched:
            return True, ""
        return False, "未包含观点关键词，仅为事实陈述"

    def _check_freshness(self, published_at: Optional[str]) -> tuple[bool, str]:
        if not published_at:
            return True, ""

        try:
            published = self._parse_datetime(published_at)
        except (ValueError, TypeError):
            logger.warning("无法解析发布日期: %s", published_at)
            return True, ""

        now = datetime.now(tz=timezone.utc)
        delta_months = (now.year - published.year) * 12 + (now.month - published.month)
        if delta_months > self.config.max_article_age_months:
            return False, f"文章超过{self.config.max_article_age_months}个月，已过旧"

        return True, ""

    def _check_content_quality(self, content: str) -> tuple[bool, str]:
        if len(content) < self.config.min_content_length:
            return False, f"内容长度不足{self.config.min_content_length}字"
        return True, ""

    @staticmethod
    def _parse_datetime(date_str: str) -> datetime:
        for fmt in (
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S.%f",
        ):
            try:
                dt = datetime.strptime(date_str, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
        raise ValueError(f"无法解析日期: {date_str}")
