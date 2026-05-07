"""全局配置层 — 集中管理评分阈值、权重、汇率等业务规则。

使用方式:
    from .settings import SETTINGS
    if pe > SETTINGS.valuation.pe_expensive: ...

如需覆盖默认值，可在项目根目录创建 `.env` 文件（未来可扩展）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FXConfig:
    """汇率配置"""
    rmb_to_hkd: float = 1.08
    usd_to_hkd: float = 7.8
    usd_to_hkd_precise: float = 7.8344  # 基石投资等场景使用


@dataclass
class ValuationThresholds:
    """估值绝对阈值"""
    pe_expensive: float = 60.0
    pe_high: float = 40.0
    pe_moderate: float = 30.0
    pe_fair: float = 20.0
    ps_expensive: float = 15.0
    ps_high: float = 8.0
    ps_fair: float = 3.0
    biotech_revenue_small: float = 100.0
    biotech_revenue_moderate: float = 500.0
    cash_runway_warning: float = 1.5
    biotech_pipeline_count_warning: int = 2
    biotech_market_cap_to_rd_extreme: float = 100.0
    biotech_keyword_hits_min: int = 2


@dataclass
class MarketHeatThresholds:
    """市场热度分级（基于超购倍数）"""
    extreme: float = 500.0
    hot: float = 100.0
    warm: float = 20.0


@dataclass
class ProspectusQualityThresholds:
    """招股书基本面评分阈值"""
    gross_margin_excellent: float = 50.0
    gross_margin_good: float = 30.0
    gross_margin_fair: float = 20.0
    growth_strong: float = 0.30
    growth_good: float = 0.10
    gross_margin_anomaly_max: float = 100.0


@dataclass
class ScoringWeights:
    """ScoringSystem 权重配置"""
    heat_max: int = 40
    quality_max: int = 55
    scale_max: int = 10
    market_max: int = 5
    cornerstone_max: int = 20
    subscription_weight: float = 0.35
    fundamental_weight: float = 0.45
    base_score: int = 20


@dataclass
class RealMoneyThresholds:
    """进阶框架 — 真实资金评分（按孖展金额 亿港元）"""
    tier1: float = 500.0   # 20 分
    tier2: float = 200.0   # 17 分
    tier3: float = 100.0   # 14 分
    tier4: float = 50.0    # 11 分
    tier5: float = 20.0    # 8 分
    tier6: float = 5.0     # 5 分
    # < tier6 得 2 分

    over_sub_tier1: float = 500.0  # 14 分（无真实金额时回退）
    over_sub_tier2: float = 100.0  # 11 分
    over_sub_tier3: float = 20.0   # 7 分
    over_sub_tier4: float = 5.0    # 4 分


@dataclass
class FloatStructureThresholds:
    """进阶框架 — 筹码结构评分"""
    public_offer_low_pct: float = 10.0
    public_offer_mid_pct: float = 20.0
    issuance_low_pct: float = 10.0
    issuance_mid_pct: float = 20.0
    cornerstone_high_pct: float = 80.0
    cornerstone_low_pct: float = 30.0
    public_offer_fund_small: float = 1.0   # 亿港元
    public_offer_fund_mid: float = 3.0
    public_offer_fund_large: float = 8.0


@dataclass
class CapacityThresholds:
    """产能利用率评分"""
    overload: float = 100.0
    high: float = 90.0
    moderate: float = 60.0


@dataclass
class RnDThresholds:
    """研发费率对技术护城河的影响"""
    moat_high: float = 15.0
    moat_mid: float = 10.0
    moat_low: float = 5.0
    # 研发费率异常
    expense_ratio_anomaly: float = 100.0
    expense_ratio_unit_mismatch_multiplier: float = 10.0
    # 技术护城河评分
    moat_strong_threshold: int = 7
    moat_medium_threshold: int = 4
    moat_max_score: int = 10
    # 临床阶段加分
    phase_iii_threshold: int = 3
    phase_iii_bonus: int = 3
    phase_ii_threshold: int = 2
    phase_ii_bonus: int = 2
    phase_default_bonus: int = 1
    # 医疗器械分类加分
    class_iii_high_threshold: int = 3
    class_iii_high_bonus: int = 2
    class_iii_low_threshold: int = 1
    class_iii_low_bonus: int = 1
    # biotech 关键词命中数
    biotech_keyword_hits_min: int = 2


@dataclass
class RiskFactorThresholds:
    """风险因子评分"""
    evidence_high: int = 5
    evidence_mid: int = 2
    penalty_high: int = 3
    penalty_mid: int = 1
    max_total_penalty: int = 20
    advanced_adjustment_range: int = 10
    advanced_adjustment_center: int = 50
    advanced_adjustment_scale: int = 50


@dataclass
class CustomerConcentrationThresholds:
    """客户/供应商集中度风险"""
    top5_customer_high: float = 50.0
    largest_customer_high: float = 20.0
    top5_supplier_high: float = 40.0
    largest_supplier_high: float = 20.0
    penalty_high: int = 5
    penalty_mid: int = 3


@dataclass
class PeerCompsThresholds:
    """同行对比评分"""
    stale_after_days: int = 90
    match_confidence_high: int = 4
    match_confidence_medium: int = 2
    premium_overpriced: float = 100.0
    premium_high: float = 50.0
    premium_expensive: float = 30.0
    premium_fair: float = -30.0
    peer_map_max: int = 8
    peer_fallback_ps_low: int = 6
    peer_fallback_ps_mid: int = 4
    peer_fallback_ps_high: int = 2
    scarcity_high: int = 7
    scarcity_medium: int = 5
    scarcity_low: int = 3
    adjusted_profit_bonus: int = 1
    sector_ps_bonus: int = 1


@dataclass
class PEGThresholds:
    """PEG估值评分"""
    undervalued: float = 0.7
    fair: float = 1.2
    high: float = 2.0


@dataclass
class StockConnectThresholds:
    """港股通纳入市值阈值（亿港元）"""
    large_cap: float = 150000.0
    fast_track: float = 20000.0
    regular: float = 10000.0
    score_ah: int = 10
    score_large: int = 10
    score_fast: int = 8
    score_regular: int = 6


@dataclass
class MainlineThresholds:
    """主线/板块判断"""
    hardtech_hit: int = 8
    hardtech_no_hit: int = 5
    healthcare_hit: int = 6
    healthcare_no_hit: int = 4
    consumer_hit: int = 5
    consumer_no_hit: int = 3
    high_threshold: int = 7
    mid_threshold: int = 4


@dataclass
class ValuationScoreLimits:
    """估值评分上限"""
    abs_max: int = 8
    relative_max: int = 8
    bonus_max: int = 4
    market_cap_to_rd_max: int = 15
    vbp_score_max: int = 15
    vbp_keyword_bonus: int = 5
    vbp_total_max: int = 20
    # 评分标签阈值
    real_money_high: int = 14
    real_money_mid: int = 8
    float_high: int = 11
    float_mid: int = 7
    cornerstone_high: int = 11
    cornerstone_mid: int = 5
    valuation_high: int = 14
    valuation_mid: int = 9
    data_quality_high: int = 4
    data_quality_mid: int = 2
    # 异常检测
    growth_extreme: float = 0.5
    revenue_ratio_extreme: float = 10.0
    net_margin_near_zero: float = 0.001
    net_margin_extreme: float = 1.0
    pe_extreme: float = 100.0
    # PEG
    peg_growth_min: float = 0.2
    # 进阶框架标签
    advanced_high: int = 75
    advanced_mid_high: int = 60
    advanced_mid: int = 45
    # 股票质地标签
    quality_excellent: int = 70
    quality_good: int = 45
    quality_fair: int = 25
    # 市值阈值（亿港元）
    large_market_cap: float = 10000.0


@dataclass
class BusinessBreakdownThresholds:
    """业务分部分析阈值"""
    new_biz_prev_share_max: float = 5.0
    new_biz_curr_share_min: float = 10.0
    new_biz_revenue_ratio_max: float = 0.3
    new_biz_total_share_min: float = 10.0
    main_segment_dominance_pct: float = 70.0


@dataclass
class GeographicThresholds:
    """地理扩张分析阈值"""
    high_pct: float = 15.0
    mid_pct: float = 10.0
    low_pct: float = 5.0
    growth_extreme: float = 100.0
    growth_high: float = 50.0


@dataclass
class CashFlowThresholds:
    """经营现金流质量阈值"""
    ocf_np_strong: float = 1.0
    ocf_np_fair: float = 0.5
    inventory_days_warning: float = 200.0


@dataclass
class CacheConfig:
    version: int = 1
    ttl_days: int = 7


@dataclass
class HistoryConfig:
    version: int = 1


@dataclass
class FileConfig:
    max_upload_size_mb: int = 80
    temp_file_ttl_days: int = 7


@dataclass
class PDFReportThresholds:
    """PDF 报告评分标签阈值"""
    score_excellent: int = 70
    score_good: int = 45
    recommend_active: int = 75
    recommend_neutral: int = 55
    recommend_cautious: int = 35


@dataclass
class DataSanitizationThresholds:
    """数据清洗/异常值检测阈值"""
    revenue_variance_max: float = 20.0  # 收入两期差异超过20倍视为异常
    net_profit_sanity_max: float = 100000.0  # 净利润异常值上限


@dataclass
class NetworkConfig:
    """网络请求参数"""
    max_retries: int = 3
    backoff_factor: float = 1.5
    default_timeout: int = 30
    pdf_download_timeout: int = 120
    playwright_timeout: int = 60000
    head_timeout: int = 10
    margin_page_size: int = 100


@dataclass
class CornerstoneThresholds:
    """基石投资评分参数"""
    # 基石占比档位（%）
    pct_healthy_low: float = 40.0
    pct_healthy_high: float = 60.0
    pct_acceptable_low: float = 30.0
    pct_acceptable_high: float = 80.0
    # 认购强度评分
    score_missing: int = 7
    score_healthy: int = 15
    score_acceptable: int = 11
    score_extreme: int = 3
    # 锁定评分
    lockup_long_money: int = 82
    lockup_default: int = 68
    lockup_weak_penalty: int = 10
    # 维度权重
    quality_weight: float = 0.35
    independence_weight: float = 0.20
    sector_fit_weight: float = 0.20
    subscription_max: int = 15
    lockup_weight: float = 0.10
    # 缺失默认值
    quality_default: int = 35
    independence_default: int = 40
    sector_fit_default: int = 40
    # 等级阈值
    grade_s: int = 85
    grade_a: int = 70
    grade_a_strong: int = 80
    grade_b: int = 50
    # 评分上限（有红旗时）
    score_cap_high_red_flags: int = 49
    score_cap_low_red_flags: int = 65
    red_flags_high_count: int = 2
    # SPV
    spv_warning_count: int = 3


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

@dataclass
class Settings:
    fx: FXConfig = field(default_factory=FXConfig)
    valuation: ValuationThresholds = field(default_factory=ValuationThresholds)
    market_heat: MarketHeatThresholds = field(default_factory=MarketHeatThresholds)
    prospectus_quality: ProspectusQualityThresholds = field(default_factory=ProspectusQualityThresholds)
    scoring: ScoringWeights = field(default_factory=ScoringWeights)
    real_money: RealMoneyThresholds = field(default_factory=RealMoneyThresholds)
    float_structure: FloatStructureThresholds = field(default_factory=FloatStructureThresholds)
    capacity: CapacityThresholds = field(default_factory=CapacityThresholds)
    rnd: RnDThresholds = field(default_factory=RnDThresholds)
    risk_factor: RiskFactorThresholds = field(default_factory=RiskFactorThresholds)
    customer_concentration: CustomerConcentrationThresholds = field(default_factory=CustomerConcentrationThresholds)
    peer_comps: PeerCompsThresholds = field(default_factory=PeerCompsThresholds)
    peg: PEGThresholds = field(default_factory=PEGThresholds)
    stock_connect: StockConnectThresholds = field(default_factory=StockConnectThresholds)
    mainline: MainlineThresholds = field(default_factory=MainlineThresholds)
    valuation_score: ValuationScoreLimits = field(default_factory=ValuationScoreLimits)
    business_breakdown: BusinessBreakdownThresholds = field(default_factory=BusinessBreakdownThresholds)
    geographic: GeographicThresholds = field(default_factory=GeographicThresholds)
    cash_flow: CashFlowThresholds = field(default_factory=CashFlowThresholds)
    cache: CacheConfig = field(default_factory=CacheConfig)
    history: HistoryConfig = field(default_factory=HistoryConfig)
    file: FileConfig = field(default_factory=FileConfig)
    pdf_report: PDFReportThresholds = field(default_factory=PDFReportThresholds)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    data_sanitization: DataSanitizationThresholds = field(default_factory=DataSanitizationThresholds)
    cornerstone: CornerstoneThresholds = field(default_factory=CornerstoneThresholds)

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)


SETTINGS = Settings()
