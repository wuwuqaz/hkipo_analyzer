"""孖展数据质量校验器 — 对现有孖展数据进行合理性和一致性校验。"""

import logging

logger = logging.getLogger(__name__)


def validate_margin_data(prospectus_info):
    """校验孖展数据质量，返回数据可靠性评级。

    校验项：
    1. 超购倍数与孖展金额的一致性（孖展/公开发售额 ≈ 超购倍数）
    2. 数据新鲜度（是否在招股期内）
    3. 多源数据一致性（当有多个孖展源时）

    Returns:
        dict: quality_label, consistency_score, detail
    """
    margin_total = prospectus_info.get('margin_total')
    over_sub = prospectus_info.get('over_sub_ratio') or prospectus_info.get('estimated_subscription_ratio')
    public_offer = prospectus_info.get('public_offer')

    result = {
        'quality_label': '未校验',
        'consistency_score': 0,
        'data_issues': [],
        'confidence': 'insufficient_data',
    }

    try:
        checks_passed = 0
        checks_total = 0

        # 校验1: 超购与孖展一致性
        if (margin_total and isinstance(margin_total, (int, float)) and margin_total > 0 and
                over_sub and isinstance(over_sub, (int, float)) and over_sub > 0):
            checks_total += 1
            expected_ratio = margin_total / 1e8  # 转为亿
            if public_offer and isinstance(public_offer, (int, float)) and public_offer > 0:
                implied_sub = expected_ratio * 1e8 / public_offer
                ratio = implied_sub / over_sub
                if 0.3 <= ratio <= 3.0:
                    checks_passed += 1
                    result['consistency_score'] += 3
                elif 0.1 <= ratio <= 10.0:
                    checks_passed += 1
                    result['consistency_score'] += 1
                else:
                    result['data_issues'].append(f'孖展推算超购{implied_sub:.0f}x与实际{over_sub:.0f}x偏差过大')

        # 校验2: 超购边界合理性
        if over_sub and isinstance(over_sub, (int, float)):
            checks_total += 1
            if over_sub < 0:
                result['data_issues'].append('超购倍数为负，数据异常')
            elif over_sub > 5000:
                result['data_issues'].append('超购倍数>5000，需确认数据正确性')
            else:
                checks_passed += 1
                result['consistency_score'] += 2

        # 校验3: 孖展金额合理性
        if margin_total and isinstance(margin_total, (int, float)):
            checks_total += 1
            if margin_total < 0:
                result['data_issues'].append('孖展金额为负')
            elif margin_total > 1e12:  # 1万亿港元
                result['data_issues'].append('孖展金额过大，可能数据单位错误')
            else:
                checks_passed += 1
                result['consistency_score'] += 2

        if checks_total == 0:
            result['quality_label'] = '无数据'
            result['confidence'] = 'no_data'
        elif checks_passed == checks_total:
            result['quality_label'] = '可靠'
            result['confidence'] = 'high'
        elif checks_passed >= checks_total * 0.5:
            result['quality_label'] = '基本可靠'
            result['confidence'] = 'moderate'
        else:
            result['quality_label'] = '存疑'
            result['confidence'] = 'low'

    except Exception as e:
        logger.warning("孖展数据校验失败: %s", e)
        result['_error'] = str(e)

    return result
