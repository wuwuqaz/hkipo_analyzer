"""评分系统 — ScoringSystem + 向后兼容的 re-export"""

import re

from .quality_analyzer import ProspectusQualityAnalyzer  # noqa: F401
from .signal_analyzer import SignalComponentAnalyzer  # noqa: F401
from .utils import _is_num
from .settings import SETTINGS

import logging
logger = logging.getLogger(__name__)

_AH_DUAL_RE = re.compile(r'dual\s+list|a\s*\+\s*h|a股.*h股|h股.*a股|ah上市|a shares?\s+and\s+h shares?', re.IGNORECASE)


class ScoringSystem:
    """评分系统"""
    STRICT_SCORING_PROFILE = "balanced_strict_2026"

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

    def _build_strategy_scores(self, prospectus_info, trade_score, fundamental_score, valuation_score, theme_score):
        valuation = prospectus_info.get('valuation') or {}
        customer = prospectus_info.get('customer_supplier') or {}
        cashflow = prospectus_info.get('cashflow') or {}
        rnd = prospectus_info.get('rnd_pipeline') or {}
        business = prospectus_info.get('business_breakdown') or {}
        risk_factors = prospectus_info.get('risk_factors') or {}
        stock_quality = prospectus_info.get('stock_quality') or {}
        peer_comparison = prospectus_info.get('peer_comparison') or {}
        shareholder = prospectus_info.get('shareholder') or {}

        sw = SETTINGS.scoring
        qt = SETTINGS.prospectus_quality

        if valuation_score <= 0:
            valuation_score = sw.long_valuation_default_score
            reasons_val_fallback = ['估值数据缺失，按中性默认值处理']

        moat_competitive_score = 50
        moat_reasons = []
        scarcity = peer_comparison.get('scarcity_score', 0) if _is_num(peer_comparison.get('scarcity_score')) else 0
        dominant_pct = peer_comparison.get('dominant_share_pct')
        if scarcity >= qt.scarcity_moat_strong:
            moat_competitive_score = 85
            moat_reasons.append(f'赛道高度稀缺(scarcity={scarcity}/10)')
        elif scarcity >= qt.scarcity_moat_moderate:
            moat_competitive_score = 65
            moat_reasons.append(f'赛道有一定稀缺性(scarcity={scarcity}/10)')
        if _is_num(dominant_pct):
            if dominant_pct >= 30:
                moat_competitive_score = min(100, moat_competitive_score + 15)
                moat_reasons.append(f'市场份额领先({dominant_pct:.0f}%)')
            elif dominant_pct >= 10:
                moat_competitive_score = min(100, moat_competitive_score + 5)

        segment_moat = business.get('segment_moat_label', '')
        if segment_moat in ('本体驱动', '方案驱动'):
            moat_competitive_score = min(100, moat_competitive_score + 5)
            moat_reasons.append(f'主业护城河明确: {segment_moat}')

        tech_moat = rnd.get('technology_moat_score', 0)
        if _is_num(tech_moat) and tech_moat >= qt.moat_score_strong:
            moat_competitive_score = min(100, moat_competitive_score + 10)
            moat_reasons.append(f'技术壁垒强({tech_moat}/10)')

        financial_health_score = 50
        health_reasons = []
        cash_runway = cashflow.get('cash_runway_years')
        if _is_num(cash_runway):
            if cash_runway >= qt.cash_runway_strong:
                financial_health_score = 80
                health_reasons.append(f'现金跑道充裕({cash_runway:.1f}年)')
            elif cash_runway >= qt.cash_runway_good:
                financial_health_score = 65
                health_reasons.append(f'现金跑道尚可({cash_runway:.1f}年)')
            elif cash_runway >= 1:
                financial_health_score = 45
                health_reasons.append(f'现金跑道偏紧({cash_runway:.1f}年)')
            else:
                financial_health_score = 25
                health_reasons.append(f'现金跑道不足1年')

        working_cap_label = cashflow.get('working_capital_pressure_label', '')
        if '高' in str(working_cap_label):
            financial_health_score = max(20, financial_health_score - 15)
            health_reasons.append('营运资本压力高')
        if cashflow.get('cash_quality_label') == '弱':
            financial_health_score = max(20, financial_health_score - 10)
            health_reasons.append('现金流质量弱')

        growth_quality_score = 50
        revenue = prospectus_info.get('revenue')
        revenue_y1 = prospectus_info.get('revenue_y1')
        growth = None
        if _is_num(revenue) and _is_num(revenue_y1) and revenue_y1 > 0:
            growth = (revenue - revenue_y1) / revenue_y1
        if growth is not None:
            if growth >= qt.growth_strong:
                growth_quality_score = 85
            elif growth >= qt.growth_good:
                growth_quality_score = 65
            elif growth >= 0:
                growth_quality_score = 50
            elif growth >= -0.1:
                growth_quality_score = 35
            else:
                growth_quality_score = 20

        stock_connect_score = 30
        market_cap = prospectus_info.get('market_cap_hkd_million')
        sc = SETTINGS.stock_connect
        is_ah = _AH_DUAL_RE.search(
            (prospectus_info.get('_extracted_text', '') or '')[:120000]
        ) if _AH_DUAL_RE else False
        if is_ah:
            stock_connect_score = 95
        elif _is_num(market_cap) and market_cap >= sc.large_cap:
            stock_connect_score = 85
        elif _is_num(market_cap) and market_cap >= sc.fast_track:
            stock_connect_score = 65
        elif _is_num(market_cap) and market_cap >= sc.regular:
            stock_connect_score = 50
        elif _is_num(market_cap) and market_cap >= sc.small_cap:
            stock_connect_score = 35
        else:
            stock_connect_score = 20

        long_raw = (
            fundamental_score * sw.long_fundamental_w
            + valuation_score * sw.long_valuation_w
            + moat_competitive_score * sw.long_moat_competitive_w
            + financial_health_score * sw.long_financial_health_w
            + growth_quality_score * sw.long_growth_quality_w
            + stock_connect_score * sw.long_stock_connect_w
            + theme_score * sw.long_theme_w
        )

        bonus = 0
        fisher_label = stock_quality.get('fisher_label', '缺失')
        lynch_label = stock_quality.get('lynch_label', '缺失')
        if fisher_label == '适配':
            bonus += 3
        elif fisher_label == '部分适配':
            bonus += 1
        if lynch_label == '适配':
            bonus += 3
        elif lynch_label == '部分适配':
            bonus += 1

        business_model_label = business.get('business_model_label', '') or ''
        if any(kw in business_model_label for kw in ('机器人', 'AI', '自动驾驶', '商业航天', '人形机器人')):
            bonus += 1
        if any(kw in business_model_label for kw in ('biotech', '创新药', '生物医药', '基因治疗', '细胞治疗')):
            bonus += 1

        bonus = min(sw.long_bonus_cap, bonus)
        long_raw += bonus

        penalty = 0
        if cashflow.get('cash_quality_label') == '弱':
            penalty += sw.long_cash_weak_penalty

        runway_months = cashflow.get('cash_runway_months')
        if _is_num(runway_months) and runway_months < 12:
            penalty += sw.long_cash_runway_penalty

        wc_risks = cashflow.get('working_capital_risks') or []
        if any(('应收' in str(x)) or ('存货' in str(x)) for x in wc_risks):
            penalty += sw.long_wc_risk_penalty

        if _is_num(risk_factors.get('total_penalty')):
            penalty += min(sw.long_risk_penalty_max, risk_factors.get('total_penalty'))

        max_penalty_ratio = round(long_raw * sw.long_penalty_max_ratio) if long_raw > 0 else 0
        max_penalty = min(max_penalty_ratio, 15)
        penalty = min(penalty, max_penalty)

        raw_long_term_score_before_penalty = int(min(100, max(0, round(long_raw))))
        long_raw -= penalty

        raw_trade_signal_score = int(min(100, max(0, round(trade_score))))
        long_term_score = int(min(100, max(0, round(long_raw))))
        valuation_pressure = self._valuation_pressure_label(valuation_score, valuation)
        long_term_label = self._score_band(long_term_score, high=70, mid=55, low=30, high_label='强', mid_label='中等', low_label='中等偏弱')

        strict_raw = (
            raw_trade_signal_score * 0.40
            + long_term_score * 0.40
            + valuation_score * 0.20
        )
        strict_cap = 100
        strict_cap_reasons = []
        if valuation_pressure == '高':
            if theme_score < 45:
                strict_cap = min(strict_cap, 58)
                strict_cap_reasons.append('估值压力高且赛道/主题弱，严格打新分封顶58')
            elif fundamental_score < 55:
                strict_cap = min(strict_cap, 58)
                strict_cap_reasons.append('估值压力高且基本面不足，严格打新分封顶58')
            else:
                strict_cap = min(strict_cap, 64)
                strict_cap_reasons.append('估值压力高，严格打新分封顶64')
        if long_term_score < 50:
            strict_cap = min(strict_cap, 58)
            strict_cap_reasons.append('长期投资分偏弱，严格打新分封顶58')
        elif long_term_score < 55:
            strict_cap = min(strict_cap, 62)
            strict_cap_reasons.append('长期投资分不足55，严格打新分封顶62')
        if valuation_score < 40:
            strict_cap = min(strict_cap, 58)
            strict_cap_reasons.append('估值分低于40，严格打新分封顶58')

        strict_ipo_score = int(min(strict_cap, max(0, round(strict_raw))))
        ipo_trade_score = strict_ipo_score
        ipo_trade_label = self._score_band(ipo_trade_score, high=70, mid=60, low=45, high_label='高', mid_label='中', low_label='偏谨慎')

        reasons = []
        if fundamental_score >= 70:
            reasons.append('基本面扎实，是严格打新评分的主要支撑')
        elif fundamental_score >= 55:
            reasons.append('基本面尚可，但仍需结合估值和热度验证')
        else:
            reasons.append('基本面偏弱，不能只依赖超购热度')

        if valuation_score >= 65:
            reasons.append('估值具备一定安全边际')
        elif valuation_score >= 55:
            reasons.append('估值大致合理，需继续对比同行')
        elif valuation_pressure == '高':
            reasons.append('估值压力高，需谨慎对待定价风险')
        else:
            reasons.append('估值吸引力不足，需人工复核')

        if theme_score >= 60:
            reasons.append('赛道主题和港股通路径对中期关注度有支撑')
        elif theme_score < 35:
            reasons.append('赛道热度或稀缺性不足，难以消化高估值')

        if raw_trade_signal_score >= 75:
            reasons.append('公开认购/筹码/资金信号强，首日交易属性突出')
        elif raw_trade_signal_score >= 60:
            reasons.append('打新交易信号偏强')
        else:
            reasons.append('打新交易信号未形成强共识')

        stock_quality_dimensions = stock_quality.get('dimensions', {})
        ocf_dim = stock_quality_dimensions.get('ocf_quality', {})
        if ocf_dim.get('label') == '强':
            reasons.append('经营现金流质量强，利润含金量高')
        moat_dim = stock_quality_dimensions.get('moat_depth', {})
        if moat_dim.get('label') == '强':
            reasons.append('护城河深度强，具备长期竞争壁垒')
        health_dim = stock_quality_dimensions.get('financial_health', {})
        if health_dim.get('label') == '强':
            reasons.append('财务健康度高，现金跑道充裕')

        if moat_competitive_score >= 70:
            reasons.append('赛道稀缺+市场份额提供长期护城河')
        if financial_health_score >= 70:
            reasons.append('财务结构稳健，中长期经营风险可控')
        if stock_connect_score >= 60:
            reasons.append('港股通入通路径清晰，有望获得南下资金覆盖')
        elif stock_connect_score >= 40:
            reasons.append('港股通入通路径可期，关注市值增长进度')

        if fisher_label == '适配':
            reasons.append('Fisher视角下具备较好的长期跟踪条件')
        elif fisher_label == '部分适配':
            reasons.append('Fisher视角部分成立，但仍需观察经营质量')
        if lynch_label == '适配':
            reasons.append('Lynch视角下具备较好的长线持有条件')
        elif lynch_label == '部分适配':
            reasons.append('Lynch视角仅部分成立，估值与盈利仍需观察')

        customer_quality = customer.get('customer_quality_score', 0)
        if customer_quality == 0 and customer.get('customer_quality_label') == '缺失':
            customer_quality = 35
        if customer_quality >= 60:
            reasons.append('头部客户验证和复购能力对长期质量有支撑')

        if cashflow.get('cash_quality_label') == '弱':
            reasons.append('经营现金流偏弱，需关注营运资金压力')
        if wc_risks:
            reasons.append('营运资本存在库存/应收或月耗现金压力')
        if valuation_pressure in ('中', '高'):
            reasons.append(f'估值压力{valuation_pressure}，不宜只看热度忽略定价')
        if valuation_score <= sw.long_valuation_default_score + 5:
            reasons.append('估值数据有局限，建议人工复核估值合理性')

        if strict_cap_reasons:
            for cap_msg in strict_cap_reasons:
                if cap_msg not in reasons:
                    reasons.append(cap_msg)

        if ipo_trade_score >= 70 and long_term_score >= 62 and valuation_score >= 55 and valuation_pressure != '高':
            recommendation = '积极申购，可跟踪中线持有条件'
        elif ipo_trade_score >= 60 and long_term_score >= 55 and valuation_pressure != '高':
            recommendation = '可小注参与，基本面与估值需继续跟踪'
        elif raw_trade_signal_score >= 75 and long_term_score >= 55 and valuation_pressure != '高':
            recommendation = '可小注参与，偏首日交易'
        elif ipo_trade_score >= 55 or raw_trade_signal_score >= 70:
            recommendation = '谨慎试水'
        else:
            recommendation = '谨慎申购或观望'

        long_term_penalty_reasons_list = [
            '现金质量弱' if cashflow.get('cash_quality_label') == '弱' else None,
            f'现金runway不足12个月({runway_months:.1f}月)' if _is_num(runway_months) and runway_months < 12 else None,
            '营运资本风险' if any(('应收' in str(x)) or ('存货' in str(x)) for x in wc_risks) else None,
            f'风险因素扣分{risk_factors.get("total_penalty", 0)}' if _is_num(risk_factors.get('total_penalty')) and risk_factors.get('total_penalty') > 0 else None,
        ]
        long_term_penalty_reasons_list = [r for r in long_term_penalty_reasons_list if r]

        return {
            'ipo_trade_score': ipo_trade_score,
            'strict_ipo_score': strict_ipo_score,
            'raw_trade_signal_score': raw_trade_signal_score,
            'strict_scoring_profile': self.STRICT_SCORING_PROFILE,
            'ipo_trade_label': ipo_trade_label,
            'long_term_score': long_term_score,
            'raw_long_term_score_before_penalty': raw_long_term_score_before_penalty,
            'long_term_penalty': penalty,
            'long_term_penalty_reasons': long_term_penalty_reasons_list,
            'long_term_label': long_term_label,
            'valuation_pressure_label': valuation_pressure,
            'subscription_recommendation': recommendation,
            'recommendation_reasons': reasons[:5],
            'strict_cap_reasons': strict_cap_reasons,
            'fisher_label': fisher_label,
            'lynch_label': lynch_label,
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

        optimized = ScoringSystem._try_load_optimized_weights()
        if optimized:
            profile_name = 'live_heat' if (has_heat or has_market) else 'prospectus_only'
            return {
                'name': f'{profile_name}_optimized',
                'weights': optimized,
                'reason': '使用贝叶斯优化权重',
            }

        sw = SETTINGS.scoring
        if has_heat or has_market:
            return {
                'name': 'live_heat',
                'weights': {
                    'trade': sw.live_heat_trade,
                    'fundamental': sw.live_heat_fundamental,
                    'data_quality': sw.live_heat_data_quality,
                    'valuation': sw.live_heat_valuation,
                    'theme': sw.live_heat_theme,
                },
                'reason': '检测到有效超购/孖展数据',
            }
        else:
            return {
                'name': 'prospectus_only',
                'weights': {
                    'trade': sw.prospectus_trade,
                    'fundamental': sw.prospectus_fundamental,
                    'data_quality': sw.prospectus_data_quality,
                    'valuation': sw.prospectus_valuation,
                    'theme': sw.prospectus_theme,
                },
                'reason': '未检测到有效热度数据，使用招股书阶段权重',
            }

    @staticmethod
    def _try_load_optimized_weights():
        try:
            import yaml
            path = SETTINGS.backtest.optimized_weights_path
            with open(path) as f:
                opt = yaml.safe_load(f)
            if opt and opt.get("weights") and isinstance(opt["weights"], dict):
                w = opt["weights"]
                required = ["trade", "fundamental", "valuation", "theme", "data_quality"]
                if all(k in w for k in required):
                    logger.info("加载优化权重: %s", w)
                    return w
        except Exception:
            pass
        return None

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
                (_is_num(relative_ps_premium) and float(relative_ps_premium) > 80)
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
            peer_adj = -6
            reasons.append("同行估值明显偏贵：公司PS显著高于同行中位数")
        elif is_somewhat_overvalued:
            peer_adj = -3
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

    @staticmethod
    def _score_to_grade(score):
        if score >= 90:
            return 'A+'
        if score >= 80:
            return 'A'
        if score >= 70:
            return 'A-'
        if score >= 65:
            return 'B+'
        if score >= 55:
            return 'B'
        if score >= 45:
            return 'B-'
        if score >= 38:
            return 'C+'
        if score >= 30:
            return 'C'
        if score >= 20:
            return 'C-'
        return 'D'

    def _calculate_dimension_grades(self, scoring_result, prospectus_info, ipo_data):
        stock_quality = prospectus_info.get('stock_quality') or {}
        business = prospectus_info.get('business_breakdown') or {}
        peer_comparison = prospectus_info.get('peer_comparison') or {}
        cashflow = prospectus_info.get('cashflow') or {}
        customer_supplier = prospectus_info.get('customer_supplier') or {}
        valuation = prospectus_info.get('valuation') or {}

        fundamental_score = stock_quality.get('score', 0)
        if business.get('profit_revenue_mismatch'):
            fundamental_score -= 5
        fundamental_score = max(0, min(100, fundamental_score))
        fundamental_detail_parts = []
        if fundamental_score >= 70:
            fundamental_detail_parts.append('基本面扎实')
        elif fundamental_score >= 50:
            fundamental_detail_parts.append('基本面尚可')
        else:
            fundamental_detail_parts.append('基本面偏弱')
        if business.get('profit_revenue_mismatch'):
            fundamental_detail_parts.append('利润支柱与收入支柱不同，业务结构存在风险')
        stock_label = stock_quality.get('label', '')
        if stock_label and stock_label != '缺失':
            fundamental_detail_parts.append(f'质地{stock_label}')
        fundamental_detail = '；'.join(fundamental_detail_parts) if fundamental_detail_parts else '基本面数据不足'

        scarcity_raw = peer_comparison.get('scarcity_score', 0) * 10
        dominant_share_pct = peer_comparison.get('dominant_share_pct')
        scarcity_bonus = 0
        if _is_num(dominant_share_pct):
            if dominant_share_pct >= 50:
                scarcity_bonus = 15
            elif dominant_share_pct >= 30:
                scarcity_bonus = 10
        scarcity_score = max(0, min(100, scarcity_raw + scarcity_bonus))
        scarcity_detail_parts = []
        if peer_comparison.get('scarcity_score', 0) >= 7:
            scarcity_detail_parts.append('赛道高度稀缺')
        elif peer_comparison.get('scarcity_score', 0) >= 4:
            scarcity_detail_parts.append('赛道有一定稀缺性')
        else:
            scarcity_detail_parts.append('赛道稀缺性一般')
        if scarcity_bonus > 0:
            scarcity_detail_parts.append(f'市场份额领先({dominant_share_pct:.0f}%)')
        scarcity_detail = '；'.join(scarcity_detail_parts) if scarcity_detail_parts else '稀缺性数据不足'

        fq_score = 50
        fq_detail_parts = []
        ocf = cashflow.get('operating_cash_flow')
        if _is_num(ocf) and ocf > 0:
            fq_score += 15
            fq_detail_parts.append('经营现金流为正')
        else:
            fq_detail_parts.append('经营现金流偏弱')
        adj_trend = cashflow.get('adjusted_profit_trend_label')
        if adj_trend == '改善':
            fq_score += 10
            fq_detail_parts.append('经调整利润趋势改善')
        elif adj_trend == '恶化':
            fq_score -= 10
            fq_detail_parts.append('经调整利润趋势恶化')
        top5_cust = customer_supplier.get('top5_customer_revenue_pct')
        if _is_num(top5_cust) and top5_cust > 50:
            fq_score -= 10
            fq_detail_parts.append(f'客户集中度高(Top5 {top5_cust:.0f}%)')
        pay_days_latest = cashflow.get('payables_turnover_days_latest')
        pay_days_prev = cashflow.get('payables_turnover_days_prev')
        if _is_num(pay_days_latest) and _is_num(pay_days_prev) and pay_days_prev > 0 and pay_days_latest > pay_days_prev:
            fq_score -= 5
            fq_detail_parts.append('应付周转天数增加')
        fq_score = max(0, min(100, fq_score))
        if not fq_detail_parts:
            fq_detail_parts.append('财务质量数据有限')
        fq_detail = '；'.join(fq_detail_parts)

        val_score = scoring_result.get('valuation_score', 0)
        valuation_score_dim = max(0, min(100, val_score))
        val_detail_parts = []
        val_label = valuation.get('valuation_label', '')
        if val_label and val_label != '缺失':
            val_detail_parts.append(f'估值标签: {val_label}')
        rel_ps_premium = peer_comparison.get('relative_weighted_ps_premium_pct')
        if rel_ps_premium is None:
            rel_ps_premium = peer_comparison.get('relative_ps_premium_pct')
        if _is_num(rel_ps_premium):
            if rel_ps_premium > 50:
                val_detail_parts.append(f'同行PS溢价{rel_ps_premium:.0f}%，偏贵')
            elif rel_ps_premium > 0:
                val_detail_parts.append(f'同行PS溢价{rel_ps_premium:.0f}%')
            else:
                val_detail_parts.append('相对同行估值合理')
        if not val_detail_parts:
            val_detail_parts.append('估值数据不足')
        val_detail = '；'.join(val_detail_parts)

        trade_score_val = scoring_result.get('trade_score', 0)
        ipo_trade_score_dim = max(0, min(100, trade_score_val))
        ipo_detail_parts = []
        if ipo_trade_score_dim >= 70:
            ipo_detail_parts.append('打新交易信号强')
        elif ipo_trade_score_dim >= 50:
            ipo_detail_parts.append('打新交易信号中等')
        else:
            ipo_detail_parts.append('打新交易信号偏弱')
        cornerstone_analysis = prospectus_info.get('cornerstone_analysis') or {}
        cs_score = cornerstone_analysis.get('score')
        if _is_num(cs_score) and cs_score >= 15:
            ipo_detail_parts.append('基石支撑较好')
        elif _is_num(cs_score) and cs_score > 0:
            ipo_detail_parts.append('基石一般')
        sc = scoring_result.get('components', {})
        heat_score = sc.get('heat', {}).get('score', 0)
        if heat_score >= 40:
            ipo_detail_parts.append('市场情绪偏强')
        if not ipo_detail_parts:
            ipo_detail_parts.append('打新交易数据有限')
        ipo_detail = '；'.join(ipo_detail_parts)

        return {
            'fundamental': {
                'grade': self._score_to_grade(fundamental_score),
                'score': fundamental_score,
                'detail': fundamental_detail,
            },
            'scarcity': {
                'grade': self._score_to_grade(scarcity_score),
                'score': scarcity_score,
                'detail': scarcity_detail,
            },
            'financial_quality': {
                'grade': self._score_to_grade(fq_score),
                'score': fq_score,
                'detail': fq_detail,
            },
            'valuation_attractiveness': {
                'grade': self._score_to_grade(valuation_score_dim),
                'score': valuation_score_dim,
                'detail': val_detail,
            },
            'ipo_trade_elasticity': {
                'grade': self._score_to_grade(ipo_trade_score_dim),
                'score': ipo_trade_score_dim,
                'detail': ipo_detail,
            },
        }

    def calculate(self, ipo, prospectus_info, signal_components=None):
        reasons = []

        components = {
            'heat': {'score': 0, 'label': '缺失', 'detail': '未获取到超购倍数'},
            'quality': {'score': 0, 'label': '缺失', 'detail': '未获取到招股书关键财务数据'},
            'cornerstone': {'score': 0, 'label': '缺失', 'detail': '未获取到基石分析'},
            'scale': {'score': 0, 'label': '缺失', 'detail': '未获取到公开集资额'},
        }

        sw = SETTINGS.scoring
        _HEAT_SCORE_MAX = sw.heat_max
        _QUALITY_SCORE_MAX = sw.quality_max
        _SCALE_SCORE_MAX = sw.scale_max
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
        has_cornerstone_section = cornerstone_analysis.get('has_cornerstone_section', False)
        
        if _is_num(cornerstone_score) and has_cornerstone_section:
            # 改进映射：使用分段映射提高70-90分常见段的区分度
            if cornerstone_score >= 90:
                component_score = 19
            elif cornerstone_score >= 80:
                component_score = 17
            elif cornerstone_score >= 70:
                component_score = 15
            elif cornerstone_score >= 60:
                component_score = 12
            elif cornerstone_score >= 50:
                component_score = 10
            elif cornerstone_score >= 40:
                component_score = 8
            elif cornerstone_score >= 30:
                component_score = 6
            else:
                component_score = 4
            component_score = min(20, component_score)
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
        elif has_cornerstone_section:
            components['cornerstone']['score'] = 2
            components['cornerstone']['label'] = "弱基石"
            components['cornerstone']['detail'] = "有基石章节，但未识别到强基石投资者"

        total_fund = ipo.get('total_fund')
        public_offer = ipo.get('public_offer')
        public_offer_ratio = prospectus_info.get('public_offer_ratio_pct')
        if _is_num(public_offer) and _is_num(public_offer_ratio) and public_offer_ratio > 0:
            total_fund = public_offer / (public_offer_ratio / 100)
        elif total_fund is None:
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
        market_bonus = 0
        market_detail = ""
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
                market_bonus = 5
                market_detail = "趋势继续走强"
            elif trend_gap >= 0.1:
                market_bonus = 4
                market_detail = "趋势偏强"
            elif trend_gap >= -0.1:
                market_bonus = 3
                market_detail = "趋势平稳"
            else:
                market_bonus = 1
                market_detail = "趋势回落"
            market_detail += f"，预测超购 {forecast_over:.2f} 倍，较{base_label}变化 {trend_gap*100:.1f}%"
        else:
            if market_heat == "极热":
                market_bonus = 5
                market_detail = "市场极热"
                reasons.append("市场极度火热")
            elif market_heat == "热门":
                market_bonus = 4
                market_detail = "市场热门"
                reasons.append("市场热门")
            elif market_heat == "温和":
                market_bonus = 3
                market_detail = "市场温和"
        if market_bonus > 0 and components['heat']['score'] > 0:
            components['heat']['score'] = min(_HEAT_SCORE_MAX, components['heat']['score'] + market_bonus)
            if market_detail:
                components['heat']['detail'] += f"；{market_detail}"
        elif market_bonus > 0 and components['heat']['score'] == 0:
            components['heat']['score'] = market_bonus
            components['heat']['label'] = '市场热度'
            components['heat']['detail'] = market_detail

        subscription_raw = components['heat']['score'] + components['scale']['score'] + components['cornerstone']['score']
        subscription_raw_max = _HEAT_SCORE_MAX + _SCALE_SCORE_MAX + _CORNERSTONE_SCORE_MAX
        subscription_score = min(100, round(subscription_raw / subscription_raw_max * 100)) if subscription_raw_max else 0
        fundamental_score = min(100, round(components['quality']['score'] / _QUALITY_SCORE_MAX * 100))

        sc = signal_components or {}

        trade_raw = (
            components['heat']['score'] + components['scale']['score']
            + components['cornerstone']['score']
        )
        trade_max = _HEAT_SCORE_MAX + _SCALE_SCORE_MAX + _CORNERSTONE_SCORE_MAX
        if sc:
            trade_raw += sc.get('real_money', {}).get('score', 0)
            trade_raw += sc.get('float_structure', {}).get('score', 0)
            trade_max += 20 + 15
        trade_score = min(100, round(trade_raw / trade_max * 100)) if trade_max else 0

        val_framework = sc.get('valuation_framework', {}) if sc else {}
        val_raw = val_framework.get('score', 0)
        val_max = val_framework.get('max_score', 20)
        # 使用平方根归一化，缓解缺失项导致的分数断崖
        if val_max > 0 and val_raw > 0:
            ratio = val_raw / val_max
            valuation_score = min(100, round((ratio ** 0.75) * 100))
        elif val_raw == 0:
            valuation_score = 0
            reasons.append("估值框架数据缺失，估值维度按0分计")
        else:
            valuation_score = 0

        theme_raw = 0
        theme_max = 35
        if sc:
            theme_raw += sc.get('mainline_beta', {}).get('score', 0)
            theme_raw += sc.get('stock_connect_path', {}).get('score', 0)
        peer_comparison = prospectus_info.get('peer_comparison', {}) or {}
        scarcity = peer_comparison.get('scarcity_score', 0)
        theme_raw += min(10, scarcity)
        theme_score = min(100, round(theme_raw / theme_max * 100)) if theme_raw else 0

        weight_profile = self._detect_weight_profile(ipo)
        trade_w = weight_profile['weights']['trade']
        fundamental_w = weight_profile['weights']['fundamental']
        data_quality_w = weight_profile['weights'].get('data_quality', 0)
        valuation_w = weight_profile['weights']['valuation']
        theme_w = weight_profile['weights']['theme']

        dq_score_raw = sc.get('data_quality', {}).get('score', 0) if sc else 0
        data_quality_score_pct = min(100, round(dq_score_raw / 5 * 100)) if dq_score_raw else 0

        raw_final = (
            trade_score * trade_w
            + fundamental_score * fundamental_w
            + data_quality_score_pct * data_quality_w
            + valuation_score * valuation_w
            + theme_score * theme_w
        )

        peer_adj, val_penalty = self._calc_valuation_adjustments(ipo, prospectus_info, reasons)

        score = round(raw_final + peer_adj + val_penalty)
        strategy_scores = self._build_strategy_scores(
            prospectus_info, trade_score, fundamental_score,
            valuation_score, theme_score,
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
                cap_value = SETTINGS.cornerstone.score_cap_severe_red_flags
                score = min(score, cap_value)
                cap_reason = f"严重基石问题封顶{cap_value}: {[f for f in severe_flags]}"
                if penalty_reason:
                    penalty_reason += f"; {cap_reason}"
                else:
                    penalty_reason = cap_reason

        final_score_after_cap = score

        score_trace = {
            'raw_weighted_score': round(raw_final, 2),
            'peer_adj': peer_adj,
            'val_penalty': val_penalty,
            'risk_penalty_placeholder': 0,
            'cap_reason': cap_reason,
            'final_score_before_cap': final_score_before_cap,
            'final_score_after_cap': final_score_after_cap,
            'weight_profile': weight_profile,
            'trade_score': trade_score,
            'fundamental_score': fundamental_score,
            'valuation_score': valuation_score,
            'theme_score': theme_score,
            'ipo_trade_score': strategy_scores['ipo_trade_score'],
            'strict_ipo_score': strategy_scores['strict_ipo_score'],
            'raw_trade_signal_score': strategy_scores['raw_trade_signal_score'],
            'strict_scoring_profile': strategy_scores['strict_scoring_profile'],
            'strict_cap_reasons': strategy_scores.get('strict_cap_reasons', []),
            'long_term_score': strategy_scores['long_term_score'],
            'raw_long_term_score_before_penalty': strategy_scores.get('raw_long_term_score_before_penalty'),
            'long_term_penalty': strategy_scores.get('long_term_penalty'),
            'long_term_penalty_reasons': [r for r in strategy_scores.get('long_term_penalty_reasons', []) if r],
        }

        # 为 components 补充 100 分制归一化分数，使维度拆解与评分概览量纲一致
        _COMPONENT_MAXS = {
            'heat': _HEAT_SCORE_MAX,
            'quality': _QUALITY_SCORE_MAX,
            'scale': _SCALE_SCORE_MAX,
            'cornerstone': _CORNERSTONE_SCORE_MAX,
        }
        for ckey, cmax in _COMPONENT_MAXS.items():
            if ckey in components:
                raw = components[ckey].get('score', 0)
                components[ckey]['max_score'] = cmax
                components[ckey]['normalized_score'] = min(100, round(raw / cmax * 100)) if cmax else 0

        scoring_result = {
            'score': min(100, max(0, score)),
            'subscription_score': subscription_score,
            'fundamental_score': fundamental_score,
            'trade_score': trade_score,
            'valuation_score': valuation_score,
            'theme_score': theme_score,
            **strategy_scores,
            'raw_trade_signal_score': strategy_scores['raw_trade_signal_score'],
            'strict_ipo_score': strategy_scores['strict_ipo_score'],
            'strict_scoring_profile': strategy_scores['strict_scoring_profile'],
            'reasons': reasons,
            'components': components,
            'weight_profile': weight_profile,
            'score_weights_note': (
                f"权重: trade={trade_w:.0%} fundamental={fundamental_w:.0%} "
                f"valuation={valuation_w:.0%} theme={theme_w:.0%} "
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
                'raw_trade_signal_score': strategy_scores['raw_trade_signal_score'],
                'strict_ipo_score': strategy_scores['strict_ipo_score'],
                'strict_scoring_profile': strategy_scores['strict_scoring_profile'],
                'cornerstone_red_flags': cornerstone_red_flags,
                'final_score_before_cap': final_score_before_cap,
                'final_score_after_cap': final_score_after_cap,
                'cap_reason': cap_reason,
            },
        }

        scoring_result['dimension_grades'] = self._calculate_dimension_grades(scoring_result, prospectus_info, ipo)

        return scoring_result
