import os
import json
import shutil
import subprocess
import time
import uuid
import platform
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from .utils import _is_num, _normalize_gm, format_iso_date, _format_cornerstone_amount, classify_market_heat, _sanitize_stock_code
from .settings import SETTINGS
from .downloader import AiPOMarginClient, ProspectusDownloader
from .parser import ProspectusParser
from .analyzers import (
    ValuationAnalyzer,
    BusinessBreakdownAnalyzer,
    GeographicExpansionAnalyzer,
    CustomerSupplierAnalyzer,
    WorkingCapitalCashFlowAnalyzer,
    ProductionCapacityAnalyzer,
    RnDPipelineAnalyzer,
    RiskFactorAnalyzer,
    ShareholderAnalyzer,
    OrderBacklogAnalyzer,
    PiotroskiFAnalyzer,
    DCFValuationAnalyzer,
    SectorAnalyzer,
    CompanyProfileAnalyzer,
    InvestmentThesisAnalyzer,
)
from .scoring import ProspectusQualityAnalyzer, SignalComponentAnalyzer, ScoringSystem
from .peer_comps import PeerComparableAnalyzer
from .report import export_pdf_report
from .history import HistoryStore
from .blogger_monitor.service import BloggerMonitorService

logger = logging.getLogger(__name__)


class _PerfTimer:
    """简单性能计时上下文管理器，用于关键路径耗时记录。"""

    def __init__(self, name: str, threshold_ms: float = 50.0):
        self.name = name
        self.threshold_ms = threshold_ms

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed_ms = (time.perf_counter() - self.start) * 1000
        if elapsed_ms >= self.threshold_ms:
            logger.info("[perf] %s took %.1fms", self.name, elapsed_ms)
        else:
            logger.debug("[perf] %s took %.1fms", self.name, elapsed_ms)


# CLI 入口配置日志
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )


def _attach_debug_info(ipo_data, pdf_path, prospectus_info, prospectus_text):
    ipo_data['pdf_downloaded'] = bool(pdf_path and os.path.exists(pdf_path))
    ipo_data['pdf_path'] = pdf_path
    if pdf_path and os.path.exists(pdf_path):
        try:
            ipo_data['pdf_file_size_mb'] = round(os.path.getsize(pdf_path) / 1024 / 1024, 2)
        except OSError:
            ipo_data['pdf_file_size_mb'] = None
    else:
        ipo_data['pdf_file_size_mb'] = None
    ipo_data['prospectus_text_length'] = len(prospectus_text) if prospectus_text else 0
    ipo_data['parse_success'] = prospectus_info.get('parse_success', False) if prospectus_info else False
    ipo_data['parse_error'] = prospectus_info.get('parse_error') if prospectus_info else None
    ipo_data['financial_extract_confidence'] = prospectus_info.get('financial_extract_confidence') if prospectus_info else None
    ipo_data['financial_data_quality_flags'] = prospectus_info.get('financial_data_quality_flags', []) if prospectus_info else []
    ipo_data['pdf_name_match'] = prospectus_info.get('pdf_name_match') if prospectus_info else None
    ipo_data['pdf_stock_code_match'] = prospectus_info.get('pdf_stock_code_match') if prospectus_info else None
    ipo_data['pdf_validation_warning'] = prospectus_info.get('pdf_validation_warning') if prospectus_info else None
    ipo_data['pdf_identity_confidence'] = prospectus_info.get('pdf_identity_confidence') if prospectus_info else None
    ipo_data['extracted_company_name'] = prospectus_info.get('extracted_company_name') if prospectus_info else None
    ipo_data['extracted_english_name'] = prospectus_info.get('extracted_english_name') if prospectus_info else None
    ipo_data['extracted_stock_code'] = prospectus_info.get('extracted_stock_code') if prospectus_info else None
    ipo_data['company_name_aliases'] = prospectus_info.get('company_name_aliases', []) if prospectus_info else []


_PROSPECTUS_COPY_FIELDS = [
    'offer_price', 'indicative_offer_price', 'final_offer_price', 'offer_price_source',
    'valuation_price_basis', 'entry_fee_hkd', 'lot_size', 'global_offer_shares',
    'hk_offer_shares', 'international_offer_shares', 'shares_in_issue_post_listing',
    'market_cap_hkd_million', 'indicative_market_cap_hkd_million',
    'final_market_cap_hkd_million', 'final_ps_ratio', 'final_total_fund',
    'final_public_offer', 'net_proceeds_hkd_million', 'issuance_ratio_pct',
    'public_offer_ratio_pct', 'international_offer_ratio_pct', 'cornerstone_total_offer_shares',
    'cornerstone_investment_hkd_million', 'cornerstone_investment_usd_million',
    'cornerstone_offer_ratio_pct', 'revenue', 'revenue_y1', 'revenue_year',
    'revenue_y1_year', 'net_profit', 'net_profit_y1', 'net_profit_year',
    'net_profit_y1_year', 'profitable', 'gross_margin', 'gross_margin_year',
    'sector', 'listing_suffix', 'is_chapter_18c', 'public_offer_clawback_max_pct',
    'public_offer_clawback_note', 'financial_extract_confidence',
    'growth_validation_status', 'growth_validation_summary',
    # 发行数据（供 scoring 使用）
    'public_offer', 'total_fund', 'cornerstone_pct',
    'board_lot',
]


def _safe_float(value):
    """将字符串/数值安全转换为 float，失败返回 None。"""
    if value is None or value == "" or value == "--":
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _fetch_margin_data(client, ipo, margin_detail=None):
    company_name = ipo.get('shortname', '') or ipo.get('shortName', '') or ipo.get('name', '')
    stock_code = ipo.get('symbol', '') or ipo.get('stockCode', '')
    margin_data = ipo.get('marginData')
    if margin_detail is None:
        margin_detail = client.fetch_margin_detail(stock_code)

    # 优先从IPO列表取日期，若为空则从margin_detail回退
    start_date = format_iso_date(ipo.get('startdate', ''))
    end_date = format_iso_date(ipo.get('enddate', ''))
    if not start_date and margin_detail:
        start_date = format_iso_date(margin_detail.get('StartDate', ''))
    if not end_date and margin_detail:
        end_date = format_iso_date(margin_detail.get('EndDate', ''))

    ipo_data = {
        'company_name': company_name,
        'hk_code': stock_code,
        'apply_start_date': start_date,
        'apply_end_date': end_date,
        'margin_total': None,
        'public_offer': None,
        'actual_over_sub_ratio': None,
        'estimated_subscription_ratio': None,
        'over_sub_ratio_estimated': None,
    }

    if margin_detail:
        total_margin = margin_detail.get('totalmargin')
        public_offer = margin_detail.get('raisemoney')
        actual_over = margin_detail.get('RateOver')
        forecast_over = margin_detail.get('RateForcast')

        ipo_data['margin_total'] = _safe_float(total_margin)
        ipo_data['public_offer'] = _safe_float(public_offer)
        actual_over = _safe_float(actual_over)
        forecast_over = _safe_float(forecast_over)

        estimated_subscription = None
        estimated_over = None
        if _is_num(ipo_data['margin_total']) and ipo_data['public_offer'] not in (None, 0):
            try:
                if ipo_data['public_offer'] > 0:
                    estimated_subscription = ipo_data['margin_total'] / ipo_data['public_offer']
                    estimated_over = estimated_subscription - 1
            except (ValueError, TypeError, ZeroDivisionError):
                estimated_subscription = None
                estimated_over = None

        if actual_over is not None:
            ipo_data['over_sub_ratio'] = actual_over
            ipo_data['over_sub_ratio_source'] = 'actual'
        elif forecast_over is not None:
            ipo_data['over_sub_ratio'] = forecast_over
            ipo_data['over_sub_ratio_source'] = 'forecast'
        elif estimated_over is not None:
            ipo_data['over_sub_ratio'] = estimated_over
            ipo_data['over_sub_ratio_source'] = 'estimated'
        else:
            ipo_data['over_sub_ratio'] = None
            ipo_data['over_sub_ratio_source'] = 'missing'

        ipo_data['estimated_subscription_ratio'] = estimated_subscription
        ipo_data['over_sub_ratio_estimated'] = estimated_over
        ipo_data['actual_over_sub_ratio'] = actual_over
        ipo_data['forecast_over_sub_ratio'] = forecast_over
        ipo_data['margin_detail'] = margin_detail

        # 只有在有真实/预测超购数据时才设置 market_heat
        if actual_over is not None:
            market_heat_value = actual_over
        elif forecast_over is not None:
            market_heat_value = forecast_over
        elif estimated_over is not None:
            market_heat_value = estimated_over
        else:
            market_heat_value = None

        ipo_data['market_heat'] = classify_market_heat(market_heat_value) or "缺失"

        logger.info("  ✓ 孖展资金总计: %s", f"{ipo_data['margin_total']:.2f}亿" if ipo_data['margin_total'] is not None else "--")
        logger.info("  ✓ 集资额（公开）: %s", f"{ipo_data['public_offer']:.2f}亿" if ipo_data['public_offer'] is not None else "--")
        logger.info("  ✓ 超购（实际）: %s", f"{actual_over:.2f}倍" if actual_over is not None else "--")
        logger.info("  ✓ 超购（预测）: %s", f"{forecast_over:.2f}倍" if forecast_over is not None else "--")
        if estimated_subscription is not None:
            logger.info("  ✓ 认购倍数（估算）: %.2f倍", estimated_subscription)
        if estimated_over is not None:
            logger.info("  ✓ 超购（估算）: %.2f倍", estimated_over)
        logger.info("  ✓ 市场热度: %s", ipo_data['market_heat'])
    elif margin_data:
        ipo_data['margin_total'] = _safe_float(margin_data)
        logger.info("  ✓ 孖展资金总计: %s", f"{ipo_data['margin_total']:.2f}亿" if ipo_data['margin_total'] is not None else "--")

    return ipo_data


