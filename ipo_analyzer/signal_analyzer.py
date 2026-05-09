"""交易信号拆解分析器 — SignalComponentAnalyzer"""

import re

from .utils import _is_num, _normalize_gm, _contains_any, SECTOR_KEYWORDS
from .settings import SETTINGS
from .cornerstone import get_sovereign_capital, get_top_tier_capital, get_weak_signal_capital


class SignalComponentAnalyzer:
    """交易信号拆解分析器（原 AdvancedIPOFrameworkAnalyzer）。

    不再输出独立 100 分"进阶框架"，而是把 7 个维度拆成信号组件，
    供主评分系统 (ScoringSystem) 统一加权。
    """

    @staticmethod
    def _strength(score, max_score, high_ratio=0.6, mid_ratio=0.3):
        if not max_score or score <= 0:
            return '缺失'
        ratio = score / max_score
        if ratio >= high_ratio:
            return '强'
        if ratio >= mid_ratio:
            return '中'
        return '弱'

    @staticmethod
    def _data_confidence_level(score, max_score):
        if score <= 0:
            return '缺失'
        if score >= max_score * 0.8:
            return '高'
        if score >= max_score * 0.4:
            return '中'
        return '低'

    SOVEREIGN_CAPITAL = get_sovereign_capital()

    TOP_TIER_CAPITAL = get_top_tier_capital()

    WEAK_SIGNAL_CAPITAL = get_weak_signal_capital()

    MAINLINE_KEYWORDS = {k: v['mainline'] for k, v in SECTOR_KEYWORDS.items()}

    @staticmethod
    def _clamp(value, low, high):
        return max(low, min(high, value))

    @staticmethod
    def _component(score, max_score, label, detail, confidence='rule_based', reasons=None, red_flags=None):
        return {
            'score': int(max(0, min(max_score, round(score)))),
            'max_score': max_score,
            'label': label,
            'detail': detail,
            'confidence': confidence,
            'reasons': reasons or [],
            'red_flags': red_flags or [],
        }

    def analyze(self, ipo, prospectus_info, text):
        components = {
            'real_money': self._analyze_real_money(ipo),
            'float_structure': self._analyze_float_structure(ipo, prospectus_info),
            'cornerstone_structure': self._analyze_cornerstone_structure(prospectus_info, text),
            'valuation_framework': self._analyze_valuation_framework(prospectus_info),
            'mainline_beta': self._analyze_mainline_beta(prospectus_info, text),
            'stock_connect_path': self._analyze_stock_connect_path(prospectus_info, text),
            'data_quality': self._analyze_data_quality(prospectus_info),
        }

        red_flags = []
        watch_items = []
        for component in components.values():
            red_flags.extend(component.get('red_flags', []))
            for reason in component.get('reasons', []):
                if reason and reason not in watch_items:
                    watch_items.append(reason)

        score = sum(component.get('score', 0) for component in components.values())
        vsl = SETTINGS.valuation_score
        if score >= vsl.advanced_high:
            legacy_label = '进阶强信号'
        elif score >= vsl.advanced_mid_high:
            legacy_label = '进阶正向'
        elif score >= vsl.advanced_mid:
            legacy_label = '进阶观察'
        else:
            legacy_label = '进阶谨慎'

        confidence = 'mixed_rule_keyword' if components['mainline_beta'].get('confidence') == 'keyword_only' else 'rule_based'
        if red_flags:
            confidence = f'{confidence}_with_flags'

        vm = components['valuation_framework']
        valuation_label = vm.get('label', '')
        is_biotech_unprofitable = (
            prospectus_info.get('sector') == 'healthcare'
            and prospectus_info.get('profitable') is False
            and ('-b' in str(prospectus_info.get('extracted_company_name', '')).lower()
                 or 'biotech' in str(prospectus_info.get('_extracted_text', '')).lower())
        )
        if is_biotech_unprofitable and valuation_label in ('缺失', '估值压力'):
            if prospectus_info.get('rnd_pipeline', {}).get('pipeline_quality_label'):
                vm_strength = '中'
            else:
                vm_strength = '弱'
        elif is_biotech_unprofitable:
            vm_strength = '中'
        else:
            vm_strength = self._strength(vm.get('score', 0), vm.get('max_score', 20))

        signal_breakdown = {
            'real_money': {
                'strength': self._strength(components['real_money'].get('score', 0), 20),
                'detail': components['real_money'].get('detail', ''),
            },
            'float_structure': {
                'strength': self._strength(components['float_structure'].get('score', 0), 15),
                'detail': components['float_structure'].get('detail', ''),
                'float_signal': components['float_structure'].get('label', ''),
            },
            'cornerstone_quality': {
                'strength': self._strength(components['cornerstone_structure'].get('score', 0), 15),
                'detail': components['cornerstone_structure'].get('detail', ''),
            },
            'valuation_reading': {
                'strength': vm_strength,
                'detail': vm.get('detail', ''),
                'label': valuation_label,
            },
            'theme_bonus': {
                'strength': self._strength(components['mainline_beta'].get('score', 0), 15, high_ratio=0.67, mid_ratio=0.33),
                'detail': components['mainline_beta'].get('detail', ''),
            },
            'liquidity_bonus': {
                'strength': self._strength(components['stock_connect_path'].get('score', 0), 10, high_ratio=0.7, mid_ratio=0.4),
                'detail': components['stock_connect_path'].get('detail', ''),
            },
            'data_confidence': {
                'strength': self._data_confidence_level(components['data_quality'].get('score', 0), 5),
                'detail': components['data_quality'].get('detail', ''),
                'red_flags': components['data_quality'].get('red_flags', []),
            },
        }

        return {
            'signal_breakdown': signal_breakdown,
            'score': int(self._clamp(score, 0, 100)),
            'label': legacy_label,
            'components': components,
            'red_flags': red_flags,
            'watch_items': watch_items[:8],
            'hold_strategy': self._build_hold_strategy(score, components, red_flags),
            'confidence': confidence,
        }

    def _analyze_real_money(self, ipo):
        margin_total = ipo.get('margin_total')
        public_offer = ipo.get('public_offer')
        over_sub = ipo.get('over_sub_ratio')
        reasons = []
        score = 0
        rt = SETTINGS.real_money

        if _is_num(margin_total):
            if margin_total >= rt.tier1:
                score = 20
            elif margin_total >= rt.tier2:
                score = 17
            elif margin_total >= rt.tier3:
                score = 14
            elif margin_total >= rt.tier4:
                score = 11
            elif margin_total >= rt.tier5:
                score = 8
            elif margin_total >= rt.tier6:
                score = 5
            else:
                score = 2
            reasons.append(f"真实融资认购金额约{margin_total:.2f}亿")
        elif _is_num(over_sub):
            if over_sub >= rt.over_sub_tier1:
                score = 14
            elif over_sub >= rt.over_sub_tier2:
                score = 11
            elif over_sub >= rt.over_sub_tier3:
                score = 7
            elif over_sub >= rt.over_sub_tier4:
                score = 4
            reasons.append("缺少真实金额，退回按超购倍数估算")

        detail_parts = []
        if _is_num(margin_total):
            detail_parts.append(f"孖展{margin_total:.2f}亿")
        if _is_num(public_offer):
            detail_parts.append(f"公开集资{public_offer:.2f}亿")
        if _is_num(over_sub):
            detail_parts.append(f"超购{over_sub:.2f}x")
        if _is_num(margin_total) and _is_num(public_offer) and public_offer > 0:
            detail_parts.append(f"资金/公开{margin_total / public_offer:.1f}x")

        vsl = SETTINGS.valuation_score
        label = '资金强' if score >= vsl.real_money_high else ('资金中' if score >= vsl.real_money_mid else ('资金弱' if score > 0 else '缺失'))
        return self._component(score, 20, label, '；'.join(detail_parts) or '未获取真实认购金额', reasons=reasons)

    def _analyze_float_structure(self, ipo, prospectus_info):
        public_offer_ratio = prospectus_info.get('public_offer_ratio_pct')
        issuance_ratio = prospectus_info.get('issuance_ratio_pct')
        cornerstone_ratio = prospectus_info.get('cornerstone_offer_ratio_pct') or prospectus_info.get('cornerstone_pct')
        public_offer = ipo.get('public_offer')
        score = 0
        reasons = []
        red_flags = []

        ft = SETTINGS.float_structure
        if _is_num(public_offer_ratio):
            if public_offer_ratio <= ft.public_offer_low_pct:
                score += 4
                reasons.append("公开发售比例低，流通筹码偏少")
            elif public_offer_ratio <= ft.public_offer_mid_pct:
                score += 3
            else:
                score += 1

        if _is_num(issuance_ratio):
            if issuance_ratio <= ft.issuance_low_pct:
                score += 4
                reasons.append("发行比例低，筹码结构偏紧")
            elif issuance_ratio <= ft.issuance_mid_pct:
                score += 3
            else:
                score += 1

        if _is_num(cornerstone_ratio):
            if ft.cornerstone_low_pct <= cornerstone_ratio <= 60:
                score += 4
                reasons.append("基石锁定比例处于健康区间")
            elif 60 < cornerstone_ratio <= ft.cornerstone_high_pct:
                score += 2
                reasons.append("基石锁定高，流通筹码更少但需看结构")
            elif cornerstone_ratio > ft.cornerstone_high_pct:
                red_flags.append("基石锁定超过80%，需警惕结构异常")
            elif cornerstone_ratio < ft.cornerstone_low_pct:
                red_flags.append("基石锁定低于30%，稳定筹码不足")

        if _is_num(public_offer):
            if public_offer <= ft.public_offer_fund_small:
                score += 3
                reasons.append("公开融资额小，少量资金即可影响首日表现")
            elif public_offer <= ft.public_offer_fund_mid:
                score += 2
            elif public_offer <= ft.public_offer_fund_large:
                score += 1

        detail = f"发行{issuance_ratio:.1f}%" if _is_num(issuance_ratio) else "发行--"
        detail += f"；公开{public_offer_ratio:.1f}%" if _is_num(public_offer_ratio) else "；公开--"
        detail += f"；基石{cornerstone_ratio:.1f}%" if _is_num(cornerstone_ratio) else "；基石--"
        vsl = SETTINGS.valuation_score
        label = '筹码紧' if score >= vsl.float_high else ('结构可看' if score >= vsl.float_mid else ('普通' if score > 0 else '缺失'))
        return self._component(score, 15, label, detail, reasons=reasons, red_flags=red_flags)

    def _analyze_cornerstone_structure(self, prospectus_info, text):
        cornerstone = prospectus_info.get('cornerstone_analysis') or {}
        cornerstone_score = cornerstone.get('score')
        if _is_num(cornerstone_score):
            score = round(cornerstone_score / 100 * 15)
            label = cornerstone.get('grade_band') or cornerstone.get('label') or 'V2基石'
            detail = cornerstone.get('combination_summary') or cornerstone.get('recommendation') or '基于基石V2五维模型'
            reasons = []
            if cornerstone.get('dimension_scores'):
                dim_text = []
                for dim in cornerstone.get('dimension_scores', {}).values():
                    dim_text.append(f"{dim.get('label', '--')}{dim.get('score', 0)}/{dim.get('max_score', 0)}")
                if dim_text:
                    reasons.append("五维评分: " + "、".join(dim_text[:5]))
            reasons.extend(cornerstone.get('strengths', [])[:3])
            red_flags = []
            red_flags.extend(cornerstone.get('concerns', [])[:2])
            red_flags.extend(cornerstone.get('red_flags', [])[:3])
            return self._component(score, 15, label, detail, reasons=reasons, red_flags=red_flags)

        rows = cornerstone.get('cornerstone_investors') or prospectus_info.get('cornerstone_investors') or []
        context = " ".join(
            " ".join(str(row.get(key, '')) for key in ('name', 'short_name', 'match_names'))
            for row in rows
        )
        context = f"{context} {text[:60000] if text else ''}"
        sovereign_hits = self._match_capital_names(context, self.SOVEREIGN_CAPITAL)
        top_hits = self._match_capital_names(context, self.TOP_TIER_CAPITAL)
        weak_hits = self._match_capital_names(context, self.WEAK_SIGNAL_CAPITAL)
        industrial_hits = self._industrial_hits(context, prospectus_info.get('sector'))

        score = 0
        reasons = []
        red_flags = []
        if sovereign_hits:
            score += 5
            reasons.append("主权/养老金资本: " + "、".join(sovereign_hits[:3]))
        if top_hits:
            score += min(6, 4 + len(top_hits))
            reasons.append("顶级机构: " + "、".join(top_hits[:4]))
        if industrial_hits:
            score += 4
            reasons.append("产业资本/赛道资本匹配")
        if sovereign_hits and top_hits and industrial_hits:
            score += 1
            reasons.append("接近主权资本+顶级机构+产业资本组合")
        if weak_hits:
            red_flags.append("弱信号基石: " + "、".join(weak_hits[:3]))
            score = max(0, score - 2)
        if cornerstone.get('red_flags'):
            red_flags.extend(cornerstone.get('red_flags', [])[:3])
        if not rows and not cornerstone.get('matched_investors'):
            red_flags.append("未完整提取基石结构")

        detail_parts = []
        if sovereign_hits:
            detail_parts.append(f"主权{len(sovereign_hits)}")
        if top_hits:
            detail_parts.append(f"顶级{len(top_hits)}")
        if industrial_hits:
            detail_parts.append("产业匹配")
        if weak_hits:
            detail_parts.append("弱信号")
        vsl = SETTINGS.valuation_score
        label = '结构强' if score >= vsl.cornerstone_high else ('结构中' if score >= vsl.cornerstone_mid else ('结构弱' if score > 0 else '缺失'))
        return self._component(score, 15, label, '；'.join(detail_parts) or '未识别到强基石组合', reasons=reasons, red_flags=red_flags)

    def _match_capital_names(self, text, groups):
        hits = []
        for name, aliases in groups:
            if _contains_any(text, aliases):
                hits.append(name)
        return hits

    def _industrial_hits(self, context, sector):
        kw_groups = SECTOR_KEYWORDS.get(sector or 'unknown', {})
        return [kw for kw in kw_groups.get('industrial', []) if kw.lower() in context.lower()]

    def _analyze_valuation_framework(self, prospectus_info):
        valuation = prospectus_info.get('valuation') or {}
        peer_comparison = prospectus_info.get('peer_comparison', {}) or {}
        sector = prospectus_info.get('sector', 'unknown')
        market_cap = prospectus_info.get('market_cap_hkd_million')
        revenue = prospectus_info.get('revenue')
        revenue_y1 = prospectus_info.get('revenue_y1')
        net_profit = prospectus_info.get('net_profit')
        adjusted_profit = prospectus_info.get('adjusted_profit_latest_RMB')
        pe = valuation.get('adjusted_pe_ratio') or valuation.get('pe_ratio')
        ps = valuation.get('ps_ratio')
        score = 0
        reasons = []
        red_flags = []

        growth = None
        if _is_num(revenue) and _is_num(revenue_y1) and revenue_y1 > 0:
            growth = (revenue - revenue_y1) / revenue_y1

        vt = SETTINGS.valuation
        vsl = SETTINGS.valuation_score
        pt = SETTINGS.peer_comps

        name = str(prospectus_info.get('extracted_company_name', '') or '').lower()
        is_biotech = (sector == 'healthcare' and ('-b' in name or 'biotech' in name))
        is_unprofitable = _is_num(net_profit) and net_profit <= 0
        is_low_rev_biotech = is_biotech and _is_num(revenue) and revenue < vt.biotech_revenue_small

        abs_score = 0
        if is_low_rev_biotech:
            reasons.append("未盈利 biotech，PE不适用")
            if _is_num(ps):
                abs_score = 2 if ps <= vt.ps_expensive else 1
                reasons.append(f"PS {ps:.1f}x（收入基数极小，仅作参考）")
            mc_rd = valuation.get('market_cap_to_rd_ratio')
            if _is_num(mc_rd):
                if mc_rd <= 20:
                    abs_score += 3
                    reasons.append(f"市值/R&D {mc_rd:.1f}x，研发转化效率看起来合理")
                elif mc_rd <= 50:
                    abs_score += 2
                    reasons.append(f"市值/R&D {mc_rd:.1f}x")
                else:
                    abs_score += 1
                    reasons.append(f"市值/R&D {mc_rd:.1f}x，偏高")
            runway = valuation.get('cash_runway_years')
            if _is_num(runway):
                if runway >= 2:
                    abs_score += 2
                    reasons.append(f"现金runway {runway:.1f}年，运营资金较充裕")
                elif runway >= 1:
                    abs_score += 1
                    reasons.append(f"现金runway {runway:.1f}年")
                else:
                    red_flags.append(f"现金runway仅{runway:.1f}年，融资紧迫性高")
            # 优质管线且临床阶段较 advanced 的 biotech，提升绝对估值评分上限
            rnd = prospectus_info.get('rnd_pipeline', {})
            pipeline_label = rnd.get('pipeline_quality_label', '')
            moat_score = rnd.get('technology_moat_score', 0)
            clinical_stage = rnd.get('latest_clinical_stage', '')
            is_quality_pipeline = pipeline_label == '强' and moat_score >= 7
            is_advanced_clinical = clinical_stage in ('Phase II', 'Phase III', 'Phase 2', 'Phase 3', 'NDA', 'BLA')
            if is_quality_pipeline and is_advanced_clinical:
                abs_score = min(10, abs_score)
            elif is_quality_pipeline:
                abs_score = min(8, abs_score)
            else:
                abs_score = min(6, abs_score)
        elif _is_num(pe) and pe > 0:
            if growth and growth > SETTINGS.valuation_score.peg_growth_min:
                peg = pe / (growth * 100)
                reasons.append(f"PEG约{peg:.2f}")
                pg = SETTINGS.peg
                abs_score = 6 if peg < pg.undervalued else (5 if peg < pg.fair else (4 if peg < pg.high else 2))
            elif pe <= vt.pe_fair:
                abs_score = 6
            elif pe <= vt.pe_high:
                abs_score = 5
            elif pe <= vt.pe_expensive:
                abs_score = 3
            else:
                abs_score = 1
                red_flags.append(f"PE偏高({pe:.1f}x)")
        elif _is_num(ps):
            if ps <= vt.ps_fair:
                abs_score = 6
            elif ps <= vt.ps_high:
                abs_score = 5
            elif ps <= vt.ps_expensive:
                abs_score = 3
            else:
                abs_score = 1
                red_flags.append(f"PS偏高({ps:.1f}x)")
        score += abs_score

        peer_score_val = peer_comparison.get('peer_score', 0)
        peer_valuation_pos = peer_comparison.get('valuation_position', '缺失')
        scarcity = peer_comparison.get('scarcity_score', 0)
        premium = peer_comparison.get('relative_ps_premium_pct')
        raw_quant_count = peer_comparison.get('quantitative_peer_count', 0)
        quant_count = int(raw_quant_count) if _is_num(raw_quant_count) else 0

        is_overpriced = ('明显偏贵' in str(peer_valuation_pos) or
                         'PS辅助(明显偏贵)' in str(peer_valuation_pos))
        is_very_overpriced = _is_num(premium) and float(premium) > pt.premium_overpriced

        # 18C/biotech license upfront 驱动型收入：不对 PS 溢价做硬性扣分
        revenue_quality = (prospectus_info.get('valuation') or {}).get('revenue_quality', 'standard')
        is_license_driven = revenue_quality == 'license_upfront_driven'

        relative_score = 0
        if is_overpriced or is_very_overpriced:
            if is_license_driven and is_low_rev_biotech:
                # license upfront 收入不应与同行经常性收入直接比 PS
                relative_score = min(2, round(peer_score_val / 15 * pt.peer_map_max)) if _is_num(peer_score_val) and peer_score_val > 0 else 1
                reasons.append('收入以授权/里程碑为主，PS溢价不直接可比，仅作提示')
            else:
                relative_score = 0
                red_flags.append('相对同行PS溢价过高' if is_very_overpriced else '同行相对估值: 明显偏贵')
                if is_overpriced:
                    reasons.append(f'相对估值: {peer_valuation_pos}')
        elif _is_num(peer_score_val) and peer_score_val > 0 and quant_count >= 2:
            relative_score = min(pt.peer_map_max, round(peer_score_val / 15 * pt.peer_map_max))
            reasons.append(f"同行对比得分{peer_score_val}/15")
            if peer_valuation_pos and peer_valuation_pos != '缺失':
                reasons.append(f"相对估值: {peer_valuation_pos}")
            if scarcity >= pt.scarcity_high:
                reasons.append(f"稀缺赛道(scarcity={scarcity}/10)提供估值容忍度")
        elif _is_num(peer_score_val) and peer_score_val > 0 and quant_count < 2:
            relative_score = min(2, round(peer_score_val / 15 * pt.peer_map_max))
            reasons.append(f"同行样本不足({quant_count}家定量)，仅作定性参考")
        elif _is_num(ps) and not is_low_rev_biotech:
            if ps <= vt.ps_fair:
                relative_score = pt.peer_fallback_ps_low
            elif ps <= vt.ps_high:
                relative_score = pt.peer_fallback_ps_mid
            elif ps <= vt.ps_expensive:
                relative_score = pt.peer_fallback_ps_high
            else:
                relative_score = 0
            reasons.append('缺少同行估值，按绝对PS口径做初筛')
        else:
            reasons.append('缺少同行估值，按招股书可得口径做初筛')

        score += relative_score

        bonus_score = 0
        if scarcity >= pt.scarcity_high:
            bonus_score += pt.scarcity_high - 4
        elif scarcity >= pt.scarcity_medium:
            bonus_score += pt.scarcity_medium - 3
        elif scarcity >= pt.scarcity_low:
            bonus_score += pt.scarcity_low - 2

        if adjusted_profit and adjusted_profit > 0:
            bonus_score += pt.adjusted_profit_bonus
            reasons.append("有经调整利润口径")
        if sector in ('hardtech', 'healthcare') and _is_num(ps) and ps <= vt.ps_expensive:
            bonus_score = min(vsl.bonus_max, bonus_score + pt.sector_ps_bonus)
            reasons.append("成长/医药科技赛道以PS/管线口径辅助")
        if _is_num(market_cap) and market_cap >= SETTINGS.valuation_score.large_market_cap:
            bonus_score = min(4, bonus_score + 1)
            reasons.append("上市市值较大，具备机构覆盖基础")

        # 18C/biotech 额外加分：优质管线 + 强基石 + 良好现金runway
        if is_low_rev_biotech:
            rnd = prospectus_info.get('rnd_pipeline', {})
            pipeline_label = rnd.get('pipeline_quality_label', '')
            moat_score = rnd.get('technology_moat_score', 0)
            product_count = rnd.get('product_count_pipeline', 0)
            if pipeline_label == '强' and moat_score >= 7 and _is_num(product_count) and product_count >= 3:
                bonus_score += 2
                reasons.append("优质管线且产品数量≥3，平台价值高")
            # 强基石组合给估值容忍度
            ca = prospectus_info.get('cornerstone_analysis') or {}
            if ca.get('score', 0) >= 70 and ca.get('grade_band') in ('强A', 'A+', 'S级'):
                bonus_score += 2
                reasons.append("强基石组合提供估值背书")
            # 良好现金runway
            runway = valuation.get('cash_runway_years')
            if _is_num(runway) and runway >= 2.5:
                bonus_score += 1
                reasons.append("现金runway充足(≥2.5年)，支撑研发周期")
            # license upfront 收入结构
            if is_license_driven:
                bonus_score += 1
                reasons.append("收入含授权/里程碑付款，具备平台变现能力")

        score += bonus_score

        if _is_num(net_profit) and _is_num(revenue) and revenue > 0 and abs(net_profit / revenue) < 0.001:
            if not is_biotech:
                red_flags.append("净利率接近0，疑似利润解析或盈利质量异常")

        detail_parts = []
        if pe and not is_low_rev_biotech:
            detail_parts.append(f"PE {pe:.1f}x")
        elif is_low_rev_biotech:
            detail_parts.append("PE不适用")
        if ps:
            detail_parts.append(f"PS {ps:.1f}x")
        if is_low_rev_biotech:
            if valuation.get('market_cap_to_rd_ratio'):
                detail_parts.append(f"市值/R&D {valuation['market_cap_to_rd_ratio']:.1f}x")
            if valuation.get('cash_runway_years') is not None:
                detail_parts.append(f"现金runway {valuation['cash_runway_years']:.1f}年")
        if peer_comparison.get('subsector'):
            detail_parts.append(f"同行:{peer_comparison['subsector']}")
        if quant_count < 2 and peer_comparison.get('subsector'):
            detail_parts.append("定性参考")
        detail = '；'.join(detail_parts) if detail_parts else 'PE/PS可得口径初筛'

        vsl = SETTINGS.valuation_score
        if is_low_rev_biotech:
            if _is_num(revenue) and revenue > 0 and revenue < vt.biotech_revenue_small:
                label = "PS失真，仅作参考"
            elif is_biotech and valuation.get('latest_clinical_stage'):
                label = "管线阶段估值"
            else:
                label = "PS辅助估值"
        else:
            label = '估值有垫' if score >= vsl.valuation_high else ('估值可看' if score >= vsl.valuation_mid else ('估值压力' if score > 0 else '缺失'))
        return self._component(score, 20, label, detail, reasons=reasons, red_flags=red_flags)

    def _analyze_mainline_beta(self, prospectus_info, text):
        sector = prospectus_info.get('sector', 'unknown')
        lower_text = (text or '').lower()
        keywords = self.MAINLINE_KEYWORDS.get(sector, [])
        hits = [kw for kw in keywords if kw.lower() in lower_text]
        mt = SETTINGS.mainline
        score = mt.hardtech_hit if sector == 'hardtech' and hits else 0
        if sector == 'healthcare':
            score = mt.healthcare_hit if hits else mt.healthcare_no_hit
        elif sector == 'consumer':
            score = mt.consumer_hit if hits else mt.consumer_no_hit
        elif sector == 'hardtech' and not hits:
            score = mt.hardtech_no_hit

        # AI drug delivery / nanomedicine / 18C 等稀缺组合额外加分
        ai_delivery_keywords = [
            'ai drug delivery', 'nanoforge', 'lnp', 'lipid nanoparticle',
            'rna formulation', 'targeted delivery', '18c', 'pre-nda',
            'nanomedicine', 'nanoparticle drug delivery', 'ai-driven drug',
        ]
        ai_hits = sum(1 for kw in ai_delivery_keywords if kw in lower_text)
        if ai_hits >= 3 and sector == 'healthcare':
            score = min(15, score + min(6, ai_hits))
            hits.extend([f'AI_delivery_{i}' for i in range(ai_hits)])

        detail = f"{sector}；关键词{len(hits)}个；需外部行情确认"
        label = '主线候选' if score >= mt.high_threshold else ('观察赛道' if score >= mt.mid_threshold else '非主线')
        return self._component(score, 15, label, detail, confidence='keyword_only', reasons=['未接入板块涨幅/成交/南向资金，主线判断为低置信度'])

    def _analyze_stock_connect_path(self, prospectus_info, text):
        market_cap = prospectus_info.get('market_cap_hkd_million')
        code_text = (text or '')[:120000].lower()
        is_w = '-w' in code_text or 'weighted voting rights' in code_text
        has_a_shares = bool(re.search(r'\ba shares?\b|\ba-share\b', code_text, re.IGNORECASE))
        has_h_shares = bool(re.search(r'\bh shares?\b|\bh-share\b', code_text, re.IGNORECASE))
        is_ah = has_a_shares and has_h_shares
        is_ah = is_ah or bool(re.search(r'dual\s+list|a\s*\+\s*h|a股.*h股|h股.*a股|ah上市|a shares?\s+and\s+h shares?', code_text, re.IGNORECASE))
        score = 0
        reasons = []
        sc = SETTINGS.stock_connect

        if is_ah:
            score, label = sc.score_ah, 'AH直通候选'
            reasons.append("疑似AH结构，需核实稳价期和港股通生效规则")
        elif _is_num(market_cap) and market_cap >= sc.large_cap:
            score, label = sc.score_large, '大型快速候选'
            reasons.append("市值接近大型股特别快速纳入观察范围")
        elif _is_num(market_cap) and market_cap >= sc.fast_track:
            score, label = sc.score_fast, '快速观察'
            reasons.append("市值接近季度快速纳入观察范围")
        elif _is_num(market_cap) and market_cap >= sc.regular:
            score, label = sc.score_regular, '半年观察'
            reasons.append("市值达到常规港股通观察区间")
        elif _is_num(market_cap) and market_cap >= sc.small_cap:
            score, label = sc.score_small, '小型观察'
            reasons.append("市值接近恒生小型股观察区间")
        else:
            label = '暂不足'
            reasons.append("市值或规则信息不足")

        if is_w and score > 0:
            score = max(0, score - 2)
            reasons.append("-W公司需满足额外上市时间、市值和成交额条件")

        detail = f"市值HK${market_cap/100:.1f}亿" if _is_num(market_cap) else "市值缺失"
        if is_w:
            detail += "；-W额外门槛"
        if is_ah:
            detail += "；AH候选"
        return self._component(score, 10, label, detail, confidence='rule_based_without_index_data', reasons=reasons)

    def _analyze_data_quality(self, prospectus_info):
        score = 5
        red_flags = []
        reasons = []
        revenue = prospectus_info.get('revenue')
        revenue_y1 = prospectus_info.get('revenue_y1')
        net_profit = prospectus_info.get('net_profit')
        market_cap = prospectus_info.get('market_cap_hkd_million')
        extraction_confidence = prospectus_info.get('financial_extract_confidence')
        parser_flags = prospectus_info.get('financial_data_quality_flags') or []
        sector = prospectus_info.get('sector', 'unknown')
        name = str(prospectus_info.get('extracted_company_name', '') or '').lower()
        is_biotech = (sector == 'healthcare' and ('-b' in name or 'biotech' in name))
        profitable = prospectus_info.get('profitable')
        # 早期未商业化公司（18A/18C）的爆发增长和巨额亏损属于正常现象
        is_early_stage = _is_num(revenue_y1) and revenue_y1 < 50 and profitable is False

        if parser_flags:
            for flag in parser_flags:
                if (is_biotech or is_early_stage) and any(k in str(flag) for k in ['净利', '利润', '单位', '差异']):
                    continue
                red_flags.append(flag)
                score -= 1
        if extraction_confidence == 'needs_review':
            red_flags.append("财务抽取结果需人工复核")
            score -= 2

        vsl = SETTINGS.valuation_score
        if _is_num(revenue) and _is_num(revenue_y1) and revenue > 0 and revenue_y1 > 0:
            growth = (revenue - revenue_y1) / revenue_y1
            # 早期未商业化公司收入爆发增长属于正常现象，豁免异常检测
            if abs(growth) > vsl.growth_extreme and not is_early_stage:
                red_flags.append(f"收入同比异常({growth*100:.1f}%)，需核对招股书解释")
                score -= 2
            ratio = max(revenue, revenue_y1) / max(min(revenue, revenue_y1), 1e-9)
            if ratio > vsl.revenue_ratio_extreme and not is_early_stage:
                red_flags.append("收入两年口径差异超过10倍，疑似单位或表格错位")
                score -= 2
        else:
            red_flags.append("缺少可比收入数据")
            score -= 1

        if _is_num(net_profit) and _is_num(revenue) and revenue > 0:
            net_margin = net_profit / revenue
            if abs(net_margin) < vsl.net_margin_near_zero:
                red_flags.append("净利率接近0，需核对利润提取")
                score -= 2
            if abs(net_margin) > vsl.net_margin_extreme:
                if is_biotech or is_early_stage:
                    reasons.append("创新药临床阶段亏损大于收入，商业化风险提示")
                else:
                    red_flags.append("净利率超过100%，疑似利润或收入口径异常")
                    score -= 2

        if _is_num(market_cap) and _is_num(net_profit) and net_profit > 0:
            pe = market_cap / net_profit
            if pe > vsl.pe_extreme:
                red_flags.append(f"PE极端({pe:.0f}x)，需核对净利润单位")
                score -= 2

        if not red_flags:
            reasons.append("核心财务口径未发现明显异常")
        label = '可信' if score >= vsl.data_quality_high else ('需复核' if score >= vsl.data_quality_mid else '高风险')
        detail = '；'.join(red_flags[:2]) if red_flags else '财务数据通过基础异常检查'
        return self._component(score, 5, label, detail, reasons=reasons, red_flags=red_flags)

    def _build_hold_strategy(self, score, components, red_flags):
        mainline_score = components.get('mainline_beta', {}).get('score', 0)
        stock_connect_score = components.get('stock_connect_path', {}).get('score', 0)
        valuation_score = components.get('valuation_framework', {}).get('score', 0)
        real_money_score = components.get('real_money', {}).get('score', 0)
        data_flags = components.get('data_quality', {}).get('red_flags', [])

        if data_flags:
            return "数据风险优先，先核对财务口径，再决定申购和持有。"
        if score >= 70 and mainline_score >= 7 and stock_connect_score >= 6:
            return "申购倾向偏积极，若上市后趋势强且入通路径清晰，可观察持有到机构覆盖或港股通节点。"
        if real_money_score >= 14 and valuation_score >= 10:
            return "真实资金和估值安全垫较好，可考虑首日后分批观察，不以单一倍数决定卖点。"
        if red_flags:
            return "红旗较多，偏向谨慎试水或只做短线，不做自动持有判断。"
        return "信号中性，上市后重点观察成交、暗盘和首日承接，按分批止盈思路处理。"
