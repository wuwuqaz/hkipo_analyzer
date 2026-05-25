from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Optional

from .analyzer import BloggerAnalyzer
from .config import load_config
from .consensus import ConsensusCalculator
from .db import BloggerMonitorDB
from .models import ConsensusResultModel, SearchResultModel
from .relevance_filter import RelevanceFilter
from .searcher import BloggerSearcher

logger = logging.getLogger(__name__)


class BloggerMonitorService:
    def __init__(self, db_path: str | None = None, db: Optional[BloggerMonitorDB] = None):
        if db_path is None:
            storage_base = os.getenv("STORAGE_BASE_PATH", "temp")
            db_path = os.path.join(storage_base, "blogger_monitor.db")
        self.config = load_config()
        self.db = db if db is not None else BloggerMonitorDB(db_path)
        self.searcher = BloggerSearcher(self.config)
        self.relevance_filter = RelevanceFilter(self.config)
        self.analyzer = BloggerAnalyzer(self.config)
        self.consensus_calculator = ConsensusCalculator(self.config)

    def run_full_pipeline(
        self,
        stock_code: str,
        company_name: Optional[str] = None,
    ) -> Optional[ConsensusResultModel]:
        if company_name is None:
            company_name = self._resolve_company_name(stock_code)
        if company_name is None:
            logger.error("无法解析公司名称，stock_code=%s", stock_code)
            return None

        logger.info(
            "开始完整流程: stock_code=%s, company_name=%s",
            stock_code,
            company_name,
        )

        search_results = self.searcher.search(company_name, stock_code)
        logger.info("搜索到 %d 篇文章", len(search_results))

        new_posts: list[dict] = []
        for i, result in enumerate(search_results):
            content_hash = self._compute_content_hash(result.content or result.snippet)
            canonical_url = BloggerSearcher.canonicalize_url(result.url)
            domain = BloggerSearcher.extract_domain(result.url)

            post_data = {
                "stock_code": stock_code,
                "keyword": "",
                "search_source": self.config.search_provider,
                "search_rank": i + 1,
                "url": result.url,
                "canonical_url": canonical_url,
                "domain": domain,
                "content_hash": content_hash,
                "title": result.title,
                "author": "",
                "source": result.source_domain,
                "published_at": result.published_at,
                "raw_content": result.content,
                "content_length": len(result.content or ""),
                "fetch_status": "fetched",
            }

            post_id = self.db.insert_post(post_data)
            if post_id is not None:
                post_data["id"] = post_id
                new_posts.append(post_data)

        logger.info("新增 %d 篇文章（去重后）", len(new_posts))

        failed_count = 0
        skipped_count = 0
        opinions: list = []
        analysis_dicts: list = []

        for post in new_posts:
            search_result = SearchResultModel(
                title=post.get("title", ""),
                url=post.get("url", ""),
                snippet="",
                content=post.get("raw_content", ""),
                published_at=post.get("published_at"),
                source_domain=post.get("source", ""),
            )

            try:
                relevance = self.relevance_filter.filter(search_result, stock_code, company_name)
            except Exception:
                logger.exception("相关性过滤失败: post_id=%s", post.get("id"))
                self.db.update_post_fetch_status(post["id"], "filter_error")
                failed_count += 1
                continue

            self.db.update_post_relevance(post["id"], relevance.relevance_score)
            post["relevance_score"] = relevance.relevance_score

            if not relevance.is_relevant:
                logger.debug(
                    "文章不相关，跳过: post_id=%s, reason=%s",
                    post.get("id"),
                    relevance.reason,
                )
                self.db.update_post_fetch_status(post["id"], "irrelevant")
                skipped_count += 1
                continue

            try:
                opinion = self.analyzer.analyze(search_result, stock_code, company_name)
            except Exception:
                logger.exception("LLM 分析失败: post_id=%s", post.get("id"))
                self.db.update_post_fetch_status(post["id"], "analysis_error")
                failed_count += 1
                continue

            if opinion is None:
                logger.warning("LLM 分析返回空结果: post_id=%s", post.get("id"))
                self.db.update_post_fetch_status(post["id"], "analysis_empty")
                failed_count += 1
                continue

            opinions.append(opinion)

            analysis_data = {
                "post_id": post["id"],
                "stock_code": opinion.stock_code or stock_code,
                "company_name": opinion.company_name or company_name,
                "source": opinion.source or post.get("source", ""),
                "author": opinion.author,
                "author_type": opinion.author_type,
                "title": opinion.title or post.get("title", ""),
                "published_at": opinion.published_at or post.get("published_at"),
                "stance": opinion.stance,
                "stance_score": opinion.stance_score,
                "apply_suggestion": opinion.apply_suggestion,
                "suggested_capital_ratio": opinion.suggested_capital_ratio,
                "main_reasons": opinion.main_reasons,
                "risk_points": opinion.risk_points,
                "valuation_comment": opinion.valuation_comment,
                "summary": opinion.summary,
                "confidence_score": opinion.confidence_score,
                "evidence_quotes": opinion.evidence_quotes,
                "is_actionable": opinion.is_actionable,
                "analysis_status": "completed",
            }
            analysis_dicts.append(analysis_data)
            self.db.insert_analysis(analysis_data)
            self.db.update_post_fetch_status(post["id"], "analyzed")

        logger.info(
            "分析完成: 成功=%d, 失败=%d, 跳过=%d",
            len(opinions),
            failed_count,
            skipped_count,
        )

        consensus = self.consensus_calculator.calculate(
            stock_code, analysis_dicts, new_posts, failed_count, skipped_count,
        )

        self.db.upsert_consensus(consensus.model_dump())
        logger.info(
            "共识汇总已保存: consensus_score=%.1f, coverage_score=%.1f",
            consensus.consensus_score,
            consensus.coverage_score,
        )

        return consensus

    def search_only(
        self,
        stock_code: str,
        company_name: Optional[str] = None,
    ) -> list[SearchResultModel]:
        if company_name is None:
            company_name = self._resolve_company_name(stock_code)
        if company_name is None:
            logger.error("无法解析公司名称，stock_code=%s", stock_code)
            return []

        return self.searcher.search(company_name, stock_code)

    def get_consensus(self, stock_code: str) -> Optional[ConsensusResultModel]:
        data = self.db.get_consensus(stock_code)
        if data is None:
            return None
        return ConsensusResultModel(**data)

    def _resolve_company_name(self, stock_code: str) -> Optional[str]:
        storage_base = os.getenv("STORAGE_BASE_PATH", "temp")
        history_path = Path(os.path.join(storage_base, "ipo_history.json"))
        if not history_path.exists():
            logger.warning("ipo_history.json 不存在: %s", history_path)
            return None

        try:
            with open(history_path, encoding="utf-8") as f:
                records = json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.exception("读取 ipo_history.json 失败")
            return None

        if not isinstance(records, list):
            return None

        padded_code = stock_code.zfill(5)

        for record in records:
            if not isinstance(record, dict):
                continue
            hk_code = str(record.get("hk_code", "")).strip()
            if hk_code == padded_code or hk_code == stock_code:
                name = record.get("company_name", "")
                if name:
                    return name

        return None

    @staticmethod
    def _compute_content_hash(content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()[:16]
