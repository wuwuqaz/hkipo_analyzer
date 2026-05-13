"""招股书基本面质地分析 — ProspectusQualityAnalyzer"""

from .utils import _is_num, _normalize_gm
from .settings import SETTINGS
from .industry_router import classify_company


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

    @staticmethod
    def _lens_label(points, high=3, mid=2):
        if points >= high:
            return "适配"
        if points >= mid:
            return "部分适配"
        return "不适配"

    def analyze(self, prospectus_info):
        score = 0
        reasons = []
        dimensions = {}
        fisher_points = 0
        fisher_reasons = []
        lynch_points = 0
        lynch_reasons = []

        gross_margin = prospectus_info.get('gross_margin')
        gross_margin_pct = None
        revenue = prospectus_info.get('revenue')
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
            profile = classify_company(prospectus_info, '')
            is_low_rev_biotech = profile.is_low_revenue_biotech
            if is_low_rev_biotech and gross_margin_pct is not None and gross_margin_pct >= SETTINGS.prospectus_quality.gross_margin_excellent:
                # 根据管线质量调节惩罚力度：优质管线减轻惩罚
                rnd = prospectus_info.get('rnd_pipeline') or {}
                pipeline_label = rnd.get('pipeline_quality_label', '')
                moat_score = rnd.get('technology_moat_score', 0)
                clinical_stage = rnd.get('latest_clinical_stage', '')
                has_pipeline_data = bool(rnd) and pipeline_label
                is_quality_pipeline = pipeline_label == '强' and moat_score >= 7
                is_advanced_clinical = clinical_stage in ('Phase II', 'Phase III', 'Phase 2', 'Phase 3', 'NDA', 'BLA')
                if is_quality_pipeline and is_advanced_clinical:
                    gm_score_reduction = 5
                elif is_quality_pipeline:
                    gm_score_reduction = 10
                elif not has_pipeline_data:
                    gm_score_reduction = 15  # 管线数据缺失，使用中等惩罚
                else:
                    gm_score_reduction = 25
                score = max(0, score - gm_score_reduction)
                reasons.append(f"未盈利生物科技，毛利率{gross_margin_pct:.1f}%需结合管线阶段评估")
            if not is_low_rev_biotech:
                if _is_num(revenue) and revenue > 0:
                    score += 8
                    reasons.append("有营收但尚未盈利")
                rnd_info = prospectus_info.get('rnd_pipeline') or {}
                moat_val = rnd_info.get('technology_moat_score', 0)
                if _is_num(moat_val) and moat_val >= 4:
                    score += 5
                    reasons.append(f"技术壁垒{moat_val}/10有长期价值支撑")

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
            if growth >= qt.growth_good:
                fisher_points += 1
                fisher_reasons.append(f"收入保持增长({growth*100:.1f}%)")
            if growth >= qt.growth_strong:
                lynch_points += 1
                lynch_reasons.append(f"增长足够快({growth*100:.1f}%)")

        if profitable is True:
            net_profit = prospectus_info.get('net_profit')
            net_margin = None
            if _is_num(net_profit) and _is_num(revenue) and revenue > 0:
                net_margin = net_profit / revenue * 100
            dimensions['profitability'] = {
                'label': '盈利',
                'detail': "已实现盈利" + (f"，净利率{net_margin:.1f}%" if net_margin is not None else ''),
            }
            fisher_points += 1
            lynch_points += 2
            fisher_reasons.append("盈利能力已验证")
            lynch_reasons.append("盈利属性对长线持有友好")
        elif profitable is False:
            net_profit = prospectus_info.get('net_profit')
            adjusted_net_profit = (prospectus_info.get('cashflow') or {}).get('adjusted_net_profit')
            if adjusted_net_profit is not None and _is_num(adjusted_net_profit) and adjusted_net_profit > 0:
                reasons.append("经调整净利润为正({:.1f}m)，剔除一次性项目后实际盈利".format(adjusted_net_profit))
                score += 3
            dimensions['profitability'] = {
                'label': '亏损',
                'detail': "仍处亏损" + (f"，净亏损{abs(net_profit):.1f}（百万口径）" if _is_num(net_profit) else ''),
            }
            fisher_reasons.append("未盈利但可结合赛道与研发判断")
            lynch_reasons.append("未盈利，不是典型Peter Lynch可持有标的")
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
        profit_revenue_mismatch = (prospectus_info.get('business_breakdown') or {}).get('profit_revenue_mismatch', False)
        if profit_revenue_mismatch:
            risk_flags.append("利润支柱与收入支柱不同，业务结构存在风险")
            score -= 2

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
            val_label = str(valuation.get('valuation_label', ''))
            if any(x in val_label for x in ('合理', '低估', '赛道合理', 'PS辅助')):
                lynch_points += 1
                lynch_reasons.append('估值未明显失控')
            elif any(x in val_label for x in ('很贵', '明显偏贵', '估值压力')):
                lynch_reasons.append('估值偏贵，不像经典长线复利股')

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
            if business.get('business_model_label') in ('机器人本体为主', '机器人解决方案为主'):
                fisher_points += 1
                fisher_reasons.append(business.get('business_model_label'))
            if business.get('segment_moat_label') in ('本体驱动', '方案驱动'):
                fisher_points += 1
                fisher_reasons.append(f"主业属性：{business.get('segment_moat_label')}")

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
            customer_quality_score = cs.get('customer_quality_score', 0)
            if customer_quality_score:
                customer_bonus = round(min(15, customer_quality_score / 100 * 15))
                score += customer_bonus
                for reason in cs.get('customer_quality_reasons', [])[:2]:
                    reasons.append(f"客户质量: {reason}")
                dimensions['customer_quality'] = {
                    'label': cs.get('customer_quality_label', '--'),
                    'detail': cs.get('customer_validation_summary') or '头部客户验证待补充',
                }

        cf = prospectus_info.get('cashflow', {})
        if isinstance(cf, dict) and cf.get('cash_quality_label') not in ('缺失', None):
            dimensions['cashflow'] = {
                'label': cf.get('cash_quality_label', '--'),
                'detail': (
                    f"OCF/收入{cf.get('ocf_to_revenue', '--')}；"
                    f"上市前runway{cf.get('cash_runway_years', '--')}年；"
                    f"存货周转{cf.get('inventory_turnover_days_latest', '--')}天"
                ),
            }
            if cf.get('cash_quality_label') == '强':
                fisher_points += 1
                lynch_points += 1
                fisher_reasons.append('现金流质量较好')
                lynch_reasons.append('现金流支持长期经营')
            elif cf.get('cash_quality_label') == '弱':
                lynch_reasons.append('经营现金流偏弱，长持质量一般')
            if cf.get('inventory_turnover_days_latest') and cf.get('inventory_turnover_days_latest') > 200:
                fisher_reasons.append('存货周转偏慢')
                lynch_reasons.append('营运资本压力较重')

        growth_status = prospectus_info.get('growth_validation_status')
        growth_summary = prospectus_info.get('growth_validation_summary')
        if growth_status:
            dimensions['growth_validation'] = {
                'label': '已解释' if growth_status == 'explained' else '未解释',
                'detail': growth_summary or '',
            }

        rnd = prospectus_info.get('rnd_pipeline', {})
        if isinstance(rnd, dict) and rnd.get('pipeline_quality_label') not in ('缺失', None):
            dimensions['rnd'] = {
                'label': rnd.get('pipeline_quality_label', '--'),
                'detail': f"研发费率{rnd.get('rd_expense_ratio', '--')}%{' (B)' if rnd.get('rd_ratio_biotech') else ''}；管线{rnd.get('product_count_pipeline', '--')}个；技术壁垒{rnd.get('technology_moat_score', 0)}/10",
            }
            if rnd.get('hardtech_moat_label') in ('强', '中'):
                fisher_points += 1
                fisher_reasons.append('研发/专利/订单有硬证据')
            if rnd.get('backlog_amount') is not None:
                fisher_points += 1
                fisher_reasons.append('在手订单对可见度有帮助')

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
            if risk_f.get('total_penalty', 0) >= 5:
                fisher_reasons.append('重大风险因素偏多')
                lynch_reasons.append('风险红旗偏多')

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

        fisher_label = self._lens_label(fisher_points, high=5, mid=3)
        lynch_label = self._lens_label(lynch_points, high=5, mid=3)
        long_term_notes = []
        if fisher_reasons:
            long_term_notes.append("Fisher: " + "；".join(fisher_reasons[:4]))
        if lynch_reasons:
            long_term_notes.append("Lynch: " + "；".join(lynch_reasons[:4]))

        return {
            'label': label,
            'score': max(0, min(100, score)),
            'reasons': reasons,
            'dimensions': dimensions,
            'fisher_label': fisher_label,
            'fisher_reasons': fisher_reasons[:6],
            'lynch_label': lynch_label,
            'lynch_reasons': lynch_reasons[:6],
            'long_term_notes': ' ｜ '.join(long_term_notes),
        }