def _detect_valuation_profitability_conflict(ipo_data, prospectus_info):
    """检测盈利状态与估值框架是否存在冲突。"""
    valuation = prospectus_info.get('valuation') or {}
    profitable = prospectus_info.get('profitable')
    biotech_label = valuation.get('biotech_valuation_label') or ''
    val_label = valuation.get('valuation_label') or ''
    is_conflict = False
    conflict_reasons = []

    if profitable is True:
        if '未盈利' in str(biotech_label):
            is_conflict = True
            conflict_reasons.append(f"盈利状态为盈利，但生物科技估值标签为'{biotech_label}'")
        if '未盈利' in str(val_label):
            is_conflict = True
            conflict_reasons.append(f"盈利状态为盈利，但估值标签包含'未盈利': '{val_label}'")

    if is_conflict:
        valuation['valuation_conflict'] = True
        valuation['valuation_conflict_reasons'] = conflict_reasons
        ipo_data['valuation_conflict'] = True
        ipo_data['valuation_conflict_reasons'] = conflict_reasons
    else:
        valuation['valuation_conflict'] = False
        valuation['valuation_conflict_reasons'] = []
        ipo_data['valuation_conflict'] = False
        ipo_data['valuation_conflict_reasons'] = []


def _validate_financial_year_consistency(ipo_data, prospectus_info):
    """校验财务年份一致性。若收入、净利润、毛利率年份不一致，标记为需要复核。"""
    revenue_year = prospectus_info.get('revenue_year')
    net_profit_year = prospectus_info.get('net_profit_year')
    gross_margin_year = prospectus_info.get('gross_margin_year')

    flags = list(prospectus_info.get('financial_data_quality_flags', []) or [])
    confidence = prospectus_info.get('financial_extract_confidence', 'unknown')
    has_issue = False
    has_severe_issue = False
    issue_reasons = []

    if revenue_year and net_profit_year:
        year_diff = abs(int(net_profit_year) - int(revenue_year))
        if year_diff > 0:
            has_severe_issue = True
            issue_reasons.append(f"收入年份({revenue_year})与净利润年份({net_profit_year})不一致")
            if "收入与净利润年份不一致" not in flags:
                flags.append("收入与净利润年份不一致")
            has_issue = True

    if revenue_year and gross_margin_year:
        year_diff = abs(int(gross_margin_year) - int(revenue_year))
        if year_diff > 0:
            has_severe_issue = True
            issue_reasons.append(f"收入年份({revenue_year})与毛利率年份({gross_margin_year})不一致")
            if "收入与毛利率年份不一致" not in flags:
                flags.append("收入与毛利率年份不一致")
            has_issue = True

    if has_issue:
        prospectus_info['financial_data_quality_flags'] = flags
        if has_severe_issue and confidence in ('high', 'medium'):
            prospectus_info['financial_extract_confidence'] = 'needs_review'
        ipo_data['financial_year_consistency_issue'] = has_severe_issue
        ipo_data['financial_year_consistency_reasons'] = issue_reasons
    else:
        ipo_data['financial_year_consistency_issue'] = False
        ipo_data['financial_year_consistency_reasons'] = []


def _calculate_risk_penalty(prospectus_info):
    """计算重大红旗风险惩罚，避免与 fundamental_score 重复扣分。

    只对以下重大红旗进行扣分：
    - 现金 runway < 12 个月
    - 重大诉讼
    - 持续经营重大不确定性
    - 审计保留意见
    - 核心产品监管失败/临床失败
    - 客户或供应商极端集中（largest_customer_pct >= 50 或 top5_customer_pct >= 80）
    - 财务数据异常且无法解释

    注意：基石红旗已在 ScoringSystem.calculate 中处理，本函数不再重复扣分。
    为避免重复扣分，已出现在 stock_quality reasons 中的同类风险不再扣 risk_penalty。
    """
    import re

    penalty_breakdown = []
    total_penalty = 0

    risk_result = prospectus_info.get('risk_factors', {})
    customer_result = prospectus_info.get('customer_supplier', {})
    valuation = prospectus_info.get('valuation', {})
    stock_quality = prospectus_info.get('stock_quality', {}) or {}
    quality_reasons = [r.lower() for r in stock_quality.get('reasons', [])]
    text = str(prospectus_info.get('_extracted_text', '') or '')

    rf = SETTINGS.risk_factor

    def _already_in_quality(flag_keywords):
        """检查 quality reasons 中是否已经提及同类风险。"""
        for qr in quality_reasons:
            if any(kw in qr for kw in flag_keywords):
                return True
        return False

    cash_runway = valuation.get('cash_runway_years')
    if _is_num(cash_runway) and cash_runway < 1:
        if not _already_in_quality(['现金runway', '现金紧张', '融资紧迫']):
            penalty = min(5, rf.max_total_penalty - total_penalty)
            total_penalty += penalty
            penalty_breakdown.append({
                'type': 'cash_runway',
                'penalty': penalty,
                'reason': f"现金runway仅{cash_runway:.1f}年，融资紧迫性高"
            })

    _HYPOTHETICAL_PREFIXES = re.compile(
        r'\b(may|might|could|would|if|should|potential|possible|hypothetical|assume|assuming|in\s+the\s+event)\b',
        re.IGNORECASE,
    )
    _ACTUAL_EVENT_RE = re.compile(
        r'\b(actual|existing|currently|已经|已发生|现有|正在|受到)\b',
        re.IGNORECASE,
    )

    def _classify_risk_evidence(evidence_text, pattern_name):
        """对风险证据进行分层分类。"""
        et_lower = evidence_text.lower()
        if _HYPOTHETICAL_PREFIXES.search(et_lower):
            return 'generic_risk_factor'
        if _ACTUAL_EVENT_RE.search(et_lower):
            return 'actual_event'
        return 'potential_risk'

    _MAJOR_RED_FLAG_PATTERNS = [
        ('lawsuit', 3, 1, 0, [
            re.compile(r'重大诉讼', re.IGNORECASE),
            re.compile(r'重大法律程序', re.IGNORECASE),
            re.compile(r'material\s+litigation', re.IGNORECASE),
            re.compile(r'class\s+action', re.IGNORECASE),
            re.compile(r'重大未决诉讼', re.IGNORECASE),
        ]),
        ('going_concern', 5, 2, 0, [
            re.compile(r'持续经营.*重大.*不确定', re.IGNORECASE),
            re.compile(r'going\s+concern.*material', re.IGNORECASE),
            re.compile(r'持续经营能力.*重大疑虑', re.IGNORECASE),
            re.compile(r'持续经营.*重大疑问', re.IGNORECASE),
        ]),
        ('audit_qualification', 5, 2, 0, [
            re.compile(r'审计.*保留意见', re.IGNORECASE),
            re.compile(r'audit\s+qualification', re.IGNORECASE),
            re.compile(r'核数师.*保留意见', re.IGNORECASE),
            re.compile(r'审计师.*不发表意见', re.IGNORECASE),
            re.compile(r'disclaimer\s+of\s+opinion', re.IGNORECASE),
            re.compile(r'adverse\s+opinion', re.IGNORECASE),
        ]),
        ('clinical_regulatory_failure', 5, 2, 0, [
            re.compile(r'临床.*失败', re.IGNORECASE),
            re.compile(r'clinical\s+failure', re.IGNORECASE),
            re.compile(r'clinical\s+hold', re.IGNORECASE),
            re.compile(r'监管.*拒绝', re.IGNORECASE),
            re.compile(r'regulatory\s+rejection', re.IGNORECASE),
            re.compile(r'CRL\b', re.IGNORECASE),
            re.compile(r'未获.*批准', re.IGNORECASE),
            re.compile(r'上市申请.*拒绝', re.IGNORECASE),
        ]),
        ('financial_irregularity', 3, 1, 0, [
            re.compile(r'财务.*异常', re.IGNORECASE),
            re.compile(r'financial\s+irregularity', re.IGNORECASE),
            re.compile(r'财务报表.*重大.*错报', re.IGNORECASE),
            re.compile(r'财务数据.*不一致', re.IGNORECASE),
        ]),
    ]

    for flag_type, actual_penalty, potential_penalty, generic_penalty, patterns in _MAJOR_RED_FLAG_PATTERNS:
        if total_penalty >= rf.max_total_penalty:
            break
        dedup_keywords = {
            'lawsuit': ['诉讼', 'litigation'],
            'going_concern': ['持续经营', 'going concern'],
            'audit_qualification': ['审计保留', 'audit qualification'],
            'clinical_regulatory_failure': ['临床失败', 'clinical failure', '监管失败'],
            'financial_irregularity': ['财务数据异常', 'financial irregularity'],
        }
        if _already_in_quality(dedup_keywords.get(flag_type, [])):
            continue
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                # 提取上下文作为证据
                start = max(0, match.start() - 120)
                end = min(len(text), match.end() + 120)
                evidence_excerpt = text[start:end].replace('\n', ' ').strip()
                section_name = 'risk_factors' if 'risk' in text[max(0, match.start()-500):match.start()].lower() else 'unknown'
                risk_tier = _classify_risk_evidence(evidence_excerpt, flag_type)
                if risk_tier == 'actual_event':
                    penalty = min(actual_penalty, rf.max_total_penalty - total_penalty)
                elif risk_tier == 'potential_risk':
                    penalty = min(potential_penalty, rf.max_total_penalty - total_penalty)
                else:
                    penalty = min(generic_penalty, rf.max_total_penalty - total_penalty)
                if penalty > 0:
                    total_penalty += penalty
                penalty_breakdown.append({
                    'type': flag_type,
                    'penalty': penalty,
                    'risk_tier': risk_tier,
                    'evidence_excerpt': evidence_excerpt[:240],
                    'confidence': 'keyword_match',
                    'section_name': section_name,
                    'reason': f"[{risk_tier}] 招股书文本匹配到风险: {pattern}" if risk_tier != 'actual_event' else f"[actual_event] 招股书文本匹配到已发生风险: {pattern}",
                })
                break

    # 客户集中度检查：检查 risk_factors 是否已标记高客户集中度，避免重复扣分
    customer_risk = risk_result.get('risks', {}).get('customer_concentration_risk', {})
    customer_already_penalized = customer_risk.get('risk_level') == '高'

    largest_customer_pct = customer_result.get('largest_customer_revenue_pct') or customer_result.get('largest_customer_pct')
    top5_customer_pct = customer_result.get('top5_customer_revenue_pct') or customer_result.get('top5_customer_pct')
    if not customer_already_penalized:
        if _is_num(largest_customer_pct) and largest_customer_pct >= 50:
            if not _already_in_quality(['客户集中', 'customer concentration']):
                penalty = min(3, rf.max_total_penalty - total_penalty)
                total_penalty += penalty
                penalty_breakdown.append({
                    'type': 'customer_concentration',
                    'penalty': penalty,
                    'reason': f"最大客户占比{largest_customer_pct:.0f}%，客户集中度极高"
                })
        elif _is_num(top5_customer_pct) and top5_customer_pct >= 80:
            if not _already_in_quality(['客户集中', 'customer concentration']):
                penalty = min(3, rf.max_total_penalty - total_penalty)
                total_penalty += penalty
                penalty_breakdown.append({
                    'type': 'customer_concentration',
                    'penalty': penalty,
                    'reason': f"前五大客户占比{top5_customer_pct:.0f}%，客户集中度极高"
                })

    total_penalty = min(total_penalty, rf.max_total_penalty)

    return {
        'total_penalty': total_penalty,
        'breakdown': penalty_breakdown
    }


