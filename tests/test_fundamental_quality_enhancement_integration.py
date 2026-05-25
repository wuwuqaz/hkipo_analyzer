"""质地增强分析器接入模型与评分链路的回归测试。"""

from ipo_analyzer.models import ProspectusInfo
from ipo_analyzer.quality_analyzer import ProspectusQualityAnalyzer
from ipo_analyzer.analyzers._profit_sustainability import ProfitSustainabilityAnalyzer


def test_enhancement_fields_survive_prospectus_info_normalization():
    info = {
        "company_name": "测试公司",
        "management_governance": {"management_score": 80, "label": "优秀", "confidence": "regex_context"},
        "balance_sheet": {"balance_sheet_score": 75, "label": "稳健", "confidence": "regex_context"},
        "profit_sustainability": {"sustainability_score": 70, "label": "基本可持续", "confidence": "regex_context"},
    }

    normalized = ProspectusInfo.from_dict(info).to_dict(drop_runtime=False)

    assert normalized["management_governance"]["management_score"] == 80
    assert normalized["balance_sheet"]["balance_sheet_score"] == 75
    assert normalized["profit_sustainability"]["sustainability_score"] == 70


def test_enhancement_dimensions_feed_quality_analyzer():
    result = ProspectusQualityAnalyzer().analyze({
        "management_governance": {
            "management_score": 80,
            "label": "优秀",
            "confidence": "regex_context",
            "management_experience_years": 12,
            "founder_ownership_pct": 30,
        },
        "balance_sheet": {
            "balance_sheet_score": 80,
            "label": "稳健",
            "confidence": "regex_context",
            "asset_liability_ratio": 0.4,
            "risk_flags": [],
        },
        "profit_sustainability": {
            "sustainability_score": 80,
            "label": "可持续",
            "confidence": "regex_context",
            "non_recurring_ratio": 0.05,
        },
    })

    dimensions = result["dimensions"]
    assert "management_governance" in dimensions
    assert "balance_sheet" in dimensions
    assert "profit_sustainability" in dimensions


def test_profit_sustainability_none_ratio_does_not_break_quality_analyzer():
    result = ProspectusQualityAnalyzer().analyze({
        "profit_sustainability": {
            "sustainability_score": 60,
            "label": "基本可持续",
            "confidence": "regex_context",
            "non_recurring_ratio": None,
        },
    })

    assert result["score"] >= 0
    assert result["dimensions"]["profit_sustainability"]["detail"] == "非经常性占比--"


def test_chinese_adjusted_net_profit_table_extracts_latest_million():
    text = """
    截至12月31日止年度
    2023年
    2024年
    2025年
    （人民幣千元）
    經調整淨利潤（非國際財務報告準則計量） . . . .
    130,134
    97,199
    92,385
    """

    result = ProfitSustainabilityAnalyzer().analyze({"net_profit": -182.421}, text)

    assert result["non_gaap_net_profit"] == 92.385
