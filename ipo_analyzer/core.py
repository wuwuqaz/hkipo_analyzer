import os
import json
import shutil
import time
import platform
import logging
from datetime import datetime

from .utils import _is_num, _normalize_gm, format_iso_date, _format_cornerstone_amount
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
)
from .scoring import ProspectusQualityAnalyzer, SignalComponentAnalyzer, ScoringSystem
from .peer_comps import PeerComparableAnalyzer
from .report import export_pdf_report

logger = logging.getLogger(__name__)

# CLI 入口配置日志
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )


def _attach_debug_info(ipo_data, pdf_path, prospectus_info, prospectus_text):
    ipo_data['pdf_downloaded'] = pdf_path is not None and os.path.exists(pdf_path) if pdf_path else False
    ipo_data['pdf_path'] = pdf_path
    if pdf_path and os.path.exists(pdf_path):
        try:
            ipo_data['pdf_file_size_mb'] = round(os.path.getsize(pdf_path) / 1024 / 1024, 2)
        except Exception:
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
    'offer_price', 'entry_fee_hkd', 'lot_size', 'global_offer_shares',
    'hk_offer_shares', 'international_offer_shares', 'shares_in_issue_post_listing',
    'market_cap_hkd_million', 'net_proceeds_hkd_million', 'issuance_ratio_pct',
    'public_offer_ratio_pct', 'cornerstone_total_offer_shares',
    'cornerstone_investment_hkd_million', 'cornerstone_investment_usd_million',
    'cornerstone_offer_ratio_pct', 'revenue', 'revenue_y1', 'revenue_year',
    'revenue_y1_year', 'net_profit', 'net_profit_y1', 'net_profit_year',
    'net_profit_y1_year', 'profitable', 'gross_margin', 'gross_margin_year',
    'sector', 'financial_extract_confidence',
]


