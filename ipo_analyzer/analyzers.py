import re
import logging
from .utils import _is_num, _normalize_gm, _contains_any, _extract_table_nums
from .table_extraction import extract_financial_table_by_row, extract_segment_table

logger = logging.getLogger(__name__)


from .settings import SETTINGS


class ValuationAnalyzer:
    """估值分析器 — 支持绝对估值 + 相对估值 + 稀缺性 + 创新药 综合判断"""

    _BIOTECH_KEYWORDS = [
        "18A", "chapter 18a", '-b ', '-w ', "biotech", "innovative drug",
        "clinical-stage", "drug candidate", "nda", "ind",
        "phase i", "phase ii", "phase iii", "phase 1", "phase 2", "phase 3",
        "parp inhibitor", "apatinib", "senaparib",
        "pipeline", "core product", "candidate",
    ]

    @classmethod
    def _is_biotech(cls, prospectus_info):
        sector = prospectus_info.get("sector", "")
        if sector != "healthcare":
            return False
        name = str(prospectus_info.get("extracted_company_name", "") or "")
        if "-b" in name.lower():
            return True
        text = str(prospectus_info.get("_extracted_text", "") or "")
        if not text:
            text = prospectus_info.get("prospectus_text", "") or ""
        hits = sum(1 for kw in cls._BIOTECH_KEYWORDS if kw.lower() in text.lower())
        if hits >= SETTINGS.valuation.biotech_keyword_hits_min:
            return True
        subsector = prospectus_info.get("peer_comparison", {}).get("subsector", "")
        if subsector in ("innovative_drug_biotech", "ai_drug_delivery_nanomedicine"):
            return True
        return False

    def analyze(self, prospectus_info, ipo_data=None):
        result = {
            'pe_ratio': None, 'adjusted_pe_ratio': None, 'pb_ratio': None, 'ps_ratio': None,
            'valuation_label': '缺失', 'absolute_valuation_label': '缺失',
            'relative_valuation_label': None,
            'valuation_reasons': [], 'confidence': 'missing',
            'valuation_type': 'absolute_only',
            'valuation_framework_type': None,
            'valuation_profitability_type': None,
            'revenue_hkd_million': None,
            'market_cap_hkd_million': None,
            'market_cap_to_rd_ratio': None,
            'biotech_valuation_label': None,
            'biotech_valuation_reasons': [],
            'biotech_stage_label': None,
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

            is_biotech = self._is_biotech(prospectus_info)

            # 币种转换（财务数据通常是RMB million）
            if fin_currency == "RMB":
                fx = SETTINGS.fx.rmb_to_hkd
            elif fin_currency == "USD":
                fx = SETTINGS.fx.usd_to_hkd
            else:
                fx = 1.0

            revenue = None
            if _is_num(revenue_raw):
                revenue = round(revenue_raw * fx, 2)
            result['revenue_hkd_million'] = revenue
            result['market_cap_hkd_million'] = market_cap_m

            if _is_num(market_cap_m) and _is_num(net_profit) and net_profit > 0:
                result['pe_ratio'] = round(market_cap_m / net_profit, 2)
            if _is_num(market_cap_m) and _is_num(adjusted_profit) and adjusted_profit > 0:
                result['adjusted_pe_ratio'] = round(market_cap_m / adjusted_profit, 2)
            if _is_num(offer_price) and _is_num(nta_per_share) and nta_per_share > 0:
                result['pb_ratio'] = round(offer_price / nta_per_share, 2)
            if _is_num(market_cap_m) and _is_num(revenue) and revenue > 0:
                result['ps_ratio'] = round(market_cap_m / revenue, 2)

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
            vt = SETTINGS.valuation
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
                    result['latest_clinical_stage'] = 'phase_ii' if found_phase else 'preclinical_or_discovery'

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
                if isinstance(product_count, (int, float)) and product_count <= SETTINGS.valuation.biotech_pipeline_count_warning and stage in ('preclinical_or_discovery', 'phase_ii'):
                    result['pipeline_concentration_warning'] = f'管线仅{product_count}个产品且阶段偏早，集中度风险高'
                    biotech_reasons.append(result['pipeline_concentration_warning'])

                revenue_small = _is_num(revenue) and revenue < SETTINGS.valuation.biotech_revenue_small
                if revenue_small:
                    result['revenue_too_small_for_ps'] = True
                    biotech_reasons.append(f"收入基数极小(HKD M{revenue:.0f})，PS严重失真，仅供参考")
                    biotech_label = "PS辅助/管线估值"
                elif ps_val is not None and _is_num(revenue) and revenue < SETTINGS.valuation.biotech_revenue_moderate:
                    biotech_reasons.append(f"收入基数小(HKD M{revenue:.0f})，PS需谨慎解读")

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

            if relative_label and relative_label != '缺失' and not is_biotech:
                if absolute_label in ('很贵',) and relative_label in ('合理', '相对低估', '偏贵但可解释'):
                    final_label = '偏贵但可解释'
                    reasons.append(f"绝对{absolute_label}，但同行相对{relative_label}，有稀缺性支撑")
                elif absolute_label in ('很贵', '偏贵') and relative_label in ('明显偏贵',):
                    final_label = '很贵'
                    reasons.append(f"绝对{absolute_label}，且相对同行也偏高")
                elif relative_label in ('合理', '相对低估') and scarcity_score >= 5:
                    if _is_num(ps_val) and ps_val > SETTINGS.valuation.ps_expensive and sector in ('healthcare', 'hardtech'):
                        final_label = '赛道合理'
                        reasons.append(f"PS{ps_val:.1f}x绝对值偏高，但同赛道公司PS中位数{peer_comparison.get('peer_median_ps', 'N/A')}x，{relative_label}")

            # 收入极小提示
            if _is_num(revenue) and revenue < SETTINGS.valuation.biotech_revenue_moderate and sector in ('healthcare', 'hardtech') and ps_val is not None:
                if absolute_label in ('很贵', '偏贵') and not is_biotech:
                    if _is_num(peer_comparison.get('peer_median_ps')):
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

            revenue_y1 = prospectus_info.get('revenue_y1')
            if _is_num(revenue) and _is_num(revenue_y1) and revenue_y1 > 0:
                growth = (revenue - revenue_y1) / revenue_y1
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
        return result


class BusinessBreakdownAnalyzer:
    _BUSINESS_LINE_PATTERNS = [
        'breakdown of our revenue by business line',
        'revenue by business line',
        'breakdown of revenue by product',
        'revenue by product',
        'breakdown of our revenue',
        'revenue breakdown',
        'breakdown of revenue',
        'breakdown of our total revenue',
    ]

    _SEGMENT_NAME_PATTERNS = [
        r'Visual Perception Products',
        r'Robot lawn mowers?',
        r'Autonomous mobile robots?',
        r'Consumer electronics',
        r'Industrial equipment',
        r'Medical implants?',
        r'Surgical equipment',
        r'Others?',
        r'Remaining',
    ]

    _EXCLUDE_SEGMENTS = [
        'net cash', 'cash and cash', 'net increase', 'decrease in cash',
        'summary', 'operating activities', 'investing activities',
        'financing activities', 'effect of exchange', 'cash at beginning',
        'cash at end', 'profit for', 'loss for', 'depreciation', 'amortization',
        'working capital', 'trade receivables', 'trade payables', 'inventories',
        'total revenue', 'total', 'amount',
    ]

    def analyze(self, text, prospectus_info):
        result = {
            'segments': [],
            'main_segment': None,
            'fastest_growing_segment': None,
            'new_business_segment': None,
            'growth_source': 'missing',
            'vbp_risk_score': 0,
            'vbp_summary': '',
            'asp_data': {},
            'business_breakdown_confidence': 'missing',
            'business_breakdown_warning': None,
            'confidence': 'missing',
        }
        try:
            segments = self._extract_generic_segments(text)
            if not segments:
                seg_table = extract_segment_table(text, ['Medical implants', 'Surgical equipment and associated'])
                for seg_name, seg_data in seg_table.items():
                    years = sorted(seg_data.keys())
                    if len(years) >= 2:
                        latest = seg_data[years[-1]]
                        prev = seg_data[years[-2]]
                        growth = (latest - prev) / abs(prev) if prev != 0 else None
                        segments.append({
                            'name': seg_name,
                            'revenue_latest': latest,
                            'revenue_previous': prev,
                            'growth_pct': round(growth * 100, 1) if growth is not None else None,
                            'year_latest': years[-1],
                        })

            if segments:
                if len(segments) == 1 and segments[0].get('share_pct', 0) == 100:
                    result['business_breakdown_warning'] = '业务分部疑似提取不完整'
                    result['business_breakdown_confidence'] = 'incomplete'
                else:
                    result['business_breakdown_confidence'] = 'regex_context'

                total_latest = sum(s.get('revenue_latest', 0) for s in segments)
                for s in segments:
                    if total_latest > 0 and s.get('share_pct') is None:
                        s['share_pct'] = round(s.get('revenue_latest', 0) / total_latest * 100, 1)

                sorted_by_share = sorted(segments, key=lambda x: x.get('share_pct', 0), reverse=True)
                result['main_segment'] = sorted_by_share[0].get('name') if sorted_by_share else None

                sorted_by_growth = sorted(segments, key=lambda x: x.get('growth_pct', 0) or 0, reverse=True)
                result['fastest_growing_segment'] = sorted_by_growth[0].get('name') if sorted_by_growth else None

                for s in segments:
                    prev_share = s.get('share_pct_previous', 0) or 0
                    curr_share = s.get('share_pct', 0) or 0
                    bt = SETTINGS.business_breakdown
                    if prev_share < bt.new_biz_prev_share_max and curr_share >= bt.new_biz_curr_share_min:
                        result['new_business_segment'] = s.get('name')
                        break

                if not result.get('new_business_segment'):
                    for s in segments:
                        prev_rev = s.get('revenue_previous', 0) or 0
                        curr_rev = s.get('revenue_latest', 0) or 0
                        if prev_rev > 0 and prev_rev < curr_rev * bt.new_biz_revenue_ratio_max and curr_rev / total_latest * 100 >= bt.new_biz_total_share_min:
                            result['new_business_segment'] = s.get('name')
                            break

                main_share = sorted_by_share[0].get('share_pct', 0) if sorted_by_share else 0
                main_growth = sorted_by_share[0].get('growth_pct', 0) if sorted_by_share else 0
                new_biz = result.get('new_business_segment')

                if new_biz:
                    result['growth_source'] = '主业增长 + 新业务贡献'
                elif main_share >= SETTINGS.business_breakdown.main_segment_dominance_pct and (main_growth or 0) > 0:
                    result['growth_source'] = '主业驱动'
                elif any(s.get('growth_pct', 0) and s['growth_pct'] > 0 for s in segments):
                    result['growth_source'] = '产品结构驱动'
                else:
                    result['growth_source'] = '增长来源待确认'

                result['segments'] = segments

            vbp_score, vbp_summary = self._analyze_vbp(text, prospectus_info)
            result['vbp_risk_score'] = vbp_score
            result['vbp_summary'] = vbp_summary

            if segments:
                result['confidence'] = result['business_breakdown_confidence']
        except Exception as e:
            logger.warning("%s: %s", type(self).__name__, e)
        return result

    def _extract_generic_segments(self, text):
        lines = text.split('\n')
        section_start = None

        for i, line in enumerate(lines):
            ll = line.lower().strip()
            if any(p in ll for p in self._BUSINESS_LINE_PATTERNS):
                section_start = i
                break

        if section_start is None:
            return []

        window_lines = lines[section_start:min(section_start + 250, len(lines))]
        window = '\n'.join(window_lines)

        year_matches = re.findall(r'\b(20\d{2})\b', window)
        years = []
        for y in year_matches:
            yi = int(y)
            if yi not in years and 2015 <= yi <= 2030:
                years.append(yi)
        years = sorted(years)
        if len(years) < 2:
            return []

        segments = self._parse_segment_table(window_lines, years)
        if segments:
            return segments

        return self._parse_segment_by_name_search(text, years)

    def _is_segment_name_line(self, clean_stripped):
        if not clean_stripped or len(clean_stripped) < 3 or len(clean_stripped) > 60:
            return False
        name_without_footnote = re.sub(r'\(\d+\)$', '', clean_stripped).strip()
        if not name_without_footnote:
            return False
        if any(c.isdigit() for c in name_without_footnote):
            return False
        if not re.match(r'^[A-Z]', name_without_footnote):
            return False
        if any(ex in name_without_footnote.lower() for ex in self._EXCLUDE_SEGMENTS):
            return False
        if not re.match(r'^[A-Za-z\s&/()\-]+$', name_without_footnote):
            return False
        return True

    def _parse_segment_table(self, window_lines, years):
        segments = []
        n_years = len(years)

        seg_entries = []
        current_seg_name = None
        current_seg_start = None

        for idx in range(len(window_lines)):
            stripped = window_lines[idx].strip()
            if not stripped:
                continue

            clean_stripped = stripped.rstrip('\x02 \t')
            ll = clean_stripped.lower()

            if ll.startswith('total'):
                if current_seg_name and current_seg_start is not None:
                    all_nums = self._collect_all_nums_from_lines(window_lines, current_seg_start)
                    amounts, pcts, extra_amounts, extra_pcts = self._split_amounts_pcts(all_nums, n_years)
                    seg_entries.append({
                        'name': current_seg_name,
                        'amounts': amounts,
                        'pcts': pcts,
                        'extra_amounts': extra_amounts,
                        'extra_pcts': extra_pcts,
                        'start_idx': current_seg_start,
                    })
                break

            if self._is_segment_name_line(clean_stripped):
                name_without_footnote = re.sub(r'\(\d+\)$', '', clean_stripped).strip()

                if current_seg_name and current_seg_start is not None:
                    all_nums = self._collect_all_nums_from_lines(window_lines, current_seg_start)
                    amounts, pcts, extra_amounts, extra_pcts = self._split_amounts_pcts(all_nums, n_years)
                    seg_entries.append({
                        'name': current_seg_name,
                        'amounts': amounts,
                        'pcts': pcts,
                        'extra_amounts': extra_amounts,
                        'extra_pcts': extra_pcts,
                        'start_idx': current_seg_start,
                    })

                current_seg_name = name_without_footnote
                current_seg_start = idx

        parent_indices = []
        for i, entry in enumerate(seg_entries):
            if not entry['amounts']:
                parent_indices.append(i)

        for parent_idx in parent_indices:
            subtotal_amounts = None
            subtotal_pcts = None
            for j in range(parent_idx + 1, len(seg_entries)):
                if seg_entries[j].get('extra_amounts'):
                    subtotal_amounts = seg_entries[j]['extra_amounts']
                    subtotal_pcts = seg_entries[j].get('extra_pcts', [])
                    seg_entries[j]['extra_amounts'] = []
                    seg_entries[j]['extra_pcts'] = []
                    break
            if subtotal_amounts:
                seg_entries[parent_idx]['amounts'] = subtotal_amounts
                seg_entries[parent_idx]['pcts'] = subtotal_pcts

        for entry in seg_entries:
            name = entry['name']
            amounts = entry['amounts']
            pcts = entry['pcts']

            if not amounts:
                continue

            seg_entry = {
                'name': name,
                'revenue_latest': amounts[-1] if amounts else None,
                'revenue_previous': amounts[-2] if len(amounts) >= 2 else None,
                'year_latest': years[-1],
            }

            if pcts:
                seg_entry['share_pct'] = pcts[-1]
                if len(pcts) >= 2:
                    seg_entry['share_pct_previous'] = pcts[-2]

            prev = seg_entry.get('revenue_previous')
            latest = seg_entry.get('revenue_latest')
            if prev and prev != 0 and latest:
                growth = (latest - prev) / abs(prev)
                seg_entry['growth_pct'] = round(growth * 100, 1)

            segments.append(seg_entry)

        return segments

    def _collect_all_nums_from_lines(self, lines, start_idx):
        all_nums = []
        for j in range(start_idx + 1, min(start_idx + 30, len(lines))):
            line = lines[j].strip()
            if not line:
                continue
            clean_stripped = line.rstrip('\x02 \t')
            if self._is_segment_name_line(clean_stripped):
                break
            if clean_stripped.lower().startswith('total'):
                break
            if clean_stripped.lower().startswith('note'):
                break
            for m in re.finditer(r'([\(]?[\d,]+\.?\d*[\)]?)', line):
                raw = m.group(1).replace(',', '').strip('()')
                if not raw:
                    continue
                try:
                    val = float(raw)
                except ValueError:
                    continue
                if 1900 <= abs(val) <= 2100:
                    continue
                if abs(val) < 0.01:
                    continue
                all_nums.append(val)
        return all_nums

    def _split_amounts_pcts(self, all_nums, n_years):
        amounts = []
        pcts = []
        extra_amounts = []
        extra_pcts = []

        if len(all_nums) >= n_years * 2:
            for i in range(n_years * 2):
                if i % 2 == 0:
                    amounts.append(all_nums[i])
                else:
                    pcts.append(all_nums[i])
            remaining = all_nums[n_years * 2:]
            if len(remaining) >= n_years * 2:
                for i in range(n_years * 2):
                    if i % 2 == 0:
                        extra_amounts.append(remaining[i])
                    else:
                        extra_pcts.append(remaining[i])
            elif len(remaining) >= n_years:
                large = [v for v in remaining if abs(v) > 100]
                small = [v for v in remaining if 0 < abs(v) <= 100]
                if len(large) >= n_years:
                    extra_amounts = large[:n_years]
                    extra_pcts = small[:n_years] if len(small) >= n_years else []
                else:
                    extra_amounts = remaining[:n_years]
        elif len(all_nums) >= n_years:
            large_nums = [v for v in all_nums if abs(v) > 100]
            small_nums = [v for v in all_nums if 0 < abs(v) <= 100]

            if len(large_nums) >= n_years:
                amounts = large_nums[:n_years]
                pcts = small_nums[:n_years] if len(small_nums) >= n_years else small_nums
            else:
                need = n_years - len(large_nums)
                promoted = sorted(small_nums, reverse=True)[:need]
                amounts = []
                pcts = []
                promoted_used = 0
                for v in all_nums:
                    if abs(v) > 100:
                        amounts.append(v)
                    elif v in promoted and promoted_used < need:
                        amounts.append(v)
                        promoted_used += 1
                    else:
                        pcts.append(v)

        return amounts, pcts, extra_amounts, extra_pcts



    def _parse_segment_by_name_search(self, text, years):
        segments = []
        for pattern in self._SEGMENT_NAME_PATTERNS:
            matches = list(re.finditer(pattern, text, re.IGNORECASE))
            if not matches:
                continue
            seg_name = matches[0].group(0)

            seg_table = extract_segment_table(text, [seg_name])
            if seg_name not in seg_table:
                continue

            seg_data = seg_table[seg_name]
            data_years = sorted(seg_data.keys())
            if len(data_years) < 2:
                continue

            latest = seg_data[data_years[-1]]
            prev = seg_data[data_years[-2]]
            growth = (latest - prev) / abs(prev) if prev != 0 else None
            segments.append({
                'name': seg_name,
                'revenue_latest': latest,
                'revenue_previous': prev,
                'growth_pct': round(growth * 100, 1) if growth is not None else None,
                'year_latest': data_years[-1],
            })

        return segments

    def _analyze_vbp(self, text, prospectus_info=None):
        sector = 'unknown'
        if prospectus_info:
            sector = prospectus_info.get('sector', 'unknown') or 'unknown'

        healthcare_sectors = {'healthcare', 'medical', 'biotech', 'pharmaceutical'}
        if sector.lower() not in healthcare_sectors:
            return 0, '非医疗行业，不适用集采/DRG/DIP风险'

        lower = text.lower()
        vbp_keywords = [
            'volume-based procurement', 'centralized procurement', 'government pricing',
        ]
        found_vbp = [kw for kw in vbp_keywords if kw in lower]
        vsl = SETTINGS.valuation_score
        score = min(vsl.vbp_score_max, len(found_vbp) * vsl.vbp_keyword_bonus)

        if re.search(r'\bDRG\b', text):
            score += vsl.vbp_keyword_bonus
        if re.search(r'\bDIP\b', text):
            score += vsl.vbp_keyword_bonus

        summary_parts = []
        if 'volume-based procurement' in lower:
            m = re.search(r'(\d+)\s+out\s+of\s+(\d+)\s+of\s+our\s+medical\s+implants\s+have\s+been\s+included', text, re.IGNORECASE)
            if m:
                summary_parts.append(f"{m.group(1)}/{m.group(2)}个产品纳入集采")
            if re.search(r'average\s+selling\s+prices?\s+decreased', text, re.IGNORECASE):
                summary_parts.append("集采后ASP下降")
            if re.search(r'sales\s+volume\s+increased\s+significantly', text, re.IGNORECASE):
                summary_parts.append("销量显著增长")
        if re.search(r'\bDRG\b', text):
            summary_parts.append("存在DRG支付改革风险")
        if re.search(r'\bDIP\b', text):
            summary_parts.append("存在DIP支付改革风险")

        score = min(vsl.vbp_total_max, score)
        summary = '；'.join(summary_parts) if summary_parts else ('存在集采/定价风险' if found_vbp else '未发现集采风险')
        return score, summary


class GeographicExpansionAnalyzer:
    _CHINA_ALIASES = ['Chinese mainland', 'Mainland China', 'PRC', 'China market', "People's Republic of China"]
    _OVERSEAS_ALIASES = ['Overseas', 'International', 'Other countries and regions', 'Outside mainland China', 'Non-PRC', 'Outside the PRC']

    def _classify_geo_line(self, line_lower):
        is_overseas = False
        is_china = False
        if 'outside mainland china' in line_lower or 'outside the prc' in line_lower or 'non-prc' in line_lower:
            return False, True
        for alias in self._OVERSEAS_ALIASES:
            if alias.lower() in line_lower and alias.lower() not in ('outside mainland china', 'outside the prc'):
                is_overseas = True
                break
        for alias in self._CHINA_ALIASES:
            if alias.lower() in line_lower:
                is_china = True
                break
        if is_overseas and is_china:
            if 'overseas' in line_lower or 'international' in line_lower:
                is_china = False
            else:
                is_overseas = False
        return is_china, is_overseas

    def analyze(self, text, prospectus_info):
        result = {
            'china_revenue_latest': None,
            'overseas_revenue_latest': None,
            'overseas_revenue_pct': None,
            'overseas_growth_pct': None,
            'overseas_growth_label': '缺失',
            'overseas_risks': [],
            'geographic_table': {},
            'geographic_confidence': 'missing',
            'confidence': 'missing',
        }
        try:
            geo_pct_data = self._extract_geo_with_pct(text)
            cn_pcts = geo_pct_data.get('china', {})
            os_pcts = geo_pct_data.get('overseas', {})

            if os_pcts:
                years = sorted(os_pcts.keys())
                latest = years[-1]
                result['overseas_revenue_pct'] = os_pcts.get(latest)
                if len(years) >= 2:
                    prev = years[-2]
                    os_prev = os_pcts.get(prev)
                    os_latest = os_pcts.get(latest)
                    if _is_num(os_prev) and os_prev > 0 and _is_num(os_latest):
                        result['overseas_growth_pct'] = round((os_latest - os_prev) / os_prev * 100, 1)
                result['geographic_table'] = {'china_pct': cn_pcts, 'overseas_pct': os_pcts}
                result['geographic_confidence'] = 'pct_from_text'
            else:
                geo_table = extract_segment_table(text, self._CHINA_ALIASES + self._OVERSEAS_ALIASES)
                cn_data = {}
                os_data = {}
                for alias in self._CHINA_ALIASES:
                    if alias in geo_table:
                        cn_data = geo_table[alias]
                        break
                for alias in self._OVERSEAS_ALIASES:
                    if alias in geo_table:
                        os_data = geo_table[alias]
                        break

                years = sorted(set(list(cn_data.keys()) + list(os_data.keys())))
                if years:
                    latest = years[-1]
                    result['china_revenue_latest'] = cn_data.get(latest)
                    result['overseas_revenue_latest'] = os_data.get(latest)
                    total = (cn_data.get(latest) or 0) + (os_data.get(latest) or 0)
                    if total > 0:
                        result['overseas_revenue_pct'] = round((os_data.get(latest) or 0) / total * 100, 1)
                    if len(years) >= 2:
                        prev = years[-2]
                        os_prev = os_data.get(prev)
                        os_latest = os_data.get(latest)
                        if _is_num(os_prev) and os_prev > 0 and _is_num(os_latest):
                            result['overseas_growth_pct'] = round((os_latest - os_prev) / os_prev * 100, 1)
                    result['geographic_table'] = {'china': cn_data, 'overseas': os_data}
                    result['geographic_confidence'] = 'regex_context'

            overseas_pct = result.get('overseas_revenue_pct')
            overseas_growth = result.get('overseas_growth_pct')
            gt = SETTINGS.geographic
            if overseas_pct is not None:
                if overseas_pct >= gt.high_pct and (overseas_growth or 0) > gt.growth_extreme:
                    result['overseas_growth_label'] = '高速扩张'
                elif overseas_pct >= gt.high_pct:
                    result['overseas_growth_label'] = '快速扩张'
                elif overseas_pct >= gt.mid_pct:
                    result['overseas_growth_label'] = '初步验证'
                elif overseas_pct < gt.low_pct and (overseas_growth or 0) > gt.growth_high:
                    result['overseas_growth_label'] = '仍然很小'
                    result['overseas_risks'].append('海外增长快但基数低')
                else:
                    result['overseas_growth_label'] = '海外放缓'
                if overseas_pct >= gt.mid_pct:
                    result['overseas_risks'].extend(['监管/合规风险', '汇率波动风险', '渠道管理风险'])

            if result['china_revenue_latest'] is not None or result['overseas_revenue_pct'] is not None:
                result['confidence'] = result['geographic_confidence']
        except Exception as e:
            logger.warning("%s: %s", type(self).__name__, e)
        return result

    def _extract_overseas_pct_direct(self, text):
        lines = text.split('\n')
        for i, line in enumerate(lines):
            ll = line.lower().strip()
            if any(alias.lower() in ll for alias in self._OVERSEAS_ALIASES):
                window = ' '.join(lines[i:min(i + 6, len(lines))])
                pcts = [float(m) for m in re.findall(r'(\d+\.?\d*)\s*%', window) if 0 < float(m) <= 100]
                if pcts:
                    return pcts[-1]
        return None

    def _extract_geo_with_pct(self, text):
        lines = text.split('\n')
        result = {'china': {}, 'overseas': {}}

        for i, line in enumerate(lines):
            ll = line.lower().strip()
            if 'subtotal' in ll or 'total' in ll:
                continue
            is_china, is_overseas = self._classify_geo_line(ll)
            if not is_overseas and not is_china:
                continue

            key = 'overseas' if is_overseas else 'china'

            nums_after = []
            for j in range(i + 1, min(i + 15, len(lines))):
                next_line = lines[j].strip()
                next_lower = next_line.lower()
                if self._classify_geo_line(next_lower) != (False, False):
                    break
                if 'total' in next_lower:
                    break
                for m in re.finditer(r'^(\d[\d,]*\.?\d*)$', next_line):
                    raw = m.group(1).replace(',', '')
                    try:
                        val = float(raw)
                        nums_after.append(val)
                    except ValueError:
                        continue

            pcts = [v for v in nums_after if 0 < v <= 100]
            amounts = [v for v in nums_after if v > 100]

            if len(pcts) >= 2 and len(amounts) >= 2:
                if key in result and result[key]:
                    continue
                result[key] = {2023 + yi: pcts[yi] for yi in range(min(len(pcts), 3))}

        return result


class CustomerSupplierAnalyzer:
    @staticmethod
    def _latest_pct_after(text, phrase_pattern, window=900, stop_patterns=None):
        """Extract the latest track-record percentage after a customer/supplier phrase."""
        match = re.search(phrase_pattern, text, re.IGNORECASE)
        if not match:
            return None
        segment = text[match.end():match.end() + window]
        default_stops = [
            r'\n[A-Z][A-Z\s,&/()-]{8,}\n',
            r'CONTROLLING\s+SHAREHOLDERS\b',
            r'RISK\s+FACTORS\b',
        ]
        stop_positions = []
        for stop_pattern in (stop_patterns or []) + default_stops:
            stop = re.search(stop_pattern, segment, re.IGNORECASE)
            if stop:
                stop_positions.append(stop.start())
        if stop_positions:
            segment = segment[:min(stop_positions)]
        pcts = re.findall(r'(\d+(?:\.\d+)?)\s*%', segment)
        if not pcts:
            return None
        try:
            return float(pcts[-1])
        except ValueError:
            return None

    def analyze(self, text, prospectus_info):
        result = {
            'top5_customer_revenue_pct': None,
            'largest_customer_revenue_pct': None,
            'top5_supplier_purchase_pct': None,
            'largest_supplier_purchase_pct': None,
            'concentration_risk_label': '缺失',
            'concentration_score_penalty': 0,
            'confidence': 'missing',
        }
        try:
            result['top5_customer_revenue_pct'] = self._latest_pct_after(
                text,
                r'(?:five\s+largest\s+customers|top\s+five\s+customers)\b',
                stop_patterns=[
                    r'revenue\s+generated\s+from\s+our\s+largest\s+customer\b',
                    r'our\s+revenue\s+generated\s+from\s+our\s+largest\s+customer\b',
                    r'our\s+largest\s+customer\b',
                    r'our\s+suppliers\b',
                    r'suppliers\s+primarily',
                    r'five\s+largest\s+suppliers\b',
                ],
            )
            result['largest_customer_revenue_pct'] = self._latest_pct_after(
                text,
                r'(?:single\s+largest\s+customer|largest\s+customer(?!s))\b',
                stop_patterns=[
                    r'our\s+revenue\s+generated\s+from\s+our\s+five\s+largest\s+customers\b',
                    r'five\s+largest\s+customers\b',
                    r'five\s+largest\s+suppliers\b',
                    r'our\s+suppliers\b',
                    r'suppliers\s+primarily',
                    r'our\s+transaction\s+amounts\s+with\s+our\s+largest\s+supplier\b',
                ],
            )
            result['top5_supplier_purchase_pct'] = self._latest_pct_after(
                text,
                r'(?:five\s+largest\s+suppliers|top\s+five\s+suppliers)\b',
                stop_patterns=[
                    r'single\s+largest\s+supplier\b',
                    r'largest\s+supplier(?!s)\b',
                ],
            )
            result['largest_supplier_purchase_pct'] = self._latest_pct_after(
                text,
                r'(?:single\s+largest\s+supplier|largest\s+supplier(?!s))\b',
                stop_patterns=[
                    r'our\s+transaction\s+amounts\s+with\s+our\s+five\s+largest\s+suppliers\b',
                    r'five\s+largest\s+suppliers\b',
                    r'we\s+select\s+our\s+suppliers\b',
                    r'see\s+["“]business',
                ],
            )

            penalty = 0
            top5_cust = result.get('top5_customer_revenue_pct')
            largest_cust_val = result.get('largest_customer_revenue_pct')
            top5_supp = result.get('top5_supplier_purchase_pct')
            largest_supp_val = result.get('largest_supplier_purchase_pct')
            ct = SETTINGS.customer_concentration

            if top5_cust is not None and top5_cust > ct.top5_customer_high:
                penalty += 3
            if largest_cust_val is not None and largest_cust_val > ct.largest_customer_high:
                penalty += 2
            if top5_supp is not None and top5_supp > ct.top5_supplier_high:
                penalty += 2
            if largest_supp_val is not None and largest_supp_val > ct.largest_supplier_high:
                penalty += 1

            result['concentration_score_penalty'] = penalty
            if penalty >= ct.penalty_high:
                result['concentration_risk_label'] = '高'
            elif penalty >= ct.penalty_mid:
                result['concentration_risk_label'] = '中'
            else:
                result['concentration_risk_label'] = '低'

            if top5_cust is not None:
                result['confidence'] = 'regex_context'
        except Exception as e:
            logger.warning("%s: %s", type(self).__name__, e)
        return result


class WorkingCapitalCashFlowAnalyzer:
    @staticmethod
    def _extract_operating_cash_flow(text):
        row_match = re.search(
            r'Net\s+cash\s+(?:used\s+in|generated\s+from|\(used\s+in\)/generated\s+from|used\s+in/generated\s+from)\s+operating\s+activities'
            r'(?P<row>[\s\S]{0,320}?)(?=Net\s+cash|Net\s+increase|Net\s+decrease|$)',
            text,
            re.IGNORECASE,
        )
        if not row_match:
            return None

        row = row_match.group(0)
        nums = _extract_table_nums(row, 2, min_val=500)
        if not nums:
            return None

        latest = nums[-1]
        unit_context = text[max(0, row_match.start() - 500):row_match.start()].lower()
        if "rmb'000" in unit_context or "rmb’000" in unit_context or "in thousands" in unit_context:
            latest = latest / 1000
        return round(latest, 3)

    def analyze(self, text, prospectus_info):
        result = {
            'operating_cash_flow': None,
            'ocf_to_net_profit': None,
            'inventory_turnover_days_latest': None,
            'receivables_growth_vs_revenue': None,
            'cash_quality_label': '缺失',
            'working_capital_risks': [],
            'confidence': 'missing',
        }
        try:
            result['operating_cash_flow'] = self._extract_operating_cash_flow(text)

            ocf_table = extract_financial_table_by_row(text, {
                'operating_cash_flow': ['cash generated from operations', 'net cash from operating activities', 'operating cash flow'],
            })
            if result['operating_cash_flow'] is None and ocf_table and 'operating_cash_flow' in ocf_table:
                years = sorted(ocf_table['operating_cash_flow'].keys())
                if years:
                    result['operating_cash_flow'] = ocf_table['operating_cash_flow'][years[-1]]

            net_profit = prospectus_info.get('net_profit')
            if _is_num(net_profit) and net_profit > 0 and _is_num(result['operating_cash_flow']):
                result['ocf_to_net_profit'] = round(abs(result['operating_cash_flow']) / net_profit, 2)

            inv_match = re.search(r'inventory\s+turnover\s+days\s+were\s+([\d,]+)\s*,\s*([\d,]+)\s*(?:and|&)\s*([\d,]+)', text, re.IGNORECASE)
            if inv_match:
                try:
                    result['inventory_turnover_days_latest'] = float(inv_match.group(3).replace(',', ''))
                except ValueError:
                    pass

            risks = []
            ocf_np = result.get('ocf_to_net_profit')
            operating_cash_flow = result.get('operating_cash_flow')
            if _is_num(operating_cash_flow) and operating_cash_flow < 0:
                result['cash_quality_label'] = '弱'
                risks.append('经营现金流为负')
            elif ocf_np is not None:
                cf = SETTINGS.cash_flow
                if ocf_np >= cf.ocf_np_strong:
                    result['cash_quality_label'] = '强'
                elif ocf_np >= cf.ocf_np_fair:
                    result['cash_quality_label'] = '一般'
                else:
                    result['cash_quality_label'] = '弱'
                    risks.append('经营现金流弱于净利润')

            inv_days = result.get('inventory_turnover_days_latest')
            if inv_days is not None and inv_days > SETTINGS.cash_flow.inventory_days_warning:
                risks.append(f'存货周转天数偏高({inv_days:.0f}天)')

            result['working_capital_risks'] = risks
            if result['operating_cash_flow'] is not None or inv_days is not None:
                result['confidence'] = 'regex_context'
        except Exception as e:
            logger.warning("%s: %s", type(self).__name__, e)
        return result


class ProductionCapacityAnalyzer:
    @staticmethod
    def _extract_utilization_rate(text):
        util_match = re.search(r'utili[sz]ation\s+rate(?:\s+of\s+production\s+line)?', text, re.IGNORECASE)
        if util_match:
            segment = text[util_match.start():util_match.start() + 1200]
            pcts = re.findall(r'(\d+(?:\.\d+)?)\s*%', segment)
            if pcts:
                try:
                    return max(float(p) for p in pcts)
                except ValueError:
                    return None

        direct_match = re.search(r'utili[sz]ation\s+rate\s*(?:of|was|:)\s*(\d+\.?\d*)\s*%', text, re.IGNORECASE)
        if direct_match:
            return float(direct_match.group(1))

        capacity_match = re.search(r'(\d+\.?\d*)\s*%\s*(?:of\s+)?(?:our\s+)?production\s+capacity', text, re.IGNORECASE)
        if capacity_match:
            return float(capacity_match.group(1))
        return None

    def analyze(self, text, prospectus_info):
        result = {
            'utilization_rate': None,
            'expansion_plan': None,
            'outsourced_production': None,
            'capacity_score': 0,
            'capacity_summary': '缺失',
            'confidence': 'missing',
        }
        try:
            result['utilization_rate'] = self._extract_utilization_rate(text)

            if re.search(r'outsourc|subcontract|sterilization\s+service', text, re.IGNORECASE):
                result['outsourced_production'] = True

            if re.search(r'expansion|new\s+production\s+facility|new\s+manufacturing', text, re.IGNORECASE):
                result['expansion_plan'] = True

            util = result.get('utilization_rate')
            ct = SETTINGS.capacity
            if util is not None:
                if util > ct.overload:
                    result['capacity_score'] = 8
                    result['capacity_summary'] = f'产能紧张(利用率{util:.0f}%)，扩产有紧迫性但需关注执行风险'
                elif util > ct.high:
                    result['capacity_score'] = 7
                    result['capacity_summary'] = f'产能利用率高({util:.0f}%)，扩产有合理性'
                elif util > ct.moderate:
                    result['capacity_score'] = 5
                    result['capacity_summary'] = f'产能利用率适中({util:.0f}%)'
                else:
                    result['capacity_score'] = 2
                    result['capacity_summary'] = f'产能利用率偏低({util:.0f}%)，募资扩产需谨慎'
                result['confidence'] = 'regex_context'
        except Exception as e:
            logger.warning("%s: %s", type(self).__name__, e)
        return result


class RnDPipelineAnalyzer:
    _BIOTECH_CLINICAL_PATTERNS = [
        r'(?:Phase|Ph)\s*(I{1,3}|1|2|3)\s*(?:/\s*(?:Phase|Ph)\s*(I{1,3}|1|2|3))?\s*(?:clinical\s*trial|study|trial)?',
        r'Core\s+Product',
        r'drug\s+candidate',
        r'clinical[- ]?stage',
        r'NDA|BLA|IND',
        r'Pivotal\s+(?:trial|study)',
        r'approved\s+(?:for|by|as)',
        r'commercialization',
        r'pipeline',
    ]

    def analyze(self, text, prospectus_info):
        result = {
            'rd_expense_latest': None, 'rd_expense_ratio': None,
            'product_count_approved': None, 'product_count_pipeline': None,
            'core_product_names': [], 'latest_clinical_stage': None,
            'phase_iii_count': 0, 'nda_or_approved_count': 0,
            'technology_moat_score': 0, 'pipeline_quality_label': '缺失',
            'commercialization_risk': '缺失', 'confidence': 'missing',
            'clinical_stage_score': 0,
        }
        try:
            rd_from_info = prospectus_info.get('rd_expense')
            revenue_from_info = prospectus_info.get('revenue')
            sector = prospectus_info.get('sector', 'unknown')
            fin_currency = prospectus_info.get('financial_currency', 'RMB')
            raw_text = (text or '') + ' ' + (prospectus_info.get('_extracted_text', '') or '')

            # --- 研发费用（对生物科技不隐藏高比例） ---
            is_biotech = False
            if sector == 'healthcare':
                biotech_kw = ['biotech', 'biopharma', 'clinical trial', 'drug candidate',
                              '18a', 'innovative drug', 'pipeline', 'phase']
                biotech_hits = sum(1 for kw in biotech_kw if kw in raw_text.lower())
                is_biotech = (biotech_hits >= SETTINGS.rnd.biotech_keyword_hits_min) or ('-b' in str(prospectus_info.get('extracted_company_name', '')).lower())

            if _is_num(rd_from_info) and _is_num(revenue_from_info) and revenue_from_info > 0:
                rd_latest = abs(rd_from_info)
                rd_ratio = rd_latest / revenue_from_info * 100
                # 对生物科技：研发费用率 >100% 是正常现象
                if rd_ratio > SETTINGS.rnd.expense_ratio_anomaly and not is_biotech and rd_latest > revenue_from_info * SETTINGS.rnd.expense_ratio_unit_mismatch_multiplier:
                    rd_latest = rd_latest / 1000
                    rd_ratio = rd_latest / revenue_from_info * 100
                if rd_ratio > SETTINGS.rnd.expense_ratio_anomaly and not is_biotech:
                    result['rd_expense_latest'] = rd_latest
                    result['rd_expense_ratio'] = None
                    result['rd_ratio_warning'] = '研发费率疑似单位错位'
                else:
                    result['rd_expense_latest'] = round(rd_latest, 3)
                    result['rd_expense_ratio'] = round(rd_ratio, 1)
                    result['confidence'] = 'from_consolidated_statement'
                    if is_biotech and rd_ratio > SETTINGS.rnd.expense_ratio_anomaly:
                        result['rd_ratio_biotech'] = True
            else:
                rd_table = extract_financial_table_by_row(text, {
                    'rd_expense': ['research and development expenses', 'r&d expenses'],
                })
                if rd_table and 'rd_expense' in rd_table:
                    years = sorted(rd_table['rd_expense'].keys())
                    if years:
                        rd_latest = abs(rd_table['rd_expense'][years[-1]])
                        if _is_num(revenue_from_info) and revenue_from_info > 0:
                            rd_ratio = rd_latest / revenue_from_info * 100
                            if rd_ratio > SETTINGS.rnd.expense_ratio_anomaly and not is_biotech and rd_latest > revenue_from_info * SETTINGS.rnd.expense_ratio_unit_mismatch_multiplier:
                                rd_latest = rd_latest / 1000
                                rd_ratio = rd_latest / revenue_from_info * 100
                            if rd_ratio > SETTINGS.rnd.expense_ratio_anomaly and not is_biotech:
                                result['rd_expense_latest'] = rd_latest
                                result['rd_expense_ratio'] = None
                                result['rd_ratio_warning'] = '研发费率疑似单位错位'
                            else:
                                result['rd_expense_latest'] = rd_latest
                                result['rd_expense_ratio'] = round(rd_ratio, 1) if rd_ratio is not None else None
                                result['confidence'] = 'regex_context'
                        else:
                            result['rd_expense_latest'] = rd_latest
                            result['confidence'] = 'regex_context'

            # --- 创新药管线识别（替代医疗器械 Class II/III） ---
            core_products = list(dict.fromkeys(
                m.group(0) for m in re.finditer(r'(?:Core\s+Product|核心产品)\s*[:\-]?\s*([A-Za-z0-9\-]+)', raw_text, re.IGNORECASE)
            ))[:5]
            result['core_product_names'] = [c.split()[-1] for c in core_products] if core_products else []

            # 临床阶段检测
            phases = []
            for pat in self._BIOTECH_CLINICAL_PATTERNS:
                for m in re.finditer(pat, raw_text, re.IGNORECASE):
                    phases.append(m.group(0)[:50])

            phase_map = {"phase iii": 3, "phase 3": 3, "phase ii": 2, "phase 2": 2,
                         "phase i": 1, "phase 1": 1, "iii": 3, "ii": 2, "i": 1}
            max_phase = 0
            for p in phases:
                pl = p.lower()
                for key, val in phase_map.items():
                    if key in pl:
                        max_phase = max(max_phase, val)

            result['latest_clinical_stage'] = f"Phase {'I' * max_phase}" if max_phase else "Pre-clinical"
            result['phase_iii_count'] = sum(1 for p in phases if "phase iii" in p.lower() or "phase 3" in p.lower())
            result['nda_or_approved_count'] = len(re.findall(r'\b(NDA|BLA|approved|commercialization)\b', raw_text, re.IGNORECASE))
            result['clinical_stage_score'] = max_phase

            # 一般管线数量（医疗器械/其他）
            class_ii = len(re.findall(r'Class\s+II(?:a|b)?\s+(?:medical\s+device|certificate|registration)', text, re.IGNORECASE))
            class_iii = len(re.findall(r'Class\s+III\s+(?:medical\s+device|certificate|registration)', text, re.IGNORECASE))
            result['class_ii_count'] = class_ii
            result['class_iii_count'] = class_iii

            # 技术护城河评分
            moat = 0
            rd_ratio = result.get('rd_expense_ratio')
            rt = SETTINGS.rnd
            if rd_ratio is not None:
                if rd_ratio >= rt.moat_high:
                    moat += 4
                elif rd_ratio >= rt.moat_mid:
                    moat += 3
                elif rd_ratio >= rt.moat_low:
                    moat += 2
                else:
                    moat += 1
            if is_biotech:
                if max_phase >= 3:
                    moat += 3
                elif max_phase >= 2:
                    moat += 2
                else:
                    moat += 1
            rt = SETTINGS.rnd
            if class_iii >= rt.class_iii_high_threshold:
                moat += rt.class_iii_high_bonus
            elif class_iii >= rt.class_iii_low_threshold:
                moat += rt.class_iii_low_bonus

            result['technology_moat_score'] = min(rt.moat_max_score, moat)
            if moat >= rt.moat_strong_threshold:
                result['pipeline_quality_label'] = '强'
            elif moat >= rt.moat_medium_threshold:
                result['pipeline_quality_label'] = '中'
            else:
                result['pipeline_quality_label'] = '弱'

            if is_biotech and max_phase >= rt.phase_iii_threshold:
                result['commercialization_risk'] = '中-上市临近'
            elif is_biotech and max_phase >= rt.phase_ii_threshold:
                result['commercialization_risk'] = '中'
            elif result.get('product_count_approved', 0) or class_iii:
                result['commercialization_risk'] = '中'
            else:
                result['commercialization_risk'] = '高'

            if rd_ratio is not None or is_biotech:
                if result['confidence'] == 'missing':
                    result['confidence'] = 'regex_context'
        except Exception as e:
            logger.warning("%s: %s", type(self).__name__, e)
        return result


class RiskFactorAnalyzer:
    def analyze(self, text, prospectus_info):
        result = {
            'risks': {},
            'total_penalty': 0,
            'confidence': 'missing',
        }
        try:
            risk_categories = {
                'regulatory_risk': ['regulatory', 'nmpa', 'fda', 'registration', 'approval', 'clinical trial approval'],
                'vbp_pricing_risk': ['volume-based procurement', 'centralized procurement', 'government pricing', 'price reduction', 'price cut', 'reimbursement'],
                'rd_failure_risk': ['r&d', 'clinical trial', 'product development', 'pipeline', 'failure'],
                'distributor_risk': ['distributor', 'distribution', 'dealer', 'sales channel'],
                'competition_risk': ['competition', 'competitive', 'market share', 'competitor'],
                'customer_concentration_risk': ['customer concentration', 'largest customer', 'dependent on'],
                'supplier_risk': ['supplier', 'raw material', 'supply chain', 'single source'],
                'inventory_risk': ['inventory', 'write-down', 'obsolete', 'slow-moving'],
                'overseas_risk': ['overseas', 'export', 'foreign', 'currency', 'exchange rate'],
                'fvtpl_risk': ['fvtpl', 'fair value', 'financial assets', 'investment securities'],
            }

            risk_section = text
            risk_start = text.lower().find('risk factors')
            if risk_start >= 0:
                risk_section = text[risk_start:risk_start + 80000]

            total_penalty = 0
            rt = SETTINGS.risk_factor
            for cat_name, keywords in risk_categories.items():
                evidence = []
                level = '低'
                penalty = 0
                for kw in keywords:
                    count = len(re.findall(kw, risk_section, re.IGNORECASE))
                    if count > 0:
                        first_match = re.search(rf'.{{0,60}}{re.escape(kw)}.{{0,60}}', risk_section, re.IGNORECASE)
                        if first_match:
                            evidence.append(first_match.group(0).strip()[:120])
                if len(evidence) >= rt.evidence_high:
                    level = '高'
                    penalty = rt.penalty_high
                elif len(evidence) >= rt.evidence_mid:
                    level = '中'
                    penalty = rt.penalty_mid
                total_penalty += penalty
                result['risks'][cat_name] = {
                    'risk_level': level,
                    'evidence_count': len(evidence),
                    'evidence_sample': evidence[:2],
                    'score_penalty': penalty,
                }

            result['total_penalty'] = min(rt.max_total_penalty, total_penalty)
            result['confidence'] = 'keyword_only'
        except Exception as e:
            logger.warning("%s: %s", type(self).__name__, e)
        return result
