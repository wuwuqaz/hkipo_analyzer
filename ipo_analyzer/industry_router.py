"""行业路由 — 集中管理公司类型判定，避免多文件重复逻辑。

所有分析器统一通过 `classify_company()` 获取公司画像，不自行判断行业特征。
"""

from dataclasses import dataclass, field
from typing import Optional

from .utils import _is_num
from .settings import SETTINGS


# ---------------------------------------------------------------------------
# 关键词配置
# ---------------------------------------------------------------------------

_BIOTECH_KEYWORDS = [
    "18A", "chapter 18a", '-b ', "biotech", "innovative drug",
    "clinical-stage", "drug candidate", "nda", "ind",
    "phase i", "phase ii", "phase iii", "phase 1", "phase 2", "phase 3",
    "parp inhibitor", "apatinib", "senaparib",
    "pipeline", "core product", "candidate",
]

_LICENSE_UPFRONT_KEYWORDS = [
    'upfront payment', 'milestone payment', 'license payment',
    '授权首付款', '里程碑付款', '一次性付款', '许可费收入',
    'collaboration revenue', 'partnership revenue',
]

_LICENSE_DOMINANCE_HINTS = ['primarily from', 'mainly from', '主要来源', '大部分来自']

_TECH_SAAS_KEYWORDS = [
    'saas', 'cloud', 'platform', 'subscription', 'recurring', 'arr', 'nrr',
    '软件即服务', '云平台', '订阅',
]

_CONSUMER_MFG_KEYWORDS = [
    'consumer', 'retail', 'brand', 'food', 'beverage', '消费',
    'manufacturing', 'factory', '生产', '制造',
]

_BIOTECH_SUBSECTORS = frozenset({
    "innovative_drug_biotech",
    "ai_drug_delivery_nanomedicine",
    "io_oncology",
    "gene_therapy",
    "cell_therapy",
    "adc_biotech",
})


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class CompanyProfile:
    """公司画像 — 行业路由的统一输出。"""

    sector: str = "unknown"
    subsector: Optional[str] = None

    # 核心类型判定
    is_biotech: bool = False
    is_tech_saas: bool = False
    is_consumer_mfg: bool = False
    is_general_loss: bool = False

    # Biotech 细分特征
    is_low_revenue_biotech: bool = False
    is_license_upfront_driven: bool = False

    # 盈利状态
    is_profitable: bool = False
    is_unprofitable: bool = False

    # 收入特征
    revenue: Optional[float] = None
    revenue_quality: str = "standard"

    # 判断置信度
    confidence: str = "rule_based"
    reasons: list[str] = field(default_factory=list)

    def is_early_stage(self) -> bool:
        """早期未商业化公司（收入极小且亏损）。"""
        return self.is_unprofitable and _is_num(self.revenue) and self.revenue < 50

    def requires_special_valuation(self) -> bool:
        """是否需要行业特化估值框架（而非简单 PE/PS）。"""
        return self.is_low_revenue_biotech or self.is_tech_saas


# ---------------------------------------------------------------------------
# 判定函数
# ---------------------------------------------------------------------------

def _text_hits(text: str, keywords: list[str]) -> int:
    lower = text.lower()
    return sum(1 for kw in keywords if kw.lower() in lower)


def _has_b_suffix_in_names(prospectus_info: dict) -> bool:
    """从公司名称及别名中识别 -B 后缀。"""
    names_to_check = []
    name = prospectus_info.get("extracted_company_name", "")
    if name:
        names_to_check.append(str(name))
    eng_name = prospectus_info.get("extracted_english_name", "")
    if eng_name:
        names_to_check.append(str(eng_name))
    for alias in prospectus_info.get("company_name_aliases", []):
        if isinstance(alias, str):
            names_to_check.append(alias)
    for n in names_to_check:
        lower = n.lower()
        if "-b" in lower or "－b" in lower or "－ｂ" in lower or "－Ｂ" in lower:
            return True
    return False


def _is_biotech(prospectus_info: dict, text: str) -> bool:
    """判定是否为 biotech 公司。"""
    # listing_suffix == "B" 强制认定为 biotech
    listing_suffix = prospectus_info.get("listing_suffix", "")
    if listing_suffix == "B":
        return True

    # 从名称别名中识别 -B
    if _has_b_suffix_in_names(prospectus_info):
        return True

    sector = prospectus_info.get("sector", "")
    if sector != "healthcare":
        return False
    name = str(prospectus_info.get("extracted_company_name", "") or "").lower()
    if "-b" in name:
        return True
    hits = _text_hits(text, _BIOTECH_KEYWORDS)
    if hits >= SETTINGS.valuation.biotech_keyword_hits_min:
        return True
    subsector = (prospectus_info.get("peer_comparison") or {}).get("subsector", "")
    if subsector in _BIOTECH_SUBSECTORS:
        return True
    return False


