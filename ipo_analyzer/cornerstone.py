import os
import re

from .utils import _contains_any, _infer_sector
from .settings import SETTINGS


def _load_investor_profiles():
    """从 YAML 加载基石投资者档案，加载失败时回退到内置数据。"""
    import yaml as _yaml
    yaml_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "cornerstone_investors.yaml",
    )
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = _yaml.safe_load(f)
        profiles = data.get("investors", [])
        if profiles:
            return profiles
    except Exception:
        pass
    return CornerstoneAnalyzer._BUILTIN_INVESTOR_PROFILES


class CornerstoneAnalyzer:
    """基石投资者信号分析"""

    TIER_BASE_SCORE = {
        'S': 95,
        'A': 78,
        'B': 58,
        '弱': 35,
        '未知': 45,
    }

    _BUILTIN_INVESTOR_PROFILES = [
        {
            'name': 'GIC',
            'tier': 'S',
            'category': '顶级主权基金/养老金',
            'aliases': ['gic private limited', 'gic private', 'government of singapore investment', '新加坡政府投资公司', '新加坡政府投资', 'gic'],
            'role_note': '新加坡主权长线资金，独立性和全球配置能力强',
            'sector_tags': ['all'],
        },
        {
            'name': 'Temasek',
            'tier': 'S',
            'category': '顶级主权基金/养老金',
            'aliases': ['temasek', '淡马锡'],
            'role_note': '新加坡长期资本，主权属性强',
            'sector_tags': ['all'],
        },
        {
            'name': 'QIA',
            'tier': 'S',
            'category': '顶级主权基金/养老金',
            'aliases': ['qia', 'qatar investment authority', '卡塔尔投资局'],
            'role_note': '中东主权财富基金，长期资金属性强',
            'sector_tags': ['all'],
        },
        {
            'name': 'ADIA',
            'tier': 'S',
            'category': '顶级主权基金/养老金',
            'aliases': ['adia', 'abu dhabi investment authority', '阿布扎比投资局'],
            'role_note': '全球大型主权财富基金，长期配置能力强',
            'sector_tags': ['all'],
        },
        {
            'name': 'CPPIB',
            'tier': 'S',
            'category': '顶级主权基金/养老金',
            'aliases': ['cpp investments', 'cppib', 'canada pension plan', '加拿大养老金'],
            'role_note': '养老金属性长线资金',
            'sector_tags': ['all'],
        },
        {
            'name': 'KIA',
            'tier': 'S',
            'category': '顶级主权基金/养老金',
            'aliases': ['kuwait investment authority', 'kia', '科威特投资局'],
            'role_note': '主权财富基金，长线属性强',
            'sector_tags': ['all'],
        },
        {
            'name': 'BlackRock',
            'tier': 'S',
            'category': '全球顶级长线资管',
            'aliases': ['blackrock', '贝莱德', '貝萊德'],
            'role_note': '全球顶级资管，市场背书和定价锚较强',
            'sector_tags': ['all'],
        },
        {
            'name': 'Capital Group',
            'tier': 'S',
            'category': '全球顶级长线资管',
            'aliases': ['capital group', 'capital research', '资本集团'],
            'role_note': '全球长线资管，研究体系成熟',
            'sector_tags': ['all'],
        },
        {
            'name': 'Fidelity/FMR',
            'tier': 'S',
            'category': '全球顶级长线资管',
            'aliases': ['fidelity international', 'fidelity', 'fmr', '富达'],
            'role_note': '全球顶级长线资管，机构认可度高',
            'sector_tags': ['all'],
        },
        {
            'name': 'T. Rowe Price',
            'tier': 'S',
            'category': '全球顶级长线资管',
            'aliases': ['t. rowe price', 't rowe price', '普信'],
            'role_note': '全球成长型长线资管',
            'sector_tags': ['all'],
        },
        {
            'name': 'Schroders',
            'tier': 'S',
            'category': '全球顶级长线资管',
            'aliases': ['schroders', '施罗德'],
            'role_note': '国际长线资管机构',
            'sector_tags': ['all'],
        },
        {
            'name': 'Oaktree Capital',
            'tier': 'S',
            'category': '全球顶级长线资管',
            'aliases': ['oaktree', 'oaktree capital', '橡树资本'],
            'role_note': '全球顶级困境资产/信用投资机构，港股基石参投经验丰富',
            'sector_tags': ['all'],
        },
        {
            'name': 'Mubadala',
            'tier': 'S',
            'category': '顶级主权基金/养老金',
            'aliases': ['mubadala', 'mubadala investment', '穆巴达拉'],
            'role_note': '阿布扎比主权财富基金，长线配置能力强',
            'sector_tags': ['all'],
        },
        {
            'name': 'Ontario Teachers',
            'tier': 'S',
            'category': '顶级主权基金/养老金',
            'aliases': ['ontario teachers', 'ontario teachers pension', '安大略教师', '安大略'],
            'role_note': '加拿大大型养老金，长线属性强',
            'sector_tags': ['all'],
        },
        {
            'name': 'Norges Bank',
            'tier': 'S',
            'category': '顶级主权基金/养老金',
            'aliases': ['norges bank', 'norway central bank', '挪威央行', '挪威主权'],
            'role_note': '全球最大主权财富基金之一，长期配置能力强',
            'sector_tags': ['all'],
        },
        {
            'name': 'PIF',
            'tier': 'S',
            'category': '顶级主权基金/养老金',
            'aliases': ['public investment fund', 'pif', '沙特主权', '沙特公共投资基金'],
            'role_note': '中东大型主权财富基金，长期资金属性强',
            'sector_tags': ['all'],
        },
        {
            'name': 'Tencent',
            'tier': 'S',
            'category': '强产业战略投资者',
            'aliases': ['tencent', '腾讯', 'huang river', 'huang river investment'],
            'role_note': '强产业生态基石，若业务协同明确则含金量高',
            'sector_tags': ['hardtech', 'consumer'],
        },
        {
            'name': 'Alibaba',
            'tier': 'S',
            'category': '强产业战略投资者',
            'aliases': ['alibaba', '阿里巴巴', '阿里'],
            'role_note': '强产业生态基石，若业务协同明确则含金量高',
            'sector_tags': ['hardtech', 'consumer'],
        },
        {
            'name': 'CATL',
            'tier': 'S',
            'category': '强产业战略投资者',
            'aliases': ['catl', '宁德时代'],
            'role_note': '产业链龙头背书，订单/生态协同价值高',
            'sector_tags': ['hardtech'],
        },
        {
            'name': 'Hillhouse/HHLR',
            'tier': 'A',
            'category': '一线PE/VC/成长基金',
            'aliases': ['hillhouse', 'hhlr', 'hhlra', '高瓴'],
            'role_note': '一线成长基金，科技/医疗投资经验强',
            'sector_tags': ['healthcare', 'hardtech', 'consumer'],
        },
        {
            'name': 'HongShan/红杉中国',
            'tier': 'A',
            'category': '一线PE/VC/成长基金',
            'aliases': ['hongshan', 'sequoia china', '红杉中国', '红杉'],
            'role_note': '一线成长基金，项目筛选能力强',
            'sector_tags': ['healthcare', 'hardtech', 'consumer'],
        },
        {
            'name': 'Boyu Capital',
            'tier': 'A',
            'category': '一线PE/VC/成长基金',
            'aliases': ['boyu', '博裕'],
            'role_note': '一线PE机构，背书有参考价值',
            'sector_tags': ['all'],
        },
        {
            'name': 'Primavera',
            'tier': 'A',
            'category': '一线PE/VC/成长基金',
            'aliases': ['primavera', '春华'],
            'role_note': '一线PE机构，背书有参考价值',
            'sector_tags': ['all'],
        },
        {
            'name': 'CPE',
            'tier': 'A',
            'category': '一线PE/VC/成长基金',
            'aliases': ['cpe', '源峰'],
            'role_note': '成长型投资机构，背书有参考价值',
            'sector_tags': ['all'],
        },
        {
            'name': 'Qiming Venture',
            'tier': 'A',
            'category': '一线PE/VC/成长基金',
            'aliases': ['qiming', '启明'],
            'role_note': '医疗/科技投资经验较强',
            'sector_tags': ['healthcare', 'hardtech'],
        },
        {
            'name': 'OrbiMed',
            'tier': 'A',
            'category': '医疗专业基金',
            'aliases': ['orbimed', '奥博'],
            'role_note': '医疗专业基金，行业尽调能力强',
            'sector_tags': ['healthcare'],
        },
        {
            'name': 'Deerfield',
            'tier': 'A',
            'category': '医疗专业基金',
            'aliases': ['deerfield'],
            'role_note': '医疗健康专业基金，临床/管线判断有参考价值',
            'sector_tags': ['healthcare'],
        },
        {
            'name': 'RTW',
            'tier': 'A',
            'category': '医疗专业基金',
            'aliases': ['rtw funds', 'rtw'],
            'role_note': '生物科技全生命周期投资机构，行业背书较强',
            'sector_tags': ['healthcare'],
        },
        {
            'name': 'Lake Bleu',
            'tier': 'A',
            'category': '医疗专业基金',
            'aliases': ['lake bleu', '清池'],
            'role_note': '医疗主题基金，赛道匹配度高',
            'sector_tags': ['healthcare'],
        },
        {
            'name': 'LAV / Lilly Asia Ventures',
            'tier': 'A',
            'category': '医疗专业基金',
            'aliases': ['lilly asia ventures', 'lav', 'lilly asia', '礼来亚洲', '禮來亞洲'],
            'role_note': '全球顶级医疗健康VC，生物医药管线判断力强',
            'sector_tags': ['healthcare'],
        },
        {
            'name': 'IDG Capital',
            'tier': 'A',
            'category': '一线PE/VC/成长基金',
            'aliases': ['idg capital', 'idg', 'idg breyer fund', 'idg breyer'],
            'role_note': '全球知名科技VC，跨越AI芯片/医药领域基石参投',
            'sector_tags': ['hardtech', 'healthcare'],
        },
        {
            'name': 'Greenwoods/景林',
            'tier': 'A',
            'category': '一线PE/VC/成长基金',
            'aliases': ['greenwoods', 'greenwoods asset', '景林', '景林资产', 'greenwoods investment'],
            'role_note': '中国头部私募基金，2025年港股基石参投最活跃机构(14次)',
            'sector_tags': ['all'],
        },
        {
            'name': '高毅资产',
            'tier': 'A',
            'category': '一线PE/VC/成长基金',
            'aliases': ['gaoyi', 'gao yi', '高毅资产', '高毅'],
            'role_note': '中国头部长线私募基金，港股基石参投经验丰富(10次+)',
            'sector_tags': ['all'],
        },
        {
            'name': 'Danshuiquan',
            'tier': 'A',
            'category': '一线PE/VC/成长基金',
            'aliases': ['danshuiquan', 'dan shui quan', '淡水泉'],
            'role_note': '中国头部长线私募基金，擅长消费/医疗/科技领域',
            'sector_tags': ['all'],
        },
        {
            'name': 'General Atlantic',
            'tier': 'A',
            'category': '一线PE/VC/成长基金',
            'aliases': ['general atlantic', '泛大西洋', '泛大西洋投资'],
            'role_note': '全球领先成长型股权基金，聚焦科技/消费/医疗',
            'sector_tags': ['hardtech', 'healthcare', 'consumer'],
        },
        {
            'name': 'Millennium',
            'tier': 'A',
            'category': '全球顶级长线资管',
            'aliases': ['millennium', 'millennium management', '千禧年', '千禧年基金'],
            'role_note': '全球头部多策略对冲基金，港股基石参投活跃',
            'sector_tags': ['all'],
        },
        {
            'name': 'ORIX Asia AM',
            'tier': 'A',
            'category': '大型投行/资管平台',
            'aliases': ['orix', 'orix asia', 'orix asia am', '欧力士', '欧力士亚洲'],
            'role_note': '日本金融集团资管平台，近年港股基石参投',
            'sector_tags': ['all'],
        },
        {
            'name': 'YF Capital/云锋投资',
            'tier': 'A',
            'category': '一线PE/VC/成长基金',
            'aliases': ['yf capital', 'yunfeng capital', 'yunfeng', '云锋投资', '云锋'],
            'role_note': '马云/虞锋发起PE基金，产业资源/生态协同强',
            'sector_tags': ['hardtech', 'healthcare', 'consumer'],
        },
        {
            'name': 'Decheng Capital',
            'tier': 'A',
            'category': '医疗专业基金',
            'aliases': ['decheng capital', 'decheng', '德诚', '德诚资本'],
            'role_note': '全球医疗健康专业VC，生物医药管线尽调能力强',
            'sector_tags': ['healthcare'],
        },
        {
            'name': 'WuXi AppTec Fund',
            'tier': 'A',
            'category': '医疗专业基金',
            'aliases': ['wuxi apptec', 'wuxi fund', 'wuxi pharmatech', '药明康德', '药明'],
            'role_note': '全球CXO龙头药明康德投资平台，行业生态协同',
            'sector_tags': ['healthcare'],
        },
        {
            'name': 'UBS Asset Management',
            'tier': 'A',
            'category': '大型投行/资管平台',
            'aliases': ['ubs asset management', 'ubs am', '瑞银资管', '瑞银', '瑞銀'],
            'role_note': '国际大型资管平台，机构认可度较好',
            'sector_tags': ['all'],
        },
        {
            'name': 'JPMorgan Asset Management',
            'tier': 'A',
            'category': '大型投行/资管平台',
            'aliases': ['jpmorgan asset management', 'jp morgan asset management', 'jpm am', '摩根资产'],
            'role_note': '国际大型资管平台，机构认可度较好',
            'sector_tags': ['all'],
        },
        {
            'name': 'Invesco',
            'tier': 'A',
            'category': '大型投行/资管平台',
            'aliases': ['invesco', '景顺'],
            'role_note': '国际资管机构，背书有参考价值',
            'sector_tags': ['all'],
        },
        {
            'name': 'M&G',
            'tier': 'A',
            'category': '大型投行/资管平台',
            'aliases': ['m&g', 'm g investment', 'm&g investments'],
            'role_note': '国际资管机构，背书有参考价值',
            'sector_tags': ['all'],
        },
        {
            'name': 'Morgan Stanley IM',
            'tier': 'A',
            'category': '大型投行/资管平台',
            'aliases': ['morgan stanley investment management', 'morgan stanley im', '摩根士丹利投资管理'],
            'role_note': '国际大型资管平台',
            'sector_tags': ['all'],
        },
        {
            'name': 'Goldman Sachs AM',
            'tier': 'A',
            'category': '大型投行/资管平台',
            'aliases': ['goldman sachs asset management', 'goldman sachs am', '高盛资管'],
            'role_note': '国际大型资管平台',
            'sector_tags': ['all'],
        },
        {
            'name': '国风投/国新系',
            'tier': 'A',
            'category': '知名中资长线/国资基金',
            'aliases': ['china venture capital innovation', '国风投', '国新', '国调基金', '中国诚通', '诚通', '混改基金'],
            'role_note': '国家级/央企背景资本，政策和产业认可度较强',
            'sector_tags': ['hardtech', 'healthcare'],
        },
        {
            'name': 'China AMC',
            'tier': 'A',
            'category': '知名中资长线/保险/公募',
            'aliases': ['china amc', '华夏基金', '华夏', '華夏'],
            'role_note': '头部中资公募，国内资金认可度较好',
            'sector_tags': ['all'],
        },
        {
            'name': 'Fullgoal Fund',
            'tier': 'A',
            'category': '知名中资长线/保险/公募',
            'aliases': ['fullgoal', '富国基金', '富国'],
            'role_note': '头部中资公募，国内资金认可度较好',
            'sector_tags': ['all'],
        },
        {
            'name': 'GF Fund',
            'tier': 'A',
            'category': '知名中资长线/保险/公募',
            'aliases': ['gf fund', '广发基金', '广发'],
            'role_note': '头部中资公募，国内资金认可度较好',
            'sector_tags': ['all'],
        },
        {
            'name': 'ICBC Credit Suisse/ICBC Wealth',
            'tier': 'A',
            'category': '知名中资长线/保险/公募',
            'aliases': ['icbcubs', 'icbc wealth', 'icbc credit suisse', '工银瑞信', '工银理财'],
            'role_note': '银行系/公募长线资金，稳定性较好',
            'sector_tags': ['all'],
        },
        {
            'name': 'E Fund',
            'tier': 'A',
            'category': '知名中资长线/保险/公募',
            'aliases': ['e fund', '易方达'],
            'role_note': '头部中资公募，国内资金认可度较好',
            'sector_tags': ['all'],
        },
        {
            'name': 'Mirae Asset',
            'tier': 'A',
            'category': '大型投行/资管平台',
            'aliases': ['mirae', '未来资产', '未來資產'],
            'role_note': '亚洲大型金融/资管平台，具备区域资金背书',
            'sector_tags': ['all'],
        },
        {
            'name': 'Huadeng Technology/华登国际',
            'tier': 'B',
            'category': '区域/主题基金',
            'aliases': ['huadeng technology', 'huadeng', '华登国际', '华登科技', 'walden international', 'walden technology'],
            'role_note': '历史悠久的半导体/TMT主题基金，在科技领域有一定背书',
            'sector_tags': ['hardtech', 'healthcare'],
        },
        {
            'name': 'Arc Avenue',
            'tier': 'B',
            'category': '区域/主题基金',
            'aliases': ['arc avenue'],
            'role_note': '区域资管平台，背书强度弱于全球头部机构',
            'sector_tags': ['all'],
        },
        {
            'name': 'Isometry Global',
            'tier': 'B',
            'category': '区域/主题基金',
            'aliases': ['isometry global', 'isometry'],
            'role_note': '主题基金，公开长期业绩和规模透明度有限',
            'sector_tags': ['healthcare'],
        },
        {
            'name': 'Sage Partners',
            'tier': 'B',
            'category': '区域/主题基金',
            'aliases': ['sage partners', 'sage'],
            'role_note': '主题基金，公开长期业绩和规模透明度有限',
            'sector_tags': ['healthcare'],
        },
        {
            'name': '地方/普通产业基金',
            'tier': 'B',
            'category': '地方国资/小型产业基金',
            'aliases': ['local government', 'city investment', 'industrial fund', '产业基金', '地方国资', '城市基金', 'huatai capital', '华泰资本'],
            'role_note': '有资金承诺，但独立研究背书较弱',
            'sector_tags': ['all'],
        },
        {
            'name': '客户/供应商/经销商',
            'tier': '弱',
            'category': '客户/供应商/经销商',
            'aliases': ['customer', 'supplier', 'distributor', '客户', '供应商', '经销商'],
            'role_note': '可能有产业关系，但独立定价判断较弱',
            'sector_tags': ['all'],
        },
        {
            'name': '不透明SPV/家办/券商关联资金',
            'tier': '弱',
            'category': '不透明基金/关系型资金',
            'aliases': ['family office', 'spv', 'special purpose vehicle', 'newly incorporated', 'sole limited partner', '家族办公室', '新设基金', '券商关联'],
            'role_note': '透明度较低，对公司质地背书有限',
            'sector_tags': ['all'],
        },
    ]

    # 章节锚点：用于判断是否存在基石投资者章节
    CORNERSTONE_ANCHORS = [
        'cornerstone investors',
        'cornerstone placing',
        'cornerstone investor',
        'cornerstone investment agreement',
        '基石投资者',
        '基石投資者',
        '基石配售',
        '基石投資協議',
        '基石投資者的資料',
    ]

    # 排除上下文：命中这些章节时，不得将投资者算作基石
    EXCLUSION_ANCHORS = [
        'pre-ipo investment',
        'pre-ipo investors',
        'pre-ipo financing',
        'shareholders',
        'substantial shareholders',
        'sophisticated independent investors',
        'pathfinder sophisticated independent investors',
        'previous investors',
        'prior investors',
        '历史投资者',
        '上市前投资',
        '首次公开发售前投资',
        '资深独立投资者',
        '领航资深独立投资者',
        '股东',
        '主要股东',
    ]

    def _find_section_anchor(self, text, anchors):
        """在 text 中查找 anchors 的最早出现位置，返回 (idx, anchor) 或 (-1, None)"""
        lower_text = text.lower()
        best_idx = -1
        best_anchor = None
        for anchor in anchors:
            idx = text.find(anchor) if any(ord(c) > 127 for c in anchor) else lower_text.find(anchor)
            if idx >= 0 and (best_idx < 0 or idx < best_idx):
                best_idx = idx
                best_anchor = anchor
        return best_idx, best_anchor

    def _cornerstone_context(self, text):
        """返回 (context, has_cornerstone_section)。
        如果没有找到基石锚点，不再 fallback 到全文扫描。
        优先查找正文章节中的锚点，跳过目录页（TOC）的匹配。
        找到真正的章节边界，确保覆盖所有基石信息。"""
        idx, anchor = self._find_section_anchor(text, self.CORNERSTONE_ANCHORS)
        if idx < 0:
            return "", False

        # 对于短文本（如测试用例），直接使用锚点位置
        if len(text) < 10000:
            context = text[idx:idx + 120000]
            return context, True

        # 检查是否在目录页（TOC）附近 - TOC 通常在文档前 10% 位置
        toc_region_end = len(text) // 10
        if idx < toc_region_end:
            # 跳过 TOC 区域，搜索正文章节
            remaining_text = text[toc_region_end:]
            idx2, anchor2 = self._find_section_anchor(remaining_text, self.CORNERSTONE_ANCHORS)
            if idx2 >= 0:
                idx = toc_region_end + idx2

        # 检查找到的位置是否在目录页
        lines_before = text[:idx].count('\n')
        if lines_before < 100:
            return "", False

        # 找到章节结束位置 - 搜索下一个同级别章节锚点或下一个大标题
        end_idx = self._find_section_end(text, idx)

        # 确保 context 至少覆盖 500000 字符，以包含所有基石投资者
        context = text[idx:max(end_idx, idx + 500000)]
        return context, True

    def _find_section_end(self, text, start_idx):
        """找到章节结束位置。"""
        # 章节结束标记：下一个主要章节标题（通常为大写且较短）
        # 或特定关键词如 "UNDERWRITING", "LOCK-UP", "ADDITIONAL INFORMATION"
        end_markers = [
            'UNDERWRITING', 'UNDERWRITERS', 'UNDERWRITING AGREEMENT',
            'LOCK-UP', 'LOCK UP',
            'ADDITIONAL INFORMATION', 'STATUTORY AND GENERAL INFORMATION',
            'APPENDIX', 'DEFINITIONS',
            'SHARE CAPITAL', 'FUTURE PLANS', 'USE OF PROCEEDS',
        ]

        # 搜索最近的有效结束位置
        min_end = len(text)

        for marker in end_markers:
            idx = text.find(marker, start_idx + 1000)  # 至少在开始位置1KB之后
            if idx > start_idx and idx < min_end:
                min_end = idx

        # 如果没有找到明确的结束标记，搜索下一个大写开头的行
        if min_end == len(text):
            # 搜索 "\n\n" 后的大写行
            search_start = start_idx + 1000
            pattern = r'\n\n([A-Z][A-Z\s]{5,50})\n'
            import re
            matches = list(re.finditer(pattern, text[search_start:]))
            if matches:
                min_end = search_start + matches[0].start()

        return min_end

    def _is_in_excluded_section(self, text, hit_idx):
        """判断 hit_idx 位置是否落在排除章节（pre-IPO/股东/资深独立投资者等）内。
        排除章节从锚点开始，到下一个同等级标题或文档末尾结束。
        关键规则：如果 hit_idx 之前存在基石章节锚点，且 hit_idx 在基石章节锚点之后，
        则 hit_idx 属于基石章节，不再受前面排除章节的影响。"""
        lower_text = text.lower()
        # 找到 hit_idx 之前最近的基石章节锚点位置
        cs_anchor_pos = -1
        for anchor in self.CORNERSTONE_ANCHORS:
            idx = text.find(anchor) if any(ord(c) > 127 for c in anchor) else lower_text.find(anchor)
            if idx >= 0 and idx < hit_idx and idx > cs_anchor_pos:
                cs_anchor_pos = idx

        # 如果 hit_idx 在基石章节锚点之后，则不属于排除章节
        if cs_anchor_pos >= 0 and hit_idx > cs_anchor_pos:
            return False

        # 收集所有排除章节的起始位置
        exclusion_ranges = []
        for anchor in self.EXCLUSION_ANCHORS:
            start = text.find(anchor) if any(ord(c) > 127 for c in anchor) else lower_text.find(anchor)
            if start < 0:
                continue
            # 章节结束：找下一个看起来像标题的行（大写开头、较短）或下一个排除锚点
            end = len(text)
            for other in self.EXCLUSION_ANCHORS:
                if other == anchor:
                    continue
                ostart = text.find(other) if any(ord(c) > 127 for c in other) else lower_text.find(other)
                if ostart > start:
                    end = min(end, ostart)
            # 同时以下一个空行+大写行作为章节边界
            next_block = text.find('\n\n', start + len(anchor))
            if next_block > start:
                # 再往后找下一个可能的标题行
                for m in re.finditer(r'\n\n([A-Z][A-Za-z\s]{3,60})\s*\n', text[next_block:]):
                    end = min(end, next_block + m.start())
                    break
            exclusion_ranges.append((start, end))
        for start, end in exclusion_ranges:
            if start <= hit_idx < end:
                return True
        return False

    def _matched_investors(self, context, full_text="", context_start_idx=0):
        """在基石章节内匹配投资者，排除 pre-IPO/股东等上下文中的命中。
        返回的 payload 中带有 source 字段：
        - 'cornerstone_section': 从基石章节中匹配到的投资者
        - 'pre_ipo_section': 从排除章节中匹配到的投资者（不计入基石评分）
        """
        profiles = self._matched_profiles_with_exclusion(context, full_text, context_start_idx)
        return [
            self._profile_match_payload_with_source(profile)
            for profile in profiles
            if profile.get('tier') in ('S', 'A')
        ]

    def _matched_profiles_with_exclusion(self, context, full_text="", context_start_idx=0):
        """匹配投资者档案，排除落在 pre-IPO/股东章节中的命中。
        返回的 profile dict 中带有 _source 字段。"""
        if not context:
            return []
        matched = []
        seen = set()
        for profile in self.INVESTOR_PROFILES:
            aliases = profile.get('aliases', [])
            hit_alias = None
            hit_idx = -1
            for alias in aliases:
                idx = context.lower().find(alias.lower())
                if idx >= 0:
                    hit_alias = alias
                    hit_idx = idx
                    break
            if hit_alias is None:
                continue
            # 检查命中位置是否在排除章节内
            source = 'cornerstone_section'
            if full_text:
                absolute_idx = context_start_idx + hit_idx
                if self._is_in_excluded_section(full_text, absolute_idx):
                    source = 'pre_ipo_section'
            key = profile['name']
            if key in seen:
                continue
            seen.add(key)
            profile_copy = dict(profile)
            profile_copy['_source'] = source
            matched.append(profile_copy)
        matched.sort(key=lambda item: {'S': 0, 'A': 1, 'B': 2, '弱': 3}.get(item.get('tier'), 4))
        return matched

    @staticmethod
    def _profile_match_payload_with_source(profile):
        return {
            'name': profile.get('name'),
            'tier': profile.get('tier'),
            'category': profile.get('category'),
            'role_note': profile.get('role_note'),
            'source': profile.get('_source', 'cornerstone_section'),
        }

    @staticmethod
    def _profile_match_payload(profile):
        return {
            'name': profile.get('name'),
            'tier': profile.get('tier'),
            'category': profile.get('category'),
            'role_note': profile.get('role_note'),
        }

    TIER_SORT_ORDER = {'S': 0, 'A': 1, 'B': 2, '弱': 3}

    def _match_profiles(self, text, best_only=False):
        if not text:
            return None if best_only else []
        matched = []
        seen = set()
        for profile in self.INVESTOR_PROFILES:
            if not _contains_any(text, profile.get('aliases', [])):
                continue
            key = profile['name']
            if key in seen:
                continue
            seen.add(key)
            matched.append(profile)
        matched.sort(key=lambda item: self.TIER_SORT_ORDER.get(item.get('tier'), 4))
        return matched[0] if best_only and matched else (matched[0] if best_only else matched)

    def _best_profile(self, text):
        return self._match_profiles(text, best_only=True)

    def _matched_profiles(self, text):
        return self._match_profiles(text, best_only=False)

    def _effective_tier_score(self, tier, offer_pct=None):
        effective_tier = tier or '未知'
        if tier == 'S' and offer_pct is not None and offer_pct < 1:
            effective_tier = 'A'
        elif tier == 'A' and offer_pct is not None and offer_pct < 1:
            effective_tier = 'B'
        return self.TIER_BASE_SCORE.get(effective_tier, self.TIER_BASE_SCORE['未知'])

    INDEPENDENCE_RULES = [
        (['主权', '养老金', '全球顶级长线资管'], (95, '独立长线')),
        (['大型投行/资管', '医疗专业基金', '中资长线'], (82, '独立机构')),
        (['PE/VC', '成长基金'], (72, '专业财务投资')),
        (['客户', '供应商', '关系型'], (35, '独立性弱')),
        (['地方', '区域'], (58, '独立性一般')),
    ]

    @staticmethod
    def _independence_score(profile):
        if not profile:
            return 45, '未知'
        category = profile.get('category', '')
        for keywords, result in CornerstoneAnalyzer.INDEPENDENCE_RULES:
            if any(kw in category for kw in keywords):
                return result
        return 60, '一般独立'

    @staticmethod
    def _sector_fit_score(profile, sector):
        if not profile:
            return 45, '未知'
        tags = profile.get('sector_tags') or []
        category = profile.get('category', '')
        if 'all' in tags or '主权' in category or '全球顶级长线资管' in category:
            return 78, '通用强背书'
        if sector and sector in tags:
            return 90, '赛道强匹配'
        CATEGORY_FIT = {'产业战略': (55, '需核实产业协同'), '客户': (45, '可能商业绑定'), '供应商': (45, '可能商业绑定')}
        for cat_kw, result in CATEGORY_FIT.items():
            if cat_kw in category:
                return result
        return 60, '赛道相关性一般'

    @staticmethod
    def _weighted_average(values):
        weighted = [(v, w) for v, w in values if v is not None and w and w > 0]
        if not weighted:
            return None
        total_weight = sum(w for _, w in weighted)
        return sum(v * w for v, w in weighted) / total_weight if total_weight else None

    @staticmethod
    def _normalize_cornerstone_line(line):
        if line is None:
            return ""
        line = re.sub(r'[\x00-\x1f\x7f-\x9f\u0002]+', ' ', line)
        line = line.replace(' ', ' ')
        line = re.sub(r'\s+', ' ', line)
        return line.strip(' \t\r\n-–—')

    @staticmethod
    def _parse_all_numbers(text):
        """Extract all numbers from text, handling footnote markers like (1)"""
        if not text:
            return []
        text = text.strip()
        text = re.sub(r'^\([0-9]+\)\s*', '', text)
        parts = text.split()
        numbers = []
        for part in parts:
            cleaned = re.sub(r'^\([0-9]+\)\s*', '', part)
            match = re.search(r'([0-9,]+(?:\.[0-9]+)?)', cleaned)
            if match:
                num_str = match.group(1).replace(',', '')
                try:
                    numbers.append(float(num_str))
                except (ValueError, TypeError):
                    pass
        return numbers

    @staticmethod
    def _is_numeric_cell(line):
        if not line:
            return False
        text = line.strip().replace(' ', '')
        if re.match(r'\([0-9]+\)', text):
            return True
        return bool(re.fullmatch(r'[0-9][0-9,]*(?:\.[0-9]+)?%?(?:\([0-9]+\))?', text))

    @staticmethod
    def _parse_cornerstone_number(text):
        if not text:
            return None
        text = text.strip()
        
        match = re.match(r'\([0-9]+\)(.+)', text)
        if match:
            text = match.group(1)
        
        match = re.search(r'([0-9,]+(?:\.[0-9]+)?)', text)
        if not match:
            return None
        num_str = match.group(1)
        try:
            return float(num_str.replace(',', ''))
        except Exception:
            return None

    @staticmethod
    def _detect_cornerstone_amount_context(table_text):
        lower_text = (table_text or '').lower()
        if (
            'usd in' in lower_text
            or 'us$ in' in lower_text
            or '$u.s. in' in lower_text
            or 'u.s. in' in lower_text
            or '(usd' in lower_text
            or '($u.s.' in lower_text
        ):
            currency = 'USD'
        elif 'hk$' in lower_text or 'in hk$' in lower_text:
            currency = 'HKD'
        elif 'us$' in lower_text or 'usd' in lower_text or '$u.s.' in lower_text:
            currency = 'USD'
        else:
            currency = 'UNKNOWN'

        if 'in hk$' in lower_text or 'in us$' in lower_text:
            unit = 'raw'
        elif 'million' in lower_text:
            unit = 'million'
        else:
            unit = 'raw'
        return currency, unit

    def _cornerstone_amount_fields(self, raw_amount_text, table_text):
        raw_amount = self._parse_cornerstone_number(raw_amount_text)
        if raw_amount is None:
            return {
                'investment_currency': None,
                'investment_amount_m': None,
                'investment_amount_hkd_m': None,
                'total_investment_amount_hkd_m': None,
                'total_investment_amount_usd_m': None,
            }

        currency, unit = self._detect_cornerstone_amount_context(table_text)
        amount_m = raw_amount
        if (unit == 'raw' or currency == 'HKD') and abs(raw_amount) > 10000:
            amount_m = raw_amount / 1_000_000

        hkd_m = None
        usd_m = None
        if currency == 'HKD':
            hkd_m = amount_m
        elif currency == 'USD':
            usd_m = amount_m
            hkd_m = amount_m * SETTINGS.fx.usd_to_hkd_precise

        return {
            'investment_currency': currency,
            'investment_amount_m': amount_m,
            'investment_amount_hkd_m': hkd_m,
            'total_investment_amount_hkd_m': hkd_m,
            'total_investment_amount_usd_m': usd_m,
        }

    def _cornerstone_short_name(self, name):
        if not name:
            return ""
        match = re.search(r'“([^”]+)”', name)
        if not match:
            match = re.search(r'"([^"]+)"', name)
        if match:
            return self._normalize_cornerstone_line(match.group(1))

        lowered = name.lower()
        if ' for and on behalf of ' in lowered:
            name = re.split(r'\s+for and on behalf of\s+', name, maxsplit=1, flags=re.IGNORECASE)[0]

        name = re.sub(r'\([^()]*\)', ' ', name)
        name = self._normalize_cornerstone_line(name)
        return name

    def _extract_cornerstone_rows(self, context):
        if not context:
            return []

        lower_context = context.lower()
        priority_markers = [
            'the table below sets forth details of the cornerstone placing',
            'the tables below set forth details of the cornerstone placing',
            'the tables below set forth the details of the cornerstone placing',
            'the cornerstone investors\nthe table below',
            'the cornerstone investors\r\nthe table below',
        ]
        fallback_markers = [
            'the cornerstone investors',
            'cornerstone investors',
        ]
        start_idx = -1
        for marker in priority_markers:
            idx = lower_context.find(marker)
            if idx >= 0:
                start_idx = idx
                break
        if start_idx < 0:
            for marker in fallback_markers:
                idx = lower_context.find(marker)
                if idx >= 0:
                    start_idx = idx
                    break
        if start_idx < 0:
            return []

        end_markers = [
            'notes:',
        ]
        end_idx = len(context)
        for marker in end_markers:
            idx = lower_context.find(marker, start_idx)
            if idx >= 0:
                end_idx = min(end_idx, idx)

        table_text = context[start_idx:end_idx]
        lines = [self._normalize_cornerstone_line(line) for line in table_text.splitlines()]
        lines = [line for line in lines if line]

        _NOISE_KW = [
            'the table below sets forth details of the cornerstone placing',
            'the tables below set forth',
            'cornerstone investor',
            'total investment amount',
            'number of offer shares',
            'approximate % of the offer shares',
            'approximate % of the issued share capital',
            '(usd in millions)',
            'based on the offer price',
            'assuming the over-allotment',
            'option is not exercised',
            'option is exercised',
            'offer shares to be acquired',
            'immediately upon',
            'completion of the global offering',
            '(in hk$)',
            'note ',
            'subject to rounding',
            'notes:',
        ]
        _NOISE_EXACT = {
            'total', 'investment', 'amount', 'subscription', 'subscription amount',
            'number of', 'number of offer', 'offer', 'shares', 'offer shares',
            'shares to be acquired', 'approximate', '%', '% of the', '% of our',
            '% of total', '% of the total', 'issued share', 'share capital',
            'capital', 'total issued', 'issued', 'immediately', 'upon',
            'completion of', 'the global', 'offering', 'global offering',
            '(usd in', 'usd in', 'millions)', 'millions', '($u.s. in',
            '$u.s. in', '(in hk$)', 'in hk$', 'assuming', 'the over',
            'allotment', 'option is', 'not', 'exercised', 'fully',
            'cornerstone investor', 'amount1', 'shares rounded',
            'down to nearest', 'whole board lot', 'of 500 h shares',
            'of 200 h shares', 'approximate % of total',
            'approximate % of h shares', 'approximate % of the',
            'approximate % of our', 'number of offer shares',
            'in issue immediately', 'following the completion of',
            'the global offering', 'shares in issue immediately',
            'cornerstone investors',
        }

        def _is_noise(line):
            ll = line.lower()
            compact = re.sub(r'\([0-9]+\)', '', ll)
            compact = re.sub(r'[^a-z0-9%$.\s]+', ' ', compact)
            compact = re.sub(r'\s+', ' ', compact).strip()
            if re.fullmatch(r'\d{1,3}', compact):
                return True
            if compact.startswith('based on the offer price'):
                return True
            if re.fullmatch(r'amount\d*', compact):
                return True
            return compact in _NOISE_EXACT or ll in _NOISE_EXACT or any(kw in ll for kw in _NOISE_KW)

        rows = []
        name_buffer = []
        numeric_buffer = []

        def flush_row():
            nonlocal name_buffer, numeric_buffer
            if not name_buffer or len(numeric_buffer) < 4:
                name_buffer = []
                numeric_buffer = []
                return

            cleaned_name_lines = []
            for part in name_buffer:
                if not _is_noise(part) or (part.lower() == 'capital' and cleaned_name_lines):
                    cleaned_name_lines.append(part)

            name = self._normalize_cornerstone_line(' '.join(cleaned_name_lines))
            if not name:
                name_buffer = []
                numeric_buffer = []
                return

            issued_share_pct_source = numeric_buffer[3]
            if len(numeric_buffer) >= 8:
                issued_share_pct_source = numeric_buffer[-2]

            row = {
                'name': name,
                'short_name': self._cornerstone_short_name(name),
                'offer_shares': int(self._parse_cornerstone_number(numeric_buffer[1]) or 0),
                'offer_shares_pct': self._parse_cornerstone_number(numeric_buffer[2]),
                'issued_share_pct': self._parse_cornerstone_number(issued_share_pct_source),
            }
            row.update(self._cornerstone_amount_fields(numeric_buffer[0], table_text))
            if (
                row['investment_amount_m'] is not None
                and row['offer_shares'] > 0
                and row['offer_shares_pct'] is not None
                and row['issued_share_pct'] is not None
                and 0 < row['offer_shares_pct'] <= 100
                and 0 <= row['issued_share_pct'] <= 100
            ):
                rows.append(row)
            name_buffer = []
            numeric_buffer = []

        for line in lines:
            lower_line = line.lower()
            if _is_noise(line):
                if lower_line == 'capital' and name_buffer and not numeric_buffer:
                    name_buffer.append(line)
                    continue
                if len(numeric_buffer) >= 4:
                    flush_row()
                elif numeric_buffer:
                    name_buffer = []
                    numeric_buffer = []
                continue

            if self._is_numeric_cell(line):
                if name_buffer:
                    numeric_buffer.append(line)
                continue

            if numeric_buffer:
                if len(numeric_buffer) >= 4:
                    flush_row()
                else:
                    continue

            if lower_line == 'notes:':
                break

            name_buffer.append(line)

        flush_row()

        if rows and any('tables below' in r.get('name', '').lower() or 'offer price' in r.get('name', '').lower() or 'global offering' in r.get('name', '').lower() for r in rows):
            rows = self._extract_cornerstone_by_regex(table_text)
        elif not rows:
            rows = self._extract_cornerstone_by_regex(table_text)

        return rows

    def _extract_cornerstone_by_regex(self, table_text):
        rows = []
        lines = table_text.split('\n')
        combined = ' '.join(line.strip() for line in lines if line.strip())
        combined = re.sub(r'[\x00-\x1f\x7f-\x9f]+', ' ', combined)
        combined = re.sub(r'\s+', ' ', combined)

        investor_patterns = [
            r'([A-Z][A-Za-z\s]{5,60}(?:Limited|Ltd|Capital|Fund|Investment|Partners?|Corporation|Inc\.))\s+'
            r'([0-9,]+(?:\.[0-9]+)?)\s+'
            r'([0-9,]+(?:\.[0-9]+)?)\s+'
            r'([0-9,.]+(?:\.[0-9]+)?)\s+'
            r'([0-9,.]+(?:\.[0-9]+)?)',
        ]
        for pattern in investor_patterns:
            for m in re.finditer(pattern, combined):
                try:
                    name = m.group(1).strip()
                    shares = int(float(m.group(3).replace(',', '')))
                    pct1 = float(m.group(4).replace(',', ''))
                    pct2 = float(m.group(5).replace(',', ''))
                    amount_fields = self._cornerstone_amount_fields(m.group(2), table_text)
                    if amount_fields.get('investment_amount_m') and shares > 1000 and 0 < pct1 <= 100:
                        row = {
                            'name': name,
                            'short_name': name,
                            'offer_shares': shares,
                            'offer_shares_pct': pct1,
                            'issued_share_pct': pct2 if pct2 <= 100 else None,
                        }
                        row.update(amount_fields)
                        rows.append(row)
                except (ValueError, IndexError):
                    continue
            if rows:
                seen_names = set()
                deduped = []
                for r in rows:
                    name_key = r.get('short_name', r.get('name', '')).strip().lower()
                    if name_key and name_key not in seen_names:
                        seen_names.add(name_key)
                        deduped.append(r)
                rows = deduped
                break
        return rows

    def _extract_cornerstone_detail_window(self, context, anchor, stop_anchors=None, window_size=2200):
        if not context or not anchor:
            return ""
        lower_context = context.lower()
        lower_anchor = anchor.lower()
        idx = lower_context.find(lower_anchor)
        if idx < 0:
            return ""
        end_idx = min(len(context), idx + window_size)
        for stop_anchor in stop_anchors or []:
            if not stop_anchor:
                continue
            lower_stop = stop_anchor.lower()
            if lower_stop == lower_anchor:
                continue
            stop_idx = lower_context.find(lower_stop, idx + len(lower_anchor) + 10)
            if stop_idx >= 0:
                end_idx = min(end_idx, stop_idx)
        return context[idx:end_idx]

    def _enrich_cornerstone_rows(self, context, rows):
        if not rows:
            return []

        narrative_markers = [
            'the information about our cornerstone investors set forth below has been provided',
            'the information about our cornerstone investors set forth below',
        ]
        narrative_idx = -1
        lower_context = context.lower()
        for marker in narrative_markers:
            idx = lower_context.find(marker)
            if idx >= 0 and (narrative_idx < 0 or idx < narrative_idx):
                narrative_idx = idx

        narrative = context[narrative_idx:] if narrative_idx >= 0 else context
        enriched = []
        row_stop_anchors = []
        for row in rows:
            if row.get('short_name'):
                row_stop_anchors.append(row.get('short_name'))
            if row.get('name'):
                row_stop_anchors.append(row.get('name'))

        for row in rows:
            anchors = []
            short_name = row.get('short_name') or ''
            if short_name:
                anchors.append(short_name)
            full_name = row.get('name') or ''
            if full_name and full_name not in anchors:
                anchors.append(full_name)

            related_matches = []
            related_profiles = []
            seen = set()
            for anchor in anchors:
                detail_window = self._extract_cornerstone_detail_window(
                    narrative,
                    anchor,
                    stop_anchors=row_stop_anchors,
                )
                if not detail_window:
                    continue
                for profile in self._matched_profiles(detail_window):
                    key = (profile.get('name'), profile.get('tier'))
                    if key in seen:
                        continue
                    seen.add(key)
                    related_profiles.append(profile)
                    related_matches.append(self._profile_match_payload(profile))

            direct_matches = []
            direct_profiles = []
            row_text = f"{row.get('name', '')} {row.get('short_name', '')}"
            for profile in self._matched_profiles(row_text):
                key = (profile.get('name'), profile.get('tier'))
                if key not in seen:
                    seen.add(key)
                    direct_profiles.append(profile)
                    direct_matches.append(self._profile_match_payload(profile))
            if direct_profiles:
                related_profiles = []
                related_matches = []

            # Prefer direct row-name matches over nearby narrative windows to avoid
            # short anchors (e.g. "ICBCUBS") inheriting the previous investor's profile.
            all_matches = direct_matches + related_matches
            all_profiles = direct_profiles + related_profiles
            best_profile = all_profiles[0] if all_profiles else self._best_profile(row_text)
            best_tier = best_profile.get('tier') if best_profile else None
            offer_pct = row.get('offer_shares_pct')
            tier_score = self._effective_tier_score(best_tier, offer_pct)
            independence_score, independence_label = self._independence_score(best_profile)
            sector_fit_score, sector_fit_label = self._sector_fit_score(best_profile, self._sector(context))

            dimension_notes = []
            if best_profile:
                dimension_notes.append(best_profile.get('role_note', ''))
            if best_tier in ('S', 'A') and offer_pct is not None and offer_pct < 1:
                dimension_notes.append('认购占比低于1%，加权时降一级')
            if sector_fit_label not in ('未知', '赛道相关性一般'):
                dimension_notes.append(sector_fit_label)

            row = dict(row)
            row['matched_investors'] = all_matches
            row['is_matched'] = bool(all_matches)
            row['tier'] = best_tier
            row['category'] = best_profile.get('category') if best_profile else '未知'
            row['role_note'] = best_profile.get('role_note') if best_profile else '未纳入高质量基石词库，按普通基石处理'
            row['tier_score'] = tier_score
            row['independence_score'] = independence_score
            row['independence_label'] = independence_label
            row['sector_fit_score'] = sector_fit_score
            row['sector_fit_label'] = sector_fit_label
            row['dimension_notes'] = [note for note in dimension_notes if note]
            if all_matches:
                row['match_note'] = "命中" + (f"，{best_tier}级" if best_tier else "")
                row['match_names'] = "、".join(f"{item.get('name')}({item.get('tier')})" for item in all_matches)
            elif best_profile:
                row['match_note'] = f"{best_tier}级 · {best_profile.get('category')}"
                row['match_names'] = best_profile.get('name', '')
            else:
                row['match_note'] = "未命中"
                row['match_names'] = ""
            enriched.append(row)

        return enriched

    def _extract_cornerstone_pct(self, context):
        if not context:
            return None

        candidates = []
        priority_candidates = []
        
        cornerstone_keyword_pattern = r'cornerstone investors?.{0,500}?([0-9]+(?:\.[0-9]+)?)%'
        for match in re.finditer(cornerstone_keyword_pattern, context, re.IGNORECASE | re.DOTALL):
            try:
                pct = float(match.group(1))
            except Exception:
                continue
            if 1 <= pct <= 95:
                priority_candidates.append(pct)
        
        direct_patterns = [
            r'represent(?:s|ing)? approximately ([0-9]+(?:\.[0-9]+)?)%',
            r'([0-9]+(?:\.[0-9]+)?)% of (?:the|our) (?:offer|global offering|placing) shares',
            r'([0-9]+(?:\.[0-9]+)?)% of the total offer shares',
        ]

        for pattern in direct_patterns:
            for match in re.finditer(pattern, context, re.IGNORECASE | re.DOTALL):
                try:
                    pct = float(match.group(1))
                except Exception:
                    continue
                if 1 <= pct <= 95:
                    match_pos = match.start()
                    
                    nearby_cornerstone = context.rfind('cornerstone', 0, match_pos + 50)
                    
                    if nearby_cornerstone >= 0 and (match_pos - nearby_cornerstone) < 300:
                        priority_candidates.append(pct)
                    else:
                        candidates.append(pct)

        share_patterns = [
            r'([0-9,]+(?:\.[0-9]+)?)\s*shares?.{0,120}?represent(?:s|ing)? approximately ([0-9]+(?:\.[0-9]+)?)%',
            r'([0-9,]+(?:\.[0-9]+)?)\s*shares?.{0,120}?out of ([0-9,]+(?:\.[0-9]+)?)\s*shares?',
        ]

        for pattern in share_patterns:
            for match in re.finditer(pattern, context, re.IGNORECASE | re.DOTALL):
                try:
                    if 'out of' in pattern:
                        numerator = float(match.group(1).replace(',', ''))
                        denominator = float(match.group(2).replace(',', ''))
                        if denominator > 0:
                            pct = numerator / denominator * 100
                        else:
                            continue
                    else:
                        pct = float(match.group(2))
                except Exception:
                    continue
                if 1 <= pct <= 95:
                    match_pos = match.start()
                    nearby_cornerstone = context.rfind('cornerstone', 0, match_pos + 50)
                    
                    if nearby_cornerstone >= 0 and (match_pos - nearby_cornerstone) < 300:
                        priority_candidates.append(pct)
                    else:
                        candidates.append(pct)

        if priority_candidates:
            return round(max(priority_candidates), 2)
        elif candidates:
            return round(max(candidates), 2)
        else:
            return None

    def _sector(self, text):
        return _infer_sector(text or '')

    def _sector_match(self, sector, context):
        lower_context = context.lower()
        if sector == 'healthcare':
            return any(keyword in lower_context for keyword in [
                'lake bleu', 'orbimed', 'healthcare', 'medical', 'biotech', 'life sciences',
                '清池', '奥博'
            ])
        if sector == 'hardtech':
            return any(keyword in lower_context for keyword in [
                'technology', 'tech', 'innovation', 'semiconductor', 'venture', 'science',
                'industrial', 'robot', 'robotics', 'automation', 'ai', 'high-tech',
                '科技', '创新', '半导体', '机器人'
            ])
        if sector == 'consumer':
            return any(keyword in lower_context for keyword in [
                'consumer', 'retail', 'brand', 'food', 'beverage', '消费'
            ])
        return None

    def _spv_risk_flags(self, context):
        lower_context = context.lower()
        hits = []
        patterns = [
            ('BVI/开曼注册主体较多', ['british virgin islands', 'bvi', 'cayman islands', '开曼']),
            ('出现 SPV / 特殊目的载体表述', ['special purpose vehicle', 'spv']),
            ('疑似临近 IPO 新设主体', ['newly incorporated', 'recently incorporated', 'incorporated on']),
            ('出资结构披露较单薄', ['single limited partner', 'sole limited partner', 'one limited partner']),
        ]
        for label, keywords in patterns:
            if any(keyword in lower_context for keyword in keywords):
                hits.append(label)
        return hits

    def _v2_profile_rows(self, cornerstone_rows, matched, sector):
        if cornerstone_rows:
            rows = []
            for row in cornerstone_rows:
                row = dict(row)
                direct_profile = self._best_profile(
                    " ".join(str(row.get(key, '')) for key in ('name', 'short_name'))
                )
                profile = direct_profile or self._best_profile(
                    " ".join(str(row.get(key, '')) for key in ('name', 'short_name', 'match_names', 'role_note'))
                )
                tier = row.get('tier') or (profile.get('tier') if profile else None)
                offer_pct = row.get('offer_shares_pct')
                tier_score = self._effective_tier_score(tier, offer_pct)
                independence_score, independence_label = self._independence_score(profile)
                sector_fit_score, sector_fit_label = self._sector_fit_score(profile, sector)
                notes = list(row.get('dimension_notes') or [])
                if tier in ('S', 'A') and offer_pct is not None and offer_pct < 1:
                    notes.append('认购占比低于1%，加权时降一级')
                row['tier'] = tier
                row['category'] = (direct_profile.get('category') if direct_profile else None) or row.get('category') or (profile.get('category') if profile else '未知')
                row['role_note'] = (direct_profile.get('role_note') if direct_profile else None) or row.get('role_note') or (profile.get('role_note') if profile else '未纳入高质量基石词库，按普通基石处理')
                row['tier_score'] = tier_score
                row['independence_score'] = independence_score
                row['independence_label'] = independence_label
                row['sector_fit_score'] = sector_fit_score
                row['sector_fit_label'] = sector_fit_label
                row['dimension_notes'] = [note for note in dict.fromkeys(notes) if note]
                rows.append(row)
            return rows

        rows = []
        for item in matched:
            profile = self._best_profile(item.get('name', ''))
            tier = item.get('tier') or (profile.get('tier') if profile else None)
            independence_score, independence_label = self._independence_score(profile)
            sector_fit_score, sector_fit_label = self._sector_fit_score(profile, sector)
            rows.append({
                'name': item.get('name', '--'),
                'short_name': item.get('name', '--'),
                'tier': tier,
                'category': item.get('category') or (profile.get('category') if profile else '未知'),
                'role_note': item.get('role_note') or (profile.get('role_note') if profile else ''),
                'tier_score': self._effective_tier_score(tier),
                'independence_score': independence_score,
                'independence_label': independence_label,
                'sector_fit_score': sector_fit_score,
                'sector_fit_label': sector_fit_label,
                'dimension_notes': [item.get('role_note')] if item.get('role_note') else [],
                'matched_investors': [item],
                'is_matched': True,
                'match_note': f"{tier}级",
            })
        return rows

    def _build_combination_summary(self, rows):
        categories = [row.get('category', '') for row in rows]
        groups = []
        if any('主权' in cat or '养老金' in cat for cat in categories):
            groups.append('国际主权/养老金')
        if any('全球顶级长线资管' in cat for cat in categories):
            groups.append('顶级资管')
        if any('医疗专业基金' in cat for cat in categories):
            groups.append('医疗基金')
        if any('国资' in cat for cat in categories):
            groups.append('国家队')
        if any('中资长线' in cat or '公募' in cat for cat in categories):
            groups.append('国内公募/长线资金')
        if any('PE/VC' in cat or '成长基金' in cat for cat in categories):
            groups.append('一线PE/VC')
        if any('产业战略' in cat for cat in categories):
            groups.append('产业资本')
        if not groups:
            groups.append('普通财务基石')

        missing = []
        if not any('主权' in cat or '养老金' in cat for cat in categories):
            missing.append('无国际主权')
        if not any('产业战略' in cat for cat in categories):
            missing.append('无产业药企/客户型战略基石')
        return " + ".join(groups) + ("；" + "、".join(missing) if missing else "")

    def _build_v2_result(self, cornerstone_rows, matched, cornerstone_pct, sector, sector_match, spv_flags):
        profile_rows = self._v2_profile_rows(cornerstone_rows, matched, sector)
        row_weights = []
        for row in profile_rows:
            weight = row.get('offer_shares_pct') or row.get('investment_amount_hkd_m') or 1
            row_weights.append((row, weight))

        ct = SETTINGS.cornerstone
        quality_raw = self._weighted_average((row.get('tier_score'), weight) for row, weight in row_weights)
        independence_raw = self._weighted_average((row.get('independence_score'), weight) for row, weight in row_weights)
        sector_fit_raw = self._weighted_average((row.get('sector_fit_score'), weight) for row, weight in row_weights)
        quality_raw = quality_raw if quality_raw is not None else ct.quality_default
        independence_raw = independence_raw if independence_raw is not None else ct.independence_default
        sector_fit_raw = sector_fit_raw if sector_fit_raw is not None else ct.sector_fit_default

        if cornerstone_pct is None:
            subscription_score = ct.score_missing
            subscription_detail = '未提取到基石占比，按中性偏低处理'
        elif ct.pct_healthy_low <= cornerstone_pct <= ct.pct_healthy_high:
            subscription_score = ct.score_healthy
            subscription_detail = f'基石占比{cornerstone_pct:.1f}%，处于{ct.pct_healthy_low:.0f}%-{ct.pct_healthy_high:.0f}%健康区间'
        elif ct.pct_acceptable_low <= cornerstone_pct <= ct.pct_acceptable_high:
            subscription_score = ct.score_acceptable
            subscription_detail = f'基石占比{cornerstone_pct:.1f}%，未触发极端红旗'
        else:
            subscription_score = ct.score_extreme
            subscription_detail = f'基石占比{cornerstone_pct:.1f}%，结构偏极端'

        has_long_money = any(row.get('tier') == 'S' or '长线' in row.get('category', '') or '主权' in row.get('category', '') for row in profile_rows)
        has_weak = any(row.get('tier') == '弱' for row in profile_rows)
        lockup_raw = ct.lockup_long_money if has_long_money else ct.lockup_default
        if has_weak:
            lockup_raw -= ct.lockup_weak_penalty

        dimensions = {
            'institution_quality': {
                'label': '机构质量',
                'score': round(quality_raw * ct.quality_weight),
                'max_score': round(ct.quality_weight * 100),
                'raw_score': round(quality_raw, 1),
                'detail': '按投资者等级和认购占比加权',
            },
            'independence': {
                'label': '独立性',
                'score': round(independence_raw * ct.independence_weight),
                'max_score': round(ct.independence_weight * 100),
                'raw_score': round(independence_raw, 1),
                'detail': '独立第三方和长线资金权重更高',
            },
            'sector_fit': {
                'label': '行业相关性',
                'score': round(sector_fit_raw * ct.sector_fit_weight),
                'max_score': round(ct.sector_fit_weight * 100),
                'raw_score': round(sector_fit_raw, 1),
                'detail': '医疗/科技/产业协同匹配度',
            },
            'subscription_strength': {
                'label': '认购强度',
                'score': subscription_score,
                'max_score': ct.subscription_max,
                'raw_score': round((subscription_score / ct.subscription_max) * 100, 1),
                'detail': subscription_detail,
            },
            'lockup_history': {
                'label': '锁定与历史行为',
                'score': round(max(0, min(100, lockup_raw)) * ct.lockup_weight),
                'max_score': round(ct.lockup_weight * 100),
                'raw_score': round(max(0, min(100, lockup_raw)), 1),
                'detail': '港股基石通常6个月禁售，长线资金加权更高',
            },
        }

        score = min(100, sum(item['score'] for item in dimensions.values()))

        categories = [row.get('category', '') for row in profile_rows]
        top_names = [row.get('short_name') or row.get('name') for row in profile_rows if row.get('tier') == 'S']
        a_names = [row.get('short_name') or row.get('name') for row in profile_rows if row.get('tier') == 'A']
        weak_rows = [row for row in profile_rows if row.get('tier') == '弱']
        strengths = []
        concerns = []
        red_flags = []

        if top_names:
            strengths.append('S级/顶级长线基石: ' + '、'.join(top_names[:3]))
        if a_names:
            strengths.append('A级专业机构覆盖较广: ' + '、'.join(a_names[:5]))
        if cornerstone_pct is not None and ct.pct_healthy_low <= cornerstone_pct <= ct.pct_healthy_high:
            strengths.append(f'基石占比{cornerstone_pct:.1f}%，锁定比例健康')
        if any('医疗专业基金' in cat for cat in categories):
            strengths.append('医疗专业基金参与，赛道验证较强')
        if any('国资' in cat for cat in categories):
            strengths.append('国家队/国资背景资金参与')

        if not any('主权' in cat or '养老金' in cat for cat in categories):
            concerns.append('无国际主权: 未见GIC/Temasek/QIA/ADIA等主权或养老金基石')
        if not any('产业战略' in cat for cat in categories):
            concerns.append('无产业药企/核心客户型战略基石，产业协同背书不足')
        if spv_flags:
            concerns.append('SPV检查: ' + '；'.join(spv_flags[:3]))
        if weak_rows:
            concerns.append(f'存在{len(weak_rows)}家弱信号/关系型基石，需关注透明度')
        if not profile_rows:
            red_flags.append('未完整提取基石明细')
        if cornerstone_pct is not None and cornerstone_pct < ct.pct_acceptable_low:
            red_flags.append('基石占比低于30%，稳定筹码不足')
        if cornerstone_pct is not None and cornerstone_pct > ct.pct_acceptable_high:
            red_flags.append('基石占比超过80%，流通结构偏极端')
        if len(spv_flags) >= ct.spv_warning_count:
            red_flags.append('疑似SPV/不透明主体较多')
        if sector_match is False:
            red_flags.append('赛道与基石机构错配')

        if red_flags:
            has_severe = any(any(severe in str(rf).lower() for severe in ct.severe_cornerstone_flags) for rf in red_flags)
            if has_severe:
                score = min(score, ct.score_cap_low_red_flags)
            else:
                penalty = min(10, len(red_flags) * 3)
                score = max(0, score - penalty)

        GRADE_BANDS = [
            (ct.grade_s, 'S级', 'S', '强背书，可显著加分'),
            (ct.grade_a, 'A级', None, '有价值背书，需结合估值'),
            (ct.grade_b, 'B级', 'B', '一般背书，小幅加分'),
        ]
        label, grade_band, recommendation = '弱基石', '弱', '弱信号，不加分'
        for threshold, lbl, band, rec in GRADE_BANDS:
            if score >= threshold:
                label = lbl
                grade_band = '强A' if band is None and score >= ct.grade_a_strong else (band or lbl.rstrip('级'))
                recommendation = rec
                break

        if not strengths:
            strengths.append('已披露基石承诺，但未识别到强机构组合')

        formula_pass_count = int(dimensions['institution_quality']['raw_score'] >= 70) + int(subscription_score >= 11) + int(not red_flags)

        return {
            'label': label,
            'grade_band': grade_band,
            'score': int(round(score)),
            'recommendation': recommendation,
            'cornerstone_investors': profile_rows,
            'matched_investors': [
                self._profile_match_payload_with_source(self._best_profile(row.get('match_names') or row.get('name') or '') or {
                    'name': row.get('short_name') or row.get('name'),
                    'tier': row.get('tier'),
                    'category': row.get('category'),
                    'role_note': row.get('role_note'),
                    '_source': 'cornerstone_section',
                })
                for row in profile_rows
                if row.get('tier') in ('S', 'A')
            ],
            's_tier_count': sum(1 for row in profile_rows if row.get('tier') == 'S'),
            'a_tier_count': sum(1 for row in profile_rows if row.get('tier') == 'A'),
            'b_tier_count': sum(1 for row in profile_rows if row.get('tier') == 'B'),
            'weak_tier_count': sum(1 for row in profile_rows if row.get('tier') == '弱'),
            'cornerstone_pct': cornerstone_pct,
            'sector': sector,
            'sector_match': sector_match,
            'spv_flags': spv_flags,
            'dimension_scores': dimensions,
            'strengths': strengths,
            'concerns': concerns,
            'red_flags': red_flags,
            'reasons': strengths[:3] + concerns[:3],
            'combination_summary': self._build_combination_summary(profile_rows),
            'formula_pass_count': formula_pass_count,
            'model_version': 'cornerstone_v2_2026_05',
        }

    def analyze(self, text):
        context, has_cornerstone_section = self._cornerstone_context(text)
        if not has_cornerstone_section:
            return {
                'label': '未披露',
                'grade_band': '缺失',
                'score': 0,
                'recommendation': '无基石',
                'matched_investors': [],
                'cornerstone_investors': [],
                'cornerstone_pct': None,
                'dimension_scores': {},
                'strengths': [],
                'concerns': [],
                'red_flags': [],
                'reasons': ['未发现基石投资者章节，不进行全文投资者匹配'],
                'formula_pass_count': 0,
                'sector': 'unknown',
                'sector_match': None,
                'has_cornerstone_section': False,
                'detail': '未发现基石投资者章节，不进行全文投资者匹配',
                'model_version': 'cornerstone_v2_2026_05',
            }

        # 计算 context 在全文中的起始位置，用于排除章节检测
        context_start_idx = text.find(context) if context else 0
        matched = self._matched_investors(context, full_text=text, context_start_idx=context_start_idx)
        # 过滤掉 source='pre_ipo_section' 的命中，不计入基石评分
        cornerstone_matched = [m for m in matched if m.get('source') == 'cornerstone_section']
        cornerstone_rows = self._enrich_cornerstone_rows(context, self._extract_cornerstone_rows(context))
        cornerstone_pct = self._extract_cornerstone_pct(context)
        sector = self._sector(text)
        sector_match = self._sector_match(sector, context)
        spv_flags = self._spv_risk_flags(context)
        result = self._build_v2_result(
            cornerstone_rows, cornerstone_matched, cornerstone_pct, sector, sector_match, spv_flags
        )
        result['has_cornerstone_section'] = True
        # 保留所有 matched_investors（含 pre_ipo_section），但分开标记
        result['all_matched_investors'] = matched
        return result


