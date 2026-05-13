import re
import logging
from ..table_extraction import extract_segment_table
from ..utils import extract_text_excerpts
from ..settings import SETTINGS
logger = logging.getLogger(__name__)


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
        r'Robot bodies?',
        r'Robotic solutions?',
        r'Industrial robots?',
        r'Parallel robots?',
        r'Mobile robots?',
        r'AGV',
        r'AMR',
        r'SCARA',
        r'Six[- ]axis robots?',
        r'Wafer handling',
        r'Controllers?',
        r'Vision systems?',
        r'机器人本体',
        r'机器人解决方案',
        r'并联机器人',
        r'移动机器人',
        r'工业机器人',
        r'晶圆搬运',
        r'控制器',
        r'视觉系统',
        r'Consumer electronics',
        r'Industrial equipment',
        r'Medical implants?',
        r'Surgical equipment',
        r'Others?',
        r'Remaining',
    ]

    _ROBOT_BUSINESS_HINTS = {
        'robot_body': [
            'robot bodies', 'robot body', 'robotic body', '工业机器人', '机器人本体',
            'parallel robots', '并联机器人', 'SCARA', '六轴', 'six-axis',
            'wafer handling', '晶圆搬运',
        ],
        'robot_solution': [
            'robotic solutions', 'robot solutions', 'robot solution', '机器人解决方案',
            'autonomous mobile robots', 'mobile robots', 'agv', 'amr', '移动机器人',
            'system integration', 'solution business',
        ],
        'robot_component': [
            'controllers', 'controller', 'vision systems', '视觉系统',
        ],
    }

    _EXCLUDE_SEGMENTS = [
        'net cash', 'cash and cash', 'net increase', 'decrease in cash',
        'summary', 'operating activities', 'investing activities',
        'financing activities', 'effect of exchange', 'cash at beginning',
        'cash at end', 'profit for', 'loss for', 'depreciation', 'amortization',
        'working capital', 'trade receivables', 'trade payables', 'inventories',
        'total revenue', 'total', 'amount',
    ]

    _GROSS_PROFIT_PATTERNS = [
        'breakdown of gross profit by business line',
        'gross profit by business line',
        'breakdown of gross profit',
        'gross profit breakdown',
        '毛利按业务线',
        '毛利拆分',
    ]

    def analyze(self, prospectus_info, text='', ipo_data=None):
        # 防御：某些调用者把 ipo_data 传到了 text 位置
        if isinstance(text, dict):
            text = ''
        result = {
            'segments': [],
            'main_segment': None,
            'fastest_growing_segment': None,
            'new_business_segment': None,
            'growth_source': 'missing',
            'business_model_label': None,
            'business_model_reasons': [],
            'segment_concentration_label': None,
            'segment_moat_label': None,
            'vbp_risk_score': 0,
            'vbp_summary': '',
            'asp_data': {},
            'business_breakdown_confidence': 'missing',
            'business_breakdown_warning': None,
            'profit_driver_segment': None,
            'revenue_driver_segment': None,
            'profit_revenue_mismatch': False,
            'profit_revenue_mismatch_detail': None,
            'confidence': 'missing',
            'evidence_excerpt': '',
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

                gp_data = self._extract_segment_gross_profits(text, segments)
                total_gp = 0
                for s in segments:
                    seg_name = s.get('name', '')
                    gp = gp_data.get(seg_name)
                    if gp and gp.get('gross_profit_latest') is not None:
                        s['gross_profit_latest'] = gp['gross_profit_latest']
                        if gp.get('gross_profit_previous') is not None:
                            s['gross_profit_previous'] = gp['gross_profit_previous']
                        rev_latest = s.get('revenue_latest')
                        if rev_latest and rev_latest != 0:
                            s['gross_margin_pct'] = round(s['gross_profit_latest'] / rev_latest * 100, 1)
                        total_gp += s['gross_profit_latest']

                if total_gp > 0:
                    for s in segments:
                        gp_latest = s.get('gross_profit_latest')
                        if gp_latest is not None:
                            s['gross_profit_share_pct'] = round(gp_latest / total_gp * 100, 1)

                segments_with_gp_share = [s for s in segments if s.get('gross_profit_share_pct') is not None]
                if segments_with_gp_share:
                    profit_driver = max(segments_with_gp_share, key=lambda x: x.get('gross_profit_share_pct', 0))
                    result['profit_driver_segment'] = profit_driver.get('name')

                sorted_by_share = sorted(segments, key=lambda x: x.get('share_pct', 0), reverse=True)
                result['main_segment'] = sorted_by_share[0].get('name') if sorted_by_share else None

                result['revenue_driver_segment'] = result.get('main_segment')

                if result['profit_driver_segment'] and result['revenue_driver_segment']:
                    if result['profit_driver_segment'] != result['revenue_driver_segment']:
                        result['profit_revenue_mismatch'] = True
                        result['profit_revenue_mismatch_detail'] = (
                            f"收入主要来自{result['revenue_driver_segment']}，"
                            f"但毛利主要来自{result['profit_driver_segment']}"
                        )

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
                main_name = (sorted_by_share[0].get('name') or '').lower() if sorted_by_share else ''
                body_share = self._segment_share_for_keywords(segments, self._ROBOT_BUSINESS_HINTS['robot_body'])
                solution_share = self._segment_share_for_keywords(segments, self._ROBOT_BUSINESS_HINTS['robot_solution'])
                component_share = self._segment_share_for_keywords(segments, self._ROBOT_BUSINESS_HINTS['robot_component'])
                concentration_share = max((s.get('share_pct', 0) or 0) for s in segments) if segments else 0
                if concentration_share >= 70:
                    result['segment_concentration_label'] = '主业集中'
                elif concentration_share >= 40:
                    result['segment_concentration_label'] = '双轮驱动'
                else:
                    result['segment_concentration_label'] = '多元分散'

                business_model_reasons = []
                if body_share or solution_share:
                    if solution_share >= body_share:
                        result['business_model_label'] = '机器人解决方案为主'
                        business_model_reasons.append('收入更偏向解决方案/集成')
                    else:
                        result['business_model_label'] = '机器人本体为主'
                        business_model_reasons.append('本体收入占比更高')
                if component_share:
                    business_model_reasons.append('存在控制器/视觉等关键部件收入')
                if main_name:
                    if any(k in main_name for k in ('solution', '解决方案')):
                        result['segment_moat_label'] = '方案驱动'
                    elif any(k in main_name for k in ('body', '本体', 'robots', 'robot')):
                        result['segment_moat_label'] = '本体驱动'
                if not result.get('business_model_label') and main_name:
                    result['business_model_label'] = '分部结构待确认'
                result['business_model_reasons'] = business_model_reasons

                if new_biz:
                    result['growth_source'] = '主业增长 + 新业务贡献'
                elif main_share >= SETTINGS.business_breakdown.main_segment_dominance_pct and (main_growth or 0) > 0:
                    result['growth_source'] = '主业驱动'
                elif any(s.get('growth_pct', 0) and s['growth_pct'] > 0 for s in segments):
                    result['growth_source'] = '产品结构驱动'
                else:
                    result['growth_source'] = '增长来源待确认'

                result['segments'] = segments
                excerpt_patterns = list(self._BUSINESS_LINE_PATTERNS[:4])
                excerpt_patterns.extend(
                    rf'{re.escape(str(seg.get("name", "")))}' for seg in segments[:4] if seg.get('name')
                )
                result['evidence_excerpt'] = "\n\n".join(
                    extract_text_excerpts(text, excerpt_patterns, window=180, max_chars=1000, limit=3)
                )

            vbp_score, vbp_summary = self._analyze_vbp(text, prospectus_info)
            result['vbp_risk_score'] = vbp_score
            result['vbp_summary'] = vbp_summary

            if segments:
                result['confidence'] = result['business_breakdown_confidence']
        except Exception as e:
            logger.warning("%s: %s", type(self).__name__, e)
            result['_error'] = str(e)
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
        if re.search(r'\d{2,}', name_without_footnote):
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

    def _segment_share_for_keywords(self, segments, keywords):
        if not segments:
            return 0
        total = 0
        for seg in segments:
            name = str(seg.get('name', '')).lower()
            if any(kw.lower() in name for kw in keywords):
                total += seg.get('share_pct', 0) or 0
        return round(total, 1)

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

    def _extract_segment_gross_profits(self, text, segments):
        if not segments:
            return {}

        gross_profits = {}
        lines = text.split('\n')
        section_start = None

        for i, line in enumerate(lines):
            ll = line.lower().strip()
            if any(p in ll for p in self._GROSS_PROFIT_PATTERNS):
                section_start = i
                break

        if section_start is not None:
            window_lines = lines[section_start:min(section_start + 250, len(lines))]
            window = '\n'.join(window_lines)

            year_matches = re.findall(r'\b(20\d{2})\b', window)
            years = []
            for y in year_matches:
                yi = int(y)
                if yi not in years and 2015 <= yi <= 2030:
                    years.append(yi)
            years = sorted(years)
            if len(years) >= 2:
                gp_entries = self._parse_segment_table(window_lines, years)
                for gp_entry in gp_entries:
                    gp_name = gp_entry.get('name', '')
                    for seg in segments:
                        seg_name = seg.get('name', '')
                        if seg_name and gp_name and (
                            gp_name.lower() == seg_name.lower()
                            or gp_name.lower() in seg_name.lower()
                            or seg_name.lower() in gp_name.lower()
                        ):
                            gross_profits[seg_name] = {
                                'gross_profit_latest': gp_entry.get('revenue_latest'),
                                'gross_profit_previous': gp_entry.get('revenue_previous'),
                            }
                            break

        for seg in segments:
            seg_name = seg.get('name', '')
            if seg_name in gross_profits:
                continue
            for pattern in [
                rf'gross\s+profit\s+margin\s+of\s+{re.escape(seg_name)}\s+was\s+([\d.]+)\s*%',
                rf'gross\s+margin\s+of\s+{re.escape(seg_name)}\s+was\s+([\d.]+)\s*%',
                rf'gross\s+profit\s+margin\s+for\s+{re.escape(seg_name)}\s+was\s+([\d.]+)\s*%',
                rf'gross\s+margin\s+for\s+{re.escape(seg_name)}\s+was\s+([\d.]+)\s*%',
                rf'{re.escape(seg_name)}\s+gross\s+profit\s+margin\s+was\s+([\d.]+)\s*%',
                rf'{re.escape(seg_name)}\s+gross\s+margin\s+was\s+([\d.]+)\s*%',
            ]:
                m = re.search(pattern, text, re.IGNORECASE)
                if m:
                    margin_pct = float(m.group(1))
                    rev_latest = seg.get('revenue_latest')
                    rev_previous = seg.get('revenue_previous')
                    gp_latest = round(rev_latest * margin_pct / 100, 2) if rev_latest and margin_pct else None
                    gp_previous = round(rev_previous * margin_pct / 100, 2) if rev_previous and margin_pct else None
                    gross_profits[seg_name] = {
                        'gross_profit_latest': gp_latest,
                        'gross_profit_previous': gp_previous,
                    }
                    break

        return gross_profits

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
