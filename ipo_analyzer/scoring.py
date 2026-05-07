import re

from .utils import _is_num, _normalize_gm, _contains_any, SECTOR_KEYWORDS
from .settings import SETTINGS


class ProspectusQualityAnalyzer:
    """招股书基本面质地分析"""

    @staticmethod
    def _growth_label(growth):
        qt = SETTINGS.prospectus_quality
        if growth >= qt.growth_strong:
            return "强"
        if growth >= qt.growth_good:
            return "中"
        if growth >= 0:
            return "弱"
        return "下滑"

    @staticmethod
    def _valuation_label(profitable, gross_margin_pct, growth):
        qt = SETTINGS.prospectus_quality
        if profitable and gross_margin_pct >= qt.gross_margin_excellent and growth >= qt.growth_good:
            return "低"
        if profitable and gross_margin_pct >= qt.gross_margin_good and growth >= 0:
            return "中"
        if gross_margin_pct >= qt.gross_margin_fair and growth >= 0:
            return "中"
        return "高"

    def analyze(self, prospectus_info):
        score = 0
        reasons = []
        dimensions = {}

        gross_margin = prospectus_info.get('gross_margin')
        gross_margin_pct = None
        revenue = prospectus_info.get('revenue')
        sector = prospectus_info.get('sector', 'unknown')
        profitable = prospectus_info.get('profitable')
        qt = SETTINGS.prospectus_quality
        if gross_margin is not None:
            gross_margin_pct = _normalize_gm(gross_margin)
            if gross_margin_pct >= qt.gross_margin_excellent:
                score += 35
                reasons.append(f"毛利率优秀({gross_margin_pct:.1f}%)")
            elif gross_margin_pct >= qt.gross_margin_good:
                score += 25
                reasons.append(f"毛利率良好({gross_margin_pct:.1f}%)")
            elif gross_margin_pct >= qt.gross_margin_fair:
                score += 15
                reasons.append(f"毛利率一般({gross_margin_pct:.1f}%)")
            else:
                score += 5
                reasons.append(f"毛利率偏低({gross_margin_pct:.1f}%)")

        if profitable is True:
            score += 35
            reasons.append("已实现盈利")
        elif profitable is False:
            reasons.append("仍处亏损")
            is_low_rev_biotech = (sector == 'healthcare' and _is_num(revenue) and revenue < SETTINGS.valuation.biotech_revenue_small)
            if is_low_rev_biotech and gross_margin_pct is not None and gross_margin_pct >= SETTINGS.prospectus_quality.gross_margin_excellent:
                # 极低收入未盈利biotech：毛利率只作参考，大量回撤评分
                gm_score_reduction = 25
                score = max(0, score - gm_score_reduction)
                reasons.append(f"极低收入未盈利生物科技，毛利率{gross_margin_pct:.1f}%仅供参考，不能作为定价锚")

        revenue_y1 = prospectus_info.get('revenue_y1')
        growth = None
        if _is_num(revenue) and _is_num(revenue_y1) and revenue > 0 and revenue_y1 > 0:
            growth = (revenue - revenue_y1) / revenue_y1
            if growth >= qt.growth_strong:
                score += 20
                reasons.append(f"收入增长强劲({growth*100:.1f}%)")
            elif growth >= qt.growth_good:
                score += 10
                reasons.append(f"收入保持增长({growth*100:.1f}%)")
            elif growth >= 0:
                score += 5
                reasons.append(f"收入微增({growth*100:.1f}%)")
            elif growth >= -0.1:
                reasons.append(f"收入小幅回落({growth*100:.1f}%)")
            else:
                score -= 5
                reasons.append(f"收入大幅回落({growth*100:.1f}%)")

        if growth is None and _is_num(revenue) and revenue > 0:
            dimensions['growth'] = {
                'label': '暂无同比数据',
                'detail': '仅获取到单年收入，暂无法判断增长趋势',
            }
        elif growth is not None:
            dimensions['growth'] = {
                'label': self._growth_label(growth),
                'detail': f"收入同比{growth*100:.1f}%",
            }

        if profitable is True:
            net_profit = prospectus_info.get('net_profit')
            net_margin = None
            if _is_num(net_profit) and _is_num(revenue) and revenue > 0:
                net_margin = net_profit / revenue * 100
            dimensions['profitability'] = {
                'label': '盈利',
                'detail': f"已实现盈利" + (f"，净利率{net_margin:.1f}%" if net_margin is not None else ''),
            }
        elif profitable is False:
            net_profit = prospectus_info.get('net_profit')
            dimensions['profitability'] = {
                'label': '亏损',
                'detail': f"仍处亏损" + (f"，净亏损{abs(net_profit):.1f}（百万口径）" if _is_num(net_profit) else ''),
            }
        else:
            dimensions['profitability'] = {
                'label': '未知',
                'detail': '未提取到足够的盈利数据',
            }

        dimensions['valuation'] = {
            'label': self._valuation_label(bool(profitable), gross_margin_pct or 0, growth or 0),
            'detail': '基于盈利能力、毛利率和收入趋势的定价压力判断',
        }

        risk_flags = []
        if profitable is False:
            risk_flags.append("尚未盈利")
        if gross_margin_pct is not None and gross_margin_pct < 25:
            risk_flags.append("毛利率偏薄")
        if growth is not None and growth < 0:
            risk_flags.append("收入同比回落")
        if revenue is None or revenue_y1 is None:
            risk_flags.append("可用财务对比数据有限")

        dimensions['risk'] = {
            'label': " / ".join(risk_flags[:3]) if risk_flags else "风险可控",
            'detail': "；".join(risk_flags) if risk_flags else "招股书可提取的核心财务指标整体可用",
        }

        valuation = prospectus_info.get('valuation', {})
        if isinstance(valuation, dict) and valuation.get('valuation_label') not in ('缺失', None):
            dimensions['valuation'] = {
                'label': valuation.get('valuation_label', '--'),
                'detail': '；'.join(valuation.get('valuation_reasons', [])[:3]),
            }

        business = prospectus_info.get('business_breakdown', {})
        if isinstance(business, dict) and business.get('growth_source') not in ('missing', None):
            segments = business.get('segments', [])
            seg_detail = '、'.join(f"{s['name']}({s.get('share_pct', 0):.0f}%)" for s in segments[:3]) if segments else business.get('growth_source', '--')
            vbp = business.get('vbp_summary', '')
            detail = f"增长来源: {business.get('growth_source', '--')}"
            if segments:
                detail += f"；{seg_detail}"
            if vbp:
                detail += f"；集采: {vbp}"
            dimensions['business'] = {
                'label': business.get('growth_source', '--'),
                'detail': detail,
            }

        geo = prospectus_info.get('geographic', {})
        if isinstance(geo, dict) and geo.get('overseas_growth_label') not in ('缺失', None):
            dimensions['geographic'] = {
                'label': geo.get('overseas_growth_label', '--'),
                'detail': f"海外收入占比{geo.get('overseas_revenue_pct', '--')}%",
            }

        cs = prospectus_info.get('customer_supplier', {})
        if isinstance(cs, dict) and cs.get('concentration_risk_label') not in ('缺失', None):
            dimensions['concentration'] = {
                'label': cs.get('concentration_risk_label', '--'),
                'detail': f"Top5客户{cs.get('top5_customer_revenue_pct', '--')}%，Top5供应商{cs.get('top5_supplier_purchase_pct', '--')}%",
            }

        cf = prospectus_info.get('cashflow', {})
        if isinstance(cf, dict) and cf.get('cash_quality_label') not in ('缺失', None):
            dimensions['cashflow'] = {
                'label': cf.get('cash_quality_label', '--'),
                'detail': f"OCF/净利润{cf.get('ocf_to_net_profit', '--')}；存货周转{cf.get('inventory_turnover_days_latest', '--')}天",
            }

        rnd = prospectus_info.get('rnd_pipeline', {})
        if isinstance(rnd, dict) and rnd.get('pipeline_quality_label') not in ('缺失', None):
            dimensions['rnd'] = {
                'label': rnd.get('pipeline_quality_label', '--'),
                'detail': f"研发费率{rnd.get('rd_expense_ratio', '--')}%{' (B)' if rnd.get('rd_ratio_biotech') else ''}；管线{rnd.get('product_count_pipeline', '--')}个；技术壁垒{rnd.get('technology_moat_score', 0)}/10",
            }

        cap = prospectus_info.get('capacity', {})
        if isinstance(cap, dict) and cap.get('capacity_summary') not in ('缺失', None):
            dimensions['capacity'] = {
                'label': f"{cap.get('utilization_rate', '--')}%" if cap.get('utilization_rate') else '--',
                'detail': cap.get('capacity_summary', '--'),
            }

        risk_f = prospectus_info.get('risk_factors', {})
        if isinstance(risk_f, dict) and risk_f.get('total_penalty', 0) > 0:
            high_risks = [k for k, v in risk_f.get('risks', {}).items() if v.get('risk_level') == '高']
            dimensions['risk_factors'] = {
                'label': f"扣{risk_f.get('total_penalty', 0)}分",
                'detail': f"高风险: {'、'.join(high_risks[:3])}" if high_risks else f"风险扣分{risk_f.get('total_penalty', 0)}",
            }

        vsl = SETTINGS.valuation_score
        if score >= vsl.quality_excellent:
            label = "优秀"
        elif score >= vsl.quality_good:
            label = "良好"
        elif score >= vsl.quality_fair:
            label = "一般"
        else:
            label = "偏弱"

        if not reasons:
            reasons.append("招股书可提取的有效财务指标较少")

        return {
            'label': label,
            'score': min(100, score),
            'reasons': reasons,
            'dimensions': dimensions,
        }

