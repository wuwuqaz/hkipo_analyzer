from ipo_analyzer.analyzers._company_profile import CompanyProfileAnalyzer


def test_normalize_llm_summary_keeps_labeled_three_lines():
    raw = """
以下是以三段格式提炼的公司业务描述：
做什么：提供智能家居硬件和软件
卖给谁：面向企业客户，属于B2B模式
怎么赚钱：通过硬件销售和系统解决方案收费
"""
    assert CompanyProfileAnalyzer._normalize_llm_summary(raw) == (
        "做什么：提供智能家居硬件和软件\n"
        "卖给谁：面向企业客户，属于B2B模式\n"
        "怎么赚钱：通过硬件销售和系统解决方案收费"
    )


def test_normalize_llm_summary_maps_three_plain_paragraphs():
    raw = """
以下是以三段格式提炼的公司业务描述：

公司提供智能家居硬件和软件。

公司面向企业客户，属于B2B模式。

公司通过硬件销售和系统解决方案收费。
"""
    assert CompanyProfileAnalyzer._normalize_llm_summary(raw) == (
        "做什么：公司提供智能家居硬件和软件\n"
        "卖给谁：公司面向企业客户，属于B2B模式\n"
        "怎么赚钱：公司通过硬件销售和系统解决方案收费"
    )


def test_normalize_llm_summary_rejects_incomplete_output():
    assert CompanyProfileAnalyzer._normalize_llm_summary("公司提供智能硬件。") is None


def test_get_business_raw_text_prefers_who_we_are_over_table_of_contents():
    text = """
目錄
業務 . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 127
財務資料 . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 208

概要
我們是誰
我們是全球消費級3D打印產品及服務提供商。我們的產品及服務主要包括3D打印機、3D打印耗材及3D掃描儀。
我們的商業模式
我們通過產品銷售及平台服務賺取收入。
風險因素
"""
    raw = CompanyProfileAnalyzer._get_business_raw_text(text)
    assert "全球消費級3D打印產品及服務提供商" in raw
    assert "業務 . ." not in raw
