#!/usr/bin/env python3
"""同行对比模块测试脚本"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import logging
logging.basicConfig(level=logging.INFO, format="%(message)s")

from ipo_analyzer.peer_comps import PeerComparableAnalyzer
from ipo_analyzer.analyzers import ValuationAnalyzer, BusinessBreakdownAnalyzer
from ipo_analyzer.scoring import SignalComponentAnalyzer, ScoringSystem, ProspectusQualityAnalyzer
from ipo_analyzer.utils import _is_num


def _build_mock_ipo(revenue=100, revenue_y1=50, net_profit=-10, gross_margin=45,
                   market_cap_hkd_million=2000, sector="hardtech",
                   segments=None, technology_moat=5, rnd_label="中等"):
    """构造模拟IPO数据"""
    return {
        "hk_code": "9999",
        "company_name": "测试公司",
        "prospectus_info": {
            "revenue": revenue,
            "revenue_y1": revenue_y1,
            "net_profit": net_profit,
            "gross_margin": gross_margin,
            "market_cap_hkd_million": market_cap_hkd_million,
            "offer_price": 10.0,
            "pro_forma_NTA_per_share_HKD": 2.0,
            "sector": sector,
            "business_breakdown": {
                "segments": segments or [{"name": "机器人", "share_pct": 80, "growth_pct": 50}],
                "growth_source": "产品快速放量",
            },
            "rnd_pipeline": {
                "technology_moat_score": technology_moat,
                "pipeline_quality_label": rnd_label,
                "rd_expense_ratio": 25.0,
            },
            "cornerstone_analysis": {
                "cornerstone_investors": [],
                "matched_investors": [],
                "score": 30,
                "label": "B级",
                "recommendation": "中性试水",
            },
        }
    }


def test_robot_comparison():
    """测试乐动机器人类似公司的同行对比"""
    print("\n" + "=" * 60)
    print("Test 1: 乐动机器人 (hardtech/robotics_visual_perception)")
    print("=" * 60)

    ipo = _build_mock_ipo(
        revenue=680,           # ~6.8亿收入 (M)
        revenue_y1=340,        # 翻倍增长
        net_profit=-90,        # 亏损
        gross_margin=44,
        market_cap_hkd_million=9100,  # 约91亿市值 → PS≈13.4x
        sector="hardtech",
        technology_moat=7,
        rnd_label="强",
        segments=[{"name": "智能割草机器人", "share_pct": 60, "growth_pct": 80},
                  {"name": "视觉感知系统", "share_pct": 25, "growth_pct": 60},
                  {"name": "算法模块", "share_pct": 15, "growth_pct": 40}],
    )

    pi = ipo["prospectus_info"]
    text = """
    Our company is a leading robotics and visual perception technology company.
    We develop advanced robot lawn mowers with lidar and sensor systems.
    Our autonomous algorithm module uses deep learning for visual perception.
    We face competition from other robotics companies in the intelligent driving space.
    Competitors: 速腾聚创 in lidar space, 石头科技 in cleaning robot.
    The market for robotic lawn mower is expected to grow significantly.
    Our perception system is based on proprietary AI algorithms.
    """

    # 同行分析
    analyzer = PeerComparableAnalyzer()
    peer_result = analyzer.analyze(pi, text, ipo)
    pi["peer_comparison"] = peer_result

    print(f"\n细分赛道: {peer_result.get('subsector', 'N/A')}")
    print(f"匹配同行: {len(peer_result.get('matched_peers', []))} 家")
    print(f"公司PS: {peer_result.get('company_ps')}")
    print(f"同行PS中位数: {peer_result.get('peer_median_ps')}")
    print(f"相对溢价: {peer_result.get('relative_ps_premium_pct')}%")
    print(f"稀缺性评分: {peer_result.get('scarcity_score')}/10")
    print(f"同行对比评分: {peer_result.get('peer_score')}/15")
    print(f"估值定位: {peer_result.get('valuation_position')}")
    print(f"总结: {peer_result.get('summary')}")
    for w in peer_result.get("warnings", []):
        print(f"  ⚠ {w}")

    # 估值分析（带同行数据）
    val = ValuationAnalyzer().analyze(pi)
    pi["valuation"] = val
    print(f"\n绝对估值: {val.get('absolute_valuation_label')}")
    print(f"相对估值: {val.get('relative_valuation_label')}")
    print(f"最终估值: {val.get('valuation_label')}")
    print(f"估值理由: {val.get('valuation_reasons', [])}")

    # 进阶框架
    adv = SignalComponentAnalyzer()
    adv_result = adv.analyze(ipo, pi, text)
    val_comp = adv_result.get("components", {}).get("valuation_framework", {})
    print(f"\n进阶框架估值评分: {val_comp.get('score')}/{val_comp.get('max_score')}")
    print(f"进阶框架估值结论: {val_comp.get('label')}")

    # 评分系统
    scorer = ScoringSystem()
    qa = ProspectusQualityAnalyzer()
    quality = qa.analyze(pi)
    scoring = scorer.calculate(ipo, pi)
    print(f"\n最终评分: {scoring.get('score')}/100")
    for r in scoring.get("reasons", []):
        print(f"  • {r}")

    assert peer_result.get("subsector") in (
        "robotics_visual_perception", "ai_chip_semiconductor"
    ), f"Expected robotics subsector, got {peer_result.get('subsector')}"
    assert len(peer_result.get("matched_peers", [])) >= 3, f"Expected >=3 peers, got {len(peer_result.get('matched_peers', []))}"
    assert _is_num(peer_result.get("peer_median_ps")), "Expected peer median PS to be numeric"
    print("\n✅ Test 1 PASSED")


def test_biotech_comparison():
    """测试剂泰科技类似公司的同行对比"""
    print("\n" + "=" * 60)
    print("Test 2: 剂泰科技 (healthcare/ai_drug_delivery_nanomedicine)")
    print("=" * 60)

    ipo = _build_mock_ipo(
        revenue=33,            # ~3300万收入 (极小的M)
        revenue_y1=5,          # 之前基数极低
        net_profit=-300,
        gross_margin=38,
        market_cap_hkd_million=3800,  # PS ≈ 115x
        sector="healthcare",
        technology_moat=8,
        rnd_label="强",
        segments=[{"name": "AI药物递送平台", "share_pct": 100, "growth_pct": 500}],
    )

    pi = ipo["prospectus_info"]
    text = """
    Our company is an AI-driven drug delivery and nanomedicine company.
    We have developed a proprietary NanoForge platform for nanoparticle drug delivery.
    Our LNP and RNA formulation technology enables targeted drug delivery.
    We leverage artificial intelligence for drug formulation optimization.
    Our platform has applications in nanomaterial-based therapeutics.
    We operate at the intersection of AI and nanomedicine for drug delivery solutions.
    """

    # 同行分析
    analyzer = PeerComparableAnalyzer()
    peer_result = analyzer.analyze(pi, text, ipo)
    pi["peer_comparison"] = peer_result

    print(f"\n细分赛道: {peer_result.get('subsector', 'N/A')}")
    print(f"匹配同行: {len(peer_result.get('matched_peers', []))} 家")
    print(f"公司PS: {peer_result.get('company_ps')}")
    print(f"同行PS中位数: {peer_result.get('peer_median_ps')}")
    print(f"相对溢价: {peer_result.get('relative_ps_premium_pct')}%")
    print(f"稀缺性评分: {peer_result.get('scarcity_score')}/10")
    print(f"同行对比评分: {peer_result.get('peer_score')}/15")
    print(f"估值定位: {peer_result.get('valuation_position')}")
    print(f"总结: {peer_result.get('summary')}")
    for w in peer_result.get("warnings", []):
        print(f"  ⚠ {w}")

    # 估值分析
    val = ValuationAnalyzer().analyze(pi)
    pi["valuation"] = val
    print(f"\n绝对估值: {val.get('absolute_valuation_label')}")
    print(f"相对估值: {val.get('relative_valuation_label')}")
    print(f"最终估值: {val.get('valuation_label')}")
    print(f"估值理由: {val.get('valuation_reasons', [])}")

    # 进阶框架
    adv = SignalComponentAnalyzer()
    adv_result = adv.analyze(ipo, pi, text)
    val_comp = adv_result.get("components", {}).get("valuation_framework", {})
    print(f"\n进阶框架估值评分: {val_comp.get('score')}/{val_comp.get('max_score')}")
    print(f"进阶框架估值结论: {val_comp.get('label')}")

    # 评分系统
    scorer = ScoringSystem()
    qa = ProspectusQualityAnalyzer()
    quality = qa.analyze(pi)
    scoring = scorer.calculate(ipo, pi)
    print(f"\n最终评分: {scoring.get('score')}/100")
    for r in scoring.get("reasons", []):
        print(f"  • {r}")

    assert peer_result.get("subsector") == "ai_drug_delivery_nanomedicine", \
        f"Expected ai_drug_delivery_nanomedicine, got {peer_result.get('subsector')}"
    assert peer_result.get("scarcity_score", 0) >= 5, \
        f"Expected scarcity >= 5 for biotech platform, got {peer_result.get('scarcity_score')}"
    # The valuation should NOT be just '很贵' - should have explanation
    assert val.get("valuation_label") not in ('很贵',), \
        f"Valuation should not be simply '很贵' for scarce biotech: {val.get('valuation_label')}"
    print("\n✅ Test 2 PASSED")


def test_no_peer_match():
    """测试无同行匹配时的回退行为"""
    print("\n" + "=" * 60)
    print("Test 3: 无同行匹配 (回退到绝对估值)")
    print("=" * 60)

    ipo = _build_mock_ipo(
        revenue=500,
        revenue_y1=400,
        net_profit=50,
        gross_margin=35,
        market_cap_hkd_million=10000,
        sector="consumer",
    )
    pi = ipo["prospectus_info"]
    text = "A consumer retail company selling gold jewelry and beauty products."

    analyzer = PeerComparableAnalyzer()
    peer_result = analyzer.analyze(pi, text, ipo)
    pi["peer_comparison"] = peer_result

    print(f"细分赛道: {peer_result.get('subsector', 'N/A')}")
    print(f"警告: {peer_result.get('warnings', [])}")
    # Should fall back gracefully
    val = ValuationAnalyzer().analyze(pi)
    pi["valuation"] = val
    print(f"最终估值: {val.get('valuation_label')}")
    print(f"估值理由: {val.get('valuation_reasons', [])}")

    # 进阶框架应回退
    adv = SignalComponentAnalyzer()
    adv_result = adv.analyze(ipo, pi, text)
    val_comp = adv_result.get("components", {}).get("valuation_framework", {})
    print(f"进阶框架估值评分: {val_comp.get('score')}/{val_comp.get('max_score')}")

    print("\n✅ Test 3 PASSED")


def test_incremental_analysis():
    """测试完整 pipeline 集成"""
    print("\n" + "=" * 60)
    print("Test 4: 完整 pipeline (core._calculate_final_score)")
    print("=" * 60)

    from ipo_analyzer.core import _calculate_final_score

    ipo = _build_mock_ipo(
        revenue=680,
        revenue_y1=340,
        net_profit=-90,
        gross_margin=44,
        market_cap_hkd_million=9100,
        sector="hardtech",
        technology_moat=7,
        rnd_label="强",
        segments=[{"name": "机器人", "share_pct": 60, "growth_pct": 80}],
    )
    pi = ipo["prospectus_info"]
    text = """
    Our company is a leading robotics and visual perception technology company.
    We develop advanced robot lawn mowers with lidar and sensor systems.
    """

    scorer = ScoringSystem()
    qa = ProspectusQualityAnalyzer()
    adv = SignalComponentAnalyzer()

    _calculate_final_score(scorer, qa, adv, ipo, pi, text)

    # Check that peer comparison was integrated
    peer_result = pi.get("peer_comparison", {})
    assert peer_result.get("subsector") is not None, "Peer comparison should have matched"
    print(f"细分赛道: {peer_result.get('subsector')}")
    print(f"同行对比评分: {peer_result.get('peer_score')}/15")
    print(f"估值定位: {peer_result.get('valuation_position')}")

    # Check that valuation used peer data
    valuation = pi.get("valuation", {})
    assert valuation.get("valuation_label", "") not in ('缺失',), "Valuation should not be missing"
    print(f"估值: {valuation.get('valuation_label')}")
    print(f"估值类型: {valuation.get('valuation_type')}")

    # Check scoring
    assert ipo.get("score", 0) > 0, "Score should be computed"
    print(f"最终评分: {ipo.get('score')}/100")

    print("\n✅ Test 4 PASSED")


def test_false_positive_filtering():
    """测试候选同行过滤 — 不应出现封面/承销商/标题词误报"""
    print("\n" + "=" * 60)
    print("Test 5: 假阳性过滤 — 剂泰科技封面/承销商误报")
    print("=" * 60)

    from ipo_analyzer.peer_comps import (
        _extract_competitor_chunks, _extract_potential_company_names,
        _filter_peer_candidates, _unmatched_candidates, _build_issuer_aliases,
    )

    # 模拟包含大量封面/承销商噪音的招股书文本
    noise_text = """
    Metis TechBio Limited
    Joint Sponsors
    Overall Coordinators
    Joint Global Coordinators
    Joint Bookrunners
    Joint Lead Managers
    Stock Code: 01234
    People's Republic of China
    Prospectus
    Global Offering
    Number of Offer Shares

    Our company is a leading AI drug delivery nanomedicine platform.

    Our competitors include Moderna and BioNTech in the mRNA space.
    We also face competition from Alnylam Pharmaceuticals in RNA therapeutics.
    Industry participants include 晶泰科技 and 英矽智能 in AI drug discovery.
    """

    ipo = _build_mock_ipo(sector="healthcare")
    pi = ipo["prospectus_info"]
    pi["extracted_english_name"] = "Metis TechBio Limited"
    pi["company_name_aliases"] = ["Metis TechBio", "Metis"]

    issuer_aliases = _build_issuer_aliases(pi, ipo)
    comp_chunks = _extract_competitor_chunks(noise_text)

    print(f"\n竞争章节提取数: {len(comp_chunks)}")
    if comp_chunks:
        print(f"首个chunk前100字: {comp_chunks[0][:100]}")

    # 直接测试公司名提取
    candidates = _extract_potential_company_names(noise_text, issuer_aliases=issuer_aliases)
    print(f"候选总数(过滤前): {len(candidates)}")
    for c in candidates:
        print(f"  {c['name']} ({c['confidence']}): {c['reason']}")

    # 测试过滤
    filtered = _filter_peer_candidates(candidates, [], issuer_aliases)
    print(f"候选总数(过滤后): {len(filtered)}")

    # 不应该出现的词
    should_not_contain = [
        "Metis TechBio", "Metis TechBio Limited", "Joint Sponsors",
        "Overall Coordinators", "Joint Global Coordinators", "Bookrunners",
        "Joint Lead Managers", "Stock Code", "People Republic",
        "Prospectus", "Global Offering", "Offer Shares",
        "Number of Offer", "The Company",
    ]
    for bad_word in should_not_contain:
        for f in filtered:
            if bad_word.lower() in f.lower() or f.lower() == bad_word.lower():
                print(f"  ⚠ 误报: {f} 包含 {bad_word}")

    # 应该出现的高质量候选
    print(f"\n最终候选: {filtered}")

    for bad_word in should_not_contain:
        for f in filtered:
            assert bad_word.lower() not in f.lower(), f"误报: {f} 包含 {bad_word}"

    print("\n✅ Test 5 PASSED")


def test_competitor_context_detection():
    """测试竞争语境中的真实公司名提取"""
    print("\n" + "=" * 60)
    print("Test 6: 竞争语境公司名识别")
    print("=" * 60)

    from ipo_analyzer.peer_comps import (
        _extract_competitor_chunks, _unmatched_candidates,
        _build_issuer_aliases, _collect_all_peer_names,
    )

    text = """
    Our competitors include Moderna, BioNTech and Alnylam Pharmaceuticals.
    We also compete with another AI drug discovery company called Insilico Medicine.
    Industry participants include Recursion Pharmaceuticals.
    """

    ipo = _build_mock_ipo(sector="healthcare")
    pi = ipo["prospectus_info"]
    comp_chunks = _extract_competitor_chunks(text)
    print(f"竞争chunks: {len(comp_chunks)}")

    # Load actual peer data
    from ipo_analyzer.peer_comps import _load_peer_data
    peer_data = _load_peer_data()
    all_peer_names = _collect_all_peer_names(peer_data)
    issuer_aliases = _build_issuer_aliases(pi, ipo)

    candidates = _unmatched_candidates(comp_chunks, all_peer_names, issuer_aliases=issuer_aliases)
    print(f"未收录候选: {candidates}")

    # Moderna, BioNTech, Alnylam should be in the peer data already (not in unmatched)
    for known_peer in ["Moderna", "BioNTech", "Alnylam"]:
        assert known_peer not in candidates, f"{known_peer} should be in peers, not unmatched"

    print("\n✅ Test 6 PASSED")


def test_issuer_exclusion():
    """测试发行人排除 — 发行人名字不应出现在 unmatched 中"""
    print("\n" + "=" * 60)
    print("Test 7: 发行人排除")
    print("=" * 60)

    from ipo_analyzer.peer_comps import (
        _extract_competitor_chunks, _unmatched_candidates,
        _build_issuer_aliases, _collect_all_peer_names,
    )

    text = """
    Metis TechBio Limited is a leading AI drug delivery platform company.
    Our competitors include Moderna and BioNTech.
    The company was founded in 2018.
    Metis TechBio Ltd continues to develop its NanoForge platform.
    """
    text2 = """
    Metis TechBio is headquartered in Shanghai.
    """

    ipo = _build_mock_ipo(sector="healthcare")
    pi = ipo["prospectus_info"]
    pi["extracted_english_name"] = "Metis TechBio Limited"

    issuer_aliases = _build_issuer_aliases(pi, ipo)
    print(f"发行人别名: {issuer_aliases}")

    comp_chunks = _extract_competitor_chunks(text + "\n" + text2)
    all_peer_names = _collect_all_peer_names(_build_mock_ipo.__globals__.get('None'))

    # Actually load real peer data
    from ipo_analyzer.peer_comps import _load_peer_data
    peer_data = _load_peer_data()
    all_peer_names = _collect_all_peer_names(peer_data)

    candidates = _unmatched_candidates(comp_chunks, all_peer_names, issuer_aliases=issuer_aliases)
    print(f"未收录候选: {candidates}")

    # Metis TechBio should NOT be in candidates
    for c in candidates:
        if "Metis" in c or "metis" in c.lower():
            print(f"⚠ 误报: 发行人 {c} 出现在 unmatched 中")

    assert not any("Metis" in c for c in candidates), "发行人不应在 unmatched 中"

    print("\n✅ Test 7 PASSED")


def test_biotech_valuation():
    """测试未盈利创新药估值 — market_cap存在时不应显示'缺失'"""
    print("\n" + "=" * 60)
    print("Test 8: 英派药业-未盈利创新药估值")
    print("=" * 60)

    # 模拟英派药业数据
    ipo = _build_mock_ipo(
        revenue=38.251,    # RMB million (≈HKD 41.3M after fx)
        revenue_y1=20.0,
        net_profit=-295.924,
        gross_margin=0,
        market_cap_hkd_million=6007,   # HKD million (提取出来的)
        sector="healthcare",
        technology_moat=8,
        rnd_label="强",
    )
    pi = ipo["prospectus_info"]
    pi["extracted_company_name"] = "英派药业-B"
    pi["financial_currency"] = "RMB"
    pi["rd_expense"] = 183.674  # RMB million
    pi["_extracted_text"] = """
    18A biotech company
    Core Product: senaparib (PARP inhibitor)
    Phase III clinical trial for ovarian cancer
    IND approved for multiple indications
    Drug candidate in pivotal trial
    """

    text = """
    An 18A biotech company focused on innovative drug discovery.
    Clinical-stage biopharmaceutical company with PARP inhibitor pipeline.
    Our competitors include BeiGene and other innovative drug companies.
    """

    # 估值分析
    val = ValuationAnalyzer().analyze(pi, ipo)
    pi["valuation"] = val

    print(f"\n市值: {pi.get('market_cap_hkd_million')} HKD M")
    print(f"收入(HKD M): {val.get('revenue_hkd_million')}")
    print(f"PS: {val.get('ps_ratio')}")
    print(f"估值类型: {val.get('valuation_framework_type')}")
    print(f"盈利类型: {val.get('valuation_profitability_type')}")
    print(f"估值标签: {val.get('valuation_label')}")
    print(f"生物科技估值: {val.get('biotech_valuation_label')}")
    print(f"市值/R&D: {val.get('market_cap_to_rd_ratio')}")
    for r in val.get('valuation_reasons', []):
        print(f"  • {r}")

    # 断言
    assert val.get('valuation_framework_type') == '18A_biotech', "应检测为18A生物科技"
    assert val.get('valuation_label') != '缺失', f"估值不应为缺失: {val.get('valuation_label')}"
    assert val.get('ps_ratio') is not None, "PS应存在"
    assert val.get('valuation_label', '') in ('PS辅助估值', 'PS失真，仅作参考', '管线阶段估值'), "标签应为PS辅助或管线估值"
    assert 'PE不适用' in str(val.get('valuation_reasons', [])), "应提示PE不适用"
    print("\n✅ Test 8 PASSED")


def test_issuer_alias_overlap_skipped():
    """测试发行人别名重叠的 candidate 被正确跳过"""
    print("\n" + "=" * 60)
    print("Test 9: 发行人别名重叠 candidate 应被排除")
    print("=" * 60)

    from ipo_analyzer.peer_comps import _filter_peer_candidates, _build_issuer_aliases

    ipo = {"company_name": "LdsRobotics Limited", "shortname": "LdsRobotics"}
    pi = {"extracted_company_name": "LdsRobotics Limited", "company_name_aliases": ["LdsRobotics"]}
    issuer_aliases = _build_issuer_aliases(pi, ipo)

    candidates = [
        {"name": "LdsRobotics Technology", "confidence": "high", "reason": "test", "source": "test"},
        {"name": "True Peer Company", "confidence": "high", "reason": "test", "source": "test"},
    ]
    filtered = _filter_peer_candidates(candidates, [], issuer_aliases)
    print(f"过滤后候选: {filtered}")
    assert "LdsRobotics Technology" not in filtered, "发行人别名重叠的 candidate 应被排除"
    assert "True Peer Company" in filtered, "真实同行应保留"
    print("\n✅ Test 9 PASSED")


def test_private_peer_not_in_quantitative():
    """测试 private peer 不进入 quantitative median"""
    print("\n" + "=" * 60)
    print("Test 10: private peer 不进入 quantitative median")
    print("=" * 60)

    from ipo_analyzer.peer_comps import PeerComparableAnalyzer

    ipo = _build_mock_ipo(sector="hardtech")
    pi = ipo["prospectus_info"]
    text = "We compete with listed robotics companies."

    analyzer = PeerComparableAnalyzer()
    result = analyzer.analyze(pi, text, ipo)

    quantitative = result.get("quantitative_peers", [])
    qualitative = result.get("qualitative_peers", [])
    print(f"quantitative: {len(quantitative)}  qualitative: {len(qualitative)}")

    for p in quantitative:
        assert p.get("type") == "listed", f"quantitative 不应包含非 listed: {p.get('name')}"
        assert p.get("data_quality") != "low", f"quantitative 不应包含低质量: {p.get('name')}"
        assert not p.get("needs_refresh", False), f"quantitative 不应包含需刷新: {p.get('name')}"

    print("\n✅ Test 10 PASSED")


def test_single_quantitative_peer_weak_conclusion():
    """测试只有 1 个 quantitative peer 时不输出强结论"""
    print("\n" + "=" * 60)
    print("Test 11: 1 个 quantitative peer → 弱结论")
    print("=" * 60)

    from ipo_analyzer.peer_comps import PeerComparableAnalyzer

    ipo = _build_mock_ipo(sector="hardtech")
    pi = ipo["prospectus_info"]
    text = "We compete with listed robotics companies."

    analyzer = PeerComparableAnalyzer()
    result = analyzer.analyze(pi, text, ipo)

    # 如果 quantitative peers < 2, valuation_position 应为"样本不足，仅作定性参考"
    if len(result.get("quantitative_peers", [])) < 2:
        vp = result.get("valuation_position", "")
        assert vp == "样本不足，仅作定性参考", f"期望'样本不足，仅作定性参考', 实际: {vp}"
        assert result.get("peer_score", 0) <= 5, f"peer_score 应受限: {result.get('peer_score')}"
        print(f"valuation_position: {vp}  (符合预期)")
    else:
        print(f"quantitative peers >= 2, 跳过此断言")

    print("\n✅ Test 11 PASSED")


def test_loss_making_valuation_not_missing():
    """测试亏损公司估值标签不是'缺失'"""
    print("\n" + "=" * 60)
    print("Test 12: 亏损公司估值标签")
    print("=" * 60)

    ipo = _build_mock_ipo(
        revenue=200,
        net_profit=-50,
        market_cap_hkd_million=3000,
        sector="healthcare",
    )
    pi = ipo["prospectus_info"]
    pi["financial_currency"] = "RMB"
    pi["_extracted_text"] = "18A biotech clinical stage"

    val = ValuationAnalyzer().analyze(pi, ipo)
    label = val.get("valuation_label", "")
    print(f"估值标签: {label}")
    assert label != "缺失", f"亏损公司估值不应为'缺失': {label}"
    assert label in ("PS辅助估值", "PS失真，仅作参考", "管线阶段估值", "数据不足，需人工核对"), \
        f" unexpected label: {label}"
    print("\n✅ Test 12 PASSED")


def test_pe_uses_hkd_net_profit():
    """测试 PE 使用 HKD 口径净利润"""
    print("\n" + "=" * 60)
    print("Test 13: PE 使用 HKD 口径净利润")
    print("=" * 60)

    ipo = _build_mock_ipo(
        revenue=1000,
        net_profit=100,  # RMB million
        market_cap_hkd_million=2000,
        sector="hardtech",
    )
    pi = ipo["prospectus_info"]
    pi["financial_currency"] = "RMB"

    val = ValuationAnalyzer().analyze(pi, ipo)
    pe = val.get("pe_ratio")
    np_hkd = val.get("net_profit_hkd_million")
    print(f"net_profit(RMB): 100  → HKD: {np_hkd}")
    print(f"PE: {pe}")

    assert np_hkd is not None, "net_profit_hkd_million 应存在"
    assert abs(np_hkd - 108.0) < 1.0, f"HKD 净利润应为约 108, 实际: {np_hkd}"
    assert pe is not None, "PE 应存在"
    expected_pe = round(2000 / np_hkd, 2)
    assert abs(pe - expected_pe) < 0.5, f"PE 应为 {expected_pe}, 实际: {pe}"
    print("\n✅ Test 13 PASSED")


if __name__ == "__main__":
    test_robot_comparison()
    test_biotech_comparison()
    test_no_peer_match()
    test_incremental_analysis()
    test_false_positive_filtering()
    test_competitor_context_detection()
    test_issuer_exclusion()
    test_biotech_valuation()
    test_issuer_alias_overlap_skipped()
    test_private_peer_not_in_quantitative()
    test_single_quantitative_peer_weak_conclusion()
    test_loss_making_valuation_not_missing()
    test_pe_uses_hkd_net_profit()
    print("\n" + "=" * 60)
    print("✅ 所有同行对比测试通过")
    print("=" * 60)
