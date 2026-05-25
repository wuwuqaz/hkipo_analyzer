"""招股书基本面质地分析 — ProspectusQualityAnalyzer (升级版：护城河 + 现金流 + 财务健康)"""

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

    @classmethod
    def _analyze_ocf_quality(cls, prospectus_info):
        """经营现金流质量分析 — 评估OCF对净利润和收入的覆盖度"""
        cf = prospectus_info.get('cashflow', {}) or {}
        net_profit = prospectus_info.get('net_profit')
        ocf = cf.get('operating_cash_flow')
        ocf_to_revenue = cf.get('ocf_to_revenue')
        ocf_to_net_profit = cf.get('ocf_to_net_profit')
        qt = SETTINGS.prospectus_quality
        score = 0
        reasons = []

        if not _is_num(ocf):
            return 0, ['经营现金流数据缺失'], {}

        if _is_num(ocf_to_revenue):
            if ocf_to_revenue >= qt.ocf_to_revenue_strong:
                score += 12
                reasons.append(f"经营现金流/收入={ocf_to_revenue:.1%}，现金流充裕")
            elif ocf_to_revenue >= qt.ocf_to_revenue_good:
                score += 8
                reasons.append(f"经营现金流/收入={ocf_to_revenue:.1%}，现金流健康")
            elif ocf_to_revenue >= 0:
                score += 4
                reasons.append(f"经营现金流/收入={ocf_to_revenue:.1%}，现金流一般")
            else:
                score -= 3
                reasons.append(f"经营现金流/收入={ocf_to_revenue:.1%}，经营现金流为负")

        if _is_num(ocf_to_net_profit) and _is_num(net_profit) and net_profit > 0:
            if ocf_to_net_profit >= qt.ocf_to_net_profit_strong:
                score += 8
                reasons.append(f"OCF/净利润={ocf_to_net_profit:.1f}，利润含金量高")
            elif ocf_to_net_profit >= qt.ocf_to_net_profit_good:
                score += 5
                reasons.append(f"OCF/净利润={ocf_to_net_profit:.1f}，利润质量良好")
            elif ocf_to_net_profit > 0:
                score += 2
                reasons.append(f"OCF/净利润={ocf_to_net_profit:.1f}，利润有一定现金支撑")

        detail = '；'.join(reasons[:3])
        return score, reasons, {'label': '强' if score >= 15 else ('中' if score >= 8 else ('弱' if score > 0 else '偏弱')), 'detail': detail or '现金流数据不足'}

    @classmethod
    def _analyze_moat_depth(cls, prospectus_info):
        """护城河深度分析 — 整合技术壁垒、赛道稀缺性、客户粘性"""
        rnd = prospectus_info.get('rnd_pipeline', {}) or {}
        peer = prospectus_info.get('peer_comparison', {}) or {}
        cs = prospectus_info.get('customer_supplier', {}) or {}
        business = prospectus_info.get('business_breakdown', {}) or {}
        qt = SETTINGS.prospectus_quality
        score = 0
        reasons = []

        moat_score = rnd.get('technology_moat_score', 0) if _is_num(rnd.get('technology_moat_score')) else 0
        if moat_score >= qt.moat_score_strong:
            score += 15
            reasons.append(f"技术壁垒强({moat_score}/10)")
        elif moat_score >= qt.moat_score_moderate:
            score += 8
            reasons.append(f"技术壁垒中等({moat_score}/10)")
        elif moat_score > 0:
            score += 3
            reasons.append(f"有一定技术积累({moat_score}/10)")

        scarcity = peer.get('scarcity_score', 0) if _is_num(peer.get('scarcity_score')) else 0
        if scarcity >= qt.scarcity_moat_strong:
            score += 10
            reasons.append(f"赛道高度稀缺(scarcity={scarcity}/10)")
        elif scarcity >= qt.scarcity_moat_moderate:
            score += 5
            reasons.append(f"赛道有一定稀缺性(scarcity={scarcity}/10)")

        dominant_pct = peer.get('dominant_share_pct')
        if _is_num(dominant_pct):
            if dominant_pct >= 30:
                score += 8
                reasons.append(f"市场份额领先({dominant_pct:.0f}%)")
            elif dominant_pct >= 10:
                score += 3
                reasons.append(f"具备一定市场份额({dominant_pct:.0f}%)")

        segment_moat = business.get('segment_moat_label', '')
        if segment_moat in ('本体驱动', '方案驱动'):
            score += 5
            reasons.append(f"主业护城河明确: {segment_moat}")

        customer_quality = cs.get('customer_quality_score', 0)
        if _is_num(customer_quality) and customer_quality >= 60:
            score += 5
            reasons.append("头部客户验证+复购体现粘性")

        top5_cust = cs.get('top5_customer_revenue_pct')
        if _is_num(top5_cust) and top5_cust > qt.customer_concentration_high:
            score -= 3
            reasons.append(f"客户集中度过高(Top5={top5_cust:.0f}%)，护城河存疑")

        if not reasons:
            reasons.append("护城河数据有限，按中性评估")

        detail = '；'.join(reasons[:4])
        return score, reasons, {'label': '强' if score >= 20 else ('中' if score >= 10 else '偏弱'), 'detail': detail}

    @classmethod
    def _analyze_financial_health(cls, prospectus_info):
        """财务健康度分析 — 现金跑道、营运资本、融资依赖"""
        cf = prospectus_info.get('cashflow', {}) or {}
        profitable = prospectus_info.get('profitable')
        qt = SETTINGS.prospectus_quality
        score = 0
        reasons = []

        cash_runway = cf.get('cash_runway_years')
        if _is_num(cash_runway):
            if cash_runway >= qt.cash_runway_strong:
                score += 12
                reasons.append(f"现金跑道充裕({cash_runway:.1f}年)")
            elif cash_runway >= qt.cash_runway_good:
                score += 7
                reasons.append(f"现金跑道尚可({cash_runway:.1f}年)")
            elif cash_runway >= 1:
                score += 3
                reasons.append(f"现金跑道偏紧({cash_runway:.1f}年)")
            else:
                score -= 5
                reasons.append(f"现金跑道不足1年({cash_runway:.1f}年)，融资紧迫")

        monthly_burn = cf.get('monthly_cash_burn')
        cash_balance = cf.get('cash_and_cash_equivalents')
        if _is_num(monthly_burn) and _is_num(cash_balance) and monthly_burn > 0:
            burn_ratio = monthly_burn / cash_balance
            if burn_ratio > 0.5:
                score -= 3
                reasons.append(f"月耗现金/余额={burn_ratio:.1%}，烧钱速度快")

        inv_days = cf.get('inventory_turnover_days_latest')
        rec_days = cf.get('receivables_turnover_days_latest')
        if _is_num(inv_days) and inv_days > 200:
            score -= 3
            reasons.append(f"存货周转偏慢({inv_days:.0f}天)")
        if _is_num(rec_days) and rec_days > 180:
            score -= 3
            reasons.append(f"应收周转偏慢({rec_days:.0f}天)")

        working_cap_label = cf.get('working_capital_pressure_label', '')
        if '高' in str(working_cap_label):
            score -= 4
            reasons.append("营运资本压力高")

        receivables_growth = cf.get('receivables_growth_vs_revenue')
        if _is_num(receivables_growth) and receivables_growth > 1.5:
            score -= 3
            reasons.append(f"应收增速远超收入({receivables_growth:.1f}x)，含金量存疑")

        financing_dep = cf.get('financing_dependency_label', '')
        if '高' in str(financing_dep):
            score -= 4
            reasons.append("融资依赖度高，造血能力不足")

        if profitable is True:
            score += 5
            reasons.append("已盈利，财务自循环能力强")

        if not reasons:
            reasons.append("财务健康数据有限，按中性评估")

        detail = '；'.join(reasons[:4])
        return score, reasons, {'label': '强' if score >= 15 else ('中' if score >= 8 else '偏弱'), 'detail': detail or '财务健康数据不足'}

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
        net_profit = prospectus_info.get('net_profit')
        net_profit_y1 = prospectus_info.get('net_profit_y1')
        net_margin = None
        profit_growth = None
        quality_cap = 100
        cap_reasons = []
        if _is_num(net_profit) and _is_num(revenue) and revenue > 0:
            net_margin = net_profit / revenue * 100
        if _is_num(net_profit) and _is_num(net_profit_y1) and abs(net_profit_y1) > 1e-9:
            profit_growth = (net_profit - net_profit_y1) / abs(net_profit_y1)
        if gross_margin is not None:
            gross_margin_pct = _normalize_gm(gross_margin)
            if gross_margin_pct >= qt.gross_margin_excellent:
                score += 25
                reasons.append(f"毛利率优秀({gross_margin_pct:.1f}%)")
            elif gross_margin_pct >= qt.gross_margin_good:
                score += 18
                reasons.append(f"毛利率良好({gross_margin_pct:.1f}%)")
            elif gross_margin_pct >= qt.gross_margin_fair:
                score += 12
                reasons.append(f"毛利率一般({gross_margin_pct:.1f}%)")
            else:
                score += 5
                reasons.append(f"毛利率偏低({gross_margin_pct:.1f}%)")

        if profitable is True:
            score += 25
            reasons.append("已实现盈利")
            if net_margin is not None:
                if net_margin < 3:
                    score -= 8
                    quality_cap = min(quality_cap, 70)
                    cap_reasons.append(f"净利率仅{net_margin:.1f}%")
                    reasons.append(f"净利率仅{net_margin:.1f}%，盈利质量偏薄")
                elif net_margin < 8:
                    score -= 4
                    quality_cap = min(quality_cap, 82)
                    cap_reasons.append(f"净利率偏低({net_margin:.1f}%)")
                    reasons.append(f"净利率偏低({net_margin:.1f}%)")
            if profit_growth is not None:
                if profit_growth < -0.30:
                    score -= 8
                    quality_cap = min(quality_cap, 75)
                    cap_reasons.append(f"净利润同比下滑{abs(profit_growth)*100:.1f}%")
                    reasons.append(f"净利润同比下滑{abs(profit_growth)*100:.1f}%")
                elif profit_growth < 0:
                    score -= 4
                    quality_cap = min(quality_cap, 85)
                    cap_reasons.append(f"净利润同比小幅下滑{abs(profit_growth)*100:.1f}%")
                    reasons.append(f"净利润同比小幅下滑{abs(profit_growth)*100:.1f}%")
        elif profitable is False:
            reasons.append("仍处亏损")
            profile = classify_company(prospectus_info, '')
            is_low_rev_biotech = profile.is_low_revenue_biotech
            if is_low_rev_biotech and gross_margin_pct is not None and gross_margin_pct >= SETTINGS.prospectus_quality.gross_margin_excellent:
                # Biotech 专用评分管线：降低盈利惩罚，引入管线质量评分
                rnd = prospectus_info.get('rnd_pipeline') or {}
                pipeline_label = rnd.get('pipeline_quality_label', '')
                moat_score = rnd.get('technology_moat_score', 0)
                clinical_stage = rnd.get('latest_clinical_stage', '')
                has_pipeline_data = bool(rnd) and pipeline_label
                is_quality_pipeline = pipeline_label == '强' and moat_score >= 7
                is_advanced_clinical = clinical_stage in ('Phase II', 'Phase III', 'Phase 2', 'Phase 3', 'NDA', 'BLA')
                
                # 盈利惩罚大幅降低（35→10），用管线质量分数替代
                score = max(0, score - 10)
                
                # 管线质量补偿评分（最高25分，替代传统盈利权重）
                if is_quality_pipeline and is_advanced_clinical:
                    pipeline_comp = 25
                    reasons.append(f"管线质量强({pipeline_label})，临床{clinical_stage}，管线补偿+{pipeline_comp}")
                elif is_quality_pipeline:
                    pipeline_comp = 20
                    reasons.append(f"管线质量强({pipeline_label})，管线补偿+{pipeline_comp}")
                elif pipeline_label == '强':
                    pipeline_comp = 15
                    reasons.append(f"管线质量强({pipeline_label})，管线补偿+{pipeline_comp}")
                elif pipeline_label in ('中', '中等'):
                    pipeline_comp = 10
                    reasons.append(f"管线质量中等({pipeline_label})，管线补偿+{pipeline_comp}")
                elif has_pipeline_data:
                    pipeline_comp = 5
                    reasons.append(f"管线质量偏弱({pipeline_label})，管线补偿+{pipeline_comp}")
                else:
                    pipeline_comp = 0
                    reasons.append("未提取到管线数据，无管线补偿")
                
                if pipeline_comp > 0:
                    score += pipeline_comp
                
                # 临床阶段额外加分（后期临床价值更高）
                if clinical_stage in ('Phase III', 'Phase 3', 'NDA', 'BLA'):
                    score += 10
                    reasons.append("临床后期/NDA阶段，管线成熟度高+10")
                elif clinical_stage in ('Phase II', 'Phase 2'):
                    score += 5
                    reasons.append("临床中期阶段+5")
            else:
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
                score += 15
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
            if gross_margin_pct < 20:
                quality_cap = min(quality_cap, 82)
                cap_reasons.append(f"毛利率低于20%({gross_margin_pct:.1f}%)")
        if profitable is True and net_margin is not None and net_margin < 8:
            risk_flags.append("净利率偏薄")
        if profit_growth is not None and profit_growth < 0:
            risk_flags.append("净利润同比下滑")
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
            # Biotech 专用加分路径
            profile = classify_company(prospectus_info, '')
            if profile.is_biotech:
                if rnd.get('pipeline_quality_label') == '强':
                    fisher_points += 1
                    fisher_reasons.append('管线质量强，具备平台价值')
                clinical_stage = rnd.get('latest_clinical_stage', '')
                if clinical_stage in ('Phase III', 'Phase 3', 'NDA', 'BLA', 'approved'):
                    lynch_points += 1
                    lynch_reasons.append('临床后期/已上市，商业化确定性高')
                if rnd.get('technology_moat_score', 0) >= 7:
                    fisher_points += 1
                    fisher_reasons.append('技术壁垒高，具备长期竞争优势')

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

        ocf_score, ocf_reasons, ocf_dim = self._analyze_ocf_quality(prospectus_info)
        score += ocf_score
        reasons.extend(ocf_reasons[:2])
        dimensions['ocf_quality'] = ocf_dim
        if ocf_dim.get('label') == '强':
            fisher_points += 1
            lynch_points += 1
            fisher_reasons.append('经营现金流质量强')
            lynch_reasons.append('现金流质量支持长期经营')

        moat_score, moat_reasons, moat_dim = self._analyze_moat_depth(prospectus_info)
        score += moat_score
        reasons.extend(moat_reasons[:2])
        dimensions['moat_depth'] = moat_dim
        if moat_dim.get('label') == '强':
            fisher_points += 1
            lynch_points += 1
            fisher_reasons.append('护城河深度强')
            lynch_reasons.append('护城河为长线持有提供安全垫')
        elif moat_dim.get('label') == '中':
            fisher_points += 0

        health_score, health_reasons, health_dim = self._analyze_financial_health(prospectus_info)
        score += health_score
        reasons.extend(health_reasons[:2])
        dimensions['financial_health'] = health_dim
        if health_dim.get('label') == '强':
            fisher_points += 1
            lynch_points += 1
            fisher_reasons.append('财务健康度高')
            lynch_reasons.append('财务健康支持长期经营')
        elif health_dim.get('label') == '偏弱':
            lynch_reasons.append('财务健康偏弱，长持需关注资金压力')

        # === 新增：管理层治理维度评分 ===
        mg = prospectus_info.get('management_governance', {})
        if mg.get('management_score') and mg.get('confidence') != 'missing':
            mg_score = mg['management_score']
            score += round(mg_score * 0.15)  # 权重15%
            if mg.get('label') == '优秀':
                reasons.append(f"管理层治理优秀(经验{mg.get('management_experience_years')}年)")
                fisher_points += 1
                fisher_reasons.append('管理层治理优秀')
            elif mg.get('label') == '良好':
                reasons.append("管理层治理良好")
                fisher_points += 0.5
            dimensions['management_governance'] = {
                'label': mg.get('label', '缺失'),
                'detail': f"核心经验{mg.get('management_experience_years')}年，创始人持股{mg.get('founder_ownership_pct')}%",
            }

        # === 新增：资产负债维度评分 ===
        bs = prospectus_info.get('balance_sheet', {})
        if bs.get('balance_sheet_score') and bs.get('confidence') != 'missing':
            bs_score = bs['balance_sheet_score']
            score += round(bs_score * 0.15)  # 权重15%
            if bs.get('risk_flags'):
                for flag in bs['risk_flags'][:2]:
                    reasons.append(f"资产负债风险: {flag}")
                    lynch_reasons.append(f'资产负债风险: {flag}')
            dimensions['balance_sheet'] = {
                'label': bs.get('label', '缺失'),
                'detail': f"资产负债率{bs.get('asset_liability_ratio')*100:.1f}%" if bs.get('asset_liability_ratio') else "资产负债率--",
            }
            if bs.get('label') == '稳健':
                fisher_points += 1
                fisher_reasons.append('资产负债结构稳健')
            elif bs.get('label') == '高风险':
                lynch_reasons.append('资产负债结构高风险，长持需警惕')

        # === 新增：盈利可持续性维度评分 ===
        ps = prospectus_info.get('profit_sustainability', {})
        if ps.get('sustainability_score') and ps.get('confidence') != 'missing':
            ps_score = ps['sustainability_score']
            score += round(ps_score * 0.10)  # 权重10%
            non_recurring_ratio = ps.get('non_recurring_ratio')
            if _is_num(non_recurring_ratio) and non_recurring_ratio > 0.3:
                reasons.append(f"非经常性损益占比{non_recurring_ratio*100:.1f}%，盈利可持续性存疑")
                lynch_reasons.append('盈利依赖非经常性损益')
            elif _is_num(non_recurring_ratio):
                reasons.append(f"非经常性占比{non_recurring_ratio*100:.1f}%")
            dimensions['profit_sustainability'] = {
                'label': ps.get('label', '缺失'),
                'detail': f"非经常性占比{non_recurring_ratio*100:.1f}%" if _is_num(non_recurring_ratio) else "非经常性占比--",
            }
            if ps.get('label') in ('可持续', '基本可持续'):
                fisher_points += 1
                fisher_reasons.append('盈利质量可持续性良好')

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
        if score > quality_cap:
            if cap_reasons:
                reasons.append(f"质地分封顶{quality_cap}: {'；'.join(cap_reasons[:3])}")
            score = quality_cap

        fisher_label = self._lens_label(fisher_points, high=7, mid=4)
        lynch_label = self._lens_label(lynch_points, high=7, mid=4)
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
