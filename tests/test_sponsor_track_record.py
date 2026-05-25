"""保荐人战绩分析器单元测试。"""

from ipo_analyzer.analyzers._sponsor_track_record import SponsorTrackRecordAnalyzer


def test_match_sponsor_by_name_exact():
    """测试精确名称匹配中金公司。"""
    text = "\n    保荐人: 中金公司\n    "
    result = SponsorTrackRecordAnalyzer().analyze({}, text)
    assert result['sponsor_tier'] == 'S'
    assert result['sponsor_score'] == 10
    assert result['confidence'] == 'database'


def test_match_sponsor_by_alias():
    """测试别名匹配 CICC。"""
    text = "\n    Sponsor: CICC\n    "
    result = SponsorTrackRecordAnalyzer().analyze({}, text)
    assert result['sponsor_tier'] == 'S'
    assert result['matched_by'] == 'exact_or_alias'


def test_tier_a_sponsor_score():
    """测试A级保荐人得分。"""
    text = "\n    保荐人: 中信证券\n    "
    result = SponsorTrackRecordAnalyzer().analyze({}, text)
    assert result['sponsor_tier'] == 'A'
    assert result['sponsor_score'] == 7


def test_tier_b_sponsor_score():
    """测试B级保荐人得分。"""
    text = "\n    保荐人: 海通国际\n    "
    result = SponsorTrackRecordAnalyzer().analyze({}, text)
    assert result['sponsor_tier'] == 'B'
    assert result['sponsor_score'] == 3


def test_unknown_sponsor_default():
    """测试未知保荐人返回兜底值。"""
    text = "\n    保荐人: XX小贷公司\n    "
    result = SponsorTrackRecordAnalyzer().analyze({}, text)
    assert result['sponsor_tier'] == 'C'
    assert result['sponsor_score'] == 0
    assert result['matched_by'] == 'default'


def test_missing_sponsor_name():
    """测试招股书无保荐人信息。"""
    result = SponsorTrackRecordAnalyzer().analyze({}, '')
    assert result['sponsor_name'] is None
    assert result['confidence'] == 'missing'
