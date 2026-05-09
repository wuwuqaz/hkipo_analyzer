"""招股书基本面质地分析 — ProspectusQualityAnalyzer"""

from .utils import _is_num, _normalize_gm, _contains_any, SECTOR_KEYWORDS
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