def _apply_final_price_basis(ipo_data, prospectus_info):
    """When allotment data contains a final offer price, make valuation use it.

    The prospectus often carries the top-end offer price while the allotment
    announcement carries the final price. Keep the prospectus values for audit,
    but make downstream valuation, peer comparison, and display use the final
    price when it is available.
    """
    post_listing = ipo_data.get('post_listing') or {}
    if post_listing.get('status') == 'ok':
        post_listing = {k: v for k, v in post_listing.items() if k not in ('message',) and not (k == 'error' and not v)}
    final_price = post_listing.get('final_offer_price')
    if not _is_num(final_price) or float(final_price) <= 0:
        prospectus_info.setdefault('valuation_price_basis', 'prospectus_price')
        prospectus_info.setdefault('offer_price_source', 'prospectus')
        return

    final_price = float(final_price)
    original_offer_price = prospectus_info.get('offer_price')
    original_market_cap = prospectus_info.get('market_cap_hkd_million')

    if _is_num(original_offer_price):
        prospectus_info.setdefault('indicative_offer_price', original_offer_price)
    if _is_num(original_market_cap):
        prospectus_info.setdefault('indicative_market_cap_hkd_million', original_market_cap)

    shares = prospectus_info.get('shares_in_issue_post_listing')
    final_market_cap = None
    if _is_num(shares):
        final_market_cap = round(float(shares) * final_price / 1_000_000, 2)
    elif _is_num(original_market_cap) and _is_num(original_offer_price) and float(original_offer_price) > 0:
        final_market_cap = round(float(original_market_cap) * final_price / float(original_offer_price), 2)

    global_offer_shares = prospectus_info.get('global_offer_shares')
    hk_offer_shares = prospectus_info.get('hk_offer_shares')
    final_total_fund = None
    final_public_offer = None
    if _is_num(global_offer_shares):
        final_total_fund = round(final_price * float(global_offer_shares) / 100_000_000, 2)
    if _is_num(hk_offer_shares):
        final_public_offer = round(final_price * float(hk_offer_shares) / 100_000_000, 2)

    prospectus_info['final_offer_price'] = final_price
    prospectus_info['offer_price'] = final_price
    prospectus_info['offer_price_source'] = 'final_price'
    prospectus_info['valuation_price_basis'] = 'final_price'
    if final_market_cap is not None:
        prospectus_info['final_market_cap_hkd_million'] = final_market_cap
        prospectus_info['market_cap_hkd_million'] = final_market_cap
    if final_total_fund is not None:
        prospectus_info['final_total_fund'] = final_total_fund
        prospectus_info['total_fund'] = final_total_fund
        ipo_data['total_fund'] = final_total_fund
    if final_public_offer is not None:
        prospectus_info['final_public_offer'] = final_public_offer
        prospectus_info['public_offer'] = final_public_offer
        ipo_data['public_offer'] = final_public_offer

    revenue = prospectus_info.get('revenue')
    fin_currency = prospectus_info.get('financial_currency', 'RMB')
    fx = SETTINGS.fx.rmb_to_hkd if fin_currency == 'RMB' else (SETTINGS.fx.usd_to_hkd if fin_currency == 'USD' else 1.0)
    if _is_num(final_market_cap) and _is_num(revenue) and float(revenue) > 0:
        prospectus_info['final_ps_ratio'] = round(final_market_cap / (float(revenue) * fx), 2)

    board_lot = prospectus_info.get('lot_size')
    if _is_num(board_lot):
        prospectus_info['entry_fee_hkd'] = final_price * float(board_lot) * (1 + SETTINGS.fx.entry_fee_rate)


# ---------------------------------------------------------------------------
# 分析阶段辅助函数（从 _calculate_final_score 抽取）
# ---------------------------------------------------------------------------

_CORE_ANALYZERS = [
    ('business_breakdown', BusinessBreakdownAnalyzer),
    ('geographic', GeographicExpansionAnalyzer),
    ('customer_supplier', CustomerSupplierAnalyzer),
    ('cashflow', WorkingCapitalCashFlowAnalyzer),
    ('capacity', ProductionCapacityAnalyzer),
    ('rnd_pipeline', RnDPipelineAnalyzer),
    ('risk_factors', RiskFactorAnalyzer),
    ('shareholder', ShareholderAnalyzer),
    ('order_backlog', OrderBacklogAnalyzer),
]


def _run_single_analyzer(key, analyzer_cls, prospectus_info, prospectus_text):
    """执行单个分析器并容错。"""
    try:
        return key, analyzer_cls().analyze(prospectus_info, prospectus_text or "")
    except (ValueError, TypeError, KeyError, AttributeError) as e:
        logger.warning("%s 分析异常: %s", key, e)
        return key, {"_error": str(e), "warnings": [f"分析异常: {e}"]}


def _run_parallel_analyzers(prospectus_info, prospectus_text):
    """阶段 1：并行运行 9 个核心分析器。"""
    with ThreadPoolExecutor(max_workers=min(len(_CORE_ANALYZERS), 4)) as executor:
        futures = {
            executor.submit(_run_single_analyzer, key, cls, prospectus_info, prospectus_text): key
            for key, cls in _CORE_ANALYZERS
        }
        for future in as_completed(futures):
            key, result = future.result()
            prospectus_info[key] = result


def _run_peer_and_valuation(prospectus_info, prospectus_text, ipo_data):
    """阶段 2：同行对比 + 子行业修正 + 估值分析。"""
    try:
        peer_result = PeerComparableAnalyzer().analyze(prospectus_info, prospectus_text, ipo_data)
    except (ValueError, TypeError, KeyError, AttributeError) as e:
        logger.warning("同行对比分析异常: %s", e)
        peer_result = {"warnings": [f"分析异常: {e}"], "_error": str(e)}
    prospectus_info['peer_comparison'] = peer_result

    # 子行业回退修正
    subsector = (peer_result or {}).get('subsector')
    biotech_subsectors = (
        'innovative_drug_biotech', 'ai_drug_delivery_nanomedicine',
        'io_oncology', 'gene_therapy', 'cell_therapy', 'adc_biotech',
    )
    if subsector in biotech_subsectors and prospectus_info.get('sector') != 'healthcare':
        logger.info("子行业回退修正: %s -> healthcare (subsector=%s)", prospectus_info.get('sector'), subsector)
        prospectus_info['sector'] = 'healthcare'
        cf = prospectus_info.get('cashflow') or {}
        if isinstance(cf, dict) and cf.get('cash_quality_label') == '弱':
            runway = cf.get('cash_runway_years')
            if _is_num(runway) and runway >= 5:
                cf['cash_quality_label'] = '一般'
                cf.setdefault('working_capital_trend_reasons', []).append('经营现金流为负，但现金runway充足(≥5年)')

    # 估值分析
    try:
        valuation_result = ValuationAnalyzer().analyze(prospectus_info, prospectus_text, ipo_data)
    except (ValueError, TypeError, KeyError, AttributeError) as e:
        logger.warning("估值分析异常: %s", e)
        valuation_result = {"_error": str(e), "warnings": [f"分析异常: {e}"]}
    prospectus_info['valuation'] = valuation_result

    try:
        thesis_result = InvestmentThesisAnalyzer().analyze(prospectus_info, prospectus_text, ipo_data)
    except (ValueError, TypeError, KeyError, AttributeError) as e:
        logger.warning("投研叙事综合分析异常: %s", e)
        thesis_result = {"_error": str(e), "warnings": [f"分析异常: {e}"]}
    prospectus_info['investment_thesis'] = thesis_result


