"""IPO 首日表现回测数据模型"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class AllotmentExtractionResult:
    """配售结果公告提取结果"""
    final_offer_price: Optional[float] = None
    public_subscription_multiple: Optional[float] = None
    one_lot_success_rate: Optional[float] = None
    clawback_ratio: Optional[float] = None
    raw_text_snippets: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return self.final_offer_price is not None and self.public_subscription_multiple is not None


@dataclass
class ProspectusSignalResult:
    """招股书信号提取结果"""
    has_greenshoe: Optional[bool] = None
    sponsors: list[str] = field(default_factory=list)
    cornerstone_investors: list[str] = field(default_factory=list)
    cornerstone_amount_hkd_million: Optional[float] = None
    cornerstone_pct: Optional[float] = None
    cornerstone_independence: Optional[str] = None
    has_related_support: bool = False
    raw_text_snippets: list[str] = field(default_factory=list)


@dataclass
class IPOBacktestRecord:
    """单只 IPO 首日表现回测样本

    包含上市日前可知信息（底色）与上市后结果。
    """
    hk_code: str = ""
    stock_code: str = ""
    company_name: str = ""
    listing_date: str = ""

    offer_price: Optional[float] = None
    first_day_open: Optional[float] = None
    first_day_close: Optional[float] = None
    first_day_high: Optional[float] = None
    first_day_low: Optional[float] = None
    first_day_return: float = 0.0
    is_break: bool = False
    is_big_meat_50: bool = False

    over_sub_ratio: float = 0.0
    public_subscription_multiple_final: Optional[float] = None
    has_greenshoe: Optional[bool] = None
    sponsors: list[str] = field(default_factory=list)
    cornerstone_investors: list[str] = field(default_factory=list)
    cornerstone_pct: Optional[float] = None
    cornerstone_independence: Optional[str] = None
    has_related_support: bool = False

    fundamental_score: Optional[float] = None
    sponsor_elastic_group: Optional[str] = None
    subscription_heat_group: Optional[str] = None
    one_lot_success_rate: Optional[float] = None
    clawback_ratio: Optional[float] = None

    market_wind_score: Optional[float] = None
    market_wind_group: Optional[str] = None
    bottom_group: Optional[str] = None
    wind_group: Optional[str] = None

    score_timestamp: str = ""
    data_quality: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_win(self) -> bool:
        return self.first_day_return > 0

    def __post_init__(self):
        if not self.stock_code:
            self.stock_code = self.hk_code
        if not self.hk_code:
            self.hk_code = self.stock_code
        if self.public_subscription_multiple_final is None:
            self.public_subscription_multiple_final = self.over_sub_ratio
        if not self._fields_explicitly_set:
            self.is_break = self.first_day_return < 0
            self.is_big_meat_50 = self.first_day_return >= 50.0

    @property
    def _fields_explicitly_set(self) -> bool:
        return False