def _safe_float(value):
    """将字符串/数值安全转换为 float，失败返回 None。"""
    if value in (None, "", "--"):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _fetch_margin_data(client, ipo, margin_detail=None):
    company_name = ipo.get('shortname', '') or ipo.get('shortName', '') or ipo.get('name', '')
    stock_code = ipo.get('symbol', '') or ipo.get('stockCode', '')
    margin_data = ipo.get('marginData')
    if margin_detail is None:
        margin_detail = client.fetch_margin_detail(stock_code)

    ipo_data = {
        'company_name': company_name,
        'hk_code': stock_code,
        'apply_start_date': format_iso_date(ipo.get('startdate', '')),
        'apply_end_date': format_iso_date(ipo.get('enddate', '')),
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
                    estimated_over = max(0, estimated_subscription - 1)
            except Exception:
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

        market_heat_value = ipo_data['over_sub_ratio'] or 0
        if market_heat_value >= SETTINGS.market_heat.extreme:
            ipo_data['market_heat'] = "极热"
        elif market_heat_value >= SETTINGS.market_heat.hot:
            ipo_data['market_heat'] = "热门"
        elif market_heat_value >= SETTINGS.market_heat.warm:
            ipo_data['market_heat'] = "温和"
        else:
            ipo_data['market_heat'] = "冷清"

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


def _calculate_final_score(scorer, quality_analyzer, signal_analyzer, ipo_data, prospectus_info, prospectus_text):
    text = prospectus_text  # 统一接口别名
    business_result = BusinessBreakdownAnalyzer().analyze(prospectus_info, text)
    geographic_result = GeographicExpansionAnalyzer().analyze(prospectus_info, text)
    customer_result = CustomerSupplierAnalyzer().analyze(prospectus_info, text)
    cashflow_result = WorkingCapitalCashFlowAnalyzer().analyze(prospectus_info, text)
    capacity_result = ProductionCapacityAnalyzer().analyze(prospectus_info, text)
    rnd_result = RnDPipelineAnalyzer().analyze(prospectus_info, text)
    risk_result = RiskFactorAnalyzer().analyze(prospectus_info, text)

    prospectus_info['business_breakdown'] = business_result
    prospectus_info['geographic'] = geographic_result
    prospectus_info['customer_supplier'] = customer_result
    prospectus_info['cashflow'] = cashflow_result
    prospectus_info['capacity'] = capacity_result
    prospectus_info['rnd_pipeline'] = rnd_result
    prospectus_info['risk_factors'] = risk_result

    # 同行对比分析 (在估值之前，为估值提供同行背景)
    try:
        peer_result = PeerComparableAnalyzer().analyze(prospectus_info, text, ipo_data)
    except Exception as e:
        logger.warning("同行对比分析异常: %s", e)
        peer_result = {"warnings": [f"分析异常: {e}"]}
    prospectus_info['peer_comparison'] = peer_result

    # 估值分析 (有同行数据可做相对估值)
    valuation_result = ValuationAnalyzer().analyze(prospectus_info, text, ipo_data)
    prospectus_info['valuation'] = valuation_result

    signal_result = signal_analyzer.analyze(ipo_data, prospectus_info, prospectus_text)
    prospectus_info['advanced_framework'] = signal_result  # 兼容旧字段

    stock_quality = quality_analyzer.analyze(prospectus_info)
    prospectus_info['stock_quality'] = stock_quality  # 供 ScoringSystem 复用，消除重复评分
    scoring = scorer.calculate(ipo_data, prospectus_info, signal_components=signal_result.get('components'))

    risk_penalty = risk_result.get('total_penalty', 0)
    vbp_risk = business_result.get('vbp_risk_score', 0)
    conc_penalty = customer_result.get('concentration_score_penalty', 0)
    rf = SETTINGS.risk_factor
    total_risk_penalty = min(rf.max_total_penalty, risk_penalty + vbp_risk // 5 + conc_penalty)

    final_score = max(0, min(100, scoring['score'] - total_risk_penalty))

    ipo_data['score'] = final_score
    ipo_data['subscription_score'] = scoring.get('subscription_score', 0)
    ipo_data['fundamental_score'] = scoring.get('fundamental_score', stock_quality.get('score', 0))
    ipo_data['stock_quality_score'] = stock_quality.get('score', 0)
    ipo_data['score_reasons'] = scoring['reasons']
    ipo_data['score_breakdown'] = scoring.get('components', {})
    ipo_data['risk_penalty'] = total_risk_penalty
    # 新五维分数
    ipo_data['trade_score'] = scoring.get('trade_score', 0)
    ipo_data['valuation_score'] = scoring.get('valuation_score', 0)
    ipo_data['theme_score'] = scoring.get('theme_score', 0)
    ipo_data['data_quality_score'] = scoring.get('data_quality_score', 0)
    # 兼容旧字段（deprecated）
    ipo_data['advanced_framework_score'] = signal_result.get('score', 0)
    ipo_data['advanced_score_adjustment'] = 0  # 已废弃，固定为0
    # 新字段
    ipo_data['signal_breakdown'] = signal_result.get('signal_breakdown', {})
    ipo_data['prospectus_info'] = prospectus_info
    ipo_data['stock_quality'] = stock_quality
    for field in _PROSPECTUS_COPY_FIELDS:
        if field in prospectus_info:
            ipo_data[field] = prospectus_info[field]


def _run_scoring_pipeline(ipo_data, prospectus_info, prospectus_text, pdf_path=None):
    """统一评分管线：_calculate_final_score + _attach_debug_info + IPOData 规范化"""
    scorer, quality_analyzer, advanced_analyzer = _init_analyzers()
    _calculate_final_score(scorer, quality_analyzer, advanced_analyzer, ipo_data, prospectus_info, prospectus_text)
    _attach_debug_info(ipo_data, pdf_path, prospectus_info, prospectus_text)
    try:
        from .models import IPOData
        normalized = IPOData.from_dict(ipo_data)
        if normalized is not None:
            return normalized.to_dict(drop_runtime=False)
    except Exception as e:
        logger.warning("IPOData 模型规范化失败: %s，返回原始 dict", e)
    return ipo_data


def _init_analyzers():
    return ScoringSystem(), ProspectusQualityAnalyzer(), SignalComponentAnalyzer()


def _process_ipo(client, downloader, parser, ipo, output_dir, force_refresh=False):
    ipo_data = _fetch_margin_data(client, ipo)
    stock_code = ipo_data['hk_code']
    company_name = ipo_data['company_name']

    local_pdf = os.path.join(output_dir, f"{stock_code}_prospectus.pdf")

    if force_refresh and os.path.exists(local_pdf):
        try:
            os.remove(local_pdf)
        except Exception:
            pass

    pdf_path = None
    if not force_refresh and os.path.exists(local_pdf):
        pdf_path = local_pdf
        logger.info(f"使用本地PDF: {local_pdf}")
    else:
        try:
            pdf_path = downloader.download_from_hkex(stock_code, company_name)
        except Exception as e:
            logger.warning(f"招股书下载异常: {e}")

    prospectus_info = {}
    if pdf_path and os.path.exists(pdf_path):
        if not os.path.exists(local_pdf) or force_refresh:
            try:
                shutil.copy2(pdf_path, local_pdf)
            except Exception:
                pass
        prospectus_info = parser.parse(stock_code, company_name)

    prospectus_text = prospectus_info.get('_extracted_text', '') or ""
    return _run_scoring_pipeline(ipo_data, prospectus_info, prospectus_text, pdf_path)


def main():
    logger.info("="*80)
    logger.info("  港股IPO分析器 - 自动更新与评分")
    logger.info("  时间: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    logger.info("="*80)

    client = AiPOMarginClient()
    live_ipos = client.fetch_live_ipos()

    if not live_ipos:
        logger.info("\n✗ 没有正在招股的IPO")
        return

    logger.info("\n✓ 找到 %d 个正在招股的IPO", len(live_ipos))

    downloader = ProspectusDownloader()

    results = []
    temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "temp")
    temp_dir = os.path.abspath(temp_dir)
    os.makedirs(temp_dir, exist_ok=True)
    parser = ProspectusParser(cache_dir=temp_dir)

    for ipo in live_ipos:
        company_name = ipo.get('shortname', '') or ipo.get('shortName', '') or ipo.get('name', '')
        stock_code = ipo.get('symbol', '') or ipo.get('stockCode', '')

        logger.info("\n" + "="*60)
        logger.info("处理: %s (%s)", company_name, stock_code)
        logger.info("="*60)

        ipo_data = _process_ipo(client, downloader, parser, ipo, temp_dir)
        results.append(ipo_data)

    results.sort(key=lambda x: x.get('score', 0), reverse=True)

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
            logger.info("   基石信号: %s / %s (%d/100)", cornerstone_analysis.get('label', '--'), cornerstone_analysis.get('recommendation', '--'), cornerstone_analysis.get('score', 0))
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
    except Exception as e:
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
        except Exception:
            pass

    try:
        if platform.system() == "Darwin":
            os.system(f'open "{pdf_file}"')
    except Exception:
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
                except Exception:
                    pass

        for ipo in live_ipos:
            try:
                ipo_data = _process_ipo(client, downloader, parser, ipo, output_dir, force_refresh=force_refresh)
                results.append(ipo_data)
            except Exception as e:
                logger.error(f"分析 {ipo.get('shortname', '')} 失败: {e}")
                continue

        results.sort(key=lambda x: x.get('score', 0), reverse=True)
    except Exception as e:
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
        except Exception as e:
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
    except Exception as e:
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
    except Exception as e:
        return {'error': str(e)}


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