def _run_signal_and_quality(signal_analyzer, quality_analyzer, ipo_data, prospectus_info, prospectus_text):
    """阶段 3：信号分析与质量分析，返回 (signal_result, stock_quality)。"""
    try:
        signal_result = signal_analyzer.analyze(ipo_data, prospectus_info, prospectus_text)
    except (ValueError, TypeError, KeyError, AttributeError) as e:
        logger.warning("信号分析异常: %s", e)
        signal_result = {"score": 0, "components": {}, "signal_breakdown": {}}
    prospectus_info['advanced_framework'] = signal_result

    # 基石占比冲突检测
    cornerstone_analysis = prospectus_info.get('cornerstone_analysis') or {}
    cornerstone_pct_text = cornerstone_analysis.get('cornerstone_pct')
    cornerstone_pct_table = prospectus_info.get('cornerstone_offer_ratio_pct')
    if cornerstone_pct_text is not None and cornerstone_pct_table is not None:
        diff = abs(cornerstone_pct_text - cornerstone_pct_table)
        if diff > 10:
            logger.warning(
                "基石占比来源差异较大: 正则提取=%.1f%%, 表格计算=%.1f%% (差异%.1f%%)",
                cornerstone_pct_text, cornerstone_pct_table, diff,
            )

    # 合并招股书发行数据到 ipo_data
    for fld in ('public_offer', 'total_fund', 'public_offer_ratio_pct', 'cornerstone_offer_ratio_pct', 'cornerstone_pct'):
        pi_val = prospectus_info.get(fld)
        if pi_val is not None and ipo_data.get(fld) in (None, ''):
            ipo_data[fld] = pi_val

    try:
        stock_quality = quality_analyzer.analyze(prospectus_info)
    except (ValueError, TypeError, KeyError, AttributeError) as e:
        logger.warning("质量分析异常: %s", e)
        stock_quality = {"score": 0, "label": "缺失", "reasons": [f"分析异常: {e}"], "dimensions": {}}
    prospectus_info['stock_quality'] = stock_quality

    return signal_result, stock_quality


def _run_investskill_analyzers(prospectus_info):
    """阶段 4：InvestSkill 框架（Piotroski + DCF + Sector + Profile）。"""
    try:
        piotroski_result = PiotroskiFAnalyzer().analyze(prospectus_info)
        prospectus_info['piotroski_f'] = piotroski_result
        logger.info("Piotroski F-Score: %d/%d (%s)", piotroski_result.total_score, piotroski_result.max_score, piotroski_result.grade)
    except Exception as e:
        logger.warning("Piotroski F-Score 分析异常: %s", e)

    try:
        dcf_result = DCFValuationAnalyzer().analyze(prospectus_info)
        prospectus_info['dcf_valuation'] = dcf_result
        if dcf_result.valuation_label != "缺失":
            logger.info(
                "DCF估值: %s (内在价值=%.0f, 上行空间=%.1f%%)",
                dcf_result.valuation_label,
                dcf_result.intrinsic_value_hkd or 0,
                dcf_result.upside_pct or 0,
            )
    except Exception as e:
        logger.warning("DCF 估值分析异常: %s", e)

    try:
        sector_result = SectorAnalyzer().analyze(prospectus_info)
        prospectus_info['sector_analysis'] = sector_result
        logger.info(
            "行业赛道: %s (贝塔=%s, 周期=%s, 政策=%s)",
            sector_result.sector_name,
            sector_result.sector_beta_label,
            sector_result.cycle_position,
            sector_result.policy_support,
        )
    except Exception as e:
        logger.warning("行业赛道分析异常: %s", e)

    try:
        profile_result = CompanyProfileAnalyzer.analyze(prospectus_info)
        prospectus_info['company_profile'] = profile_result
        logger.info(
            "公司简介: %s (置信度=%s)",
            profile_result.company_summary[:50] if profile_result.company_summary else "无",
            profile_result.confidence,
        )
    except Exception as e:
        logger.warning("公司简介提取异常: %s", e)


def _collect_analyzer_errors(prospectus_info):
    """收集所有分析器的 _error。"""
    extra_keys = ['peer_comparison', 'valuation', 'investment_thesis', 'advanced_framework', 'stock_quality', 'piotroski_f', 'dcf_valuation', 'sector_analysis', 'company_profile']
    all_keys = [key for key, _ in _CORE_ANALYZERS] + extra_keys
    errors = {}
    for key in all_keys:
        result = prospectus_info.get(key, {})
        if isinstance(result, dict) and result.get('_error'):
            errors[key] = result['_error']
    return errors


def _inject_market_context(prospectus_info, prospectus_text):
    """注入市场情绪、宏观环境、回拨、孖展验证、自动同行提取。"""
    from .ipo_sentiment import get_ipo_sentiment
    from .macro_factors import get_macro_factors
    from .clawback_impact import analyze_clawback_impact
    from .margin_validator import validate_margin_data
    from .peer_auto_expand import extract_peer_companies_from_text

    prospectus_info['ipo_sentiment'] = get_ipo_sentiment()
    prospectus_info['macro_factors'] = get_macro_factors()
    prospectus_info['clawback_impact'] = analyze_clawback_impact(prospectus_info)
    prospectus_info['margin_validity'] = validate_margin_data(prospectus_info)
    prospectus_info['auto_peer_companies'] = extract_peer_companies_from_text(prospectus_text)


def _apply_scoring_and_risk(scorer, ipo_data, prospectus_info, signal_result):
    """阶段 5：评分计算 + 风险惩罚，返回 (final_score, scoring, risk_penalty_result)。"""
    scoring = scorer.calculate(ipo_data, prospectus_info, signal_components=signal_result.get('components'))
    risk_penalty_result = _calculate_risk_penalty(prospectus_info)
    total_risk_penalty = risk_penalty_result['total_penalty']
    risk_penalty_breakdown = risk_penalty_result['breakdown']

    final_score = max(0, min(100, scoring['score'] - total_risk_penalty))

    parse_success = prospectus_info.get('parse_success', False)
    analysis_mode = 'full'
    if not parse_success:
        analysis_mode = 'market_only'
        if "仅热度参考" not in str(scoring.get('reasons', [])):
            scoring.setdefault('reasons', []).append("招股书解析失败，评分仅热度参考")

    trace = scoring.get('score_trace', {}) or {}
    trace['risk_penalty'] = total_risk_penalty
    trace['risk_penalty_breakdown'] = [b['reason'] for b in risk_penalty_breakdown]
    trace['true_final_score'] = final_score
    scoring['score_trace'] = trace

    return final_score, scoring, risk_penalty_result, analysis_mode


def _normalize_output_fields(ipo_data, prospectus_info, scoring, risk_penalty_result, signal_result, stock_quality, analysis_mode, analyzer_errors):
    """阶段 6：字段映射、规范化、语义转换。"""
    total_risk_penalty = risk_penalty_result['total_penalty']
    risk_penalty_breakdown = risk_penalty_result['breakdown']

    if analyzer_errors:
        ipo_data['analyzer_errors'] = analyzer_errors

    ipo_data['score'] = max(0, min(100, scoring['score'] - total_risk_penalty))
    ipo_data['subscription_score'] = scoring.get('subscription_score', 0)
    ipo_data['ipo_trade_score'] = scoring.get('ipo_trade_score', scoring.get('trade_score', 0))
    ipo_data['strict_ipo_score'] = scoring.get('strict_ipo_score', ipo_data['ipo_trade_score'])
    ipo_data['raw_trade_signal_score'] = scoring.get('raw_trade_signal_score', scoring.get('trade_score', 0))
    ipo_data['strict_scoring_profile'] = scoring.get('strict_scoring_profile', '')
    ipo_data['ipo_trade_label'] = scoring.get('ipo_trade_label', '')
    ipo_data['long_term_score'] = scoring.get('long_term_score', 0)
    ipo_data['raw_long_term_score_before_penalty'] = scoring.get('raw_long_term_score_before_penalty')
    ipo_data['long_term_penalty'] = scoring.get('long_term_penalty')
    ipo_data['long_term_penalty_reasons'] = [r for r in (scoring.get('long_term_penalty_reasons') or []) if r]
    ipo_data['long_term_label'] = scoring.get('long_term_label', '')
    ipo_data['fisher_label'] = scoring.get('fisher_label', '')
    ipo_data['lynch_label'] = scoring.get('lynch_label', '')
    ipo_data['valuation_pressure_label'] = scoring.get('valuation_pressure_label', '')
    ipo_data['subscription_recommendation'] = scoring.get('subscription_recommendation', '')
    ipo_data['recommendation_reasons'] = scoring.get('recommendation_reasons', [])
    ipo_data['fundamental_score'] = scoring.get('fundamental_score', stock_quality.get('score', 0))
    ipo_data['stock_quality_score'] = stock_quality.get('score', 0)
    ipo_data['score_reasons'] = scoring['reasons']
    ipo_data['score_breakdown'] = scoring.get('components', {})
    ipo_data['risk_penalty'] = total_risk_penalty
    ipo_data['risk_penalty_breakdown'] = risk_penalty_breakdown
    ipo_data['trade_score'] = scoring.get('trade_score', 0)
    ipo_data['valuation_score'] = scoring.get('valuation_score', 0)
    ipo_data['theme_score'] = scoring.get('theme_score', 0)
    dq_component = signal_result.get('components', {}).get('data_quality', {})
    ipo_data['data_quality_score'] = min(100, round(dq_component.get('score', 0) / 5 * 100))
    ipo_data['weight_profile'] = scoring.get('weight_profile')
    ipo_data['debug_info'] = scoring.get('debug_info')
    ipo_data['score_trace'] = scoring.get('score_trace')
    ipo_data['penalty_reason'] = scoring.get('penalty_reason')
    ipo_data['analysis_mode'] = analysis_mode
    ipo_data['advanced_framework_score'] = signal_result.get('score', 0)
    ipo_data['advanced_score_adjustment'] = 0
    ipo_data['signal_breakdown'] = signal_result.get('signal_breakdown', {})
    ipo_data['prospectus_info'] = prospectus_info
    ipo_data['stock_quality'] = stock_quality
    ipo_data['investment_thesis'] = prospectus_info.get('investment_thesis')

    for field in _PROSPECTUS_COPY_FIELDS:
        if field in prospectus_info:
            ipo_data[field] = prospectus_info[field]

    # 语义规范化
    if _safe_float(ipo_data.get('public_offer')) is not None:
        ipo_data['public_offer_fund_hkd_billion'] = ipo_data['public_offer']
    if _safe_float(ipo_data.get('total_fund')) is not None:
        ipo_data['total_fund_hkd_billion'] = ipo_data['total_fund']
    if _safe_float(ipo_data.get('margin_total')) is not None:
        ipo_data['margin_total_hkd_billion'] = ipo_data['margin_total']

    # 截止日 fallback
    if not ipo_data.get('apply_start_date') and prospectus_info.get('apply_start_date'):
        ipo_data['apply_start_date'] = prospectus_info['apply_start_date']
    if not ipo_data.get('apply_end_date') and prospectus_info.get('apply_end_date'):
        ipo_data['apply_end_date'] = prospectus_info['apply_end_date']

    _detect_valuation_profitability_conflict(ipo_data, prospectus_info)
    _validate_financial_year_consistency(ipo_data, prospectus_info)

    # 映射前端展示字段
    if _safe_float(ipo_data.get('public_offer_ratio_pct')):
        ipo_data['public_offer_ratio'] = ipo_data['public_offer_ratio_pct']
    if _safe_float(ipo_data.get('international_offer_ratio_pct')):
        ipo_data['international_offer_ratio'] = ipo_data['international_offer_ratio_pct']

    _hk_shares = _safe_float(ipo_data.get('hk_offer_shares'))
    _intl_shares = _safe_float(ipo_data.get('international_offer_shares'))
    _total_shares = _safe_float(ipo_data.get('global_offer_shares'))
    if not _total_shares and _hk_shares and _intl_shares:
        _total_shares = _hk_shares + _intl_shares
    if not _safe_float(ipo_data.get('public_offer_ratio')) and _hk_shares and _total_shares and _total_shares > 0:
        ipo_data['public_offer_ratio'] = _hk_shares / _total_shares * 100
    if not _safe_float(ipo_data.get('international_offer_ratio')) and _intl_shares and _total_shares and _total_shares > 0:
        ipo_data['international_offer_ratio'] = _intl_shares / _total_shares * 100

    # 公开发售手数
    hk_offer_shares = _safe_float(ipo_data.get('hk_offer_shares'))
    board_lot = _safe_float(ipo_data.get('board_lot')) or _safe_float(ipo_data.get('lot_size'))
    if hk_offer_shares and board_lot and board_lot > 0:
        ipo_data['public_offer_lots'] = hk_offer_shares / board_lot


