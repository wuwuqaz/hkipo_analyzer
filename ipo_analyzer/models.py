"""核心数据模型 — dataclass + dict 兼容层

本模块为 IPO 分析 pipeline 提供类型安全的数据结构。
所有 dataclass 均支持 .to_dict() 和 .from_dict()，便于与现有 JSON/dict 代码兼容。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Any, Optional


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

def _drop_underscore(value: Any) -> Any:
    """递归剔除 dict 中以 '_' 开头的运行时字段（如 _extracted_text）。"""
    if isinstance(value, dict):
        return {
            k: _drop_underscore(v)
            for k, v in value.items()
            if not k.startswith("_")
        }
    if isinstance(value, list):
        return [_drop_underscore(item) for item in value]
    return value


def _maybe_asdict(value: Any) -> Any:
    """如果值是 dataclass 则递归转 dict，否则原样返回。"""
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, list):
        return [_maybe_asdict(v) for v in value]
    if isinstance(value, dict):
        return {k: _maybe_asdict(v) for k, v in value.items()}
    return value


def _from_dict(cls, data: dict[str, Any] | None) -> Any:
    """将 dict 转为 dataclass 实例，忽略未知字段。"""
    if data is None:
        return None
    if not isinstance(data, dict):
        return data
    valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
    kwargs = {k: _maybe_asdict(v) for k, v in data.items() if k in valid_keys}
    # 递归处理嵌套 dataclass（仅一层，后续可扩展）
    for f_name, f_def in cls.__dataclass_fields__.items():
        if f_name not in kwargs:
            continue
        f_type = f_def.type
        val = kwargs[f_name]
        if val is None:
            continue
        # 处理 Optional[T]
        origin = getattr(f_type, "__origin__", None)
        if origin is not None:
            args = getattr(f_type, "__args__", ())
            if origin is type(Optional) or (hasattr(origin, "__name__") and origin.__name__ == "Optional"):
                f_type = args[0] if args else f_type
        # 简单判断是否为 dataclass
        if isinstance(f_type, type) and hasattr(f_type, "__dataclass_fields__") and isinstance(val, dict):
            kwargs[f_name] = _from_dict(f_type, val)
        elif isinstance(f_type, type) and f_type is list and isinstance(val, list):
            # list 内的元素如果是 dataclass，需要类型提示才能递归；这里先跳过
            pass
    return cls(**kwargs)


# ---------------------------------------------------------------------------
# 子模型 — 各分析器结果
# ---------------------------------------------------------------------------

@dataclass
class ValuationResult:
    pe_ratio: Optional[float] = None
    adjusted_pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    ps_ratio: Optional[float] = None
    valuation_label: str = "缺失"
    absolute_valuation_label: str = "缺失"
    relative_valuation_label: Optional[str] = None
    valuation_reasons: list[str] = field(default_factory=list)
    confidence: str = "missing"
    valuation_type: str = "absolute_only"
    valuation_framework_type: Optional[str] = None
    valuation_profitability_type: Optional[str] = None
    revenue_hkd_million: Optional[float] = None
    market_cap_hkd_million: Optional[float] = None
    market_cap_to_rd_ratio: Optional[float] = None
    biotech_valuation_label: Optional[str] = None
    biotech_valuation_reasons: list[str] = field(default_factory=list)
    biotech_stage_label: Optional[str] = None
    latest_clinical_stage: Optional[str] = None
    phase_iii_count: int = 0
    nda_or_approved_count: int = 0
    cash_runway_years: Optional[float] = None
    pipeline_concentration_warning: Optional[str] = None
    revenue_too_small_for_ps: bool = False
    net_profit_hkd_million: Optional[float] = None
    adjusted_profit_hkd_million: Optional[float] = None
    financial_currency: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Optional[ValuationResult]:
        return _from_dict(cls, data)


@dataclass
class BusinessSegment:
    name: str = ""
    revenue_latest: Optional[float] = None
    revenue_previous: Optional[float] = None
    growth_pct: Optional[float] = None
    share_pct: Optional[float] = None
    share_pct_previous: Optional[float] = None
    year_latest: Optional[int] = None


@dataclass
class BusinessBreakdown:
    segments: list[BusinessSegment] = field(default_factory=list)
    main_segment: Optional[str] = None
    fastest_growing_segment: Optional[str] = None
    new_business_segment: Optional[str] = None
    growth_source: str = "missing"
    vbp_risk_score: int = 0
    vbp_summary: str = ""
    asp_data: dict[str, Any] = field(default_factory=dict)
    business_breakdown_confidence: str = "missing"
    business_breakdown_warning: Optional[str] = None
    confidence: str = "missing"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Optional[BusinessBreakdown]:
        if data is None:
            return None
        # segments 需要手动转换
        seg_raw = data.get("segments", [])
        segs = [BusinessSegment(**s) if isinstance(s, dict) else s for s in seg_raw]
        data = {k: v for k, v in data.items() if k != "segments"}
        return cls(segments=segs, **data)


@dataclass
class GeographicResult:
    china_revenue_latest: Optional[float] = None
    overseas_revenue_latest: Optional[float] = None
    overseas_revenue_pct: Optional[float] = None
    overseas_growth_pct: Optional[float] = None
    overseas_growth_label: str = "缺失"
    overseas_risks: list[str] = field(default_factory=list)
    geographic_table: dict[str, Any] = field(default_factory=dict)
    geographic_confidence: str = "missing"
    confidence: str = "missing"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Optional[GeographicResult]:
        return _from_dict(cls, data)


@dataclass
class CustomerSupplierResult:
    top5_customer_revenue_pct: Optional[float] = None
    largest_customer_revenue_pct: Optional[float] = None
    top5_supplier_purchase_pct: Optional[float] = None
    largest_supplier_purchase_pct: Optional[float] = None
    concentration_risk_label: str = "缺失"
    concentration_score_penalty: int = 0
    confidence: str = "missing"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Optional[CustomerSupplierResult]:
        return _from_dict(cls, data)


@dataclass
class CashFlowResult:
    operating_cash_flow: Optional[float] = None
    ocf_to_net_profit: Optional[float] = None
    inventory_turnover_days_latest: Optional[float] = None
    receivables_growth_vs_revenue: Optional[float] = None
    cash_quality_label: str = "缺失"
    working_capital_risks: list[str] = field(default_factory=list)
    confidence: str = "missing"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Optional[CashFlowResult]:
        return _from_dict(cls, data)


@dataclass
class CapacityResult:
    utilization_rate: Optional[float] = None
    expansion_plan: Optional[bool] = None
    outsourced_production: Optional[bool] = None
    capacity_score: int = 0
    capacity_summary: str = "缺失"
    confidence: str = "missing"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Optional[CapacityResult]:
        return _from_dict(cls, data)


@dataclass
class RnDResult:
    rd_expense_latest: Optional[float] = None
    rd_expense_ratio: Optional[float] = None
    product_count_approved: Optional[int] = None
    product_count_pipeline: Optional[int] = None
    core_product_names: list[str] = field(default_factory=list)
    latest_clinical_stage: Optional[str] = None
    phase_iii_count: int = 0
    nda_or_approved_count: int = 0
    technology_moat_score: int = 0
    pipeline_quality_label: str = "缺失"
    commercialization_risk: str = "缺失"
    confidence: str = "missing"
    clinical_stage_score: int = 0
    rd_ratio_warning: Optional[str] = None
    rd_ratio_biotech: bool = False
    class_ii_count: int = 0
    class_iii_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Optional[RnDResult]:
        return _from_dict(cls, data)


@dataclass
class RiskCategory:
    risk_level: str = "低"
    evidence_count: int = 0
    evidence_sample: list[str] = field(default_factory=list)
    score_penalty: int = 0


@dataclass
class RiskFactorResult:
    risks: dict[str, RiskCategory] = field(default_factory=dict)
    total_penalty: int = 0
    confidence: str = "missing"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Optional[RiskFactorResult]:
        if data is None:
            return None
        risks_raw = data.get("risks", {})
        risks = {k: RiskCategory(**v) if isinstance(v, dict) else v for k, v in risks_raw.items()}
        other = {k: v for k, v in data.items() if k != "risks"}
        return cls(risks=risks, **other)


@dataclass
class PeerComparisonResult:
    subsector: Optional[str] = None
    matched_sector: Optional[str] = None
    peer_keywords: list[str] = field(default_factory=list)
    all_subsector_matches: list[tuple[str, str]] = field(default_factory=list)
    match_confidence: str = "none"
    extracted_competitors: list[str] = field(default_factory=list)
    prospectus_peer_candidates: list[str] = field(default_factory=list)
    unmatched_peer_candidates: list[str] = field(default_factory=list)
    matched_peers: list[dict[str, Any]] = field(default_factory=list)
    company_ps: Optional[float] = None
    company_pe: Optional[float] = None
    company_pb: Optional[float] = None
    peer_median_ps: Optional[float] = None
    peer_median_pe: Optional[float] = None
    peer_median_pb: Optional[float] = None
    peer_ps_count: int = 0
    peer_pe_count: int = 0
    relative_ps_premium_pct: Optional[float] = None
    relative_pe_premium_pct: Optional[float] = None
    valuation_position: str = "缺失"
    scarcity_score: int = 0
    peer_score: int = 0
    summary: str = ""
    warnings: list[str] = field(default_factory=list)
    semantic_id: str = "peer_comparison"
    relative_market_cap_pct: Optional[float] = None
    company_market_cap_vs_peer_pct: Optional[float] = None
    quantitative_peers: list[dict[str, Any]] = field(default_factory=list)
    qualitative_peers: list[dict[str, Any]] = field(default_factory=list)
    quantitative_basis: str = "none"
    quantitative_peer_count: int = 0
    qualitative_peer_count: int = 0
    peer_sample_warning: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Optional[PeerComparisonResult]:
        return _from_dict(cls, data)


@dataclass
class DimensionScore:
    score: int = 0
    max_score: int = 0
    label: str = ""
    detail: str = ""
    confidence: str = "rule_based"
    reasons: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)


@dataclass
class AdvancedFrameworkResult:
    score: int = 0
    label: str = ""
    components: dict[str, DimensionScore] = field(default_factory=dict)
    red_flags: list[str] = field(default_factory=list)
    watch_items: list[str] = field(default_factory=list)
    hold_strategy: str = ""
    confidence: str = "mixed_rule_keyword"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Optional[AdvancedFrameworkResult]:
        if data is None:
            return None
        comps_raw = data.get("components", {})
        comps = {k: DimensionScore(**v) if isinstance(v, dict) else v for k, v in comps_raw.items()}
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        other = {k: v for k, v in data.items() if k != "components" and k in valid_keys}
        return cls(components=comps, **other)


@dataclass
class StockQualityDimension:
    label: str = ""
    detail: str = ""


@dataclass
class StockQuality:
    label: str = ""
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    dimensions: dict[str, StockQualityDimension] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Optional[StockQuality]:
        if data is None:
            return None
        dims_raw = data.get("dimensions", {})
        dims = {k: StockQualityDimension(**v) if isinstance(v, dict) else v for k, v in dims_raw.items()}
        other = {k: v for k, v in data.items() if k != "dimensions"}
        return cls(dimensions=dims, **other)


# ---------------------------------------------------------------------------
# 核心模型 — ProspectusInfo & IPOData
# ---------------------------------------------------------------------------

@dataclass
class ProspectusInfo:
    """招股书解析结果（对应原 parser.extract_info 返回的 dict）。

    字段按功能分组：
    - 身份验证
    - 发行基本信息
    - 财务数据
    - 基石投资者
    - 分析器结果（可选）
    """

    # --- 解析元信息 ---
    parse_success: bool = False
    parse_error: Optional[str] = None
    pdf_name_match: Optional[bool] = None
    pdf_stock_code_match: Optional[bool] = None
    pdf_identity_confidence: str = "low"
    pdf_text_length: int = 0
    pdf_validation_warning: Optional[str] = None
    extracted_company_name: Optional[str] = None
    extracted_english_name: Optional[str] = None
    extracted_stock_code: Optional[str] = None
    company_name_aliases: list[str] = field(default_factory=list)
    _extracted_text: str = ""  # 运行时字段，不参与序列化

    # --- 发行信息 ---
    offer_price: Optional[float] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    lot_size: Optional[int] = None
    entry_fee_hkd: Optional[float] = None
    global_offer_shares: Optional[int] = None
    hk_offer_shares: Optional[int] = None
    international_offer_shares: Optional[int] = None
    shares_in_issue_post_listing: Optional[int] = None
    market_cap_hkd_million: Optional[float] = None
    market_cap_hkd_million_low: Optional[float] = None
    market_cap_hkd_million_high: Optional[float] = None
    market_cap_hkd_million_mid: Optional[float] = None
    market_cap_source: Optional[str] = None
    net_proceeds_hkd_million: Optional[float] = None
    issuance_ratio_pct: Optional[float] = None
    public_offer_ratio_pct: Optional[float] = None
    public_offer: Optional[float] = None
    total_fund: Optional[float] = None
    listing_date: Optional[str] = None
    results_date: Optional[str] = None
    sector: str = "unknown"
    listing_suffix: Optional[str] = None

    # --- 财务数据 ---
    revenue: Optional[float] = None
    revenue_y1: Optional[float] = None
    revenue_year: Optional[int] = None
    revenue_y1_year: Optional[int] = None
    net_profit: Optional[float] = None
    net_profit_y1: Optional[float] = None
    net_profit_year: Optional[int] = None
    net_profit_y1_year: Optional[int] = None
    profitable: Optional[bool] = None
    gross_margin: Optional[float] = None
    gross_margin_year: Optional[int] = None
    gross_margin_y1: Optional[float] = None
    gross_margin_y1_year: Optional[int] = None
    rd_expense: Optional[float] = None
    operating_cash_flow: Optional[float] = None
    cost_of_sales: Optional[float] = None
    adjusted_profit_latest_RMB: Optional[float] = None
    pro_forma_NTA_per_share_HKD: Optional[float] = None
    financial_currency: str = "RMB"
    financial_currency_unit: str = "unknown"
    financial_currency_source: Optional[str] = None
    financial_extract_confidence: Optional[str] = None
    financial_data_quality_flags: list[str] = field(default_factory=list)
    financial_table: Optional[dict[str, Any]] = None
    financial_table_source: Optional[str] = None

    # --- 基石投资者 ---
    cornerstone_analysis: Optional[dict[str, Any]] = None
    cornerstone_investors: list[dict[str, Any]] = field(default_factory=list)
    cornerstone_pct: Optional[float] = None
    cornerstone_total_offer_shares: Optional[int] = None
    cornerstone_investment_hkd_million: Optional[float] = None
    cornerstone_investment_usd_million: Optional[float] = None
    cornerstone_offer_ratio_pct: Optional[float] = None

    # --- 分析器结果（pipeline 中动态附加）---
    valuation: Optional[ValuationResult] = None
    business_breakdown: Optional[BusinessBreakdown] = None
    geographic: Optional[GeographicResult] = None
    customer_supplier: Optional[CustomerSupplierResult] = None
    cashflow: Optional[CashFlowResult] = None
    capacity: Optional[CapacityResult] = None
    rnd_pipeline: Optional[RnDResult] = None
    risk_factors: Optional[RiskFactorResult] = None
    peer_comparison: Optional[PeerComparisonResult] = None
    advanced_framework: Optional[AdvancedFrameworkResult] = None
    stock_quality: Optional[StockQuality] = None

    def to_dict(self, drop_runtime: bool = True) -> dict[str, Any]:
        d = asdict(self)
        if drop_runtime:
            d = _drop_underscore(d)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Optional[ProspectusInfo]:
        if data is None:
            return None
        # 手动处理嵌套 dataclass 字段
        nested_map = {
            "valuation": ValuationResult,
            "business_breakdown": BusinessBreakdown,
            "geographic": GeographicResult,
            "customer_supplier": CustomerSupplierResult,
            "cashflow": CashFlowResult,
            "capacity": CapacityResult,
            "rnd_pipeline": RnDResult,
            "risk_factors": RiskFactorResult,
            "peer_comparison": PeerComparisonResult,
            "advanced_framework": AdvancedFrameworkResult,
            "stock_quality": StockQuality,
        }
        kwargs = {}
        for k, v in data.items():
            if k in nested_map and isinstance(v, dict):
                kwargs[k] = nested_map[k].from_dict(v)
            else:
                kwargs[k] = copy.deepcopy(v)
        # 过滤掉不在 dataclass 中的字段（保留到 extra_fields？这里先忽略）
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        kwargs = {k: v for k, v in kwargs.items() if k in valid_keys}
        return cls(**kwargs)


@dataclass
class ScoreBreakdownComponent:
    score: int = 0
    label: str = "缺失"
    detail: str = "未获取"


@dataclass
class IPOData:
    """IPO 分析最终结果（对应原 core.py _process_ipo 返回的 dict）。"""

    company_name: str = ""
    hk_code: str = ""
    apply_start_date: str = ""
    apply_end_date: str = ""

    # 孖展数据
    margin_total: Optional[float] = None
    public_offer: Optional[float] = None
    total_fund: Optional[float] = None
    actual_over_sub_ratio: Optional[float] = None
    forecast_over_sub_ratio: Optional[float] = None
    estimated_subscription_ratio: Optional[float] = None
    over_sub_ratio_estimated: Optional[float] = None
    over_sub_ratio: Optional[float] = None
    over_sub_ratio_source: str = "missing"
    market_heat: str = ""
    margin_detail: Optional[dict[str, Any]] = None

    # 评分
    score: int = 0
    subscription_score: int = 0
    fundamental_score: int = 0
    stock_quality_score: int = 0
    score_reasons: list[str] = field(default_factory=list)
    score_breakdown: dict[str, ScoreBreakdownComponent] = field(default_factory=dict)
    risk_penalty: int = 0
    # 新五维评分（0.4.0-alpha）
    trade_score: int = 0
    valuation_score: int = 0
    theme_score: int = 0
    data_quality_score: int = 0
    # 兼容旧字段（deprecated）
    advanced_framework_score: int = 0
    advanced_score_adjustment: int = 0
    # 交易信号拆解（供 UI 展示）
    signal_breakdown: dict[str, Any] = field(default_factory=dict)

    # 重新分析相关字段
    weight_profile: dict[str, Any] = field(default_factory=dict)
    score_weights_note: str = ""
    data_confidence_gate_warning: Optional[str] = None
    risk_penalty_breakdown: list[dict[str, Any]] = field(default_factory=list)
    debug_info: Optional[dict[str, Any]] = None
    score_trace: Optional[dict[str, Any]] = None
    penalty_reason: Optional[str] = None
    analysis_mode: str = "full"
    _reanalysis: dict[str, Any] = field(default_factory=dict)
    post_listing: dict[str, Any] = field(default_factory=dict)

    # 解析元信息
    pdf_downloaded: bool = False
    pdf_path: Optional[str] = None
    pdf_file_size_mb: Optional[float] = None
    prospectus_text_length: int = 0
    parse_success: bool = False
    parse_error: Optional[str] = None
    financial_extract_confidence: Optional[str] = None
    financial_data_quality_flags: list[str] = field(default_factory=list)
    pdf_name_match: Optional[bool] = None
    pdf_stock_code_match: Optional[bool] = None
    pdf_validation_warning: Optional[str] = None
    pdf_identity_confidence: str = "low"
    extracted_company_name: Optional[str] = None
    extracted_english_name: Optional[str] = None
    extracted_stock_code: Optional[str] = None
    company_name_aliases: list[str] = field(default_factory=list)

    # 核心子对象
    prospectus_info: Optional[ProspectusInfo] = None
    stock_quality: Optional[StockQuality] = None

    # 运行时字段（缓存用）
    _cached_at: Optional[str] = None
    _cache_version: Optional[int] = None
    _archived_at: Optional[str] = None
    _archive_source: Optional[str] = None
    _history_version: Optional[int] = None

    def to_dict(self, drop_runtime: bool = True) -> dict[str, Any]:
        d = asdict(self)
        if drop_runtime:
            d = _drop_underscore(d)
        # 递归处理嵌套 dataclass
        for k, v in d.items():
            if hasattr(v, "to_dict"):
                d[k] = v.to_dict(drop_runtime=drop_runtime)
            elif isinstance(v, dict):
                d[k] = {sk: sv.to_dict(drop_runtime=drop_runtime) if hasattr(sv, "to_dict") else sv for sk, sv in v.items()}
            elif isinstance(v, list):
                d[k] = [item.to_dict(drop_runtime=drop_runtime) if hasattr(item, "to_dict") else item for item in v]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Optional[IPOData]:
        if data is None:
            return None
        # score_breakdown 手动处理
        sb_raw = data.get("score_breakdown", {})
        if isinstance(sb_raw, dict):
            sb = {k: ScoreBreakdownComponent(**v) if isinstance(v, dict) else v for k, v in sb_raw.items()}
        else:
            sb = {}
        data = {k: v for k, v in data.items() if k != "score_breakdown"}
        # prospectus_info / stock_quality 手动处理
        pi_raw = data.get("prospectus_info")
        sq_raw = data.get("stock_quality")
        kwargs = {k: copy.deepcopy(v) for k, v in data.items() if k not in ("prospectus_info", "stock_quality", "score_breakdown")}
        kwargs["score_breakdown"] = sb
        kwargs["prospectus_info"] = ProspectusInfo.from_dict(pi_raw) if isinstance(pi_raw, dict) else pi_raw
        kwargs["stock_quality"] = StockQuality.from_dict(sq_raw) if isinstance(sq_raw, dict) else sq_raw
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        kwargs = {k: v for k, v in kwargs.items() if k in valid_keys}
        return cls(**kwargs)