class SignalComponentAnalyzer:
    """交易信号拆解分析器（原 AdvancedIPOFrameworkAnalyzer）。

    不再输出独立 100 分“进阶框架”，而是把 7 个维度拆成信号组件，
    供主评分系统 (ScoringSystem) 统一加权。
    """

    # strength 映射辅助
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

    SOVEREIGN_CAPITAL = [
        ("GIC", ["gic", "新加坡政府投资"]),
        ("Temasek", ["temasek", "淡马锡"]),
        ("ADIA", ["abu dhabi investment authority", "adia", "阿布扎比"]),
        ("QIA", ["qatar investment authority", "qia", "卡塔尔"]),
        ("KIA", ["kuwait investment authority", "kia", "科威特"]),
        ("PIF", ["public investment fund", "pif", "沙特"]),
        ("CPP Investments", ["cpp investments", "canada pension", "加拿大养老金"]),
        ("Ontario Teachers", ["ontario teachers", "安大略"]),
        ("Norges Bank", ["norges bank", "挪威"]),
        ("Mubadala", ["mubadala", "穆巴达拉"]),
    ]

    TOP_TIER_CAPITAL = [
        ("Sequoia", ["sequoia", "红杉"]),
        ("IDG", ["idg"]),
        ("Boyu Capital", ["boyu", "博裕"]),
        ("Hillhouse", ["hillhouse", "高瓴"]),
        ("CPE", ["cpe", "峰"]),
        ("Greenwoods", ["greenwoods", "景林"]),
        ("Gao Yi", ["gaoyi", "高毅"]),
        ("Danshuiquan", ["danshuiquan", "淡水泉"]),
        ("Tencent", ["tencent", "腾讯"]),
        ("BlackRock", ["blackrock", "贝莱德"]),
        ("Fidelity", ["fidelity", "富达"]),
        ("Invesco", ["invesco", "景顺"]),
        ("Oaktree", ["oaktree", "橡树"]),
        ("Millennium", ["millennium", "千禧年"]),
        ("Schroders", ["schroders", "施罗德"]),
        ("Capital Group", ["capital group", "capital research", "资本集团"]),
        ("General Atlantic", ["general atlantic", "泛大西洋"]),
        ("YF Capital", ["yf capital", "yunfeng", "云锋"]),
        ("OrbiMed", ["orbimed", "奥博"]),
        ("Deerfield", ["deerfield"]),
        ("RTW", ["rtw"]),
        ("Lake Bleu", ["lake bleu", "清池"]),
        ("LAV", ["lilly asia ventures", "lilly asia", "lav", "礼来亚洲"]),
        ("Decheng Capital", ["decheng", "德诚"]),
        ("WuXi AppTec", ["wuxi apptec", "药明康德"]),
    ]

    WEAK_SIGNAL_CAPITAL = [
        ("UBS", ["ubs", "瑞银"]),
        ("地方国资", ["state-owned", "state owned", "government-owned", "地方国资", "国资"]),
        ("SPV/通道", ["special purpose vehicle", "spv", "bvi", "cayman", "single limited partner"]),
        ("Huatai/Sage/Arc", ["huatai capital", "sage partners", "arc avenue", "isometry", "华泰资本"]),
    ]

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

        # ---- 兼容旧结构：保留 score / label / components ----
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

        # ---- 新结构：signal_breakdown（供 UI 展示） ----
        vm = components['valuation_framework']
        valuation_label = vm.get('label', '')
        # 未盈利 biotech：valuation strength 不纯看分数，看定性标签
        is_biotech_unprofitable = (
            prospectus_info.get('sector') == 'healthcare'
            and prospectus_info.get('profitable') is False
            and ('-b' in str(prospectus_info.get('extracted_company_name', '')).lower()
                 or 'biotech' in str(prospectus_info.get('_extracted_text', '')).lower())
        )
        if is_biotech_unprofitable and valuation_label in ('缺失', '估值压力'):
            # 如果 valuation_framework 返回缺失但实际有管线数据，提升到“中”
            if prospectus_info.get('rnd_pipeline', {}).get('pipeline_quality_label'):
                vm_strength = '中'
            else:
                vm_strength = '弱'
        elif is_biotech_unprofitable:
            vm_strength = '中'  # PS辅助/管线估值等统一视为“中”性信号
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
            # 新字段
            'signal_breakdown': signal_breakdown,
            # 兼容旧字段（deprecated）
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
        # 满分20分：绝对估值8 + 同行相对估值8 + 稀缺性/主线/平台属性4
        score = 0
        reasons = []
        red_flags = []

        growth = None
        if _is_num(revenue) and _is_num(revenue_y1) and revenue_y1 > 0:
            growth = (revenue - revenue_y1) / revenue_y1

        vt = SETTINGS.valuation
        vsl = SETTINGS.valuation_score
        pt = SETTINGS.peer_comps

        # ---- 未盈利 biotech 识别 ----
        name = str(prospectus_info.get('extracted_company_name', '') or '').lower()
        is_biotech = (sector == 'healthcare' and ('-b' in name or 'biotech' in name))
        is_unprofitable = _is_num(net_profit) and net_profit <= 0
        is_low_rev_biotech = is_biotech and _is_num(revenue) and revenue < vt.biotech_revenue_small

        # ---- 绝对估值 (8分上限) ----
        abs_score = 0
        if is_low_rev_biotech:
            # 极低收入 biotech：PE 不适用，PS 失真，改用管线/平台估值视角
            reasons.append("未盈利 biotech，PE不适用")
            if _is_num(ps):
                # PS 只能给极低权重，防止拉高或拉低
                abs_score = 2 if ps <= vt.ps_expensive else 1
                reasons.append(f"PS {ps:.1f}x（收入基数极小，仅作参考）")
            # 市值/R&D、现金runway 作为补充信号
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
            abs_score = min(6, abs_score)  # 未盈利 biotech 绝对估值上限 6
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

        # ---- 同行相对估值 (8分上限) ----
        peer_score_val = peer_comparison.get('peer_score', 0)
        peer_valuation_pos = peer_comparison.get('valuation_position', '缺失')
        scarcity = peer_comparison.get('scarcity_score', 0)
        premium = peer_comparison.get('relative_ps_premium_pct')
        quant_count = peer_comparison.get('quantitative_peer_count', 0)

        is_overpriced = ('明显偏贵' in str(peer_valuation_pos) or
                         'PS辅助(明显偏贵)' in str(peer_valuation_pos))
        is_very_overpriced = _is_num(premium) and float(premium) > pt.premium_overpriced

        relative_score = 0
        if is_overpriced or is_very_overpriced:
            relative_score = 0
            red_flags.append('相对同行PS溢价过高' if is_very_overpriced else '同行相对估值: 明显偏贵')
            if is_overpriced:
                reasons.append(f'相对估值: {peer_valuation_pos}')
        elif _is_num(peer_score_val) and peer_score_val > 0 and quant_count >= 2:
            # peer_score 0-15, 映射到0-8分；样本充足时才正常映射
            relative_score = min(pt.peer_map_max, round(peer_score_val / 15 * pt.peer_map_max))
            reasons.append(f"同行对比得分{peer_score_val}/15")
            if peer_valuation_pos and peer_valuation_pos != '缺失':
                reasons.append(f"相对估值: {peer_valuation_pos}")
            if scarcity >= pt.scarcity_high:
                reasons.append(f"稀缺赛道(scarcity={scarcity}/10)提供估值容忍度")
        elif _is_num(peer_score_val) and peer_score_val > 0 and quant_count < 2:
            # 样本不足：最多给 2 分，标记为定性参考
            relative_score = min(2, round(peer_score_val / 15 * pt.peer_map_max))
            reasons.append(f"同行样本不足({quant_count}家定量)，仅作定性参考")
        elif _is_num(ps) and not is_low_rev_biotech:
            # 没有同行数据，回退到使用原有PS规则（上限6分）
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

        # ---- 稀缺性/主线/平台属性 (4分上限) ----
        bonus_score = 0
        if scarcity >= pt.scarcity_high:
            bonus_score += pt.scarcity_high - 4  # 3
        elif scarcity >= pt.scarcity_medium:
            bonus_score += pt.scarcity_medium - 3  # 2
        elif scarcity >= pt.scarcity_low:
            bonus_score += pt.scarcity_low - 2  # 1

        if adjusted_profit and adjusted_profit > 0:
            bonus_score += pt.adjusted_profit_bonus
            reasons.append("有经调整利润口径")
        if sector in ('hardtech', 'healthcare') and _is_num(ps) and ps <= vt.ps_expensive:
            bonus_score = min(vsl.bonus_max, bonus_score + pt.sector_ps_bonus)
            reasons.append("成长/医药科技赛道以PS/管线口径辅助")
        if _is_num(market_cap) and market_cap >= SETTINGS.valuation_score.large_market_cap:
            bonus_score = min(4, bonus_score + 1)
            reasons.append("上市市值较大，具备机构覆盖基础")
        score += bonus_score

        # Red flags（不扣分但记录）
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
            # 未盈利 biotech 专用标签
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
        elif _is_num(market_cap) and market_cap >= 5000:
            score, label = 4, '小型观察'
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

        if parser_flags:
            # 标记生物科技相关的 parser flags 改为低严重性
            for flag in parser_flags:
                if is_biotech and ('净利' in str(flag) or '利润' in str(flag) or '单位' in str(flag)):
                    continue  # 创新药亏损大于收入是正常现象
                red_flags.append(flag)
                score -= 1
        if extraction_confidence == 'needs_review':
            red_flags.append("财务抽取结果需人工复核")
            score -= 2

        vsl = SETTINGS.valuation_score
        if _is_num(revenue) and _is_num(revenue_y1) and revenue > 0 and revenue_y1 > 0:
            growth = (revenue - revenue_y1) / revenue_y1
            if abs(growth) > vsl.growth_extreme:
                red_flags.append(f"收入同比异常({growth*100:.1f}%)，需核对招股书解释")
                score -= 2
            ratio = max(revenue, revenue_y1) / max(min(revenue, revenue_y1), 1e-9)
            if ratio > vsl.revenue_ratio_extreme:
                red_flags.append("收入两年口径差异超过10倍，疑似单位或表格错位")
                score -= 2
        else:
            red_flags.append("缺少可比收入数据")
            score -= 1

        vsl = SETTINGS.valuation_score
        if _is_num(net_profit) and _is_num(revenue) and revenue > 0:
            net_margin = net_profit / revenue
            if abs(net_margin) < vsl.net_margin_near_zero:
                red_flags.append("净利率接近0，需核对利润提取")
                score -= 2
            if abs(net_margin) > vsl.net_margin_extreme:
                if is_biotech:
                    reasons.append("创新药临床阶段亏损大于收入，商业化风险提示")
                else:
                    red_flags.append("净利率超过100%，疑似利润或收入口径异常")
                    score -= 2

        vsl = SETTINGS.valuation_score
        if _is_num(market_cap) and _is_num(net_profit) and net_profit > 0:
            pe = market_cap / net_profit
            if pe > vsl.pe_extreme:
                red_flags.append(f"PE极端({pe:.0f}x)，需核对净利润单位")
                score -= 2

        if not red_flags:
            reasons.append("核心财务口径未发现明显异常")
        vsl = SETTINGS.valuation_score
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