def _run_practical_analysis(prospectus_info, ipo_data):
    """实战分析模块：中签率预测、甲乙组策略、绿鞋机制、暗盘信号、新股日历、卖出时机。"""
    from .allotment_predictor import AllotmentPredictor
    from .a_b_group_strategy import ABGroupStrategyAnalyzer
    from .greenshoe_analyzer import GreenshoeAnalyzer
    from .grey_market_signal import GreyMarketSignalAnalyzer
    from .ipo_calendar import IPOCalendarCalculator
    from .sell_timing_advisor import SellTimingAdvisor
    
    over_sub = ipo_data.get('over_sub_ratio') or ipo_data.get('forecast_over_sub_ratio')
    try:
        over_sub = float(over_sub) if over_sub else None
    except (TypeError, ValueError):
        over_sub = None
    
    allotment_predictor = AllotmentPredictor()
    allotment_prediction = allotment_predictor.predict_one_lot_allotment(over_sub)
    group_allotment = allotment_predictor.predict_group_allotment(over_sub)
    steady_capital = allotment_predictor.predict_steady_one_lot_capital(over_sub)
    
    prospectus_info['allotment_prediction'] = {
        'one_lot_rate_min': allotment_prediction.one_lot_rate_min,
        'one_lot_rate_max': allotment_prediction.one_lot_rate_max,
        'heat_label': allotment_prediction.heat_label,
        'detail': allotment_prediction.detail,
        'group_a': {
            'one_lot_rate_min': group_allotment.get('group_a_one_lot_rate_min'),
            'one_lot_rate_max': group_allotment.get('group_a_one_lot_rate_max'),
        },
        'group_b': {
            'one_lot_rate_min': group_allotment.get('group_b_one_lot_rate_min'),
            'one_lot_rate_max': group_allotment.get('group_b_one_lot_rate_max'),
            'multiplier': group_allotment.get('group_b_multiplier'),
        },
        'steady_one_lot': steady_capital,
    }
    
    ab_strategy = ABGroupStrategyAnalyzer()
    ab_result = ab_strategy.analyze(
        over_sub_ratio=over_sub,
        public_offer_shares=prospectus_info.get('public_offer_shares'),
        lot_size=prospectus_info.get('lot_size'),
    )
    prospectus_info['ab_group_strategy'] = ab_result
    
    greenshoe = GreenshoeAnalyzer()
    greenshoe_result = greenshoe.analyze(prospectus_info)
    prospectus_info['greenshoe'] = greenshoe_result
    
    # 暗盘交易信号（如果有暗盘数据）
    post_listing = ipo_data.get('post_listing') or prospectus_info.get('post_listing') or {}
    grey_market = post_listing.get('grey_market', {})
    if grey_market.get('status') == 'ok' and grey_market.get('price'):
        grey_analyzer = GreyMarketSignalAnalyzer()
        grey_signal = grey_analyzer.analyze(
            grey_price=grey_market.get('price'),
            offer_price=ipo_data.get('offer_price') or prospectus_info.get('offer_price'),
            grey_volume=grey_market.get('volume'),
            public_offer_shares=prospectus_info.get('public_offer_shares'),
        )
        prospectus_info['grey_market_signal'] = {
            'change_pct': grey_signal.change_pct,
            'signal_strength': grey_signal.signal_strength,
            'score_adjustment': grey_signal.score_adjustment,
            'volume_ratio_pct': grey_signal.volume_ratio_pct,
            'volume_label': grey_signal.volume_label,
            'detail': grey_signal.detail,
        }
    
    # 新股日历
    calendar_calc = IPOCalendarCalculator()
    calendar = calendar_calc.calculate(
        apply_start_date=ipo_data.get('apply_start_date'),
        apply_end_date=ipo_data.get('apply_end_date'),
        listing_date=ipo_data.get('listing_date') or prospectus_info.get('listing_date'),
        has_greenshoe=greenshoe_result.get('has_greenshoe'),
    )
    prospectus_info['ipo_calendar'] = calendar
    
    # 卖出时机建议
    sell_advisor = SellTimingAdvisor()
    sell_timing = sell_advisor.analyze(
        sector=prospectus_info.get('sector'),
        subsector=prospectus_info.get('peer_comparison', {}).get('subsector') if prospectus_info.get('peer_comparison') else None,
        grey_market_change_pct=grey_market.get('change_pct') if grey_market.get('status') == 'ok' else None,
        over_sub_ratio=over_sub,
        cornerstone_quality=prospectus_info.get('cornerstone_analysis', {}).get('tier_label') if prospectus_info.get('cornerstone_analysis') else None,
    )
    prospectus_info['sell_timing'] = {
        'recommended_hold_days': sell_timing.recommended_hold_days,
        'sell_timing_label': sell_timing.sell_timing_label,
        'confidence': sell_timing.confidence,
        'reasoning': sell_timing.reasoning,
        'detail': sell_timing.detail,
    }
    
    logger.info(
        "实战分析: 中签率=%s, 绿鞋=%s, 卖出建议=%s",
        allotment_prediction.heat_label,
        "有" if greenshoe_result.get("has_greenshoe") else "无" if greenshoe_result.get("has_greenshoe") is False else "未知",
        sell_timing.sell_timing_label,
    )


def _calculate_final_score(scorer, quality_analyzer, signal_analyzer, ipo_data, prospectus_info, prospectus_text):
    """评分管线主编排函数：按阶段调用各辅助函数。"""
    _apply_final_price_basis(ipo_data, prospectus_info)

    if prospectus_text and '_text_lower' not in prospectus_info:
        prospectus_info['_text_lower'] = prospectus_text.lower()

    with _PerfTimer("parallel_analyzers"):
        _run_parallel_analyzers(prospectus_info, prospectus_text)
    with _PerfTimer("peer_and_valuation"):
        _run_peer_and_valuation(prospectus_info, prospectus_text, ipo_data)
    with _PerfTimer("signal_and_quality"):
        signal_result, stock_quality = _run_signal_and_quality(
            signal_analyzer, quality_analyzer, ipo_data, prospectus_info, prospectus_text
        )
    with _PerfTimer("investskill_analyzers"):
        _run_investskill_analyzers(prospectus_info)
    with _PerfTimer("collect_errors"):
        analyzer_errors = _collect_analyzer_errors(prospectus_info)
    with _PerfTimer("market_context"):
        _inject_market_context(prospectus_info, prospectus_text)
    with _PerfTimer("practical_analysis"):
        _run_practical_analysis(prospectus_info, ipo_data)
    with _PerfTimer("scoring_and_risk"):
        final_score, scoring, risk_penalty_result, analysis_mode = _apply_scoring_and_risk(
            scorer, ipo_data, prospectus_info, signal_result
        )
    with _PerfTimer("normalize_output"):
        _normalize_output_fields(
            ipo_data, prospectus_info, scoring, risk_penalty_result,
            signal_result, stock_quality, analysis_mode, analyzer_errors,
        )


