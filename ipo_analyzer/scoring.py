"""评分系统 — ScoringSystem + 向后兼容的 re-export"""

from .quality_analyzer import ProspectusQualityAnalyzer  # noqa: F401
from .signal_analyzer import SignalComponentAnalyzer  # noqa: F401
from .utils import _is_num
from .settings import SETTINGS


class ScoringSystem:
    """评分系统"""

    @staticmethod
    def _score_band(score, high=70, mid=50, low=35, high_label="高", mid_label="中", low_label="偏弱"):
        if score >= high:
            return high_label
        if score >= mid:
            return mid_label
        if score >= low:
            return low_label
        return "弱"

    @staticmethod
    def _valuation_pressure_label(valuation_score, valuation):
        label = str((valuation or {}).get('valuation_label') or '')
        if any(x in label for x in ('很贵', '明显偏贵', '估值压力')):
            return '高'
        if any(x in label for x in ('偏贵', 'PS辅助')):
            return '中'
        if valuation_score >= 65:
            return '低'
        if valuation_score >= 40:
            return '中'
        return '高'

    def _build_strategy_scores(self, prospectus_info, trade_score, fundamental_score, valuation_score, theme_score, data_quality_score):
        valuation = prospectus_info.get('valuation') or {}
        customer = prospectus_info.get('customer_supplier') or {}
        cashflow = prospectus_info.get('cashflow') or {}
        risk_factors = prospectus_info.get('risk_factors') or {}

        customer_quality = customer.get('customer_quality_score', 0)
        sw = SETTINGS.scoring
        long_raw = (
            fundamental_score * sw.long_fundamental_w
            + valuation_score * sw.long_valuation_w
            + data_quality_score * sw.long_data_quality_w
            + min(100, customer_quality) * sw.long_customer_quality_w
            + theme_score * sw.long_theme_w
        )
        if cashflow.get('cash_quality_label') == '弱':
            long_raw -= sw.long_cash_weak_penalty
        # 现金 runway < 1 年的极端情况由 _calculate_risk_penalty 统一处理，避免双重扣减
        if _is_num(risk_factors.get('total_penalty')):
            long_raw -= min(sw.long_risk_penalty_max, risk_factors.get('total_penalty'))

        ipo_trade_score = int(min(100, max(0, round(trade_score))))
        long_term_score = int(min(100, max(0, round(long_raw))))
        valuation_pressure = self._valuation_pressure_label(valuation_score, valuation)
        ipo_trade_label = self._score_band(ipo_trade_score, high=75, mid=60, low=40, high_label='极高', mid_label='高', low_label='中')
        long_term_label = self._score_band(long_term_score, high=70, mid=55, low=25, high_label='强', mid_label='中等', low_label='中等偏弱')

        reasons = []
        if ipo_trade_score >= 75:
            reasons.append('公开认购/筹码/资金信号强，首日交易属性突出')
        elif ipo_trade_score >= 60:
            reasons.append('打新交易信号偏强')
        else:
            reasons.append('打新交易信号未形成强共识')

        if customer_quality >= 60:
            reasons.append('头部客户验证和复购能力对长期质量有支撑')
        if cashflow.get('cash_quality_label') == '弱':
            reasons.append('经营现金流偏弱，需关注营运资金压力')
        if valuation_pressure in ('中', '高'):
            reasons.append(f'估值压力{valuation_pressure}，不宜只看热度忽略定价')

        if ipo_trade_score >= 70 and long_term_score < 55:
            recommendation = '可打新，但不宜当成长线价值股处理'
        elif ipo_trade_score >= 70 and long_term_score >= 65 and valuation_pressure != '高':
            recommendation = '积极申购，可跟踪中线持有条件'
        elif ipo_trade_score >= 55:
            recommendation = '可小注参与，偏首日交易'
        else:
            recommendation = '谨慎申购或观望'

        return {
            'ipo_trade_score': ipo_trade_score,
            'ipo_trade_label': ipo_trade_label,
            'long_term_score': long_term_score,
            'long_term_label': long_term_label,
            'valuation_pressure_label': valuation_pressure,
            'subscription_recommendation': recommendation,
            'recommendation_reasons': reasons[:5],
        }

    COMPONENT_LABELS = {
        "heat": [(35, "极热"), (25, "热门"), (15, "温和"), (0, "冷清")],
        "quality": [(35, "强"), (20, "中"), (1, "弱"), (0, "缺失")],
        "scale": [(8, "大"), (5, "中"), (1, "小"), (0, "缺失")],
        "market": [(5, "加分"), (3, "一般"), (1, "微弱"), (0, "缺失")],
    }

    @classmethod
    def _component_label(cls, score, score_type):
        for threshold, label in cls.COMPONENT_LABELS.get(score_type, []):
            if score >= threshold:
                return label
        return "N/A"

    @staticmethod
    def _detect_weight_profile(ipo):
        """检测权重配置文件：判断是 live_heat 还是 prospectus_only"""
        over_sub_ratio = ipo.get('over_sub_ratio')
        over_sub_ratio_source = ipo.get('over_sub_ratio_source')
        forecast_over_sub_ratio = ipo.get('forecast_over_sub_ratio')
        market_heat = ipo.get('market_heat', '')

        has_heat = _is_num(over_sub_ratio) and over_sub_ratio_source in ("actual", "forecast", "estimated", "historical_actual", "historical_forecast", "post_listing_actual")
        has_market = _is_num(forecast_over_sub_ratio) or market_heat in ("温和", "热门", "极热")

        sw = SETTINGS.scoring
        if has_heat or has_market:
            return {
                'name': 'live_heat',
                'weights': {
                    'trade': sw.live_heat_trade,
                    'fundamental': sw.live_heat_fundamental,
                    'valuation': sw.live_heat_valuation,
                    'theme': sw.live_heat_theme,
                    'data_quality': sw.live_heat_dq,
                },
                'reason': '检测到有效超购/孖展数据',
            }
        else:
            return {
                'name': 'prospectus_only',
                'weights': {
                    'trade': sw.prospectus_trade,
                    'fundamental': sw.prospectus_fundamental,
                    'valuation': sw.prospectus_valuation,
                    'theme': sw.prospectus_theme,
                    'data_quality': sw.prospectus_dq,
                },
                'reason': '未检测到有效热度数据，使用招股书阶段权重',
            }

    def _calc_valuation_adjustments(self, ipo, prospectus_info, reasons):
        """计算估值相关的 peer_adj 和 val_penalty，集中管理估值调整逻辑。"""
        valuation = prospectus_info.get('valuation', {}) or {}
        peer_comparison = prospectus_info.get('peer_comparison', {}) or {}
        scarcity = peer_comparison.get('scarcity_score', 0)
        peer_score_val = peer_comparison.get('peer_score', 0)
        peer_valuation_pos = peer_comparison.get('valuation_position', '')
        relative_ps_premium = peer_comparison.get('relative_weighted_ps_premium_pct')
        if relative_ps_premium is None:
            relative_ps_premium = peer_comparison.get('relative_ps_premium_pct')
        quant_count = peer_comparison.get('quantitative_peer_count')
        val_label = valuation.get('valuation_label', '')
        rel_val_label = valuation.get('relative_valuation_label', '')
        revenue_too_small_for_ps = valuation.get('revenue_too_small_for_ps', False)
        revenue_quality = valuation.get('revenue_quality', 'standard')
        is_license_driven = revenue_quality == 'license_upfront_driven'

        # 判断 valuation_framework 是否已经包含相对估值（避免重复扣分）
        valuation.get('valuation_framework_type', '')
        has_relative_valuation_in_framework = bool(rel_val_label and rel_val_label != '缺失')

        insufficient_peer_sample = bool(peer_comparison.get('peer_sample_warning')) or '样本不足' in str(peer_valuation_pos)
        if _is_num(quant_count) and quant_count < 2:
            insufficient_peer_sample = True

        peer_adj = 0
        # 只有 quant_count >= 2 且 premium > 100% 时才允许 severe penalty
        is_clearly_overvalued = False
        is_somewhat_overvalued = False
        if _is_num(quant_count) and quant_count >= 2:
            is_clearly_overvalued = (
                ('明显偏贵' in str(peer_valuation_pos)) or
                ('PS辅助(明显偏贵)' in str(peer_valuation_pos)) or
                (_is_num(relative_ps_premium) and float(relative_ps_premium) > 100)
            )
            is_somewhat_overvalued = (
                _is_num(relative_ps_premium) and float(relative_ps_premium) > 50
            )

        # 对 low_revenue_biotech 且 revenue_too_small_for_ps=True，PS 只提示不硬扣
        if revenue_too_small_for_ps and (is_clearly_overvalued or is_somewhat_overvalued):
            reasons.append("低收入biotech PS失真，同行溢价仅作提示，不硬扣分")
            is_clearly_overvalued = False
            is_somewhat_overvalued = False

        # 对 license_upfront_driven 的 biotech，不用 PS 溢价直接扣分
        if is_license_driven and (is_clearly_overvalued or is_somewhat_overvalued):
            reasons.append("收入以授权/里程碑为主，PS溢价不直接扣分")
            is_clearly_overvalued = False
            is_somewhat_overvalued = False

        if is_clearly_overvalued:
            peer_adj = -5
            reasons.append("同行估值明显偏贵：公司PS显著高于同行中位数")
        elif is_somewhat_overvalued:
            peer_adj = -2
            reasons.append(f"同行估值偏贵：公司PS高于同行中位数{relative_ps_premium:.0f}%")
        elif _is_num(peer_score_val) and peer_score_val > 0:
            if insufficient_peer_sample:
                if peer_score_val >= 6:
                    reasons.append("同行定量样本不足，仅作定性参考，不额外加分")
            elif peer_score_val >= 12:
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

        val_penalty = 0

        if isinstance(valuation, dict):
            # valuation_framework 已包含 relative valuation 时，不重复扣同一类 PS/同行偏贵
            if has_relative_valuation_in_framework and rel_val_label in ('合理', '相对低估', '偏贵但可解释'):
                # 相对估值已合理，不再因绝对估值偏贵而重扣
                pass
            else:
                if val_label in ('很贵',):
                    if is_license_driven:
                        val_penalty = -1
                        reasons.append("收入以授权/里程碑为主，绝对估值标签仅作提示")
                    elif rel_val_label and rel_val_label in ('合理', '相对低估', '偏贵但可解释'):
                        val_penalty = -2
                    else:
                        val_penalty = -5
                elif val_label in ('偏贵', '明显偏贵'):
                    if is_license_driven:
                        val_penalty = 0
                        reasons.append("收入以授权/里程碑为主，相对估值标签不直接扣分")
                    elif rel_val_label and rel_val_label in ('合理', '相对低估', '偏贵但可解释'):
                        val_penalty = -1
                    else:
                        val_penalty = -3
            if scarcity >= 7 and val_label in ('很贵', '偏贵', '明显偏贵'):
                val_penalty += 2
                reasons.append("稀缺赛道高估值容忍(+2)")

        return peer_adj, val_penalty

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
        if _is_num(over_sub):
            source_label = {
                'actual': '实际',
                'forecast': '预测',
                'estimated': '估算',
                'historical_actual': '历史实际',
                'historical_forecast': '历史预测',
                'post_listing_actual': '上市后',
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

        stock_quality = prospectus_info.get('stock_quality') or {}
        quality_score_raw = stock_quality.get('score', 0)
        quality_reasons = stock_quality.get('reasons', [])
        quality_label = stock_quality.get('label', '缺失')
        quality_dimensions = stock_quality.get('dimensions', {})

        if quality_score_raw > 0:
            mapped = round(quality_score_raw / 100 * _QUALITY_SCORE_MAX)
            components['quality']['score'] = min(_QUALITY_SCORE_MAX, mapped)
            components['quality']['label'] = quality_label
            detail_parts = []
            dim = quality_dimensions.get('growth', {})
            if dim.get('detail'):
                detail_parts.append(dim['detail'])
            dim = quality_dimensions.get('profitability', {})
            if dim.get('detail'):
                detail_parts.append(dim['detail'])
            components['quality']['detail'] = '；'.join(detail_parts) if detail_parts else quality_label
            for r in quality_reasons[:4]:
                if r not in reasons:
                    reasons.append(r)
        else:
            components['quality']['score'] = 0
            components['quality']['label'] = '缺失'
            components['quality']['detail'] = '未获取到招股书关键财务数据'
            quality_reasons = []

        components['quality']['label'] = self._component_label(components['quality']['score'], "quality")

        cornerstone_analysis = prospectus_info.get('cornerstone_analysis') or {}
        cornerstone_score = cornerstone_analysis.get('score')
        cornerstone_analysis.get('label')
        has_cornerstone_section = cornerstone_analysis.get('has_cornerstone_section', False)
        
        if _is_num(cornerstone_score) and has_cornerstone_section:
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
                matched_cornerstone = [m for m in cornerstone_analysis['matched_investors'] 
                                      if m.get('source') == 'cornerstone_section']
                if matched_cornerstone:
                    names = "、".join(item.get('name', '') for item in matched_cornerstone[:3])
                    reasons.append(f"基石V2重点: {names}")
            for strength in cornerstone_analysis.get('strengths', [])[:2]:
                reasons.append(f"基石亮点: {strength}")
            for concern in cornerstone_analysis.get('concerns', [])[:2]:
                reasons.append(f"基石隐忧: {concern}")
            for red_flag in cornerstone_analysis.get('red_flags', []):
                reasons.append(f"基石红旗: {red_flag}")

        total_fund = ipo.get('total_fund')
        public_offer = ipo.get('public_offer')
        public_offer_ratio = prospectus_info.get('public_offer_ratio_pct')
        if _is_num(public_offer) and _is_num(public_offer_ratio) and public_offer_ratio > 0:
            total_fund = public_offer / (public_offer_ratio / 100)
        elif not total_fund:
            total_fund = public_offer
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
                'historical_actual': '历史实际',
                'historical_forecast': '历史预测',
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

        subscription_raw = components['heat']['score'] + components['scale']['score'] + components['market']['score'] + components['cornerstone']['score']
        subscription_raw_max = _HEAT_SCORE_MAX + _SCALE_SCORE_MAX + _MARKET_SCORE_MAX + _CORNERSTONE_SCORE_MAX
        subscription_score = min(100, round(subscription_raw / subscription_raw_max * 100))
        fundamental_score = min(100, round(components['quality']['score'] / _QUALITY_SCORE_MAX * 100))

        sc = signal_components or {}

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

        val_framework = sc.get('valuation_framework', {}) if sc else {}
        val_raw = val_framework.get('score', 0)
        valuation_score = min(100, round(val_raw / 20 * 100))

        theme_raw = 0
        theme_max = 35
        if sc:
            theme_raw += sc.get('mainline_beta', {}).get('score', 0)
            theme_raw += sc.get('stock_connect_path', {}).get('score', 0)
        peer_comparison = prospectus_info.get('peer_comparison', {}) or {}
        scarcity = peer_comparison.get('scarcity_score', 0)
        theme_raw += min(10, scarcity)
        theme_score = min(100, round(theme_raw / theme_max * 100)) if theme_raw else 0

        dq = sc.get('data_quality', {}) if sc else {}
        data_quality_score = min(100, round(dq.get('score', 3) / 5 * 100))

        data_confidence_gate_warning = None
        if data_quality_score < 40:
            data_confidence_gate_warning = "数据质量高风险，综合评分上限已限制"
        elif data_quality_score < 60:
            data_confidence_gate_warning = "数据质量中等，部分指标建议复核"

        weight_profile = self._detect_weight_profile(ipo)
        trade_w = weight_profile['weights']['trade']
        fundamental_w = weight_profile['weights']['fundamental']
        valuation_w = weight_profile['weights']['valuation']
        theme_w = weight_profile['weights']['theme']
        dq_w = weight_profile['weights']['data_quality']

        raw_final = (
            trade_score * trade_w
            + fundamental_score * fundamental_w
            + valuation_score * valuation_w
            + theme_score * theme_w
            + data_quality_score * dq_w
        )

        peer_adj, val_penalty = self._calc_valuation_adjustments(ipo, prospectus_info, reasons)

        score = round(raw_final + peer_adj + val_penalty)
        strategy_scores = self._build_strategy_scores(
            prospectus_info, trade_score, fundamental_score,
            valuation_score, theme_score, data_quality_score,
        )

        cornerstone_red_flags = cornerstone_analysis.get('red_flags', [])
        final_score_before_cap = score
        cap_reason = None
        penalty_reason = None

        severe_cornerstone_flags = SETTINGS.cornerstone.severe_cornerstone_flags

        if cornerstone_red_flags:
            severe_flags = []
            normal_flags = []
            for flag in cornerstone_red_flags:
                flag_lower = str(flag).lower()
                is_severe = any(
                    severe_keyword.lower() in flag_lower
                    for severe_keyword in severe_cornerstone_flags
                )
                if is_severe:
                    severe_flags.append(flag)
                else:
                    normal_flags.append(flag)

            penalty_from_normal = min(10, len(normal_flags) * 3)
            if penalty_from_normal > 0:
                score = max(0, score - penalty_from_normal)
                penalty_reason = f"基石红旗扣{penalty_from_normal}分: {[f for f in normal_flags]}"

            if severe_flags:
                score = min(score, 60)
                cap_reason = f"严重基石问题封顶60: {[f for f in severe_flags]}"
                if penalty_reason:
                    penalty_reason += f"; {cap_reason}"
                else:
                    penalty_reason = cap_reason

        if data_quality_score < 40:
            score = min(score, 60)
            if cap_reason:
                cap_reason += "; 数据质量低风险封顶60"
            else:
                cap_reason = "数据质量低风险封顶60"
        elif data_quality_score < 60:
            score = min(score, 85)
            if cap_reason:
                cap_reason += "; 数据质量中风险封顶85"
            else:
                cap_reason = "数据质量中风险封顶85"

        final_score_after_cap = score

        # 完整的 score_trace，解释最终分数从哪里来
        score_trace = {
            'raw_weighted_score': round(raw_final, 2),
            'peer_adj': peer_adj,
            'val_penalty': val_penalty,
            'risk_penalty_placeholder': 0,  # risk_penalty 在 core.py 中单独计算并扣除
            'cap_reason': cap_reason,
            'final_score_before_cap': final_score_before_cap,
            'final_score_after_cap': final_score_after_cap,
            'weight_profile': weight_profile,
            'trade_score': trade_score,
            'fundamental_score': fundamental_score,
            'valuation_score': valuation_score,
            'theme_score': theme_score,
            'data_quality_score': data_quality_score,
            'ipo_trade_score': strategy_scores['ipo_trade_score'],
            'long_term_score': strategy_scores['long_term_score'],
        }

        return {
            'score': min(100, max(0, score)),
            'subscription_score': subscription_score,
            'fundamental_score': fundamental_score,
            'trade_score': trade_score,
            'valuation_score': valuation_score,
            'theme_score': theme_score,
            'data_quality_score': data_quality_score,
            **strategy_scores,
            'reasons': reasons,
            'components': components,
            'data_confidence_gate_warning': data_confidence_gate_warning,
            'weight_profile': weight_profile,
            'score_weights_note': (
                f"权重: trade={trade_w:.0%} fundamental={fundamental_w:.0%} "
                f"valuation={valuation_w:.0%} theme={theme_w:.0%} dq={dq_w:.0%} "
                f"({weight_profile['reason']})"
            ),
            'penalty_reason': penalty_reason,
            'score_trace': score_trace,
            'debug_info': {
                'over_sub_ratio': over_sub,
                'over_sub_ratio_source': ipo.get('over_sub_ratio_source'),
                'weight_profile': weight_profile,
                'heat_score': components['heat']['score'],
                'trade_score': trade_score,
                'cornerstone_red_flags': cornerstone_red_flags,
                'final_score_before_cap': final_score_before_cap,
                'final_score_after_cap': final_score_after_cap,
                'cap_reason': cap_reason,
            },
        }
