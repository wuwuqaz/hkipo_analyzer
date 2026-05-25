"""IPO Calendar / Key Dates Calculator for Hong Kong IPOs.

Calculates the complete timeline of an IPO: application period, allotment date,
grey market date, listing date, stock connect eligibility, and greenshoe expiry.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional


class IPOCalendarCalculator:
    """新股日历/关键日期计算。
    
    港股IPO典型时间线：
    - 认购期：3-5个交易日
    - 配发结果：上市前1个工作日
    - 暗盘交易：上市前1个交易日
    - 正式上市：T日
    - 港股通入通：上市后T+21个交易日（中位数）
    - 绿鞋过期：上市后30天
    """
    
    STOCK_CONNECT_DAYS = 21  # 港股通入通中位数21天
    GREENSHOE_DAYS = 30  # 绿鞋有效期30天
    
    def calculate(
        self,
        apply_start_date: Optional[str] = None,
        apply_end_date: Optional[str] = None,
        listing_date: Optional[str] = None,
        has_greenshoe: Optional[bool] = None,
        current_date: Optional[date] = None,
    ) -> dict[str, Any]:
        """计算IPO完整时间线。
        
        Args:
            apply_start_date: 认购开始日期 (YYYY-MM-DD)
            apply_end_date: 认购截止日期 (YYYY-MM-DD)
            listing_date: 上市日期 (YYYY-MM-DD)
            has_greenshoe: 是否有绿鞋机制
            current_date: 当前日期（用于计算剩余天数）
        
        Returns:
            完整时间线字典
        """
        current_date = current_date or date.today()
        
        listing_dt = self._parse_date(listing_date) if listing_date else None
        apply_start_dt = self._parse_date(apply_start_date) if apply_start_date else None
        apply_end_dt = self._parse_date(apply_end_date) if apply_end_date else None
        
        # 推算缺失日期
        if listing_dt and not apply_end_dt:
            apply_end_dt = listing_dt - timedelta(days=3)
        if apply_end_dt and not apply_start_dt:
            apply_start_dt = apply_end_dt - timedelta(days=3)
        if apply_end_dt and not listing_dt:
            listing_dt = apply_end_dt + timedelta(days=3)
        
        if listing_dt:
            grey_market_dt = listing_dt - timedelta(days=1)
            allotment_dt = grey_market_dt
            stock_connect_dt = listing_dt + timedelta(days=self.STOCK_CONNECT_DAYS)
            greenshoe_expiry_dt = listing_dt + timedelta(days=self.GREENSHOE_DAYS) if has_greenshoe else None
        else:
            grey_market_dt = None
            allotment_dt = None
            stock_connect_dt = None
            greenshoe_expiry_dt = None
        
        # 计算剩余天数
        days_to_apply_end = (apply_end_dt - current_date).days if apply_end_dt else None
        days_to_listing = (listing_dt - current_date).days if listing_dt else None
        
        # 认购状态
        apply_status = self._calc_apply_status(
            apply_start_dt, apply_end_dt, listing_dt, current_date
        )
        
        return {
            "apply_start_date": apply_start_dt.isoformat() if apply_start_dt else None,
            "apply_end_date": apply_end_dt.isoformat() if apply_end_dt else None,
            "allotment_date": allotment_dt.isoformat() if allotment_dt else None,
            "grey_market_date": grey_market_dt.isoformat() if grey_market_dt else None,
            "listing_date": listing_dt.isoformat() if listing_dt else None,
            "stock_connect_eligible_date": stock_connect_dt.isoformat() if stock_connect_dt else None,
            "greenshoe_expiry_date": greenshoe_expiry_dt.isoformat() if greenshoe_expiry_dt else None,
            "days_to_apply_end": days_to_apply_end,
            "days_to_listing": days_to_listing,
            "apply_status": apply_status,
            "timeline_summary": self._build_timeline_summary(
                apply_start_dt, apply_end_dt, allotment_dt, grey_market_dt,
                listing_dt, stock_connect_dt, greenshoe_expiry_dt, has_greenshoe,
            ),
        }
    
    def _parse_date(self, date_str: str) -> Optional[date]:
        """解析日期字符串。"""
        if not date_str:
            return None
        try:
            if isinstance(date_str, date):
                return date_str
            return datetime.strptime(str(date_str).split("T")[0], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
    
    def _calc_apply_status(
        self,
        apply_start: Optional[date],
        apply_end: Optional[date],
        listing: Optional[date],
        current: date,
    ) -> str:
        """计算认购状态。"""
        if listing and current >= listing:
            return "已上市"
        if apply_end and current > apply_end:
            return "已截止"
        if apply_start and current < apply_start:
            return "未开始"
        if apply_start and apply_end and apply_start <= current <= apply_end:
            return "认购中"
        return "未知"
    
    def _build_timeline_summary(
        self,
        apply_start: Optional[date],
        apply_end: Optional[date],
        allotment: Optional[date],
        grey_market: Optional[date],
        listing: Optional[date],
        stock_connect: Optional[date],
        greenshoe_expiry: Optional[date],
        has_greenshoe: Optional[bool],
    ) -> str:
        """构建时间线摘要。"""
        parts = []
        if apply_start and apply_end:
            parts.append(f"认购期: {apply_start} ~ {apply_end}")
        if listing:
            parts.append(f"上市日: {listing}")
            if grey_market:
                parts.append(f"暗盘: {grey_market}")
            if stock_connect:
                parts.append(f"港股通入通预计: {stock_connect}")
            if has_greenshoe and greenshoe_expiry:
                parts.append(f"绿鞋截止: {greenshoe_expiry}")
        return " | ".join(parts)