def _run_scoring_pipeline(ipo_data, prospectus_info, prospectus_text, pdf_path=None):
    """统一评分管线：_calculate_final_score + _attach_debug_info + IPOData 规范化"""
    with _PerfTimer("scoring_pipeline_total"):
        scorer, quality_analyzer, advanced_analyzer = _init_analyzers()
        _calculate_final_score(scorer, quality_analyzer, advanced_analyzer, ipo_data, prospectus_info, prospectus_text)
        _attach_debug_info(ipo_data, pdf_path, prospectus_info, prospectus_text)
        try:
            from .models import IPOData
            normalized = IPOData.from_dict(ipo_data)
            if normalized is not None:
                return normalized.to_dict(drop_runtime=False)
        except (ValueError, TypeError, KeyError, AttributeError, ImportError) as e:
            logger.warning("IPOData 模型规范化失败: %s，返回原始 dict", e)
        return ipo_data


def _init_analyzers():
    return ScoringSystem(), ProspectusQualityAnalyzer(), SignalComponentAnalyzer()


def _process_ipo(client, downloader, parser, ipo, output_dir, force_refresh=False):
    company_name = ipo.get('shortname', '') or ipo.get('shortName', '') or ipo.get('name', '')
    stock_code = ipo.get('symbol', '') or ipo.get('stockCode', '')
    safe_code = _sanitize_stock_code(stock_code)
    local_pdf = os.path.join(output_dir, f"{safe_code}_prospectus.pdf")

    if force_refresh and os.path.exists(local_pdf):
        try:
            os.remove(local_pdf)
        except OSError:
            pass

    pdf_path = None
    if not force_refresh and os.path.exists(local_pdf):
        pdf_path = local_pdf
        logger.info(f"使用本地PDF: {local_pdf}")
        ipo_data = _fetch_margin_data(client, ipo)
    else:
        with ThreadPoolExecutor(max_workers=2) as _exec:
            margin_future = _exec.submit(client.fetch_margin_detail, stock_code)
            pdf_future = _exec.submit(_try_download_pdf, downloader, stock_code, company_name)
            margin_detail = margin_future.result()
            pdf_path = pdf_future.result()
        ipo_data = _fetch_margin_data(client, ipo, margin_detail=margin_detail)

    prospectus_info = {}
    if pdf_path and os.path.exists(pdf_path):
        if not os.path.exists(local_pdf) or force_refresh:
            try:
                shutil.copy2(pdf_path, local_pdf)
            except OSError:
                pass
        prospectus_info = parser.parse(stock_code, company_name)

    prospectus_text = prospectus_info.get('_extracted_text', '') or ""
    return _run_scoring_pipeline(ipo_data, prospectus_info, prospectus_text, pdf_path)


def _try_download_pdf(downloader, stock_code, company_name):
    try:
        return downloader.download_from_hkex(stock_code, company_name)
    except (ConnectionError, TimeoutError, OSError, ValueError) as e:
        logger.warning(f"招股书下载异常: {e}")
        return None


def main():
    logger.info("="*80)
    logger.info("  港股IPO分析器 - 自动更新与评分")
    logger.info("  时间: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    logger.info("="*80)

    temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "temp")
    temp_dir = os.path.abspath(temp_dir)
    results = analyze_live_ipos(output_dir=temp_dir)

    if not results:
        logger.info("\n✗ 没有正在招股的IPO")
        return

    logger.info("\n\n" + "="*80)
    logger.info("  申购优先级排名")
    logger.info("="*80 + "\n")
    
    for i, ipo in enumerate(results, 1):
        logger.info("%d. %s (%s) - 评分: %d/100", i, ipo['company_name'], ipo['hk_code'], ipo.get('score', 0))
        logger.info("   招股期: %s 至 %s", ipo.get('apply_start_date', ''), ipo.get('apply_end_date', ''))
        if ipo.get('margin_total') is not None:
            logger.info("   孖展资金总计: %.2f亿", ipo['margin_total'])
        if ipo.get('public_offer') is not None:
            logger.info("   集资额（公开）: %.2f亿", ipo['public_offer'])
        if ipo.get('actual_over_sub_ratio'):
            logger.info("   超购（实际）: %.2f倍", ipo['actual_over_sub_ratio'])
        if ipo.get('forecast_over_sub_ratio'):
            logger.info("   超购（预测）: %.2f倍", ipo['forecast_over_sub_ratio'])
        if ipo.get('estimated_subscription_ratio'):
            logger.info("   认购倍数（估算）: %.2f倍", ipo['estimated_subscription_ratio'])
        if ipo.get('over_sub_ratio_estimated'):
            logger.info("   超购（估算参考）: %.2f倍", ipo['over_sub_ratio_estimated'])
        logger.info("   申购热度分: %d/100", ipo.get('subscription_score', 0))
        logger.info("   股票质地分: %d/100", ipo.get('fundamental_score', 0))
        if ipo.get('market_heat'):
            logger.info("   市场热度: %s", ipo['market_heat'])

        cornerstone_analysis = ipo.get('prospectus_info', {}).get('cornerstone_analysis', {})
        if cornerstone_analysis:
            has_cs_section = cornerstone_analysis.get('has_cornerstone_section', True)
            cs_score = cornerstone_analysis.get('score', 0)
            if has_cs_section and cs_score > 0:
                logger.info("   基石信号: %s / %s (%d/100)", cornerstone_analysis.get('label', '--'), cornerstone_analysis.get('recommendation', '--'), cs_score)
                if cornerstone_analysis.get('cornerstone_pct') is not None:
                    logger.info("   基石占比: %.1f%%", cornerstone_analysis['cornerstone_pct'])
                matched = cornerstone_analysis.get('matched_investors', [])
                cornerstone_rows = cornerstone_analysis.get('cornerstone_investors', [])
                if cornerstone_rows:
                    logger.info("   招股书基石投资者名单（%d家）:", len(cornerstone_rows))
                    for row in cornerstone_rows:
                        row_name = row.get('name', '--')
                        matched_investors = row.get('matched_investors', [])
                        is_matched = row.get('is_matched', False)
                        tier = row.get('tier')

                        extra = []
                        if row.get('offer_shares_pct') is not None:
                            extra.append(f"占发售股份{row.get('offer_shares_pct'):.2f}%")
                        amount_text = _format_cornerstone_amount(row)
                        if amount_text != "--":
                            extra.append(amount_text)
                        extra_text = f"｜{'，'.join(extra)}" if extra else ""

                        if is_matched and matched_investors:
                            match_names = "、".join(f"{item.get('name')}({item.get('tier')})" for item in matched_investors)
                            logger.info("     - %s（V2分级 → %s）%s", row_name, match_names, extra_text)
                        elif is_matched and tier:
                            logger.info("     - %s（V2分级 → %s级）%s", row_name, tier, extra_text)
                        else:
                            logger.info("     - %s（V2未分级）%s", row_name, extra_text)
                elif matched:
                    logger.info("   招股书基石投资者名单未完整提取，以下为V2重点机构:")
                    for item in matched:
                        tier = item.get('tier', 'N/A')
                        name = item.get('name', 'N/A')
                        logger.info("     - %s（%s级）", name, tier)
                if matched and not cornerstone_rows:
                    pass
                elif not matched:
                    logger.info("   V2未识别到S级或A级重点基石")
                for red_flag in cornerstone_analysis.get('red_flags', []):
                    logger.info("   基石红旗: %s", red_flag)
            elif not has_cs_section:
                logger.info("   基石信号: 未披露基石投资者")
            else:
                logger.info("   基石信号: %s / %s (%d/100)", cornerstone_analysis.get('label', '--'), cornerstone_analysis.get('recommendation', '--'), cs_score)
                for red_flag in cornerstone_analysis.get('red_flags', []):
                    logger.info("   基石红旗: %s", red_flag)

        stock_quality = ipo.get('stock_quality', {})
        if stock_quality:
            logger.info("   股票质地: %s (%d/100)", stock_quality.get('label', '--'), stock_quality.get('score', 0))
            dimensions = stock_quality.get('dimensions', {})
            for dim_name, dim_title in [
                ('growth', '成长性'),
                ('profitability', '盈利质量'),
                ('valuation', '估值压力'),
                ('risk', '风险点'),
            ]:
                dim = dimensions.get(dim_name, {})
                if dim:
                    line = f"   {dim_title}: {dim.get('label', '--')}"
                    detail = dim.get('detail')
                    if detail:
                        line += f" - {detail}"
                    logger.info(line)
            for reason in stock_quality.get('reasons', []):
                logger.info("     • %s", reason)

        prospectus_info = ipo.get('prospectus_info', {})
        if prospectus_info.get('gross_margin'):
            gm = prospectus_info['gross_margin']
            gm_pct = _normalize_gm(gm)
            logger.info("   毛利率: %.1f%%", gm_pct)

        logger.info("   评分理由:")
        for reason in ipo.get('score_reasons', []):
            logger.info("     • %s", reason)

    logger.info("")

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    pdf_file = os.path.join(temp_dir, f"IPO分析报告_{timestamp}.pdf")
    try:
        export_pdf_report(results, pdf_file)
    except (OSError, ValueError, TypeError, ImportError) as e:
        logger.error("✗ PDF生成失败: %s", e)

    json_file = os.path.join(temp_dir, f"ipo_live_data_{timestamp}.json")
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info("✓ 数据已保存: %s", json_file)

    # 清理超过7天的临时文件
    for old_file in os.listdir(temp_dir):
        old_path = os.path.join(temp_dir, old_file)
        try:
            if os.path.isfile(old_path) and time.time() - os.path.getmtime(old_path) > SETTINGS.file.temp_file_ttl_days * 86400:
                os.remove(old_path)
        except OSError:
            pass

    try:
        if platform.system() == "Darwin":
            subprocess.run(["open", pdf_file], check=False)
    except (OSError, FileNotFoundError):
        pass
    logger.info("\n" + "="*80)
    logger.info("  分析完成！")
    logger.info("="*80)


