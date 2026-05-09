"""评分系统 — ScoringSystem + 向后兼容的 re-export"""

from .quality_analyzer import ProspectusQualityAnalyzer
from .signal_analyzer import SignalComponentAnalyzer
from .utils import _is_num, _normalize_gm
from .settings import SETTINGS


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

    @staticmethod
    def _detect_weight_profile(ipo):
        """检测权重配置文件：判断是 live_heat 还是 prospectus_only"""
        over_sub_ratio = ipo.get('over_sub_ratio')
        over_sub_ratio_source = ipo.get('over_sub_ratio_source')
        forecast_over_sub_ratio = ipo.get('forecast_over_sub_ratio')
        market_heat = ipo.get('market_heat', '')

        has_heat = _is_num(over_sub_ratio) and over_sub_ratio_source in ("actual", "forecast", "estimated", "historical_actual", "historical_forecast")
        has_market = _is_num(forecast_over_sub_ratio) or market_heat in ("温和", "热门", "极热")

        if has_heat or has_market:
            return {
                'name': 'live_heat',
                'weights': {
                    'trade': 0.35,
                    'fundamental': 0.30,
                    'valuation': 0.20,
                    'theme': 0.10,
                    'data_quality': 0.05,
                },
                'reason': '检测到有效超购/孖展数据',
            }
        else:
            return {
                'name': 'prospectus_only',
                'weights': {
                    'trade': 0.20,
                    'fundamental': 0.35,
                    'valuation': 0.20,
                    'theme': 0.15,
                    'data_quality': 0.10,
                },
                'reason': '未检测到有效热度数据，使用招股书阶段权重',
            }

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
        cornerstone_label = cornerstone_analysis.get('label')
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

        valuation = prospectus_info.get('valuation', {}) or {}
        peer_score_val = peer_comparison.get('peer_score', 0)
        peer_valuation_pos = peer_comparison.get('valuation_position', '')
        relative_ps_premium = peer_comparison.get('relative_ps_premium_pct')
        quant_count = peer_comparison.get('quantitative_peer_count')
        insufficient_peer_sample = bool(peer_comparison.get('peer_sample_warning')) or '样本不足' in str(peer_valuation_pos)
        if _is_num(quant_count) and quant_count < 2:
            insufficient_peer_sample = True
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
        revenue_quality = valuation.get('revenue_quality', 'standard')
        is_license_driven = revenue_quality == 'license_upfront_driven'

        if isinstance(valuation, dict):
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
                reasons.append(f"稀缺赛道高估值容忍(+2)")

        score = round(raw_final + peer_adj + val_penalty)

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
            'weight_profile': weight_profile,
            'score_weights_note': (
                f"权重: trade={trade_w:.0%} fundamental={fundamental_w:.0%} "
                f"valuation={valuation_w:.0%} theme={theme_w:.0%} dq={dq_w:.0%} "
                f"({weight_profile['reason']})"
            ),
            'penalty_reason': penalty_reason,
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