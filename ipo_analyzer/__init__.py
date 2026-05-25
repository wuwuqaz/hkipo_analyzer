# 轻量 __init__.py — 不 eager import 重依赖模块
# 各业务模块按需自行 import

__version__ = "0.5.3-alpha"

# 数据模型（仅标准库依赖，安全暴露）
from .models import (  # noqa: F401
    ProspectusInfo,
    IPOData,
    ValuationResult,
    BusinessBreakdown,
    GeographicResult,
    CustomerSupplierResult,
    CashFlowResult,
    CapacityResult,
    RnDResult,
    RiskFactorResult,
    PeerComparisonResult,
    AdvancedFrameworkResult,
    StockQuality,
    StockQualityDimension,
    DimensionScore,
    BusinessSegment,
    RiskCategory,
    ScoreBreakdownComponent,
)