def _is_license_upfront_driven(revenue: Optional[float], text: str) -> bool:
    """判定收入是否以授权/里程碑付款为主。"""
    if not _is_num(revenue) or revenue >= SETTINGS.valuation.biotech_revenue_small:
        return False
    upfront_hits = _text_hits(text, _LICENSE_UPFRONT_KEYWORDS)
    if upfront_hits < 2:
        return False
    lower = text.lower()
    has_dominance_hint = any(h in lower for h in _LICENSE_DOMINANCE_HINTS)
    has_license_ref = any(k in lower for k in ['upfront', 'license', 'milestone', '授权', '许可'])
    return has_dominance_hint and has_license_ref


def _is_tech_saas(sector: str, text: str) -> bool:
    """判定是否为 SaaS/科技平台型公司。"""
    if sector != 'hardtech':
        return False
    hits = _text_hits(text, _TECH_SAAS_KEYWORDS)
    return hits >= 2


def _is_consumer_mfg(sector: str, text: str) -> bool:
    """判定是否为消费制造型公司。"""
    if sector != 'consumer':
        return False
    hits = _text_hits(text, _CONSUMER_MFG_KEYWORDS)
    return hits >= 2


# ---------------------------------------------------------------------------
# 公开入口
# ---------------------------------------------------------------------------

def classify_company(prospectus_info: dict, text: str = "") -> CompanyProfile:
    """根据招股书信息判定公司画像。

    Args:
        prospectus_info: parser 输出的 dict（或 IPOData 的子集）
        text: 招股书全文文本（用于关键词匹配）

    Returns:
        CompanyProfile 实例
    """
    sector = prospectus_info.get('sector')
    if sector is None:
        sector = 'unknown'
    subsector = (prospectus_info.get('peer_comparison') or {}).get('subsector')
    revenue = prospectus_info.get('revenue')
    net_profit = prospectus_info.get('net_profit')

    # 文本回退：若未传入 text，尝试从 prospectus_info 获取
    if not text:
        text = str(prospectus_info.get('_extracted_text', '') or prospectus_info.get('prospectus_text', ''))

    # listing_suffix 处理："B" 强制 healthcare + biotech；"W" 不作为 biotech 依据
    listing_suffix = prospectus_info.get("listing_suffix", "")
    if not listing_suffix:
        # 从名称中推断 listing_suffix
        if _has_b_suffix_in_names(prospectus_info):
            listing_suffix = "B"
        # 未来可扩展 W/P 的推断
    if listing_suffix == "B":
        sector = "healthcare"

    profile = CompanyProfile(
        sector=sector,
        subsector=subsector,
        revenue=revenue,
    )

    # 盈利状态
    if _is_num(net_profit):
        profile.is_profitable = net_profit > 0
        profile.is_unprofitable = net_profit <= 0

    # Biotech 判定
    profile.is_biotech = _is_biotech(prospectus_info, text)
    if profile.is_biotech and _is_num(revenue) and revenue < SETTINGS.valuation.biotech_revenue_small:
        profile.is_low_revenue_biotech = True
        profile.revenue_quality = 'contains_upfront' if _text_hits(text, _LICENSE_UPFRONT_KEYWORDS) >= 2 else 'standard'
        if _is_license_upfront_driven(revenue, text):
            profile.is_license_upfront_driven = True
            profile.revenue_quality = 'license_upfront_driven'

    # Tech SaaS 判定
    profile.is_tech_saas = _is_tech_saas(sector, text)

    # Consumer Mfg 判定
    profile.is_consumer_mfg = _is_consumer_mfg(sector, text)

    # 通用亏损（非特化行业）
    if profile.is_unprofitable and not profile.is_biotech and not profile.is_tech_saas:
        profile.is_general_loss = True

    # 判定原因
    if profile.is_biotech:
        profile.reasons.append("判定为 biotech（healthcare + biotech 关键词）")
    if profile.is_low_revenue_biotech:
        profile.reasons.append(f"低营收 biotech（收入 {revenue:.1f}M < {SETTINGS.valuation.biotech_revenue_small}M）")
    if profile.is_license_upfront_driven:
        profile.reasons.append("收入以授权/里程碑付款为主")
    if profile.is_tech_saas:
        profile.reasons.append("判定为 SaaS/科技平台型")
    if profile.is_consumer_mfg:
        profile.reasons.append("判定为消费制造型")

    return profile
