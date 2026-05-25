"""交易信号拆解分析器 — SignalComponentAnalyzer"""

import re

from .utils import _is_num, _contains_any, SECTOR_KEYWORDS
from .settings import SETTINGS
from .cornerstone import get_sovereign_capital, get_top_tier_capital, get_weak_signal_capital
from .industry_router import classify_company
from .market_heat import LiveMarketHeatAnalyzer
from .float_dryness import FloatDrynessAnalyzer


def _score_from_board_heat(label: str) -> int:
    return {
        "强势": 6,
        "热门": 4,
        "温和": 2,
        "冷清": 0,
        "缺失": 0,
    }.get(label, 0)


_A_SHARE_RE = re.compile(r'\ba shares?\b|\ba-share\b', re.IGNORECASE)
_H_SHARE_RE = re.compile(r'\bh shares?\b|\bh-share\b', re.IGNORECASE)
_AH_DUAL_RE = re.compile(r'dual\s+list|a\s*\+\s*h|a股.*h股|h股.*a股|ah上市|a shares?\s+and\s+h shares?', re.IGNORECASE)


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
            'float_dryness': self._analyze_float_dryness(ipo, prospectus_info, text),
            'cornerstone_structure': self._analyze_cornerstone_structure(prospectus_info, text),
            'valuation_framework': self._analyze_valuation_framework(prospectus_info, text),
            'mainline_beta': self._analyze_mainline_beta(ipo, prospectus_info, text),
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

        live_heat = components['mainline_beta'].get('live_market_heat') or {}
        live_heat_label = live_heat.get('sector_heat_label', '缺失')
        live_heat_score = live_heat.get('sector_heat_score', 0) or 0
        live_flow_label = live_heat.get('sector_flow_label', '缺失')
        live_flow_score = live_heat.get('sector_flow_score', 0) or 0
        live_momentum_label = live_heat.get('sector_momentum_label', '缺失')
        live_momentum_score = live_heat.get('sector_momentum_score', 0) or 0
        live_board_label = live_heat.get('sector_board_label', '缺失')
        live_board_heat_label = live_heat.get('sector_board_heat_label', '缺失')

        vm = components['valuation_framework']
        valuation_label = vm.get('label', '')
        profile = classify_company(prospectus_info, text)
        is_biotech_unprofitable = profile.is_biotech and profile.is_unprofitable
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
                'score': components['real_money'].get('score', 0),
                'max_score': components['real_money'].get('max_score', 20),
                'label': components['real_money'].get('label', ''),
                'strength': self._strength(components['real_money'].get('score', 0), 20),
                'detail': components['real_money'].get('detail', ''),
            },
            'float_structure': {
                'score': components['float_structure'].get('score', 0),
                'max_score': components['float_structure'].get('max_score', 15),
                'label': components['float_structure'].get('label', ''),
                'strength': self._strength(components['float_structure'].get('score', 0), 15),
                'detail': components['float_structure'].get('detail', ''),
                'float_signal': components['float_structure'].get('label', ''),
            },
            'float_dryness': {
                'score': components['float_dryness'].get('score', 0),
                'max_score': components['float_dryness'].get('max_score', 20),
                'label': components['float_dryness'].get('label', ''),
                'strength': components['float_dryness'].get('strength', '—'),
                'detail': components['float_dryness'].get('detail', ''),
                'mechanism_b': components['float_dryness'].get('mechanism_b', False),
                'squeeze_risk_label': components['float_dryness'].get('squeeze_risk_label', '低'),
                'squeeze_risk_score': components['float_dryness'].get('squeeze_risk_score', 0),
                'float_signals': components['float_dryness'].get('float_signals', []),
            },
            'cornerstone_quality': {
                'score': components['cornerstone_structure'].get('score', 0),
                'max_score': components['cornerstone_structure'].get('max_score', 15),
                'label': components['cornerstone_structure'].get('label', ''),
                'strength': self._strength(components['cornerstone_structure'].get('score', 0), 15),
                'detail': components['cornerstone_structure'].get('detail', ''),
            },
            'valuation_reading': {
                'score': vm.get('score', 0),
                'max_score': vm.get('max_score', 10),
                'label': valuation_label,
                'strength': vm_strength,
                'detail': vm.get('detail', ''),
            },
            'market_heat': {
                'score': live_heat_score,
                'max_score': 15,
                'label': live_heat_label,
                'strength': self._strength(live_heat_score, 15, high_ratio=0.7, mid_ratio=0.4),
                'detail': live_heat.get('sector_heat_detail', '') or components['mainline_beta'].get('detail', ''),
            },
            'sector_flow': {
                'score': live_flow_score,
                'max_score': 8,
                'label': live_flow_label,
                'strength': self._strength(live_flow_score, 8, high_ratio=0.7, mid_ratio=0.4),
                'detail': live_heat.get('sector_flow_detail', ''),
            },
            'sector_momentum': {
                'score': live_momentum_score,
                'max_score': 8,
                'label': live_momentum_label,
                'strength': self._strength(live_momentum_score, 8, high_ratio=0.7, mid_ratio=0.4),
                'detail': live_heat.get('sector_momentum_detail', ''),
            },
            'sector_board': {
                'score': _score_from_board_heat(live_board_heat_label),
                'max_score': 8,
                'label': live_board_label,
                'strength': self._strength(_score_from_board_heat(live_board_heat_label), 8, high_ratio=0.7, mid_ratio=0.4),
                'detail': live_heat.get('sector_board_detail', ''),
            },
            'theme_bonus': {
                'score': components['mainline_beta'].get('score', 0),
                'max_score': components['mainline_beta'].get('max_score', 15),
                'label': components['mainline_beta'].get('label', ''),
                'strength': self._strength(components['mainline_beta'].get('score', 0), 15, high_ratio=0.67, mid_ratio=0.33),
                'detail': components['mainline_beta'].get('detail', ''),
            },
            'liquidity_bonus': {
                'score': components['stock_connect_path'].get('score', 0),
                'max_score': components['stock_connect_path'].get('max_score', 10),
                'label': components['stock_connect_path'].get('label', ''),
                'strength': self._strength(components['stock_connect_path'].get('score', 0), 10, high_ratio=0.7, mid_ratio=0.4),
                'detail': components['stock_connect_path'].get('detail', ''),
            },
            'data_confidence': {
                'score': components['data_quality'].get('score', 0),
                'max_score': components['data_quality'].get('max_score', 5),
                'label': components['data_quality'].get('label', ''),
                'strength': self._data_confidence_level(components['data_quality'].get('score', 0), 5),
                'detail': components['data_quality'].get('detail', ''),
                'red_flags': components['data_quality'].get('red_flags', []),
            },
            'valuation_driver': None,
        }

        vd = self._analyze_valuation_driver(ipo, prospectus_info)
        if vd:
            vd['score'] = vd.get('score', 0)
            vd['max_score'] = vd.get('max_score', 10)
        signal_breakdown['valuation_driver'] = vd

        return {
            'signal_breakdown': signal_breakdown,
            'score': int(self._clamp(score, 0, 100)),
            'label': legacy_label,
            'components': components,
            'red_flags': red_flags,
            'watch_items': watch_items[:8],
            'hold_strategy': self._build_hold_strategy(score, components, red_flags),
            'confidence': confidence,
            'live_market_heat': live_heat,
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
        cornerstone_pct_text = prospectus_info.get('cornerstone_pct')
        cornerstone_pct_table = prospectus_info.get('cornerstone_offer_ratio_pct')
        if _is_num(cornerstone_pct_text) and _is_num(cornerstone_pct_table) and abs(cornerstone_pct_text - cornerstone_pct_table) > 10:
            cornerstone_ratio = cornerstone_pct_text
        else:
            cornerstone_ratio = cornerstone_pct_table or cornerstone_pct_text
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

        ct = SETTINGS.cornerstone  # 使用统一的基石占比阈值
        if _is_num(cornerstone_ratio):
            if ct.pct_healthy_low <= cornerstone_ratio <= ct.pct_healthy_high:
                score += 4
                reasons.append(f"基石锁定比例处于健康区间({ct.pct_healthy_low:.0f}%-{ct.pct_healthy_high:.0f}%)")
            elif ct.pct_healthy_low - 10 <= cornerstone_ratio < ct.pct_healthy_low:
                score += 3
                reasons.append(f"基石锁定比例适中({ct.pct_healthy_low - 10:.0f}%-{ct.pct_healthy_low:.0f}%)")
            elif ct.pct_healthy_low - 20 <= cornerstone_ratio < ct.pct_healthy_low - 10:
                score += 2
                reasons.append(f"基石锁定比例偏低({ct.pct_healthy_low - 20:.0f}%-{ct.pct_healthy_low - 10:.0f}%)")
            elif ct.pct_healthy_high < cornerstone_ratio <= ct.pct_acceptable_high:
                score += 2
                reasons.append("基石锁定高，流通筹码更少但需看结构")
            elif cornerstone_ratio > ct.pct_acceptable_high:
                red_flags.append("基石锁定超过80%，需警惕结构异常")
            elif cornerstone_ratio < ct.pct_healthy_low - 20:
                red_flags.append(f"基石锁定低于{ct.pct_healthy_low - 20:.0f}%，稳定筹码不足")

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

    def _analyze_float_dryness(self, ipo, prospectus_info, text):
        """流通盘干涸度分析 — 综合 Mechanism B / 流通盘 / 基石锁定 / 公开发售 等因素。"""
        fd = FloatDrynessAnalyzer().analyze(prospectus_info, text or "", ipo)
        dryness_label = fd.get('dryness_label', '缺失')
        dryness_score = fd.get('dryness_score', 0) or 0
        squeeze_label = fd.get('squeeze_risk_label', '低')
        squeeze_score = fd.get('squeeze_risk_score', 0) or 0
        detail_parts = []
        if fd.get('mechanism_b'):
            detail_parts.append(" 机制B")
        if fd.get('float_millions') is not None:
            detail_parts.append(f"流通盘{fd['float_millions']:.1f}亿")
        if fd.get('cornerstone_lockup_pct') is not None:
            detail_parts.append(f"基石锁定{fd['cornerstone_lockup_pct']:.0f}%")
        if fd.get('public_offer_lots') is not None:
            detail_parts.append(f"公开发售{int(fd['public_offer_lots'])}手")
        if fd.get('float_signals'):
            detail_parts.extend(fd['float_signals'][:2])
        detail = '；'.join(detail_parts) if detail_parts else '数据不足'
        return {
            'score': dryness_score,
            'max_score': 20,
            'label': f"{dryness_label}/{squeeze_label}",
            'strength': self._strength(dryness_score, 20),
            'detail': detail,
            'mechanism_b': fd.get('mechanism_b', False),
            'squeeze_risk_label': squeeze_label,
            'squeeze_risk_score': squeeze_score,
            'float_signals': fd.get('float_signals', []),
        }

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

            # V2 模型已通过 red_flags 和 score_cap_severe_red_flags 扣分，此处不再二次惩罚
            return self._component(score, 15, label, detail, reasons=reasons, red_flags=red_flags)

        # --- Fallback 路径：无 V2 评分时使用关键词匹配 ---
        # 注意：只匹配 cornerstone_section 来源的投资者，排除 pre-IPO 章节
        rows = cornerstone.get('cornerstone_investors') or prospectus_info.get('cornerstone_investors') or []
        matched_from_section = [r for r in rows if r.get('source') == 'cornerstone_section']
        context = " ".join(
            " ".join(str(row.get(key, '')) for key in ('name', 'short_name', 'match_names'))
            for row in matched_from_section
        )
        # 补充招股书全文，但只取基石章节附近文本（粗略估计前8万字）
        fallback_text = str(prospectus_info.get('_extracted_text', '') or text or '')
        context = f"{context} {fallback_text[:80000]}"
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

    def _analyze_valuation_framework(self, prospectus_info, text=''):
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
        growth_for_peg = None
        if _is_num(revenue) and _is_num(revenue_y1) and revenue_y1 > 0:
            growth = (revenue - revenue_y1) / revenue_y1
        net_profit_y1 = prospectus_info.get('net_profit_y1')
        if _is_num(net_profit) and _is_num(net_profit_y1) and net_profit_y1 != 0:
            growth_for_peg = (net_profit - net_profit_y1) / abs(net_profit_y1)
        elif growth is not None:
            growth_for_peg = growth

        vt = SETTINGS.valuation
        vsl = SETTINGS.valuation_score
        pt = SETTINGS.peer_comps

        profile = classify_company(prospectus_info, text)
        is_biotech = profile.is_biotech
        is_low_rev_biotech = profile.is_low_revenue_biotech

        # 行业感知 PS 阈值（与 _valuation.py 保持一致）
        is_growth_sector = sector in ('hardtech', 'saas', 'software', 'technology')
        if is_growth_sector:
            ps_expensive = vt.ps_expensive_saas
            ps_high = vt.ps_high_saas
            ps_fair = vt.ps_fair_saas
        else:
            ps_expensive = vt.ps_expensive
            ps_high = vt.ps_high
            ps_fair = vt.ps_fair

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
            # 上限与 vsl.abs_max 对齐，避免管线质量直接覆盖绝对估值逻辑
            if is_quality_pipeline and is_advanced_clinical:
                abs_score = min(vsl.abs_max, abs_score)
            elif is_quality_pipeline:
                abs_score = min(vsl.abs_max - 1, abs_score)
            else:
                abs_score = min(vsl.abs_max - 2, abs_score)
        elif _is_num(pe) and pe > 0:
            if growth_for_peg is not None and abs(growth_for_peg) > SETTINGS.valuation_score.peg_growth_min:
                peg = pe / (growth_for_peg * 100)
                reasons.append(f"PEG约{peg:.2f}")
                if growth_for_peg == growth and _is_num(net_profit) and _is_num(net_profit_y1) and net_profit_y1 != 0:
                    reasons.append("使用营收增速替代盈利增速计算PEG")
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
            if ps <= ps_fair:
                abs_score = 6
            elif ps <= ps_high:
                abs_score = 5
            elif ps <= ps_expensive:
                abs_score = 3
            else:
                abs_score = 1
                red_flags.append(f"PS偏高({ps:.1f}x)")
        score += abs_score

        peer_score_val = peer_comparison.get('peer_score', 0)
        peer_valuation_pos = peer_comparison.get('valuation_position', '缺失')
        scarcity = peer_comparison.get('scarcity_score', 0)
        premium = peer_comparison.get('relative_weighted_ps_premium_pct')
        if premium is None:
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
            if ps <= ps_fair:
                relative_score = pt.peer_fallback_ps_low
            elif ps <= ps_high:
                relative_score = pt.peer_fallback_ps_mid
            elif ps <= ps_expensive:
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

        if not is_biotech and _is_num(pe) and pe > 0:
            valuation_cap = None
            cap_reason = None
            if pe > SETTINGS.valuation_score.pe_extreme:
                valuation_cap = 8
                cap_reason = f"PE极高({pe:.1f}x)，相对PS低也不能视为便宜"
            elif pe > 60:
                valuation_cap = 10
                cap_reason = f"PE偏高({pe:.1f}x)"
            elif pe > vt.pe_expensive:
                valuation_cap = 13
                cap_reason = f"PE高于港股小盘IPO贵价阈值({pe:.1f}x)"

            net_margin = None
            if _is_num(net_profit) and _is_num(revenue) and revenue > 0:
                net_margin = net_profit / revenue * 100
            if net_margin is not None and net_margin < 5 and pe > vt.pe_expensive:
                valuation_cap = min(valuation_cap or 20, 8)
                cap_reason = f"净利率仅{net_margin:.1f}%且PE {pe:.1f}x，盈利质量不足以支撑高估值"

            net_profit_y1 = prospectus_info.get('net_profit_y1')
            if _is_num(net_profit) and _is_num(net_profit_y1) and abs(net_profit_y1) > 1e-9:
                profit_growth = (net_profit - net_profit_y1) / abs(net_profit_y1)
                if profit_growth < -0.30 and pe > vt.pe_high:
                    valuation_cap = min(valuation_cap or 20, 9)
                    cap_reason = f"净利润同比下滑{abs(profit_growth)*100:.1f}%且PE {pe:.1f}x"

            if valuation_cap is not None and score > valuation_cap:
                score = valuation_cap
                if cap_reason:
                    red_flags.append(cap_reason)
                    reasons.append(f"估值分封顶{valuation_cap}/20: {cap_reason}")

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
        if peer_comparison.get('weighted_peer_ps'):
            detail_parts.append(f"加权同行PS {peer_comparison['weighted_peer_ps']:.1f}x")
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

    def _analyze_mainline_beta(self, ipo, prospectus_info, text):
        sector = prospectus_info.get('sector', 'unknown')
        peer_comparison = prospectus_info.get('peer_comparison') or {}
        business_breakdown = prospectus_info.get('business_breakdown') or {}
        rnd_pipeline = prospectus_info.get('rnd_pipeline') or {}
        subsector = peer_comparison.get('subsector') or ''
        business_model_label = business_breakdown.get('business_model_label') or ''
        hardtech_moat_label = rnd_pipeline.get('hardtech_moat_label') or rnd_pipeline.get('pipeline_quality_label') or ''
        market_heat = ipo.get('market_heat', '')
        over_sub_ratio = ipo.get('over_sub_ratio')
        forecast_over_sub_ratio = ipo.get('forecast_over_sub_ratio')
        actual_over_sub_ratio = ipo.get('actual_over_sub_ratio')
        live_heat = ipo.get('live_market_heat') or LiveMarketHeatAnalyzer().analyze(prospectus_info, text, peer_comparison=peer_comparison)
        live_heat_label = live_heat.get('sector_heat_label', '缺失')
        live_heat_score = live_heat.get('sector_heat_score', 0) or 0
        live_flow_label = live_heat.get('sector_flow_label', '缺失')
        live_momentum_label = live_heat.get('sector_momentum_label', '缺失')
        live_board_label = live_heat.get('sector_board_label', '缺失')
        live_board_heat_label = live_heat.get('sector_board_heat_label', '缺失')
        live_board_flow_label = live_heat.get('sector_board_flow_label', '缺失')
        live_board_change_pct = live_heat.get('sector_board_change_pct')
        lower_text = (text or '').lower()
        keywords = list(self.MAINLINE_KEYWORDS.get(sector, []))
        if subsector == 'robotics_factory_automation':
            keywords.extend([
                'robot body', 'robot bodies', 'robotic solution', 'robotic solutions',
                'industrial robot', 'automation system', 'scara', 'six-axis', 'parallel robot',
                'agv', 'amr', 'wafer handling', 'factory automation', '机器人本体', '机器人解决方案',
                '并联机器人', '移动机器人', '六轴机器人', '晶圆搬运', '控制器', '视觉系统',
            ])
        elif subsector == 'ai_drug_delivery_nanomedicine':
            keywords.extend([
                'ai drug delivery', 'nanomedicine', 'nanoparticle', 'lipid nanoparticle',
                'lnp', 'rna formulation', 'targeted delivery', 'drug delivery platform',
                '18c', 'ai-driven drug',
            ])
        elif subsector == 'robotics_visual_perception':
            keywords.extend([
                'visual perception', 'machine vision', 'vision system', 'robot vision',
                '3d vision', '视觉', '机器视觉',
            ])

        hits = []
        for kw in keywords:
            if kw.lower() in lower_text and kw not in hits:
                hits.append(kw)

        mt = SETTINGS.mainline
        score = mt.hardtech_hit if sector == 'hardtech' and hits else 0
        if sector == 'healthcare':
            score = mt.healthcare_hit if hits else mt.healthcare_no_hit
        elif sector == 'consumer':
            score = mt.consumer_hit if hits else mt.consumer_no_hit
        elif sector == 'hardtech' and not hits:
            score = mt.hardtech_no_hit

        market_bonus = 0
        if market_heat == '极热':
            market_bonus = 4
        elif market_heat == '热门':
            market_bonus = 3
        elif market_heat == '温和':
            market_bonus = 1
        elif _is_num(over_sub_ratio):
            if over_sub_ratio >= 100:
                market_bonus = 3
            elif over_sub_ratio >= 20:
                market_bonus = 2
            elif over_sub_ratio >= 5:
                market_bonus = 1

        if market_bonus and hits:
            score += market_bonus
        elif market_bonus and sector in ('healthcare', 'hardtech') and subsector:
            score += max(1, market_bonus - 1)

        live_market_bonus = 0
        if live_heat_label == '极热':
            live_market_bonus = 4
        elif live_heat_label == '热门':
            live_market_bonus = 3
        elif live_heat_label == '温和':
            live_market_bonus = 1
        if live_market_bonus:
            score += live_market_bonus
        if live_flow_label == '放量':
            score += 2
        elif live_flow_label == '活跃':
            score += 1
        if live_momentum_label == '强势':
            score += 2
        elif live_momentum_label == '上行':
            score += 1
        if live_board_heat_label == '强势':
            score += 2
        elif live_board_heat_label == '热门':
            score += 1

        if sector == 'hardtech':
            if business_model_label in ('机器人本体为主', '机器人解决方案为主'):
                score += 1
            if hardtech_moat_label in ('强', '中'):
                score += 1
        elif sector == 'healthcare' and subsector:
            score += 1

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

        detail_parts = [sector]
        if subsector:
            detail_parts.append(f"细分:{subsector.replace('_', ' / ')}")
        detail_parts.append(f"关键词{len(hits)}个")
        if market_heat:
            detail_parts.append(f"热度:{market_heat}")
        elif _is_num(over_sub_ratio):
            detail_parts.append(f"超购:{over_sub_ratio:.1f}x")
        if _is_num(forecast_over_sub_ratio):
            detail_parts.append(f"预测:{forecast_over_sub_ratio:.1f}x")
        if _is_num(actual_over_sub_ratio):
            detail_parts.append(f"实际:{actual_over_sub_ratio:.1f}x")
        if market_bonus:
            detail_parts.append(f"热度加成{market_bonus}")
        if live_heat_label and live_heat_label != '缺失':
            detail_parts.append(f"同行热度:{live_heat_label}")
            if live_heat.get('sector_peer_count'):
                detail_parts.append(f"样本{live_heat['sector_peer_count']}家")
            if _is_num(live_heat.get('sector_index_change_pct')):
                detail_parts.append(f"恒指{live_heat['sector_index_change_pct']:+.2f}%")
            if live_momentum_label != '缺失':
                detail_parts.append(f"动能:{live_momentum_label}")
            if live_board_label != '缺失':
                detail_parts.append(f"板块:{live_board_label}")
            if live_heat_score:
                detail_parts.append(f"实时分{live_heat_score}")
            if live_flow_label != '缺失':
                detail_parts.append(f"资金流:{live_flow_label}")
            if live_board_heat_label != '缺失':
                detail_parts.append(f"板块热度:{live_board_heat_label}")
            if live_board_flow_label != '缺失':
                detail_parts.append(f"板块流:{live_board_flow_label}")
            if _is_num(live_board_change_pct):
                detail_parts.append(f"板块涨跌{live_board_change_pct:+.2f}%")
        if business_model_label:
            detail_parts.append(f"业务:{business_model_label}")
        if hardtech_moat_label:
            detail_parts.append(f"护城河:{hardtech_moat_label}")

        reasons = []
        red_flags = []
        if hits:
            reasons.append("赛道关键词与文本匹配")
        if market_heat:
            reasons.append(f"招股热度为{market_heat}")
        elif _is_num(over_sub_ratio):
            reasons.append(f"超购倍数约{over_sub_ratio:.1f}x")
        else:
            reasons.append("未获取公开热度数据，按文本与赛道特征判断")
        if live_heat_label != '缺失':
            reasons.append(f"可比公司实时热度为{live_heat_label}")
            if live_heat.get('sector_peer_median_change_pct') is not None:
                reasons.append(f"同行中位涨跌约{live_heat['sector_peer_median_change_pct']:+.2f}%")
            if live_momentum_label != '缺失':
                reasons.append(f"板块动能为{live_momentum_label}")
            if live_flow_label != '缺失':
                reasons.append(f"板块资金流为{live_flow_label}")
            if live_board_label != '缺失':
                reasons.append(f"板块指数为{live_board_label}")
            if live_board_heat_label != '缺失':
                reasons.append(f"板块指数热度为{live_board_heat_label}")
            if live_board_flow_label != '缺失':
                reasons.append(f"板块指数资金流为{live_board_flow_label}")
        if subsector:
            reasons.append(f"细分赛道:{subsector.replace('_', ' / ')}")
        if business_model_label in ('机器人本体为主', '机器人解决方案为主'):
            reasons.append("业务模型与主线方向一致")
        if hardtech_moat_label in ('强', '中'):
            reasons.append("研发/订单/专利信号支持赛道持续性")

        if not hits:
            red_flags.append("文本中未识别出明显主线词，需谨慎")
        if sector == 'unknown':
            red_flags.append("行业未明确，主线判断依赖较弱")

        if market_heat or _is_num(over_sub_ratio) or _is_num(forecast_over_sub_ratio) or _is_num(actual_over_sub_ratio) or live_heat_label != '缺失':
            confidence = 'market_signal'
        else:
            confidence = 'keyword_only'

        score = min(15, score)
        label = '主线候选' if score >= mt.high_threshold and (hits or market_heat in ('极热', '热门') or market_bonus >= 3) else ('观察赛道' if score >= mt.mid_threshold else '非主线')
        component = self._component(score, 15, label, '；'.join(detail_parts), confidence=confidence, reasons=reasons, red_flags=red_flags)
        component['live_market_heat'] = live_heat
        return component

    def _analyze_stock_connect_path(self, prospectus_info, text):
        market_cap = prospectus_info.get('market_cap_hkd_million')
        listing_date_str = prospectus_info.get('listing_date')
        code_text = (text or '')[:120000].lower()
        is_w = '-w' in code_text or 'weighted voting rights' in code_text
        is_18c = prospectus_info.get('is_chapter_18c', False)
        has_a_shares = bool(_A_SHARE_RE.search(code_text))
        has_h_shares = bool(_H_SHARE_RE.search(code_text))
        is_ah = has_a_shares and has_h_shares
        is_ah = is_ah or bool(_AH_DUAL_RE.search(code_text))
        score = 0
        reasons = []
        sc = SETTINGS.stock_connect

        # 上市时间检查
        listing_months = None
        listing_days = None
        if listing_date_str:
            try:
                from datetime import datetime, date
                ld_text = str(listing_date_str).strip()
                if 'T' in ld_text:
                    ld_text = ld_text.split('T', 1)[0]
                listing_dt = datetime.strptime(ld_text, '%Y-%m-%d').date()
                today = date.today()
                diff_days = (today - listing_dt).days
                listing_days = max(0, diff_days)
                listing_months = max(0, diff_days / 30.0)
            except Exception:
                pass

        if is_ah:
            score, label = sc.score_ah, 'AH直通候选'
            reasons.append("AH结构H股享有绿色通道，豁免市值和恒指成分股要求")
            if listing_months is not None and listing_months < 1:
                reasons.append(f"上市仅{listing_days}天，需满10个交易日后生效")
        elif _is_num(market_cap) and market_cap >= sc.large_cap:
            score, label = sc.score_large, '大型快速候选'
            reasons.append("市值达大型股水平，入通概率较高")
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
            reasons.append("市值未达到港股通观察区间")

        # -W公司惩罚
        if is_w and score > 0:
            score = max(0, score - 2)
            reasons.append("-W公司需满足额外上市时间、市值和成交额条件")

        # 18C特专科技公司入通限制
        if is_18c and score > 0 and not is_ah:
            score = max(0, score - 1)
            reasons.append("18C特专科技公司入通需额外观察流动性和市值稳定性")

        # 上市时间不足惩罚（非AH股）
        if not is_ah and listing_days is not None and listing_days < 30:
            if score > 0:
                score = max(0, score - 2)
                reasons.append(f"上市仅{listing_days}天，快速纳入需满1个日历月")

        # --- 构建详细港股通路径说明 ---
        detail_parts = []
        detail_parts.append("入通需恒生综指成分股")

        if listing_days is not None:
            if listing_days < 30:
                detail_parts.append(f"上市{listing_days}天")
            else:
                detail_parts.append(f"上市{int(listing_months)}月")

        if _is_num(market_cap):
            # 阈值列表：(百万港元, 中文描述, 简称)
            thresholds = [
                (sc.large_cap, '大型快速纳入', '大型'),
                (sc.fast_track, '季度快速纳入', '快速'),
                (sc.regular, '常规观察', '常规'),
                (sc.small_cap, '小型股观察', '小型股'),
            ]
            # 找到当前达到的最高门槛和下一个更高门槛
            reached = None
            next_level = None
            for th, desc, short in thresholds:
                if market_cap >= th:
                    reached = (th, desc, short)
                    break
                next_level = (th, desc, short)

            cap_hkd = market_cap / 100  # 转为亿港元
            detail_parts.append(f"市值HK${cap_hkd:.1f}亿")

            if is_ah:
                detail_parts.append("AH直通候选")
            elif reached:
                detail_parts.append(f"已达{reached[1]}门槛（{reached[0]/100:.0f}亿）")
                if next_level:
                    gap = next_level[0] - market_cap
                    gap_pct = gap / market_cap * 100
                    detail_parts.append(f"距{next_level[1]}（{next_level[0]/100:.0f}亿）还需涨{gap/100:.1f}亿（+{gap_pct:.1f}%）")
                else:
                    detail_parts.append("已达最高港股通门槛")
                # 小型股特别提示
                if reached[0] == sc.small_cap:
                    detail_parts.append("小型股需12个月平均市值≥50亿港元")
            elif next_level:
                gap = next_level[0] - market_cap
                gap_pct = gap / market_cap * 100
                detail_parts.append(f"距入通（{next_level[1]}，{next_level[0]/100:.0f}亿）还需涨{gap/100:.1f}亿（+{gap_pct:.1f}%）")
        else:
            detail_parts.append("市值缺失")

        if is_w:
            detail_parts.append("-W额外门槛")
        if is_18c:
            detail_parts.append("18C特专科技")
        if is_ah:
            detail_parts.append("AH候选")

        detail = "；".join(detail_parts)
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
        prospectus_info.get('sector', 'unknown')
        str(prospectus_info.get('extracted_company_name', '') or '').lower()
        extracted_text = str(prospectus_info.get('_extracted_text', '') or prospectus_info.get('prospectus_text', ''))
        is_biotech = classify_company(prospectus_info, extracted_text).is_biotech
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
                business = prospectus_info.get('business_breakdown') or {}
                segments = business.get('segments') or []
                positive_segments = [
                    s for s in segments
                    if _is_num(s.get('revenue_latest')) and _is_num(s.get('revenue_previous'))
                    and s.get('revenue_latest') > s.get('revenue_previous')
                ]
                has_segment_explanation = bool(
                    business.get('growth_source') not in (None, '', 'missing', '增长来源待确认')
                    and positive_segments
                )
                if has_segment_explanation:
                    summary = f"高增长({growth*100:.1f}%)，已由招股书分部数据验证: {business.get('growth_source')}"
                    reasons.append(summary)
                    prospectus_info['growth_validation_status'] = 'explained'
                    prospectus_info['growth_validation_summary'] = summary
                else:
                    red_flags.append(f"收入同比异常({growth*100:.1f}%)，需核对招股书解释")
                    prospectus_info['growth_validation_status'] = 'unexplained'
                    prospectus_info['growth_validation_summary'] = f"收入同比{growth*100:.1f}%，未找到分部解释"
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

        yoy_anomalies = prospectus_info.get('cashflow', {}).get('yoy_anomalies', [])
        unexplained_count = 0
        for anomaly in yoy_anomalies:
            if anomaly.get('explanation'):
                reasons.append(f"{anomaly['item']}同比{anomaly['direction']}{anomaly['change_pct']}%，已有解释")
            else:
                unexplained_count += 1
                red_flags.append(f"{anomaly['item']}同比{anomaly['direction']}{anomaly['change_pct']}%，未找到解释")
        if unexplained_count > 0:
            score -= min(unexplained_count, 3)

        if not red_flags:
            reasons.append("核心财务口径未发现明显异常")

        # 修复问题3: 当存在严重red_flags时，强制降低数据置信度等级
        # 避免"中"级置信度但有严重异常警告的矛盾
        has_severe_flag = any(
            '异常' in f or '超过100%' in f or '极端' in f or '超过10倍' in f
            for f in red_flags
        )
        if has_severe_flag and score >= 3:
            score = min(score, 2)

        label = '可信' if score >= vsl.data_quality_high else ('需复核' if score >= vsl.data_quality_mid else '低')
        detail = '；'.join(red_flags[:2]) if red_flags else '财务数据通过基础异常检查'
        return self._component(score, 5, label, detail, reasons=reasons, red_flags=red_flags)

    def _analyze_valuation_driver(self, ipo_data, prospectus_info):
        sector = prospectus_info.get('sector', 'unknown')
        subsector = (prospectus_info.get('peer_comparison') or {}).get('subsector') or ''
        valuation = prospectus_info.get('valuation') or {}
        pe = valuation.get('adjusted_pe_ratio') or valuation.get('pe_ratio')
        ps = valuation.get('ps_ratio')
        profitable = prospectus_info.get('profitable')

        subsector_theme_map = {
            'robotics_factory_automation': '机器人/自动化',
            'ai_drug_delivery_nanomedicine': 'AI+纳米医药',
            'robotics_visual_perception': '机器视觉',
            'ai_chip_semiconductor': 'AI芯片',
            'innovative_drug_biotech': '创新药',
            'medical_device_surgery': '医疗器械',
        }
        sector_theme_map = {
            'hardtech': '硬科技',
            'healthcare': '医药创新',
        }
        theme_name = subsector_theme_map.get(subsector, sector_theme_map.get(sector, '主题'))

        if profitable is False and sector in ('hardtech', 'healthcare'):
            return {
                'driver_type': 'growth_scarcity',
                'key_drivers': ['收入增速', '订单可见度', '毛利率维持', f'{theme_name}主题贝塔'],
                'driver_detail': '该赛道按收入增速+稀缺性定价，不按当期利润',
            }
        elif profitable is True and _is_num(pe) and pe > 0 and pe < 20:
            return {
                'driver_type': 'profit_value',
                'key_drivers': ['盈利增长', '股息率', '利润率稳定性'],
                'driver_detail': '估值以盈利增长和股息回报为锚，关注利润可持续性',
            }
        elif sector in ('hardtech', 'healthcare') and _is_num(ps) and ps > 10:
            return {
                'driver_type': 'theme_beta',
                'key_drivers': ['主题动量', '板块资金流', '可比估值'],
                'driver_detail': '估值由主题热度与资金流驱动，需关注主题持续性',
            }
        else:
            return {
                'driver_type': 'mixed',
                'key_drivers': ['盈利增长', '收入增速', '估值安全垫'],
                'driver_detail': '估值受多因素混合驱动，需综合判断',
            }

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
