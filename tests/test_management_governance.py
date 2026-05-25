"""管理层与治理质量分析器单元测试。"""

from ipo_analyzer.analyzers._management_governance import ManagementGovernanceAnalyzer


def test_extract_management_experience_direct_match():
    """测试直接匹配管理层经验年限。"""
    text = """
    张先生拥有15年半导体行业经验。
    李女士在医疗器械行业从业12年。
    """
    result = ManagementGovernanceAnalyzer().analyze({}, text)
    assert result['management_experience_years'] is not None
    assert result['management_experience_years'] >= 10


def test_extract_management_experience_variant_patterns():
    """测试中文变体、英文和年份型管理层经验。"""
    analyzer = ManagementGovernanceAnalyzer()
    assert analyzer._extract_management_experience("核心团队具备12年行业经验。") == 12
    assert analyzer._extract_management_experience("He has 15 years of experience in robotics.") == 15
    assert analyzer._extract_management_experience("The founder joined the industry in 2010.") >= 10


def test_extract_founder_ownership():
    """测试提取创始人持股比例。"""
    text = """
    本公司创始人王明先生持有公司35.2%的股份。
    """
    result = ManagementGovernanceAnalyzer().analyze({}, text)
    assert result['founder_ownership_pct'] is not None
    assert 30 <= result['founder_ownership_pct'] <= 40


def test_auditor_big4_detection():
    """测试识别四大会计师事务所。"""
    text = """
    申报会计师：普华永道中天会计师事务所
    """
    result = ManagementGovernanceAnalyzer().analyze({}, text)
    assert result['auditor_quality'] == '四大'


def test_governance_risk_detection():
    """测试识别治理风险。"""
    text = """
    本公司董事涉及未决诉讼，可能对公司声誉造成不利影响。
    """
    result = ManagementGovernanceAnalyzer().analyze({}, text)
    assert len(result['governance_risk_flags']) > 0
    assert any('诉讼' in f for f in result['governance_risk_flags'])


def test_score_calculation_with_good_governance():
    """测试良好治理情况下评分较高。"""
    text = """
    张先生拥有12年行业经验。
    创始人持有公司30%的股份。
    申报会计师：德勤华永会计师事务所
    """
    analyzer = ManagementGovernanceAnalyzer()
    result = analyzer.analyze({}, text)
    assert result['management_score'] >= 60
    assert result['label'] in ('良好', '优秀')


def test_score_calculation_with_risks():
    """测试存在治理风险时评分较低。"""
    text = """
    本公司涉及财务造假指控。
    董事涉及诉讼。
    """
    result = ManagementGovernanceAnalyzer().analyze({}, text)
    assert result['management_score'] < 50
    assert result['label'] in ('偏弱', '一般')


def test_missing_data_returns_default():
    """测试数据缺失时返回默认值。"""
    result = ManagementGovernanceAnalyzer().analyze({}, '')
    assert result['management_experience_years'] is None
    assert result['management_score'] == 50
    assert result['label'] == '缺失'
    assert result['confidence'] == 'missing'