class ScoringSystem:
    """评分系统"""

    @staticmethod
    def _component_label(score, score_type):
        if score_type == "heat":
            if score >= 35:
                return "极热"
            if score >= 25:
                return "热门"
            if score >= 15:
                return "温和"
            return "冷清"
        if score_type == "quality":
            if score >= 35:
                return "强"
            if score >= 20:
                return "中"
            if score > 0:
                return "弱"
            return "缺失"
        if score_type == "scale":
            if score >= 8:
                return "大"
            if score >= 5:
                return "中"
            if score > 0:
                return "小"
            return "缺失"
        if score_type == "market":
            if score >= 5:
                return "加分"
            if score >= 3:
                return "一般"
            if score > 0:
                return "微弱"
            return "缺失"
        return "N/A"
    
    def calculate(self, ipo, prospectus_info, signal_components=None):
        reasons = []

        components = {
            'heat': {'score': 0, 'label': '缺失', 'detail': '未获取到超购倍数'},
            'quality': {'score': 0, 'label': '缺失', 'detail': '未获取到招股书关键财务数据'},
            'cornerstone': {'score': 0, 'label': '缺失', 'detail': '未获取到基石分析'},
            'scale': {'score': 0, 'label': '缺失', 'detail': '未获取到公开集资额'},
            'market': {'score': 0, 'label': '缺失', 'detail': '未获取到市场热度'},
        }

        sw = SETTINGS.scoring
        _HEAT_SCORE_MAX = sw.heat_max
        _QUALITY_SCORE_MAX = sw.quality_max
        _SCALE_SCORE_MAX = sw.scale_max
        _MARKET_SCORE_MAX = sw.market_max
        _CORNERSTONE_SCORE_MAX = sw.cornerstone_max

        over_sub = ipo.get('over_sub_ratio')
        if over_sub is not None:
            source_label = {
                'actual': '实际',
                'forecast': '预测',
                'estimated': '估算',
            }.get(ipo.get('over_sub_ratio_source'), '可用')
            mh = SETTINGS.market_heat
            if over_sub >= mh.extreme:
                components['heat']['score'] = _HEAT_SCORE_MAX
                reasons.append(f"超购极热({over_sub:.0f}倍)")
            elif over_sub >= mh.hot:
                components['heat']['score'] = 35
                reasons.append(f"超购热门({over_sub:.0f}倍)")
            elif over_sub >= mh.warm:
                components['heat']['score'] = 30
                reasons.append(f"超购较高({over_sub:.0f}倍)")
            elif over_sub >= 5:
                components['heat']['score'] = 20
                reasons.append(f"超购温和({over_sub:.0f}倍)")
            else:
                components['heat']['score'] = 10
            components['heat']['label'] = self._component_label(components['heat']['score'], "heat")
            components['heat']['detail'] = f"{source_label}超购 {over_sub:.2f} 倍"

        gross_margin = prospectus_info.get('gross_margin')
        if gross_margin is not None:
            gm_pct = _normalize_gm(gross_margin)
            if gm_pct > 50:
                components['quality']['score'] += 25
                reasons.append(f"毛利率优秀({gm_pct:.1f}%)")
            elif gm_pct > 30:
                components['quality']['score'] += 20
                reasons.append(f"毛利率良好({gm_pct:.1f}%)")
            elif gm_pct > 20:
                components['quality']['score'] += 15
                reasons.append(f"毛利率一般({gm_pct:.1f}%)")
            else:
                components['quality']['score'] += 10
                reasons.append(f"毛利率偏低({gm_pct:.1f}%)")
            components['quality']['detail'] = f"毛利率{gm_pct:.1f}%"

        if prospectus_info.get('profitable'):
            components['quality']['score'] += 20
            reasons.append("公司已实现盈利")
            components['quality']['detail'] = components['quality']['detail'] + "；已实现盈利" if components['quality']['detail'] != '未获取到招股书关键财务数据' else "已实现盈利"
        elif prospectus_info.get('profitable') is False:
            components['quality']['score'] += 5
            components['quality']['detail'] = components['quality']['detail'] + "；仍处亏损" if components['quality']['detail'] != '未获取到招股书关键财务数据' else "仍处亏损"

        revenue = prospectus_info.get('revenue')
        revenue_y1 = prospectus_info.get('revenue_y1')
        if _is_num(revenue) and _is_num(revenue_y1) and revenue > 0 and revenue_y1 > 0:
            growth = (revenue - revenue_y1) / revenue_y1
            qt = SETTINGS.prospectus_quality
            if growth >= qt.growth_strong:
                components['quality']['score'] += 10
                reasons.append(f"收入增长强劲({growth*100:.1f}%)")
            elif growth >= qt.growth_good:
                components['quality']['score'] += 5
                reasons.append(f"收入保持增长({growth*100:.1f}%)")
            elif growth >= 0:
                components['quality']['score'] += 2
                reasons.append(f"收入微增({growth*100:.1f}%)")
            elif growth >= -0.1:
                components['quality']['score'] -= 3
                reasons.append(f"收入小幅回落({growth*100:.1f}%)")
            else:
                components['quality']['score'] -= 8
                reasons.append(f"收入大幅回落({growth*100:.1f}%)")
            components['quality']['score'] = max(0, components['quality']['score'])
            if components['quality']['detail'] == '未获取到招股书关键财务数据':
                components['quality']['detail'] = f"收入同比{growth*100:.1f}%"
            else:
                components['quality']['detail'] += f"；收入同比{growth*100:.1f}%"
        elif _is_num(revenue) and revenue > 0:
            if components['quality']['detail'] == '未获取到招股书关键财务数据':
                components['quality']['detail'] = '仅获取到单年收入'

        components['quality']['label'] = self._component_label(components['quality']['score'], "quality")

        cornerstone_analysis = prospectus_info.get('cornerstone_analysis') or {}
        cornerstone_score = cornerstone_analysis.get('score')
        cornerstone_label = cornerstone_analysis.get('label')
        if _is_num(cornerstone_score):
            component_score = min(20, round(cornerstone_score / 5))
            components['cornerstone']['score'] = component_score
            components['cornerstone']['label'] = cornerstone_analysis.get('label', 'N/A')
            combo = cornerstone_analysis.get('combination_summary')
            band = cornerstone_analysis.get('grade_band')
            if combo:
                components['cornerstone']['detail'] = f"{band or cornerstone_analysis.get('label', 'N/A')}，{combo}"
            else:
                components['cornerstone']['detail'] = f"{band or cornerstone_analysis.get('label', 'N/A')}，{cornerstone_analysis.get('recommendation', '谨慎参考')}"
            v2_rows = cornerstone_analysis.get('cornerstone_investors') or []
            top_rows = [
                row for row in v2_rows
                if row.get('tier') in ('S', 'A')
            ][:3]
            if top_rows:
                names = "、".join((row.get('short_name') or row.get('name') or '') for row in top_rows)
                reasons.append(f"基石V2重点: {names}")
            elif cornerstone_analysis.get('matched_investors'):
                names = "、".join(item.get('name', '') for item in cornerstone_analysis['matched_investors'][:3])
                reasons.append(f"基石V2重点: {names}")
            for strength in cornerstone_analysis.get('strengths', [])[:2]:
                reasons.append(f"基石亮点: {strength}")
            for concern in cornerstone_analysis.get('concerns', [])[:2]:
                reasons.append(f"基石隐忧: {concern}")
            for red_flag in cornerstone_analysis.get('red_flags', []):
                reasons.append(f"基石红旗: {red_flag}")

        total_fund = ipo.get('total_fund')
        if total_fund:
            if total_fund > 10:
                components['scale']['score'] = 10
                reasons.append(f"集资规模大({total_fund:.1f}亿)")
            elif total_fund > 5:
                components['scale']['score'] = 7
                reasons.append(f"集资规模中等({total_fund:.1f}亿)")
            elif total_fund > 1:
                components['scale']['score'] = 5
                reasons.append(f"集资规模较小({total_fund:.1f}亿)")
            else:
                components['scale']['score'] = 3
            components['scale']['label'] = self._component_label(components['scale']['score'], "scale")
            components['scale']['detail'] = f"公开集资额 {total_fund:.2f} 亿"
        
        forecast_over = ipo.get('forecast_over_sub_ratio')
        market_heat = ipo.get('market_heat', '')
        if _is_num(forecast_over) and _is_num(over_sub) and over_sub > 0:
            trend_gap = (forecast_over - over_sub) / over_sub
            base_label = {
                'actual': '实际',
                'forecast': '预测',
                'estimated': '估算',
            }.get(ipo.get('over_sub_ratio_source'), '可用基准')
            if trend_gap >= 0.3:
                components['market']['score'] = 5
                components['market']['label'] = "继续走强"
            elif trend_gap >= 0.1:
                components['market']['score'] = 4
                components['market']['label'] = "偏强"
            elif trend_gap >= -0.1:
                components['market']['score'] = 3
                components['market']['label'] = "平稳"
            else:
                components['market']['score'] = 1
                components['market']['label'] = "回落"
            components['market']['detail'] = f"预测超购 {forecast_over:.2f} 倍，较{base_label}变化 {trend_gap*100:.1f}%"
        else:
            if market_heat == "极热":
                components['market']['score'] = 5
                components['market']['label'] = "极热"
                reasons.append("市场极度火热")
            elif market_heat == "热门":
                components['market']['score'] = 4
                components['market']['label'] = "热门"
                reasons.append("市场热门")
            elif market_heat == "温和":
                components['market']['score'] = 3
                components['market']['label'] = "温和"
            else:
                components['market']['score'] = 0
                components['market']['label'] = "缺失"
            components['market']['detail'] = f"当前热度 {market_heat}" if market_heat else "未获取到热度"

        # ---- 兼容旧结构：subscription_score / fundamental_score ----
        subscription_raw = components['heat']['score'] + components['scale']['score'] + components['market']['score'] + components['cornerstone']['score']
        subscription_raw_max = _HEAT_SCORE_MAX + _SCALE_SCORE_MAX + _MARKET_SCORE_MAX + _CORNERSTONE_SCORE_MAX
        subscription_score = min(100, round(subscription_raw / subscription_raw_max * 100))
        fundamental_score = min(100, round(components['quality']['score'] / _QUALITY_SCORE_MAX * 100))

        # ---- 新五维评分 ----
        sc = signal_components or {}

        # trade_score (0-100)：孖展、超购、筹码结构
        trade_raw = (
            components['heat']['score'] + components['scale']['score']
            + components['market']['score'] + components['cornerstone']['score']
        )
        trade_max = _HEAT_SCORE_MAX + _SCALE_SCORE_MAX + _MARKET_SCORE_MAX + _CORNERSTONE_SCORE_MAX
        if sc:
            trade_raw += sc.get('real_money', {}).get('score', 0)
            trade_raw += sc.get('float_structure', {}).get('score', 0)
            trade_max += 20 + 15
        trade_score = min(100, round(trade_raw / trade_max * 100)) if trade_max else 0

        # valuation_score (0-100)：PE/PS/PB、同行估值、未盈利专项
        val_framework = sc.get('valuation_framework', {}) if sc else {}
        val_raw = val_framework.get('score', 0)
        valuation_score = min(100, round(val_raw / 20 * 100))

        # theme_score (0-50)：主线 + 港股通 + 稀缺性；权重0.10，满分50→最多贡献5分
        theme_raw = 0
        if sc:
            theme_raw += sc.get('mainline_beta', {}).get('score', 0)      # 0-15
            theme_raw += sc.get('stock_connect_path', {}).get('score', 0)  # 0-10
        peer_comparison = prospectus_info.get('peer_comparison', {}) or {}
        scarcity = peer_comparison.get('scarcity_score', 0)
        theme_raw += min(10, scarcity)  # 0-10
        theme_score = min(50, round(theme_raw / 35 * 50)) if theme_raw else 0

        # data_quality_score (0-100)：解析置信度；权重0.05，满分100→最多贡献5分
        dq = sc.get('data_quality', {}) if sc else {}
        data_quality_score = min(100, round(dq.get('score', 3) / 5 * 100))

        # confidence_gate：数据质量差时限制综合评分上限
        data_confidence_gate_warning = None
        if data_quality_score < 40:
            data_confidence_gate_warning = "数据质量高风险，综合评分上限已限制"
        elif data_quality_score < 60:
            data_confidence_gate_warning = "数据质量中等，部分指标建议复核"

        # ---- 新 final_score 公式 ----
        # final_score = trade*0.35 + fundamental*0.30 + valuation*0.20 + theme*0.10 + data_quality*0.05
        raw_final = (
            trade_score * 0.35
            + fundamental_score * 0.30
            + valuation_score * 0.20
            + theme_score * 0.10
            + data_quality_score * 0.05
        )

        # 保留原有的 peer_adj 和 valuation 扣分作为微调，但权重降低
        valuation = prospectus_info.get('valuation', {}) or {}
        peer_score_val = peer_comparison.get('peer_score', 0)
        peer_valuation_pos = peer_comparison.get('valuation_position', '')
        relative_ps_premium = peer_comparison.get('relative_ps_premium_pct')
        val_label = valuation.get('valuation_label', '')
        rel_val_label = valuation.get('relative_valuation_label', '')

        peer_adj = 0
        is_clearly_overvalued = (
            ('明显偏贵' in str(peer_valuation_pos)) or
            ('PS辅助(明显偏贵)' in str(peer_valuation_pos)) or
            (_is_num(relative_ps_premium) and float(relative_ps_premium) > 100)
        )
        is_somewhat_overvalued = (
            _is_num(relative_ps_premium) and float(relative_ps_premium) > 50
        )
        if is_clearly_overvalued:
            peer_adj = -5
            reasons.append("同行估值明显偏贵：公司PS显著高于同行中位数")
        elif is_somewhat_overvalued:
            peer_adj = -2
            reasons.append(f"同行估值偏贵：公司PS高于同行中位数{relative_ps_premium:.0f}%")
        elif _is_num(peer_score_val) and peer_score_val > 0:
            if peer_score_val >= 12:
                peer_adj = 6
                reasons.append("同行对比优异: 赛道稀缺+增长强+估值合理(+6分)")
            elif peer_score_val >= 9:
                premium_ok = (not _is_num(relative_ps_premium)) or float(relative_ps_premium) <= 30
                if premium_ok:
                    peer_adj = 3
                    reasons.append("同行对比较好: 相对同行估值有空间(+3分)")
            elif peer_score_val >= 6:
                peer_adj = 1
            elif peer_score_val <= 3:
                peer_adj = -5
                reasons.append("同行对比偏弱: 相对同行估值偏高(-5分)")

        # 估值扣分(考虑同行对比, 减轻绝对估值惩罚)
        val_penalty = 0
        if isinstance(valuation, dict):
            if val_label in ('很贵',):
                if rel_val_label and rel_val_label in ('合理', '相对低估', '偏贵但可解释'):
                    val_penalty = -2
                else:
                    val_penalty = -5
            elif val_label in ('偏贵', '明显偏贵'):
                if rel_val_label and rel_val_label in ('合理', '相对低估', '偏贵但可解释'):
                    val_penalty = -1
                else:
                    val_penalty = -3
            # 稀缺性对冲
            if scarcity >= 7 and val_label in ('很贵', '偏贵', '明显偏贵'):
                val_penalty += 2
                reasons.append(f"稀缺赛道高估值容忍(+2)")

        score = round(raw_final + peer_adj + val_penalty)

        # cornerstone 弱时限制
        if _is_num(cornerstone_score) and cornerstone_score < 50:
            score = min(score, 55)
        if cornerstone_label in ('弱基石', '未披露'):
            score = min(score, 55)
        if cornerstone_analysis.get('red_flags'):
            score = min(score, 40)

        # confidence_gate 上限限制
        if data_quality_score < 40:
            score = min(score, 60)
        elif data_quality_score < 60:
            score = min(score, 85)

        return {
            'score': min(100, max(0, score)),
            'subscription_score': subscription_score,
            'fundamental_score': fundamental_score,
            'trade_score': trade_score,
            'valuation_score': valuation_score,
            'theme_score': theme_score,
            'data_quality_score': data_quality_score,
            'reasons': reasons,
            'components': components,
            'data_confidence_gate_warning': data_confidence_gate_warning,
        }
