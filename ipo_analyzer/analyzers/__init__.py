"""分析器包 — 每个分析器一个模块，此文件提供向后兼容的统一导入。"""

import logging

logger = logging.getLogger(__name__)

def _is_unit_in_thousands(context: str) -> bool:
    """检测财务数据是否以千元为单位。"""
    return any(kw in context for kw in ("rmb'000", "rmb'000", "in thousands", "人民幣千元", "人民币千元", "以千元計", "以千元计"))


def _adjust_for_unit(value: float, context: str) -> float:
    """如果上下文指示千元单位，将值除以 1000 转换为百万元。"""
    if _is_unit_in_thousands(context.lower()):
        value = value / 1000
    return round(value, 3)


from ._valuation import ValuationAnalyzer  # noqa: E402
from ._business_breakdown import BusinessBreakdownAnalyzer  # noqa: E402
from ._geographic import GeographicExpansionAnalyzer  # noqa: E402
from ._customer_supplier import CustomerSupplierAnalyzer  # noqa: E402
from ._cashflow import WorkingCapitalCashFlowAnalyzer  # noqa: E402
from ._capacity import ProductionCapacityAnalyzer  # noqa: E402
from ._rnd_pipeline import RnDPipelineAnalyzer  # noqa: E402
from ._risk_factors import RiskFactorAnalyzer  # noqa: E402
from ._shareholder import ShareholderAnalyzer  # noqa: E402
from ._order_backlog import OrderBacklogAnalyzer  # noqa: E402
# InvestSkill 集成框架
from ._piotroski_f import PiotroskiFAnalyzer  # noqa: E402
from ._dcf_valuation import DCFValuationAnalyzer  # noqa: E402
from ._sector_analysis import SectorAnalyzer  # noqa: E402
from ._company_profile import CompanyProfileAnalyzer  # noqa: E402
# 质地增强分析器
from ._management_governance import ManagementGovernanceAnalyzer  # noqa: E402
from ._balance_sheet import BalanceSheetAnalyzer  # noqa: E402
from ._profit_sustainability import ProfitSustainabilityAnalyzer  # noqa: E402
from ._earnings_quality import EarningsQualityAnalyzer  # noqa: E402
from ._sponsor_track_record import SponsorTrackRecordAnalyzer  # noqa: E402
from ._investment_thesis import InvestmentThesisAnalyzer  # noqa: E402

__all__ = [
    "ValuationAnalyzer",
    "BusinessBreakdownAnalyzer",
    "GeographicExpansionAnalyzer",
    "CustomerSupplierAnalyzer",
    "WorkingCapitalCashFlowAnalyzer",
    "ProductionCapacityAnalyzer",
    "RnDPipelineAnalyzer",
    "RiskFactorAnalyzer",
    "ShareholderAnalyzer",
    "OrderBacklogAnalyzer",
    # InvestSkill 集成框架
    "PiotroskiFAnalyzer",
    "DCFValuationAnalyzer",
    "SectorAnalyzer",
    "CompanyProfileAnalyzer",
    # 质地增强分析器
    "ManagementGovernanceAnalyzer",
    "BalanceSheetAnalyzer",
    "ProfitSustainabilityAnalyzer",
    "EarningsQualityAnalyzer",
    # 保荐人战绩
    "SponsorTrackRecordAnalyzer",
    "InvestmentThesisAnalyzer",
]
