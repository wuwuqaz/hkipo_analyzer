"""投研叙事综合分析器。

把已抽取的点状指标组织成接近人工投研报告的判断框架：
基本面质量、商业模式、估值压力、做空视角、催化与反证指标。
"""

from __future__ import annotations

from ..settings import SETTINGS
from ..utils import _is_num


class InvestmentThesisAnalyzer:
    """生成面向打新/中长期研究的综合投研结论。"""

    def analyze(self, prospectus_info: dict, text: str = "", ipo_data: dict | None = None) -> dict:
        result = {
            "overall_tone": "中性",
            "one_line_conclusion": "",
            "coverage": {
                "business_model": False,
                "financial_quality": False,
                "valuation": False,
                "short_seller_case": False,
                "catalysts": True,
                "invalidation_signals": True,
            },
            "fundamental_diagnosis": [],
            "business_model_takeaways": [],
            "valuation_takeaways": [],
            "short_seller_case": {
                "bear_points": [],
                "target_price_range_hkd": None,
                "target_ps_range": None,
                "method": None,
            },
            "catalysts": [],
            "invalidation_signals": [],
            "missing_angles": [],
            "confidence": "derived",
        }

        revenue = prospectus_info.get("revenue")
        revenue_y1 = prospectus_info.get("revenue_y1")
        net_profit = prospectus_info.get("net_profit")
        net_profit_y1 = prospectus_info.get("net_profit_y1")
        adjusted_profit = prospectus_info.get("adjusted_profit_latest_RMB")
        cashflow = prospectus_info.get("cashflow") or {}
        business = prospectus_info.get("business_breakdown") or {}
        valuation = prospectus_info.get("valuation") or {}
        peer = prospectus_info.get("peer_comparison") or {}
        risks = (prospectus_info.get("risk_factors") or {}).get("risks", {}) or {}

        self._fill_fundamental(result, revenue, revenue_y1, net_profit, net_profit_y1, adjusted_profit, cashflow)
        self._fill_business_model(result, business, peer)
        self._fill_valuation(result, valuation, peer)
        self._fill_short_case(result, prospectus_info, valuation, peer, cashflow, risks)
        self._fill_catalysts(result, prospectus_info, cashflow, business, risks)
        self._fill_invalidation_signals(result)
        self._fill_missing_angles(result, prospectus_info, business, peer)
        self._finalize_tone(result)

        return result

    @staticmethod
    def _pct_change(latest, previous):
        if not _is_num(latest) or not _is_num(previous) or previous == 0:
            return None
        return (latest - previous) / abs(previous) * 100

    def _fill_fundamental(self, result, revenue, revenue_y1, net_profit, net_profit_y1, adjusted_profit, cashflow):
        diagnosis = result["fundamental_diagnosis"]
        rev_growth = self._pct_change(revenue, revenue_y1)
        profit_growth = self._pct_change(net_profit, net_profit_y1)

        if rev_growth is not None:
            result["coverage"]["financial_quality"] = True
            if rev_growth >= 25:
                diagnosis.append(f"收入增长较快(+{rev_growth:.1f}%)，属于高增长发行人")
            elif rev_growth >= 0:
                diagnosis.append(f"收入保持增长(+{rev_growth:.1f}%)")
            else:
                diagnosis.append(f"收入同比下滑({rev_growth:.1f}%)")

        if profit_growth is not None:
            result["coverage"]["financial_quality"] = True
            if profit_growth < -30:
                diagnosis.append(f"净利润明显恶化({profit_growth:.1f}%)，增长尚未转化为利润")
            elif profit_growth < 0:
                diagnosis.append(f"净利润同比下降({profit_growth:.1f}%)")

        if _is_num(net_profit) and net_profit < 0 and _is_num(adjusted_profit) and adjusted_profit > 0:
            diagnosis.append(f"账面亏损但经调整利润为正({adjusted_profit:.1f}m)，需区分一次性项目与经营质量")

        ocf = cashflow.get("operating_cash_flow")
        ocf_prev = cashflow.get("operating_cash_flow_prev")
        if _is_num(ocf) and ocf < 0:
            if _is_num(ocf_prev) and ocf_prev > 0:
                diagnosis.append(f"经营现金流转负({ocf:.1f}m)，现金流质量弱于收入增长")
            else:
                diagnosis.append(f"经营现金流为负({ocf:.1f}m)")

        for label, latest_key, prev_key in (
            ("存货", "inventory_amount", "inventory_amount_prev"),
            ("应收", "receivables_amount", "receivables_amount_prev"),
        ):
            change = self._pct_change(cashflow.get(latest_key), cashflow.get(prev_key))
            if change is not None and change >= 20:
                diagnosis.append(f"{label}较前期增加{change:.1f}%，营运资本占用上升")

    def _fill_business_model(self, result, business, peer):
        segments = business.get("segments") or []
        if not segments:
            return

        result["coverage"]["business_model"] = True
        takeaways = result["business_model_takeaways"]
        main = max(segments, key=lambda x: x.get("share_pct") or 0)
        main_name = main.get("name") or business.get("main_segment") or "主业"
        main_share = main.get("share_pct")
        main_margin = main.get("gross_margin_pct")

        if _is_num(main_share):
            takeaways.append(f"收入仍由{main_name}驱动，占比约{main_share:.1f}%")
        if _is_num(main_margin):
            if main_margin < 30:
                takeaways.append(f"{main_name}毛利率约{main_margin:.1f}%，硬件属性较强、利润率弹性有限")
            else:
                takeaways.append(f"{main_name}毛利率约{main_margin:.1f}%")

        higher_margin = [
            s for s in segments
            if _is_num(s.get("gross_margin_pct")) and _is_num(main_margin) and s["gross_margin_pct"] > main_margin + 3
        ]
        if higher_margin:
            names = "、".join(s.get("name", "") for s in higher_margin[:3] if s.get("name"))
            takeaways.append(f"更高毛利业务集中在{names}，是利润结构改善的观察点")

        dominant_share = peer.get("dominant_share_pct")
        dominant_segment = peer.get("dominant_segment")
        if _is_num(dominant_share) and dominant_share >= 20:
            takeaways.append(f"在{dominant_segment or '细分市场'}具备较高份额({dominant_share:.1f}%)")

    @staticmethod
    def _fill_valuation(result, valuation, peer):
        ps = valuation.get("ps_ratio") or peer.get("company_ps")
        adj_pe = valuation.get("adjusted_pe_ratio")
        peer_ps = peer.get("peer_median_ps")
        premium = peer.get("relative_ps_premium_pct")
        takeaways = result["valuation_takeaways"]

        if _is_num(ps) or _is_num(adj_pe) or _is_num(peer_ps):
            result["coverage"]["valuation"] = True
        if _is_num(ps):
            takeaways.append(f"PS约{ps:.2f}x")
        if _is_num(adj_pe):
            takeaways.append(f"经调整PE约{adj_pe:.1f}x，利润口径下估值压力较高")
        if _is_num(peer_ps):
            if _is_num(premium):
                takeaways.append(f"相对同行PS中位数{peer_ps:.2f}x溢价约{premium:.1f}%")
            else:
                takeaways.append(f"同行PS中位数约{peer_ps:.2f}x")
        vp = peer.get("valuation_position")
        if vp and vp != "缺失":
            takeaways.append(f"同行定位：{vp}")

    def _fill_short_case(self, result, prospectus_info, valuation, peer, cashflow, risks):
        bear = result["short_seller_case"]["bear_points"]

        if _is_num(cashflow.get("operating_cash_flow")) and cashflow["operating_cash_flow"] < 0:
            bear.append("经营现金流为负，收入增长占用现金")
        if _is_num(peer.get("relative_ps_premium_pct")) and peer["relative_ps_premium_pct"] > 50:
            bear.append("PS显著高于同行，存在估值回归压力")
        if "competition_risk" in risks:
            bear.append("竞争风险已在招股书风险因素中出现")
        if "overseas_channel_tariff_risk" in risks:
            bear.append("海外渠道/关税风险可能压缩需求或毛利")

        peer_ps = peer.get("peer_median_ps")
        revenue = prospectus_info.get("revenue")
        shares = prospectus_info.get("shares_in_issue_post_listing")
        if _is_num(peer_ps) and _is_num(revenue) and _is_num(shares) and shares > 0:
            fx = self._financial_fx(prospectus_info)
            low_ps = max(0.1, peer_ps)
            high_ps = max(low_ps, min((valuation.get("ps_ratio") or low_ps), peer_ps * 1.5))
            revenue_hkd_m = revenue * fx
            low_price = revenue_hkd_m * low_ps * 1_000_000 / shares
            high_price = revenue_hkd_m * high_ps * 1_000_000 / shares
            result["short_seller_case"]["target_ps_range"] = [round(low_ps, 2), round(high_ps, 2)]
            result["short_seller_case"]["target_price_range_hkd"] = [round(low_price, 2), round(high_price, 2)]
            result["short_seller_case"]["method"] = "同行PS重估"

        result["coverage"]["short_seller_case"] = bool(bear or result["short_seller_case"]["target_price_range_hkd"])

    @staticmethod
    def _financial_fx(prospectus_info):
        currency = prospectus_info.get("financial_currency", "RMB")
        if currency == "RMB":
            return SETTINGS.fx.rmb_to_hkd
        if currency == "USD":
            return SETTINGS.fx.usd_to_hkd
        return 1.0

    @staticmethod
    def _fill_catalysts(result, prospectus_info, cashflow, business, risks):
        catalysts = result["catalysts"]
        if prospectus_info.get("results_date"):
            catalysts.append(f"配售结果公布({prospectus_info['results_date']})")
        if prospectus_info.get("listing_date"):
            catalysts.append(f"上市首日交易({prospectus_info['listing_date']})")
        catalysts.append("中报验证收入增长、经营现金流、存货和应收是否改善")

        if business.get("profit_revenue_mismatch"):
            catalysts.append("后续分部毛利结构是否继续向高毛利业务迁移")
        else:
            catalysts.append("后续分部结构和主业毛利率变化")

        if "overseas_channel_tariff_risk" in risks:
            catalysts.append("海外关税和渠道库存变化")
        catalysts.append("基石/IPO前股东解禁窗口")

    @staticmethod
    def _fill_invalidation_signals(result):
        result["invalidation_signals"] = [
            "收入继续高增长且经调整净利润同步恢复增长",
            "经营现金流转正，存货和应收增速回落",
            "核心业务毛利率企稳或高毛利业务占比提升",
            "同行估值中枢上移，PS溢价收窄",
            "主要风险因素未兑现，海外收入和渠道动销保持稳定",
        ]

    @staticmethod
    def _fill_missing_angles(result, prospectus_info, business, peer):
        if not business.get("segments"):
            result["missing_angles"].append("缺少按业务线收入/毛利拆分，无法判断利润驱动分部")
        if not peer.get("peer_median_ps") and not peer.get("peer_median_pe"):
            result["missing_angles"].append("缺少可量化同行估值，做空目标价只能定性")
        if not prospectus_info.get("cornerstone_analysis"):
            result["missing_angles"].append("缺少基石投资者质量分析")
        if not prospectus_info.get("geographic"):
            result["missing_angles"].append("缺少地域收入结构，出海风险判断不足")

    @staticmethod
    def _finalize_tone(result):
        text = " ".join(
            result["fundamental_diagnosis"]
            + result["valuation_takeaways"]
            + result["short_seller_case"]["bear_points"]
        )
        risk_points = 0
        for kw in ("经营现金流", "转负", "恶化", "溢价", "估值压力", "明显高于同行", "高于同行"):
            if kw in text:
                risk_points += 1

        if risk_points >= 4:
            tone = "谨慎"
        elif risk_points >= 2:
            tone = "中性偏谨慎"
        else:
            tone = "中性"
        result["overall_tone"] = tone

        if tone == "谨慎":
            result["one_line_conclusion"] = "公司增长和赛道有真实基础，但利润/现金流兑现不足，发行估值需要更多业绩验证。"
        elif tone == "中性偏谨慎":
            result["one_line_conclusion"] = "公司具备增长故事，但估值和财务质量仍需跟踪验证。"
        else:
            result["one_line_conclusion"] = "当前信息未显示强烈方向，需结合认购热度和后续财务验证。"
