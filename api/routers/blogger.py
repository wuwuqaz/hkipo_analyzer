import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import require_api_token
from api.deps import get_blogger_db
from ipo_analyzer.blogger_monitor.db import BloggerMonitorDB

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/blogger", tags=["blogger"])


class BloggerSearchResponse(BaseModel):
    stock_code: str
    consensus_score: Optional[float] = None
    total_posts: int = 0
    positive_count: int = 0
    neutral_count: int = 0
    negative_count: int = 0
    sentiment_label: Optional[str] = None
    top_reasons: list[str] = []
    top_risks: list[str] = []
    representative_posts: list[dict] = []
    message: Optional[str] = None


@router.get("/{stock_code}")
async def get_blogger_consensus(stock_code: str, blogger_db: BloggerMonitorDB = Depends(get_blogger_db)):
    from ipo_analyzer.blogger_monitor.service import BloggerMonitorService
    service = BloggerMonitorService(db=blogger_db)
    consensus = service.get_consensus(stock_code)

    if consensus is None:
        return BloggerSearchResponse(
            stock_code=stock_code,
            message="暂无博主观点数据。点击搜索获取最新观点。",
        )

    sentiment = "中性"
    if consensus.positive_count > consensus.negative_count * 1.5:
        sentiment = "偏多"
    elif consensus.negative_count > consensus.positive_count * 1.5:
        sentiment = "偏空"

    return BloggerSearchResponse(
        stock_code=stock_code,
        consensus_score=consensus.consensus_score,
        total_posts=consensus.total_posts,
        positive_count=consensus.positive_count,
        neutral_count=consensus.neutral_count,
        negative_count=consensus.negative_count,
        sentiment_label=sentiment,
        top_reasons=consensus.top_reasons or [],
        top_risks=consensus.top_risks or [],
        representative_posts=[
            {"title": p.get("title", ""), "url": p.get("url", ""), "sentiment": p.get("sentiment", "neutral")}
            for p in (consensus.representative_posts or [])
        ],
    )


@router.post("/{stock_code}/search")
async def search_blogger_opinions(
    stock_code: str,
    _token: str = Depends(require_api_token),
    blogger_db: BloggerMonitorDB = Depends(get_blogger_db),
):
    from ipo_analyzer.blogger_monitor.service import BloggerMonitorService
    service = BloggerMonitorService(db=blogger_db)

    try:
        consensus = service.run_full_pipeline(stock_code)
        if consensus is None:
            raise HTTPException(status_code=404, detail="Unable to resolve company name for this stock code")

        sentiment = "中性"
        if consensus.positive_count > consensus.negative_count * 1.5:
            sentiment = "偏多"
        elif consensus.negative_count > consensus.positive_count * 1.5:
            sentiment = "偏空"

        return BloggerSearchResponse(
            stock_code=stock_code,
            consensus_score=consensus.consensus_score,
            total_posts=consensus.total_posts,
            positive_count=consensus.positive_count,
            neutral_count=consensus.neutral_count,
            negative_count=consensus.negative_count,
            sentiment_label=sentiment,
            top_reasons=consensus.top_reasons or [],
            top_risks=consensus.top_risks or [],
            representative_posts=[
                {"title": p.get("title", ""), "url": p.get("url", ""), "sentiment": p.get("sentiment", "neutral")}
                for p in (consensus.representative_posts or [])
            ],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Blogger search failed for {stock_code}: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")