# 模块级加载：优先从 YAML 读取，失败回退到内置数据
CornerstoneAnalyzer.INVESTOR_PROFILES = _load_investor_profiles()
CornerstoneAnalyzer.S_TIER = [
    (p['name'], p['aliases'])
    for p in CornerstoneAnalyzer.INVESTOR_PROFILES
    if p['tier'] == 'S'
]
CornerstoneAnalyzer.A_TIER = [
    (p['name'], p['aliases'])
    for p in CornerstoneAnalyzer.INVESTOR_PROFILES
    if p['tier'] == 'A'
]


# ---------------------------------------------------------------------------
# 模块级辅助函数 — 供外部模块（如 SignalComponentAnalyzer）使用
# ---------------------------------------------------------------------------

def get_sovereign_capital():
    """获取主权/养老基金列表 -> [(name, aliases), ...]"""
    return [
        (p['name'], p['aliases'])
        for p in CornerstoneAnalyzer.INVESTOR_PROFILES
        if p.get('category') == '顶级主权基金/养老金'
    ]


def get_top_tier_capital():
    """获取顶级资本列表 -> [(name, aliases), ...]
    包含 S-tier（非主权）+ A-tier。
    """
    return [
        (p['name'], p['aliases'])
        for p in CornerstoneAnalyzer.INVESTOR_PROFILES
        if p.get('tier') in ('S', 'A')
        and p.get('category') != '顶级主权基金/养老金'
    ]


def get_weak_signal_capital():
    """获取弱信号资本列表 -> [(name, aliases), ...]
    包含 B-tier 和 弱-tier。
    """
    return [
        (p['name'], p['aliases'])
        for p in CornerstoneAnalyzer.INVESTOR_PROFILES
        if p.get('tier') in ('B', '弱')
    ]
