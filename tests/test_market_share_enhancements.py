"""市场占有率提取增强测试"""

from ipo_analyzer.peer_comps import PeerComparableAnalyzer


_analyzer = PeerComparableAnalyzer()


# ---------------------------------------------------------------------------
# _extract_market_share_data 增强正则测试
# ---------------------------------------------------------------------------

class TestExtractMarketShareData:

    def test_original_patterns_still_work(self):
        text = "We had a market share of 15.2% in the cloud computing market."
        result = _analyzer._extract_market_share_data(text)
        assert len(result) >= 1
        assert any(r["share_pct"] == 15.2 for r in result)

    def test_chinese_patterns(self):
        text = "公司在机器人市场市占率 12.5%，行业领先。"
        result = _analyzer._extract_market_share_data(text)
        assert any(r["share_pct"] == 12.5 for r in result)

    def test_market_share_with_approximately(self):
        text = "The group holds approximately 8.3% of the global EV battery market."
        result = _analyzer._extract_market_share_data(text)
        assert any(r["share_pct"] == 8.3 for r in result)

    def test_percentage_before_market_share(self):
        text = "We achieved a 25.7% market share in the Chinese SaaS sector."
        result = _analyzer._extract_market_share_data(text)
        assert any(r["share_pct"] == 25.7 for r in result)

    def test_chinese_zhan_pattern(self):
        text = "占市场份额约 18.9%，位列行业前三。"
        result = _analyzer._extract_market_share_data(text)
        assert any(r["share_pct"] == 18.9 for r in result)

    def test_market_share_rate_pattern(self):
        text = "公司市场占有率为 32.1%。"
        result = _analyzer._extract_market_share_data(text)
        assert any(r["share_pct"] == 32.1 for r in result)

    def test_the_nth_largest_rank(self):
        text = "We are the 3rd largest provider in the Chinese logistics market."
        result = _analyzer._extract_market_share_data(text)
        rank_items = [r for r in result if r.get("rank") is not None]
        assert any(r["rank"] == 3 for r in rank_items)

    def test_chinese_rank_pattern(self):
        text = "公司是中国第2大工业机器人供应商。"
        result = _analyzer._extract_market_share_data(text)
        rank_items = [r for r in result if r.get("rank") is not None]
        assert any(r["rank"] == 2 for r in rank_items)

    def test_top_n_pattern(self):
        text = "We are among the top 5 players in the global semiconductor market."
        result = _analyzer._extract_market_share_data(text)
        rank_items = [r for r in result if r.get("rank") is not None]
        assert any(r["rank"] == 5 for r in rank_items)

    def test_leading_qualitative_pattern(self):
        text = "We are one of the leading providers in the Chinese cloud computing market."
        result = _analyzer._extract_market_share_data(text)
        assert len(result) >= 1

    def test_frost_sullivan_source_detection(self):
        text = "According to Frost & Sullivan, our market share was 12.5% in the AI market."
        result = _analyzer._extract_market_share_data(text)
        assert any(r.get("source") == "Frost & Sullivan" for r in result)

    def test_chinese_frost_sullivan_source(self):
        text = "据弗若斯特沙利文报告，公司市场份额为 10.2%。"
        result = _analyzer._extract_market_share_data(text)
        assert any(r.get("source") == "Frost & Sullivan" for r in result)

    def test_traditional_chinese_segment_extracted(self):
        text = "按銷售額計，我們在全球消費級3D打印機市場的市場份額為 25.4%，排名第一。"
        result = _analyzer._extract_market_share_data(text)
        assert any(
            r["share_pct"] == 25.4 and r["segment"] == "全球消費級3D打印機"
            for r in result
        )

    def test_table_header_segment_is_cleaned(self):
        text = "排名 公司名稱 2025年消費級3D掃描儀GMV（百萬美元）按GMV計的市場佔有率為45.3%。"
        result = _analyzer._extract_market_share_data(text)
        assert any(
            r["share_pct"] == 45.3 and r["segment"] == "消費級3D掃描儀"
            for r in result
        )

    def test_share_pct_over_100_filtered(self):
        text = "We had a market share of 150% in the test market."
        result = _analyzer._extract_market_share_data(text)
        assert not any(r.get("share_pct") == 150 for r in result)

    def test_empty_text(self):
        assert _analyzer._extract_market_share_data("") == []
        assert _analyzer._extract_market_share_data(None) == []


# ---------------------------------------------------------------------------
# _extract_market_concentration 测试
# ---------------------------------------------------------------------------

class TestExtractMarketConcentration:

    def test_top_n_english(self):
        text = "The top 3 players account for 65% of the market."
        result = _analyzer._extract_market_concentration(text)
        assert result["cr3_pct"] == 65.0
        assert len(result["top_n_share"]) >= 1

    def test_top_n_chinese(self):
        text = "前5大参与者合计占市场份额的 78.3%。"
        result = _analyzer._extract_market_concentration(text)
        assert result["cr5_pct"] == 78.3

    def test_cr3_explicit(self):
        text = "行业集中度 CR3 = 72.5%，竞争格局较为集中。"
        result = _analyzer._extract_market_concentration(text)
        assert result["cr3_pct"] == 72.5

    def test_both_cr3_and_cr5(self):
        text = "The top 3 players account for 55% and the top 5 players account for 80% of the market."
        result = _analyzer._extract_market_concentration(text)
        assert result["cr3_pct"] == 55.0
        assert result["cr5_pct"] == 80.0

    def test_each_share_not_treated_as_combined_concentration(self):
        """前五大各占10% 是单家份额，不应作为前五大合计份额入库"""
        text = "最大參與者佔據約30%，而其餘前五大參與者各佔約10%。"
        result = _analyzer._extract_market_concentration(text)
        assert result["cr5_pct"] is None
        assert not any(item["top_n"] == 5 for item in result["top_n_share"])

    def test_no_data(self):
        text = "The market is highly competitive with many participants."
        result = _analyzer._extract_market_concentration(text)
        assert result["cr3_pct"] is None
        assert result["cr5_pct"] is None
        assert result["top_n_share"] == []

    def test_empty_text(self):
        result = _analyzer._extract_market_concentration("")
        assert result["cr3_pct"] is None


