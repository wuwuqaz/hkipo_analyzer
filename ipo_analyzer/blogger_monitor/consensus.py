import json
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from .config import BloggerMonitorConfig, load_config
from .models import ConsensusResultModel

logger = logging.getLogger(__name__)


class ConsensusCalculator:
    def __init__(self, config: Optional[BloggerMonitorConfig] = None):
        self.config = config or load_config()

    def calculate(
        self,
        stock_code: str,
        analyses: list[dict],
        posts: list[dict],
        failed_count: int = 0,
        skipped_count: int = 0,
        last_error: str = "",
    ) -> ConsensusResultModel:
        positive_count, neutral_count, negative_count = self._count_stances(analyses)
        consensus_score = self._calculate_consensus_score(analyses, posts)
        top_reasons = self._extract_top_items(analyses, "main_reasons")
        top_risks = self._extract_top_items(analyses, "risk_points")
        representative_posts = self._select_representative_posts(analyses, posts)
        total_posts = len(posts)
        coverage_score = self._calculate_coverage_score(total_posts, analyses, posts)
        quality_warning = self._generate_quality_warning(coverage_score, total_posts)

        return ConsensusResultModel(
            stock_code=stock_code,
            total_posts=total_posts,
            positive_count=positive_count,
            neutral_count=neutral_count,
            negative_count=negative_count,
            consensus_score=round(consensus_score, 1),
            top_reasons=top_reasons,
            top_risks=top_risks,
            representative_posts=representative_posts,
            coverage_score=round(coverage_score, 1),
            data_quality_warning=quality_warning,
            failed_posts_count=failed_count,
            skipped_posts_count=skipped_count,
            last_error_message=last_error,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    def _count_stances(self, analyses: list[dict]) -> tuple[int, int, int]:
        positive = sum(1 for a in analyses if a.get("stance") == "positive")
        neutral = sum(1 for a in analyses if a.get("stance") == "neutral")
        negative = sum(1 for a in analyses if a.get("stance") == "negative")
        return positive, neutral, negative

    def _calculate_consensus_score(self, analyses: list[dict], posts: list[dict]) -> float:
        if not analyses:
            return 0.0

        post_map = {p.get("id"): p for p in posts}
        total_weight = 0.0
        weighted_sum = 0.0

        for analysis in analyses:
            post_id = analysis.get("post_id")
            post = post_map.get(post_id)
            if post is None:
                continue

            domain = post.get("domain", "")
            fetched_at = post.get("fetched_at", "")
            relevance_score = post.get("relevance_score", 0.0)
            content_length = post.get("content_length", 0)
            evidence_quotes = self._parse_json_field(analysis.get("evidence_quotes"))

            source_weight = self._get_source_weight(domain)
            recency_weight = self._get_recency_weight(fetched_at)
            relevance_weight = self._get_relevance_weight(relevance_score)
            quality_weight = self._get_content_quality_weight(content_length, evidence_quotes)

            weight = source_weight * recency_weight * relevance_weight * quality_weight
            stance_score = analysis.get("stance_score", 50)

            weighted_sum += weight * stance_score
            total_weight += weight

        if total_weight == 0:
            return 0.0

        return min(max(weighted_sum / total_weight, 0), 100)

    def _get_source_weight(self, domain: str) -> float:
        weights = self.config.source_weights
        if domain in weights:
            return weights[domain]
        return weights.get("default", 0.5)

    def _get_recency_weight(self, fetched_at: str) -> float:
        if not fetched_at:
            return 0.4
        try:
            dt = datetime.fromisoformat(fetched_at)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            days = (now - dt).days
            if days <= 7:
                return 1.0
            if days <= 30:
                return 0.7
            return 0.4
        except (ValueError, TypeError):
            logger.warning("无法解析 fetched_at: %s", fetched_at)
            return 0.4

    def _get_relevance_weight(self, relevance_score: float) -> float:
        return max(min(relevance_score, 1.0), 0.0)

    def _get_content_quality_weight(self, content_length: int, evidence_quotes: list[str]) -> float:
        if content_length >= 1000 and len(evidence_quotes) >= 2:
            return 1.0
        if content_length >= 500 and len(evidence_quotes) >= 1:
            return 0.8
        if content_length >= 200:
            return 0.6
        return 0.4

    def _extract_top_items(self, analyses: list[dict], field: str, top_n: int = 5) -> list[str]:
        counter = Counter()
        for analysis in analyses:
            items = self._parse_json_field(analysis.get(field))
            for item in items:
                if isinstance(item, str) and item.strip():
                    counter[item.strip()] += 1
        return [item for item, _ in counter.most_common(top_n)]

    def _select_representative_posts(self, analyses: list[dict], posts: list[dict]) -> list[dict]:
        post_map = {p.get("id"): p for p in posts}

        stance_groups: dict[str, list[dict]] = {}
        for analysis in analyses:
            stance = analysis.get("stance", "neutral")
            stance_groups.setdefault(stance, []).append(analysis)

        result = []
        for stance in ("positive", "neutral", "negative"):
            group = stance_groups.get(stance, [])
            if not group:
                continue

            best = None
            best_score = -1.0

            for analysis in group:
                post_id = analysis.get("post_id")
                post = post_map.get(post_id)
                if post is None:
                    continue

                domain = post.get("domain", "")
                fetched_at = post.get("fetched_at", "")
                relevance_score = post.get("relevance_score", 0.0)
                content_length = post.get("content_length", 0)
                evidence_quotes = self._parse_json_field(analysis.get("evidence_quotes"))

                source_weight = self._get_source_weight(domain)
                recency_weight = self._get_recency_weight(fetched_at)
                relevance_weight = self._get_relevance_weight(relevance_score)
                quality_weight = self._get_content_quality_weight(content_length, evidence_quotes)

                score = source_weight * recency_weight * relevance_weight * quality_weight
                if score > best_score:
                    best_score = score
                    best = analysis

            if best is not None:
                best_post = post_map.get(best.get("post_id"), {})
                result.append(
                    {
                        "stance": stance,
                        "title": best.get("title", ""),
                        "url": best_post.get("url", ""),
                        "author": best.get("author", ""),
                        "source": best.get("source", "") or best_post.get("source", "") or best_post.get("domain", ""),
                        "stance_score": best.get("stance_score", 50),
                        "summary": best.get("summary", ""),
                        "apply_suggestion": best.get("apply_suggestion", ""),
                        "main_reasons": self._parse_json_field(best.get("main_reasons")),
                    }
                )

        return result

    def _calculate_coverage_score(self, total_posts: int, analyses: list[dict], posts: list[dict]) -> float:
        if total_posts == 0:
            return 0.0

        if total_posts < 3:
            base = total_posts / 3 * 40
        elif total_posts <= 5:
            base = 40 + (total_posts - 3) / 2 * 20
        elif total_posts <= 10:
            base = 60 + (total_posts - 6) / 4 * 20
        else:
            base = min(80 + (total_posts - 10) / 5 * 20, 100)

        unique_domains = len({p.get("domain") for p in posts if p.get("domain")})
        diversity_ratio = unique_domains / total_posts
        diversity_bonus = diversity_ratio * 10

        return min(base + diversity_bonus, 100)

    def _generate_quality_warning(self, coverage_score: float, total_posts: int) -> str:
        if total_posts == 0:
            return "暂无博主观点数据"
        if coverage_score < 30:
            return "样本严重不足，共识不可靠"
        if coverage_score < 50:
            return "样本不足，共识仅供参考"
        return ""

    @staticmethod
    def _parse_json_field(value) -> list:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                result = json.loads(value)
                if isinstance(result, list):
                    return result
            except (json.JSONDecodeError, TypeError):
                pass
        return []
