import re
import logging
from ..utils import _is_num, _normalize_gm
from ..settings import SETTINGS
from ..industry_router import classify_company
logger = logging.getLogger(__name__)


class ValuationAnalyzer:
    """估值分析器 — 支持绝对估值 + 相对估值 + 稀缺性 + 创新药 综合判断"""

    def analyze(self, prospectus_info: dict, text: str = '', ipo_data: dict = None) -> dict:
        # 防御：某些调用者把 ipo_data 传到了 text 位置
        if isinstance(text, dict):
            text = ''
        result = {
            'pe_ratio': None, 'adjusted_pe_ratio': None, 'pb_ratio': None, 'ps_ratio': None,
            'valuation_label': '缺失', 'absolute_valuation_label': '缺失',
            'relative_valuation_label': None,
            'valuation_reasons': [], 'confidence': 'missing',
            'valuation_type': 'absolute_only',
            'valuation_framework_type': None,
            'valuation_profitability_type': None,
            'revenue_hkd_million': None,
            'revenue_previous_hkd_million': None,
            'market_cap_hkd_million': None,
            'valuation_price_basis': prospectus_info.get('valuation_price_basis', 'prospectus_price'),
            'indicative_offer_price': prospectus_info.get('indicative_offer_price'),
            'final_offer_price': prospectus_info.get('final_offer_price'),
            'indicative_market_cap_hkd_million': prospectus_info.get('indicative_market_cap_hkd_million'),
            'final_market_cap_hkd_million': prospectus_info.get('final_market_cap_hkd_million'),
            'final_ps_ratio': prospectus_info.get('final_ps_ratio'),
            'final_total_fund': prospectus_info.get('final_total_fund'),
            'final_public_offer': prospectus_info.get('final_public_offer'),
            'market_cap_to_rd_ratio': None,
            'biotech_valuation_label': None,
            'biotech_valuation_reasons': [],
            'biotech_stage_label': None,
            'biotech_valuation_framework': None,
            'latest_clinical_stage': None,
            'phase_iii_count': 0,
            'nda_or_approved_count': 0,
            'cash_runway_years': None,
            'pipeline_concentration_warning': None,
            'revenue_too_small_for_ps': False,
        }
        try:
            market_cap_m = prospectus_info.get('market_cap_hkd_million')
            offer_price = prospectus_info.get('offer_price')
            net_profit = prospectus_info.get('net_profit')
            revenue_raw = prospectus_info.get('revenue')
            nta_per_share = prospectus_info.get('pro_forma_NTA_per_share_HKD')
            adjusted_profit = prospectus_info.get('adjusted_profit_latest_RMB')
            sector = prospectus_info.get('sector', 'unknown')
            fin_currency = prospectus_info.get('financial_currency', 'RMB')
            rd_expense = prospectus_info.get('rd_expense')
            peer_comparison = prospectus_info.get('peer_comparison', {}) or {}
            scarcity_score = peer_comparison.get('scarcity_score', 0)
            valuation_position = peer_comparison.get('valuation_position', '缺失')

            # 行业路由（集中判定，替代分散的 _is_biotech）
            profile = classify_company(prospectus_info, text)
            is_biotech = profile.is_biotech

            # 币种转换（财务数据通常是RMB million）
            if fin_currency == "RMB":
                fx = SETTINGS.fx.rmb_to_hkd
            elif fin_currency == "USD":
                fx = SETTINGS.fx.usd_to_hkd
            else:
                fx = 1.0

            revenue = None
            revenue_previous = None
            net_profit_hkd = None
            adjusted_profit_hkd = None
            if _is_num(revenue_raw):
                revenue = round(revenue_raw * fx, 2)
            revenue_y1_raw = prospectus_info.get('revenue_y1')
            if _is_num(revenue_y1_raw):
                revenue_previous = round(revenue_y1_raw * fx, 2)
            if _is_num(net_profit):
                net_profit_hkd = round(net_profit * fx, 2)
            if _is_num(adjusted_profit):
                adjusted_profit_hkd = round(adjusted_profit * fx, 2)
            result['revenue_hkd_million'] = revenue
            result['revenue_previous_hkd_million'] = revenue_previous
            result['net_profit_hkd_million'] = net_profit_hkd
            result['adjusted_profit_hkd_million'] = adjusted_profit_hkd
            result['market_cap_hkd_million'] = market_cap_m

            # --- 估值阈值（提前初始化，避免后续使用未定义变量）---
            vt = SETTINGS.valuation

            # --- 收入质量识别（对 biotech 重要）---
            text_lower = str(prospectus_info.get('_extracted_text', '')).lower()
            upfront_keywords = [
                'upfront payment', 'milestone payment', 'license payment',
                '授权首付款', '里程碑付款', '一次性付款', '许可费收入',
                'collaboration revenue', 'partnership revenue',
            ]
            upfront_mentions = sum(1 for kw in upfront_keywords if kw in text_lower)
            result['revenue_quality'] = 'standard'
            if upfront_mentions >= 2:
                result['revenue_quality'] = 'contains_upfront'
                # 若收入极小且文本明确提到 upfront/license 占主导
                if _is_num(revenue) and revenue < vt.biotech_revenue_small:
                    if any(x in text_lower for x in ['primarily from', 'mainly from', '主要来源', '大部分来自']):
                        if any(x in text_lower for x in ['upfront', 'license', 'milestone', '授权', '许可']):
                            result['revenue_quality'] = 'license_upfront_driven'

            if _is_num(market_cap_m) and _is_num(net_profit_hkd) and net_profit_hkd > 0:
                result['pe_ratio'] = round(market_cap_m / net_profit_hkd, 2)
            if _is_num(market_cap_m) and _is_num(adjusted_profit_hkd) and adjusted_profit_hkd > 0:
                result['adjusted_pe_ratio'] = round(market_cap_m / adjusted_profit_hkd, 2)
            if _is_num(offer_price) and _is_num(nta_per_share) and nta_per_share > 0:
                result['pb_ratio'] = round(offer_price / nta_per_share, 2)
            if _is_num(market_cap_m) and _is_num(revenue) and revenue > 0:
                result['ps_ratio'] = round(market_cap_m / revenue, 2)
                if result.get('valuation_price_basis') == 'final_price':
                    result['final_ps_ratio'] = result['ps_ratio']

            # 研发费用倍数（对生物科技重要）
            if _is_num(market_cap_m) and _is_num(rd_expense) and rd_expense > 0:
                rd_hkd = round(rd_expense * fx, 2)
                if rd_hkd > 0:
                    result['market_cap_to_rd_ratio'] = round(market_cap_m / rd_hkd, 2)

            reasons = []
            pe = result['pe_ratio']
            ps_val = result['ps_ratio']

            # 盈利类型
            if _is_num(net_profit) and net_profit <= 0:
                result['valuation_profitability_type'] = 'loss_making'
            elif _is_num(net_profit) and net_profit > 0:
                result['valuation_profitability_type'] = 'profitable'

            # 估值框架类型
            if is_biotech:
                result['valuation_framework_type'] = '18A_biotech'
                result['valuation_type'] = 'biotech_special'
            elif sector == "healthcare":
                result['valuation_framework_type'] = 'healthcare_standard'

            # --- 绝对估值 ---
            absolute_label = '缺失'
            if pe is not None:
                if pe > vt.pe_expensive:
                    absolute_label = '很贵'
                elif pe > vt.pe_high:
                    absolute_label = '偏贵'
                elif pe > vt.pe_fair:
                    absolute_label = '合理'
                else:
                    absolute_label = '低估'
            elif ps_val is not None:
                if ps_val > vt.ps_expensive:
                    absolute_label = '很贵'
                elif ps_val > vt.ps_high:
                    absolute_label = '偏贵'
                elif ps_val > vt.ps_fair:
                    absolute_label = '合理'
                else:
                    absolute_label = '低估'
            result['absolute_valuation_label'] = absolute_label

            # --- 生物科技估值 ---
            if is_biotech and _is_num(market_cap_m):
                biotech_reasons = []
                biotech_label = "未盈利生物科技"

                # 管线阶段检测
                text_for_pipeline = prospectus_info.get('_extracted_text', '') or ''
                phase_iii = len(re.findall(r'phase\s*iii|phase\s*3|pivotal\s*(?:trial|study)|关键\s*(?:临床|试验)', text_for_pipeline, re.IGNORECASE))
                nda_count = len(re.findall(r'\bnda\b|new drug application|上市申请|pre-nda', text_for_pipeline, re.IGNORECASE))
                approved = len(re.findall(r'\bapproved\b|获批上市|已上市|marketing authorization|commercialized', text_for_pipeline, re.IGNORECASE))
                result['phase_iii_count'] = phase_iii
                result['nda_or_approved_count'] = nda_count + approved

                if approved > 0:
                    result['latest_clinical_stage'] = 'approved'
                elif nda_count > 0:
                    result['latest_clinical_stage'] = 'nda'
                elif phase_iii > 0:
                    result['latest_clinical_stage'] = 'phase_iii'
                else:
                    found_phase = re.search(r'phase\s*(ii|2)', text_for_pipeline, re.IGNORECASE)
                    result['latest_clinical_stage'] = 'phase_ii' if found_phase else 'early_stage'

                stage = result['latest_clinical_stage'] or 'unknown'
                if stage in ('approved', 'nda'):
                    result['biotech_stage_label'] = '后期/商业化'
                elif stage == 'phase_iii':
                    result['biotech_stage_label'] = '临床后期'
                elif stage == 'phase_ii':
                    result['biotech_stage_label'] = '临床中期'
                else:
                    result['biotech_stage_label'] = '早期研发'

                # 现金runway估算
                cash_text = prospectus_info.get('_extracted_text', '')
                cash_matches = re.findall(r'(?:cash and cash equivalents?|现金及现金等价物).*?(?:HK\$|HKD|RMB)?\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:million|billion)?', cash_text, re.IGNORECASE)
                operating_loss_matches = re.findall(r'net cash used in operating.*?(?:HK\$|HKD|RMB)?\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:million|billion)?', cash_text, re.IGNORECASE)
                if cash_matches and operating_loss_matches:
                    try:
                        cash_val = float(cash_matches[0].replace(',', ''))
                        loss_val = float(operating_loss_matches[0].replace(',', ''))
                        if loss_val > 0:
                            result['cash_runway_years'] = round(cash_val / loss_val, 1)
                    except Exception:
                        pass
                if result.get('cash_runway_years') is not None and result['cash_runway_years'] < SETTINGS.valuation.cash_runway_warning:
                    biotech_reasons.append(f"现金runway仅{result['cash_runway_years']}年，需关注融资需求")
                if result.get('cash_runway_years') is not None:
                    biotech_reasons.append(f"现金runway约{result['cash_runway_years']}年")

                # 管线集中度
                rnd_info = prospectus_info.get('rnd_pipeline', {}) or {}
                product_count = rnd_info.get('product_count_pipeline', 0)
                if isinstance(product_count, (int, float)) and product_count <= SETTINGS.valuation.biotech_pipeline_count_warning and stage in ('early_stage', 'phase_ii'):
                    result['pipeline_concentration_warning'] = f'管线仅{product_count}个产品且阶段偏早，集中度风险高'
                    biotech_reasons.append(result['pipeline_concentration_warning'])

                revenue_small = _is_num(revenue) and revenue < SETTINGS.valuation.biotech_revenue_small
                if revenue_small:
                    result['revenue_too_small_for_ps'] = True
                    biotech_reasons.append(f"收入基数极小(HKD M{revenue:.0f})，PS严重失真，仅供参考")
                    biotech_label = "PS辅助/管线估值"
                elif ps_val is not None and _is_num(revenue) and revenue < SETTINGS.valuation.biotech_revenue_moderate:
                    biotech_reasons.append(f"收入基数小(HKD M{revenue:.0f})，PS需谨慎解读")

                # 确定 biotech 估值框架
                if revenue_small:
                    if result.get('market_cap_to_rd_ratio') is not None:
                        result['biotech_valuation_framework'] = 'market_cap_rd'
                    else:
                        result['biotech_valuation_framework'] = 'pipeline_based'
                elif ps_val is not None:
                    result['biotech_valuation_framework'] = 'ps_reference'
                elif result.get('market_cap_to_rd_ratio') is not None:
                    result['biotech_valuation_framework'] = 'market_cap_rd'
                else:
                    result['biotech_valuation_framework'] = 'pipeline_based'

                if result.get('market_cap_to_rd_ratio') is not None:
                    rdr = result['market_cap_to_rd_ratio']
                    biotech_reasons.append(f"市值/研发费用={rdr:.1f}x")
                    if rdr > SETTINGS.valuation.biotech_market_cap_to_rd_extreme and revenue_small:
                        biotech_reasons.append("市值/R&D极高，需关注估值泡沫风险")

                if result['valuation_profitability_type'] == 'loss_making':
                    biotech_reasons.append("未盈利临床阶段创新药，PE不适用")

                result['biotech_valuation_label'] = biotech_label
                result['biotech_valuation_reasons'] = biotech_reasons
                reasons.extend(biotech_reasons)

            # --- 同行相对估值 ---
            relative_label = None
            if valuation_position != '缺失' and valuation_position is not None:
                relative_label = valuation_position
            result['relative_valuation_label'] = relative_label

            # --- 综合估值 ---
            if is_biotech and result.get('biotech_valuation_label'):
                final_label = result['biotech_valuation_label']
            elif absolute_label == '缺失' and _is_num(market_cap_m):
                final_label = "市值基准"  # 有市值但无PS/PE
                if _is_num(revenue):
                    final_label = "PS辅助估值"
            else:
                final_label = absolute_label

            # 未盈利/生物科技细化标签
            if _is_num(net_profit) and net_profit <= 0:
                if is_biotech:
                    if _is_num(revenue) and revenue > 0:
                        if revenue < SETTINGS.valuation.biotech_revenue_small:
                            final_label = "PS失真，仅作参考"
                        else:
                            final_label = "PS辅助估值"
                    else:
                        final_label = "管线阶段估值"
                elif not _is_num(revenue):
                    final_label = "数据不足，需人工核对"
            elif not _is_num(net_profit) and not _is_num(revenue):
                if is_biotech:
                    final_label = "管线阶段估值"
                else:
                    final_label = "数据不足，需人工核对"

            # 低收入 biotech：revenue_too_small_for_ps=True 时 valuation_label 不能是"很贵/明显偏贵"
            if result.get('revenue_too_small_for_ps') and final_label in ('很贵', '明显偏贵'):
                final_label = "PS失真，仅作参考"

            if relative_label and relative_label != '缺失' and not is_biotech:
                if absolute_label in ('很贵',) and any(x in (relative_label or '') for x in ('合理', '相对低估', '偏贵但可解释')):
                    final_label = '偏贵但可解释'
                    reasons.append(f"绝对{absolute_label}，但同行相对{relative_label}，有稀缺性支撑")
                elif absolute_label in ('很贵', '偏贵') and '明显偏贵' in (relative_label or ''):
                    final_label = '很贵'
                    reasons.append(f"绝对{absolute_label}，且相对同行也偏高")
                elif any(x in (relative_label or '') for x in ('合理', '相对低估')) and scarcity_score >= 5:
                    if _is_num(ps_val) and ps_val > SETTINGS.valuation.ps_expensive and sector in ('healthcare', 'hardtech'):
                        final_label = '赛道合理'
                        reasons.append(f"PS{ps_val:.1f}x绝对值偏高，但同赛道公司PS中位数{peer_comparison.get('peer_median_ps', 'N/A')}x，{relative_label}")

            # 收入极小提示（仅当最终标签尚未包含 PS辅助 前缀时添加，避免双重包裹）
            if _is_num(revenue) and revenue < SETTINGS.valuation.biotech_revenue_moderate and sector in ('healthcare', 'hardtech') and ps_val is not None:
                if absolute_label in ('很贵', '偏贵') and not is_biotech:
                    if _is_num(peer_comparison.get('peer_median_ps')):
                        if 'PS辅助' not in (final_label or ''):
                            final_label = f"PS辅助({final_label})"

            # --- reasons ---
            vt = SETTINGS.valuation
            if pe is not None:
                reasons.append(f"P/E {pe:.1f}x{'偏高' if pe > vt.pe_expensive else '中等' if pe > vt.pe_moderate else '合理'}")
            if result['pb_ratio'] is not None:
                reasons.append(f"P/B {result['pb_ratio']:.1f}x")
            if ps_val is not None:
                reasons.append(f"PS {ps_val:.1f}x")
            if result.get('market_cap_to_rd_ratio') is not None and is_biotech:
                reasons.append(f"市值/R&D {result['market_cap_to_rd_ratio']:.1f}x")
            if result.get('cash_runway_years') is not None:
                reasons.append(f"现金runway {result['cash_runway_years']:.1f}年")

            # 收入增长率使用同一币种口径（HKD）
            if _is_num(revenue) and _is_num(revenue_previous) and revenue_previous > 0:
                growth = (revenue - revenue_previous) / revenue_previous
                reasons.append(f"收入增速{growth*100:.1f}%")
            gm = prospectus_info.get('gross_margin')
            if gm is not None and not (_is_num(gm) and gm > SETTINGS.prospectus_quality.gross_margin_anomaly_max):
                gm_pct = _normalize_gm(gm)
                if _is_num(gm_pct) and gm_pct > 0:
                    reasons.append(f"毛利率{gm_pct:.1f}%")

            if scarcity_score > 0:
                reasons.append(f"赛道稀缺性评分{scarcity_score}/10")
                result['valuation_type'] = 'combined' if not is_biotech else 'biotech_special'
            if scarcity_score >= SETTINGS.peer_comps.scarcity_high:
                reasons.append("稀缺赛道估值容忍度较高")

            result['valuation_label'] = final_label
            result['valuation_reasons'] = reasons
            if pe is not None or ps_val is not None:
                result['confidence'] = 'exact_table'
            elif _is_num(market_cap_m):
                result['confidence'] = 'market_cap_only'
        except Exception as e:
            logger.warning("%s: %s", type(self).__name__, e)
            result['_error'] = str(e)

        # 合并旧 valuation 中因文本缺失而无法重新计算的字段
        cashflow = prospectus_info.get('cashflow') or {}
        if isinstance(cashflow, dict) and _is_num(cashflow.get('cash_runway_years')):
            result['cash_runway_years'] = cashflow.get('cash_runway_years')
            runway_reason = f"现金runway {cashflow.get('cash_runway_years'):.1f}年"
            if runway_reason not in result.get('valuation_reasons', []):
                result.setdefault('valuation_reasons', []).append(runway_reason)
        old_valuation = prospectus_info.get('valuation') or {}
        if isinstance(old_valuation, dict):
            for key in ('cash_runway_years', 'revenue_quality', 'latest_clinical_stage',
                        'pipeline_concentration_warning', 'biotech_valuation_label',
                        'biotech_stage_label', 'biotech_valuation_framework'):
                if result.get(key) in (None, '', 'standard') and old_valuation.get(key) not in (None, '', 'standard'):
                    result[key] = old_valuation[key]

        return result