def _live_status(status, results=None, message=""):
    return {
        "status": status,
        "results": results or [],
        "message": message,
    }


def _refresh_live_blogger_consensus(results, output_dir="temp"):
    if not results:
        return

    db_path = os.path.join(output_dir, "blogger_monitor.db")
    service = BloggerMonitorService(db_path=db_path)

    for ipo in results:
        stock_code = str(ipo.get("hk_code", "") or "").strip()
        company_name = str(ipo.get("company_name", "") or "").strip()
        if not stock_code or not company_name:
            continue
        try:
            logger.info("刷新博主观点: %s (%s)", company_name, stock_code)
            service.run_full_pipeline(stock_code, company_name=company_name)
        except Exception as e:
            logger.warning("博主观点刷新失败 %s (%s): %s", company_name, stock_code, e)


def analyze_live_ipos(output_dir="temp", force_refresh=False, return_status=False):
    results = []
    try:
        client = AiPOMarginClient()
        live_ipos = client.fetch_live_ipos()
        if not live_ipos:
            error = getattr(client, "last_error", None)
            if return_status and error:
                return _live_status("error", message=str(error))
            if return_status:
                return _live_status("no_data", message="当前没有正在招股的IPO")
            return []

        downloader = ProspectusDownloader()
        parser = ProspectusParser(cache_dir=output_dir)
        os.makedirs(output_dir, exist_ok=True)

        if force_refresh:
            cache_file = os.path.join(output_dir, 'results_cache.json')
            if os.path.exists(cache_file):
                try:
                    os.remove(cache_file)
                except OSError:
                    pass

        def _process_one(ipo):
            company_name = ipo.get('shortname', '') or ipo.get('shortName', '') or ipo.get('name', '')
            stock_code = ipo.get('symbol', '') or ipo.get('stockCode', '')
            logger.info("\n" + "="*60)
            logger.info("处理: %s (%s)", company_name, stock_code)
            logger.info("="*60)
            try:
                return _process_ipo(client, downloader, parser, ipo, output_dir, force_refresh=force_refresh)
            except (ValueError, TypeError, KeyError, ConnectionError, TimeoutError, OSError) as e:
                logger.error(f"分析 {company_name} 失败: {e}")
                return None

        max_workers = min(len(live_ipos), 3)
        if max_workers <= 1:
            for ipo in live_ipos:
                ipo_data = _process_one(ipo)
                if ipo_data:
                    results.append(ipo_data)
        else:
            logger.info("并发处理 %d 只IPO（%d 线程）", len(live_ipos), max_workers)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(_process_one, ipo): ipo for ipo in live_ipos}
                for future in as_completed(futures):
                    ipo_data = future.result()
                    if ipo_data:
                        results.append(ipo_data)

        def _sort_key(x):
            """按截止时间排序：未截止的放前面（截止时间从近到远），已截止的放后面"""
            from datetime import datetime
            stock_code = str(x.get('hk_code') or x.get('stock_code') or '')
            end_str = (x.get('apply_end_date') or '')[:10]
            if end_str:
                try:
                    end_date = datetime.strptime(end_str, '%Y-%m-%d').date()
                    now = datetime.now().date()
                    return (0 if end_date >= now else 1, end_str, stock_code)
                except ValueError:
                    pass
            return (1, '9999-99-99', stock_code)

        results.sort(key=_sort_key)
    except (ValueError, TypeError, ConnectionError, TimeoutError, OSError) as e:
        logger.error(f"获取IPO列表失败: {e}")
        if return_status:
            return _live_status("error", results=results, message=str(e))

    if return_status:
        if results:
            return _live_status("ok", results=results)
        return _live_status("error", message="已获取IPO列表，但所有项目分析都失败了")
    return results


def analyze_single_ipo(stock_code, company_name=None, output_dir="temp"):
    try:
        client = AiPOMarginClient()
        downloader = ProspectusDownloader()
        parser = ProspectusParser(cache_dir=output_dir)
        os.makedirs(output_dir, exist_ok=True)

        ipo_data = {
            'company_name': company_name or stock_code,
            'hk_code': stock_code,
            'margin_total': None,
            'public_offer': None,
        }

        margin_detail = client.fetch_margin_detail(stock_code)
        if margin_detail:
            ipo_data = _fetch_margin_data(client, {
                'symbol': stock_code,
                'shortname': company_name or stock_code,
                'marginData': None,
            }, margin_detail=margin_detail)

        pdf_path = None
        try:
            pdf_path = downloader.download_from_hkex(stock_code, company_name or stock_code)
        except (ConnectionError, TimeoutError, OSError, ValueError) as e:
            logger.warning(f"招股书下载异常: {e}")

        prospectus_info = {}
        if pdf_path and os.path.exists(pdf_path):
            prospectus_info = parser.parse_pdf_file(
                pdf_path,
                stock_code=stock_code,
                company_name=company_name or stock_code,
            )

        prospectus_text = prospectus_info.get('_extracted_text', '') or ""
        return _run_scoring_pipeline(ipo_data, prospectus_info, prospectus_text, pdf_path)
    except (ValueError, TypeError, KeyError, ConnectionError, TimeoutError, OSError) as e:
        return {'error': str(e), 'hk_code': stock_code, 'company_name': company_name}


def analyze_uploaded_pdf(pdf_path, stock_code=None, company_name=None):
    try:
        parser = ProspectusParser()
        prospectus_info = parser.parse_pdf_file(pdf_path, stock_code=stock_code, company_name=company_name)

        prospectus_text = prospectus_info.get('_extracted_text', '') or ""

        if not prospectus_text and not prospectus_info.get('parse_success'):
            return {'error': 'PDF文本为空'}

        resolved_stock_code = stock_code or prospectus_info.get('extracted_stock_code') or '未知'
        if isinstance(resolved_stock_code, str) and resolved_stock_code.isdigit():
            resolved_stock_code = resolved_stock_code.zfill(5)

        ipo_data = {
            'company_name': company_name or prospectus_info.get('extracted_company_name') or '未知',
            'hk_code': resolved_stock_code,
            'margin_total': None,
            'public_offer': None,
        }

        return _run_scoring_pipeline(ipo_data, prospectus_info, prospectus_text, pdf_path)
    except (ValueError, TypeError, KeyError, OSError) as e:
        return {'error': str(e)}


