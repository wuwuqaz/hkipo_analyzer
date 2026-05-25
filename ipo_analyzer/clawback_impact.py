"""回拨机制影响分析 — 超购触发回拨后公开发售比例增加，影响筹码结构和首日表现。"""

import logging

logger = logging.getLogger(__name__)


def analyze_clawback_impact(prospectus_info):
    """分析回拨机制对打新的影响。

    逻辑：
    - 超购触发回拨：散户获配增加 → 筹码分散 → 首日抛压更大
    - 回拨比例越高，散户参与越多，破发风险相应提升

    Returns:
        dict: impact_score, impact_label, clawback_triggered, detail
    """
    over_sub = prospectus_info.get('over_sub_ratio') or prospectus_info.get('actual_over_sub_ratio')
    clawback_max = prospectus_info.get('public_offer_clawback_max_pct')
    public_ratio = prospectus_info.get('public_offer_ratio_pct') or 10.0

    result = {
        'clawback_triggered': False,
        'clawback_ratio': None,
        'impact_score': 0,
        'impact_label': '未触发',
        'detail': '',
        'confidence': 'insufficient_data',
    }

    try:
        if not over_sub or not isinstance(over_sub, (int, float)) or over_sub <= 0:
            return result

        # 港股标准回拨规则
        triggered_ratio = None
        if over_sub < 15:
            triggered_ratio = public_ratio  # 未触发，保持不变
        elif over_sub < 50:
            triggered_ratio = 30.0
        elif over_sub < 100:
            triggered_ratio = 40.0
        else:
            triggered_ratio = 50.0

        # 如果有实际的clawback_max_pct，用实际值覆盖
        if clawback_max and isinstance(clawback_max, (int, float)):
            triggered_ratio = clawback_max

        result['clawback_triggered'] = triggered_ratio > public_ratio
        result['clawback_ratio'] = triggered_ratio
        result['confidence'] = 'calculated'

        gap = triggered_ratio - public_ratio

        if gap <= 0:
            result['impact_label'] = '未触发回拨'
            result['detail'] = f'公开发售维持{public_ratio:.0f}%'
        elif gap <= 15:
            result['impact_score'] = -1
            result['impact_label'] = '回拨温和'
            result['detail'] = f'超购{over_sub:.0f}x触发回拨，公开发售{triggered_ratio:.0f}%(+{gap:.0f}pp)'
            result['confidence'] = 'calculated'
        elif gap <= 30:
            result['impact_score'] = -2
            result['impact_label'] = '回拨显著'
            result['detail'] = f'超购{over_sub:.0f}x触发回拨，公开发售{triggered_ratio:.0f}%(+{gap:.0f}pp)，筹码分散'
            result['confidence'] = 'calculated'
        else:
            result['impact_score'] = -4
            result['impact_label'] = '回拨剧烈'
            result['detail'] = f'超购{over_sub:.0f}x触发最大回拨，公开发售{triggered_ratio:.0f}%(+{gap:.0f}pp)，极度散户化'
            result['confidence'] = 'calculated'

    except Exception as e:
        logger.warning("回拨分析失败: %s", e)
        result['_error'] = str(e)

    return result
