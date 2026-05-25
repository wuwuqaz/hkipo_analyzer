"""行业赛道分析（基于 InvestSkill 框架）。

分析IPO公司所处行业的：
- 行业贝塔（系统性风险/收益）
- 行业周期位置
- 政策环境
- 行业增速
"""

from __future__ import annotations

from ..models import SectorAnalysisResult


# 行业赛道数据库
SECTOR_DATA = {
    # 科技/硬科技
    'technology': {
        'sector_beta': 1.3,
        'cycle': '成长期',
        'policy': '强支持',
        'growth': 0.25,
        'label': '高增长科技',
    },
    'hardtech': {
        'sector_beta': 1.4,
        'cycle': '成长期',
        'policy': '强支持',
        'growth': 0.30,
        'label': '硬科技（芯片/半导体/机器人）',
    },
    'ai': {
        'sector_beta': 1.5,
        'cycle': '爆发期',
        'policy': '强支持',
        'growth': 0.40,
        'label': '人工智能',
    },
    # 医疗/生物科技
    'biotech': {
        'sector_beta': 1.4,
        'cycle': '成长期',
        'policy': '支持',
        'growth': 0.20,
        'label': '生物科技',
    },
    'healthcare': {
        'sector_beta': 1.1,
        'cycle': '成熟期',
        'policy': '支持',
        'growth': 0.12,
        'label': '医疗健康',
    },
    # 消费
    'consumer': {
        'sector_beta': 0.9,
        'cycle': '成熟期',
        'policy': '中性',
        'growth': 0.08,
        'label': '消费',
    },
    'retail': {
        'sector_beta': 0.8,
        'cycle': '成熟期',
        'policy': '中性',
        'growth': 0.06,
        'label': '零售',
    },
    # 金融
    'financial': {
        'sector_beta': 1.0,
        'cycle': '成熟期',
        'policy': '强监管',
        'growth': 0.05,
        'label': '金融',
    },
    'banking': {
        'sector_beta': 0.9,
        'cycle': '成熟期',
        'policy': '强监管',
        'growth': 0.04,
        'label': '银行',
    },
    # 工业/制造
    'industrial': {
        'sector_beta': 1.0,
        'cycle': '成熟期',
        'policy': '支持',
        'growth': 0.10,
        'label': '工业制造',
    },
    'manufacturing': {
        'sector_beta': 1.0,
        'cycle': '成熟期',
        'policy': '支持',
        'growth': 0.08,
        'label': '制造业',
    },
    # 房地产
    'real_estate': {
        'sector_beta': 1.2,
        'cycle': '下行期',
        'policy': '调控',
        'growth': -0.05,
        'label': '房地产',
    },
    # 能源
    'energy': {
        'sector_beta': 1.1,
        'cycle': '转型期',
        'policy': '转型支持',
        'growth': 0.05,
        'label': '能源',
    },
    # 默认
    'unknown': {
        'sector_beta': 1.0,
        'cycle': '未知',
        'policy': '中性',
        'growth': 0.05,
        'label': '未知行业',
    },
}


class SectorAnalyzer:
    """行业赛道分析器"""

    @staticmethod
    def analyze(prospectus_info: dict) -> SectorAnalysisResult:
        """分析招股书数据，返回行业赛道分析结果。"""
        result = SectorAnalysisResult()

        sector = prospectus_info.get('sector', 'unknown')
        sector_info = SECTOR_DATA.get(sector, SECTOR_DATA['unknown'])

        result.sector_name = sector_info['label']

        # 1. 行业贝塔分析
        beta = sector_info['sector_beta']
        result.sector_beta_score = int(beta * 50)  # 转换为0-100分

        if beta >= 1.3:
            result.sector_beta_label = "高贝塔（高风险高收益）"
            result.reasons.append(f"行业贝塔={beta:.1f}，属于高波动赛道")
        elif beta >= 1.0:
            result.sector_beta_label = "中贝塔（中等风险收益）"
            result.reasons.append(f"行业贝塔={beta:.1f}，波动适中")
        else:
            result.sector_beta_label = "低贝塔（低风险低收益）"
            result.reasons.append(f"行业贝塔={beta:.1f}，波动较低")

        # 2. 行业周期位置
        cycle = sector_info['cycle']
        result.cycle_position = cycle

        cycle_scores = {
            '爆发期': 90,
            '成长期': 75,
            '成熟期': 50,
            '转型期': 40,
            '下行期': 20,
            '未知': 50,
        }
        result.cycle_score = cycle_scores.get(cycle, 50)

        if cycle in ('爆发期', '成长期'):
            result.reasons.append(f"行业处于{cycle}，增长空间大")
        elif cycle == '成熟期':
            result.reasons.append("行业成熟，增长稳定但空间有限")
        elif cycle in ('下行期', '转型期'):
            result.reasons.append(f"行业处于{cycle}，需谨慎")

        # 3. 政策环境
        policy = sector_info['policy']
        result.policy_support = policy

        policy_scores = {
            '强支持': 90,
            '支持': 70,
            '中性': 50,
            '转型支持': 60,
            '调控': 30,
            '强监管': 40,
        }
        result.policy_score = policy_scores.get(policy, 50)

        if policy in ('强支持', '支持'):
            result.reasons.append(f"政策环境{policy}，利好行业发展")
        elif policy == '中性':
            result.reasons.append("政策环境中性，无明显利好或利空")
        elif policy in ('强监管', '调控'):
            result.reasons.append(f"政策环境{policy}，行业面临监管压力")

        # 4. 行业增速
        growth = sector_info['growth']
        result.sector_growth_pct = growth * 100  # 转换为百分比

        if growth >= 0.20:
            result.sector_growth_label = "高速增长"
        elif growth >= 0.10:
            result.sector_growth_label = "中速增长"
        elif growth >= 0.05:
            result.sector_growth_label = "低速增长"
        elif growth >= 0:
            result.sector_growth_label = "微增长"
        else:
            result.sector_growth_label = "负增长"

        result.reasons.append(f"行业增速约{growth*100:.0f}%")

        # 5. 综合推荐
        total_score = (result.sector_beta_score * 0.3 +
                       result.cycle_score * 0.3 +
                       result.policy_score * 0.2 +
                       result.sector_beta_score * 0.2)

        if total_score >= 75:
            result.sector_recommendation = "积极"
            result.reasons.append("行业综合评分高，值得积极关注")
        elif total_score >= 55:
            result.sector_recommendation = "中性"
            result.reasons.append("行业综合评分中等，保持关注")
        else:
            result.sector_recommendation = "谨慎"
            result.reasons.append("行业综合评分偏低，需谨慎")

        return result