def reanalyze_ipo(stock_code=None, company_name=None, pdf_path=None, uploaded_file=None, 
                  historical_market_data=None, force_refresh=False, output_dir="temp"):
    """重新分析已结束招股的IPO，支持多种输入方式。
    
    Args:
        stock_code: 股票代码（如 "09995"）
        company_name: 公司名称
        pdf_path: 本地PDF文件路径
        uploaded_file: 上传的文件对象，会先保存为临时文件
        historical_market_data: 历史热度数据字典，格式：
            {
                "margin_total": 123.45,
                "public_offer": 1.23,
                "actual_over_sub_ratio": 456.7,
                "forecast_over_sub_ratio": 500.0,
                "market_heat": "极热",
                "live_market_heat": {
                    "sector_heat_label": "热门",
                    "sector_flow_label": "活跃",
                    "sector_momentum_label": "上行"
                }
            }
        force_refresh: 是否强制刷新缓存
        output_dir: 临时文件输出目录
    
    Returns:
        统一返回结构：
        {
            "status": "ok" | "warning" | "error",
            "message": "...",
            "suggestion": "...",
            "result": {...}
        }
    """
    os.makedirs(output_dir, exist_ok=True)

    # 验证用户提供的 PDF 路径，防止路径遍历
    if pdf_path:
        if not os.path.isfile(pdf_path):
            return {
                "status": "error",
                "message": "PDF 文件不存在",
                "suggestion": "请检查文件路径是否正确",
                "result": None
            }
        if not pdf_path.lower().endswith('.pdf'):
            return {
                "status": "error",
                "message": "文件不是 PDF 格式",
                "suggestion": "请提供 .pdf 后缀的文件",
                "result": None
            }

    messages = []
    warnings = []
    errors = []
    source_type = None
    pdf_path_final = pdf_path
    _uploaded_temp_path = None
    downloader = None

    # 处理上传文件：先保存为临时PDF
    if uploaded_file is not None:
        temp_filename = f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex}.pdf"
        pdf_path_final = os.path.join(output_dir, temp_filename)
        with open(pdf_path_final, "wb") as f:
            f.write(uploaded_file.getbuffer())
        _uploaded_temp_path = pdf_path_final
        source_type = 'uploaded_pdf'
    
    # 处理股票代码下载
    elif stock_code and not pdf_path_final:
        try:
            downloader = ProspectusDownloader()
            pdf_path_final = downloader.download_from_hkex(stock_code, company_name)
            source_type = 'stock_code_download'
        except (ConnectionError, TimeoutError, OSError, ValueError) as e:
            errors.append(f"招股书下载失败: {str(e)}")
            if _uploaded_temp_path:
                try:
                    os.remove(_uploaded_temp_path)
                except OSError:
                    pass
            return {
                "status": "error",
                "message": "无法自动下载招股书",
                "suggestion": "请上传PDF文件进行分析",
                "result": None,
                "error_messages": errors
            }
    
    # 使用本地PDF
    elif pdf_path_final:
        source_type = 'local_pdf'
    
    else:
        if _uploaded_temp_path:
            try:
                os.remove(_uploaded_temp_path)
            except OSError:
                pass
        return {
            "status": "error",
            "message": "未提供股票代码或PDF文件",
            "suggestion": "请提供股票代码或上传PDF文件",
            "result": None
        }
    
    # 解析PDF
    prospectus_info = {}
    try:
        parser = ProspectusParser(cache_dir=output_dir)
        prospectus_info = parser.parse_pdf_file(pdf_path_final, stock_code=stock_code, company_name=company_name)
    except (OSError, ValueError, TypeError) as e:
        errors.append(f"PDF解析失败: {str(e)}")
        if _uploaded_temp_path:
            try:
                os.remove(_uploaded_temp_path)
            except OSError:
                pass
        return {
            "status": "error",
            "message": "PDF解析失败",
            "suggestion": "请检查PDF文件是否损坏或尝试重新上传",
            "result": None,
            "error_messages": errors
        }
    
    # 身份校验警告
    pdf_identity_confidence = prospectus_info.get('pdf_identity_confidence', 0)
    if _is_num(pdf_identity_confidence) and pdf_identity_confidence < 0.5 and stock_code:
        warnings.append("股票代码/公司名与PDF内容匹配度较低，请人工确认")
    
    # 构建IPO数据
    resolved_stock_code = stock_code or prospectus_info.get('extracted_stock_code') or '未知'
    if isinstance(resolved_stock_code, str) and resolved_stock_code.isdigit():
        resolved_stock_code = resolved_stock_code.zfill(5)
    
    ipo_data = {
        'company_name': company_name or prospectus_info.get('extracted_company_name') or '未知',
        'hk_code': resolved_stock_code,
    }
    
    # 从历史库加载已有的上市后跟踪数据
    history_store = HistoryStore(output_dir)
    existing_records = history_store.load()
    for record in existing_records:
        if record.get('hk_code') == resolved_stock_code:
            # 保留招股日期（重新分析时 API 不再提供，需从历史记录继承）
            if record.get('apply_start_date'):
                ipo_data['apply_start_date'] = record['apply_start_date']
            if record.get('apply_end_date'):
                ipo_data['apply_end_date'] = record['apply_end_date']
            # 加载已保存的 actual_over_sub_ratio
            if 'actual_over_sub_ratio' in record:
                ipo_data['actual_over_sub_ratio'] = record['actual_over_sub_ratio']
            # 加载 post_listing 数据
            if 'post_listing' in record:
                ipo_data['post_listing'] = record['post_listing']
                # 如果 post_listing 中有 actual_over_sub_ratio，优先使用
                post_actual = record['post_listing'].get('final_over_sub_ratio')
                if post_actual is None:
                    post_actual = record['post_listing'].get('actual_over_sub_ratio')
                if post_actual is not None and 'actual_over_sub_ratio' not in ipo_data:
                    try:
                        ipo_data['actual_over_sub_ratio'] = float(post_actual)
                    except (ValueError, TypeError):
                        pass
            break
    
    # 处理历史热度数据
    heat_data_source = 'missing'
    if historical_market_data:
        # 设置孖展数据
        if 'margin_total' in historical_market_data:
            ipo_data['margin_total'] = _safe_float(historical_market_data['margin_total'])
        if 'public_offer' in historical_market_data:
            ipo_data['public_offer'] = _safe_float(historical_market_data['public_offer'])

        # 设置超购数据
        actual_over = _safe_float(historical_market_data.get('actual_over_sub_ratio'))
        forecast_over = _safe_float(historical_market_data.get('forecast_over_sub_ratio'))

        if actual_over is not None:
            ipo_data['over_sub_ratio'] = actual_over
            ipo_data['over_sub_ratio_source'] = 'historical_actual'
            ipo_data['actual_over_sub_ratio'] = actual_over
            heat_data_source = 'historical_actual'
        elif forecast_over is not None:
            ipo_data['over_sub_ratio'] = forecast_over
            ipo_data['over_sub_ratio_source'] = 'historical_forecast'
            ipo_data['forecast_over_sub_ratio'] = forecast_over
            heat_data_source = 'historical_forecast'
        else:
            # 尝试从孖展数据估算超购
            margin_val = ipo_data.get('margin_total')
            public_val = ipo_data.get('public_offer')
            if _is_num(margin_val) and _is_num(public_val) and public_val > 0:
                estimated_sub = margin_val / public_val
                estimated_over = estimated_sub - 1
                ipo_data['over_sub_ratio'] = estimated_over
                ipo_data['over_sub_ratio_source'] = 'estimated'
                ipo_data['estimated_subscription_ratio'] = estimated_sub
                ipo_data['over_sub_ratio_estimated'] = estimated_over
                heat_data_source = 'estimated'

        # 设置市场热度：优先使用显式值，否则根据超购倍数自动计算
        if 'market_heat' in historical_market_data and historical_market_data['market_heat']:
            ipo_data['market_heat'] = historical_market_data['market_heat']
        elif _is_num(ipo_data.get('over_sub_ratio')):
            ipo_data['market_heat'] = classify_market_heat(ipo_data['over_sub_ratio'])

        live_market_heat = historical_market_data.get('live_market_heat')
        if isinstance(live_market_heat, dict) and live_market_heat:
            ipo_data['live_market_heat'] = {k: v for k, v in live_market_heat.items() if v not in (None, '')}
        else:
            live_market_heat = {}
            sector_heat_label = historical_market_data.get('sector_heat_label')
            sector_flow_label = historical_market_data.get('sector_flow_label')
            sector_momentum_label = historical_market_data.get('sector_momentum_label')
            sector_heat_detail = historical_market_data.get('sector_heat_detail')
            sector_flow_detail = historical_market_data.get('sector_flow_detail')
            sector_momentum_detail = historical_market_data.get('sector_momentum_detail')
            if any(v not in (None, '') for v in [
                sector_heat_label, sector_flow_label, sector_momentum_label,
                sector_heat_detail, sector_flow_detail, sector_momentum_detail
            ]):
                live_market_heat = {
                    'sector_heat_label': sector_heat_label or '缺失',
                    'sector_flow_label': sector_flow_label or '缺失',
                    'sector_momentum_label': sector_momentum_label or '缺失',
                    'sector_heat_detail': sector_heat_detail or '',
                    'sector_flow_detail': sector_flow_detail or '',
                    'sector_momentum_detail': sector_momentum_detail or '',
                    'sector_peer_count': historical_market_data.get('sector_peer_count'),
                    'sector_index_change_pct': historical_market_data.get('sector_index_change_pct'),
                    'sector_peer_median_change_pct': historical_market_data.get('sector_peer_median_change_pct'),
                }
                ipo_data['live_market_heat'] = {k: v for k, v in live_market_heat.items() if v not in (None, '')}
    else:
        existing_actual_over = ipo_data.get('actual_over_sub_ratio')
        if existing_actual_over is not None:
            ipo_data['over_sub_ratio'] = existing_actual_over
            ipo_data['over_sub_ratio_source'] = 'post_listing_actual'
            messages.append("使用上市后跟踪数据中的真实公配倍数")
        else:
            ipo_data['over_sub_ratio'] = None
            ipo_data['over_sub_ratio_source'] = 'missing'
            messages.append("未提供历史孖展/超购数据，本次按招股书阶段权重评分")
    
    # 运行评分管线
    prospectus_text = prospectus_info.get('_extracted_text', '') or ""
    try:
        result = _run_scoring_pipeline(ipo_data, prospectus_info, prospectus_text, pdf_path_final)
    except (ValueError, TypeError, KeyError, AttributeError) as e:
        errors.append(f"评分计算失败: {str(e)}")
        if _uploaded_temp_path:
            try:
                os.remove(_uploaded_temp_path)
            except OSError:
                pass
        return {
            "status": "error",
            "message": "评分计算失败",
            "suggestion": "请检查日志获取详细错误信息",
            "result": None,
            "error_messages": errors
        }
    
    # 添加额外元数据
    result['_reanalysis'] = {
        'analysis_mode': 'reanalysis',
        'reanalyzed_at': datetime.now().isoformat(),
        'source_type': source_type,
        'heat_data_source': heat_data_source,
        'historical_market_data': historical_market_data,
        'pdf_identity_confidence': pdf_identity_confidence,
        'warning_messages': warnings,
        'error_messages': errors,
        'info_messages': messages,
    }

    # 保存到 HistoryStore
    try:
        history_store = HistoryStore(output_dir)
        record, version_delta = history_store.save_reanalysis(result)
        if version_delta:
            result['version_delta'] = version_delta
    except (OSError, ValueError, TypeError) as e:
        logger.warning(f"保存重新分析记录失败: {e}")

    status = "ok"
    message = "分析完成"
    suggestion = ""

    if errors:
        status = "error"
        message = "; ".join(errors)
        suggestion = "请检查输入参数或PDF文件"
    elif warnings:
        status = "warning"
        message = "; ".join(warnings)
        suggestion = "建议人工复核分析结果"
    elif messages:
        message = "; ".join(messages)

    if _uploaded_temp_path:
        try:
            os.remove(_uploaded_temp_path)
        except OSError:
            pass

    return {
        "status": status,
        "message": message if message else "分析完成",
        "suggestion": suggestion,
        "result": result,
        "warning_messages": warnings,
        "error_messages": errors,
        "info_messages": messages,
    }


def generate_pdf_report(results, output_dir="temp"):
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    pdf_file = os.path.join(output_dir, f"IPO分析报告_{timestamp}.pdf")
    export_pdf_report(results, pdf_file)
    return pdf_file


def save_json_report(results, output_dir="temp"):
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    json_file = os.path.join(output_dir, f"ipo_live_data_{timestamp}.json")
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    return json_file


if __name__ == "__main__":
    main()