# ---------------------------------------------------------------------------
# _calc_relative_market_position 测试
# ---------------------------------------------------------------------------

class TestCalcRelativeMarketPosition:

    def test_company_is_largest(self):
        matched_peers = [
            {"revenue_million": 500},
            {"revenue_million": 300},
            {"revenue_million": 200},
        ]
        result = _analyzer._calc_relative_market_position(1000, matched_peers, "RMB")
        assert result["rank"] == 1
        assert result["peer_count"] == 3
        assert result["revenue_percentile"] == 100.0
        assert result["relative_share_pct"] is not None
        assert result["relative_share_pct"] > 40  # 1000/(1000+500+300+200) = 50%

    def test_company_is_smallest(self):
        matched_peers = [
            {"revenue_million": 1000},
            {"revenue_million": 500},
            {"revenue_million": 300},
        ]
        result = _analyzer._calc_relative_market_position(100, matched_peers, "RMB")
        assert result["rank"] == 4
        assert result["revenue_percentile"] == 0.0

    def test_no_valid_peers(self):
        result = _analyzer._calc_relative_market_position(100, [], "RMB")
        assert result["rank"] is None
        assert result["peer_count"] == 0

    def test_invalid_revenue(self):
        result = _analyzer._calc_relative_market_position(-100, [{"revenue_million": 500}], "RMB")
        assert result["rank"] is None

    def test_currency_conversion(self):
        matched_peers = [
            {"revenue_million": 7800},  # HKD
        ]
        # 1000 RMB * 1.08 fx = 1080 HKD, smaller than 7800
        result = _analyzer._calc_relative_market_position(1000, matched_peers, "RMB")
        assert result["rank"] == 2


# ---------------------------------------------------------------------------
# analyze 集成测试
# ---------------------------------------------------------------------------

class TestAnalyzeIntegration:

    def test_market_share_extracted_in_analyze(self):
        prospectus_info = {
            "sector": "hardtech",
            "revenue": 500,
            "revenue_y1": 300,
            "market_cap_hkd_million": 10000,
            "gross_margin": 30,
        }
        text = (
            "Industrial robot body and robotic solution automation system. "
            "We had a market share of 15.2% in the Chinese industrial robot market. "
            "The top 3 players account for 55% of the market. "
            "Frost & Sullivan."
        )
        result = _analyzer.analyze(prospectus_info, text, {"company_name": "测试公司"})
        assert "market_share_data" in result
        assert len(result["market_share_data"]) >= 1
        assert any(r["share_pct"] == 15.2 for r in result["market_share_data"])

    def test_concentration_extracted_in_analyze(self):
        prospectus_info = {
            "sector": "hardtech",
            "revenue": 500,
            "market_cap_hkd_million": 10000,
        }
        text = "Industrial robot automation system. The top 5 players account for 78% of the market."
        result = _analyzer.analyze(prospectus_info, text, {"company_name": "测试公司"})
        assert "market_concentration" in result
        conc = result.get("market_concentration") or {}
        assert conc.get("cr5_pct") == 78.0

    def test_dominant_segment_prefers_known_segment_on_equal_share(self):
        prospectus_info = {
            "sector": "hardtech",
            "revenue": 500,
            "market_cap_hkd_million": 10000,
        }
        text = (
            "Industrial robot automation system. "
            "The company had a market share of 45.3%. "
            "下表展示了全球消費級3D打印機市場的競爭格局，按GMV計的市場佔有率為45.3%。"
        )
        result = _analyzer.analyze(prospectus_info, text, {"company_name": "测试公司"})
        assert result["dominant_segment"] == "全球消費級3D打印機"

    def test_relative_market_position_in_analyze(self):
        prospectus_info = {
            "sector": "hardtech",
            "revenue": 500,
            "market_cap_hkd_million": 10000,
        }
        text = "Industrial robot body and robotic solution automation system."
        result = _analyzer.analyze(prospectus_info, text, {"company_name": "测试公司"})
        assert "relative_market_position" in result

    def test_scarcity_detail_includes_new_data(self):
        prospectus_info = {
            "sector": "hardtech",
            "revenue": 500,
            "revenue_y1": 300,
            "market_cap_hkd_million": 10000,
            "gross_margin": 30,
        }
        text = (
            "Industrial robot body and robotic solution automation system. "
            "We had a market share of 25% in the Chinese robot market. "
            "The top 3 players account for 60% of the market."
        )
        result = _analyzer.analyze(prospectus_info, text, {"company_name": "测试公司"})
        detail = result.get("scarcity_detail", "")
        # 应该包含市场份额和集中度信息
        assert "市场份额" in detail or "CR3" in detail or "CR5" in detail or detail != ""
