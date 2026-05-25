import os
import re
import logging

from .utils import _contains_any, _infer_sector
from .settings import SETTINGS

logger = logging.getLogger(__name__)

# ---- 基石分析器预编译正则 ----
_CRE_CONTROL = re.compile(r'[\x00-\x1f\x7f-\x9f\u0002]+')
_CRE_WHITESPACE = re.compile(r'\s+')
_CRE_DOT_LEADER = re.compile(r'(?:\s*\.\s*){3,}')
_CRE_LEADING_PARENS = re.compile(r'^\([0-9]+\)\s*')
_CRE_NUMBER = re.compile(r'([0-9,]+(?:\.[0-9]+)?)')
_CRE_PARENS_ONLY = re.compile(r'\([0-9]+\)')
_CRE_NUMERIC_CELL = re.compile(r'(?:US\$|HK\$|US|HK|\$)?[0-9][0-9,]*(?:\.[0-9]+)?%?(?:\([0-9]+\))?')
_CRE_PARENS_CAPTURE = re.compile(r'\([0-9]+\)(.+)')
_CRE_CURRENCY_PREFIX = re.compile(r'^(?:US\$|HK\$|US|HK|\$)')
_CRE_STRIP_PARENS = re.compile(r'\([0-9]+\)$')
_CRE_HAS_LETTER = re.compile(r'[a-zA-Z]')
_CRE_CURRENCY_START = re.compile(r'^(?:US\$|HK\$|\$)')
_CRE_SECTION_HEADER = re.compile(r'\n\n([A-Z][A-Za-z\s]{3,60})\s*\n')
_CRE_CN_QUOTED = re.compile(r'"([^"]+)"')
_CRE_CN_QUOTED2 = re.compile(r'「([^」]+)」')
_CRE_FOR_AND_ON_BEHALF = re.compile(r'\s+for and on behalf of\s+', re.IGNORECASE)
_CRE_ALL_PARENS = re.compile(r'\([^()]*\)')

# flush_row 噪音检测预编译（原在函数内每次编译）
_CRE_FLUSH_PARENS_END = re.compile(r'\([0-9]+\)$')
_CRE_FLUSH_CLEAN_PARENS = re.compile(r'\([0-9]+\)')
_CRE_FLUSH_NON_ALPHA = re.compile(r'[^a-z0-9%$.\s]+')
_CRE_FLUSH_WHITESPACE = re.compile(r'\s+')
_CRE_FLUSH_FULL_DIGITS = re.compile(r'\d{1,3}')
_CRE_FLUSH_AMOUNT = re.compile(r'amount\d*')
_CRE_FLUSH_GENERIC = re.compile(r'\(?[a-z\s]+\)?\s*limited\)?')

# 预编译负面语境模式
_CRE_NEGATIVE_CTX_1 = re.compile(r'(?:not\s+include|not\s+included|excluding|without|absence\s+of|no\s+)\s*[^,.]{0,60}?', re.IGNORECASE)
_CRE_NEGATIVE_CTX_2 = re.compile(r'(?:未见|无|没有|不含|不包括|未纳入|未包含|除外|排除)[^，。,\.]{0,30}?')
_CRE_NEGATIVE_CORNERSTONE_MENTION = re.compile(
    r'(?:'
    r'\b(?:no|without)\s+(?:any\s+)?cornerstone\s+investors?\b|'
    r'\b(?:did|does|do|has|have|had|will)\s+not\s+'
    r'(?:introduce|appoint|identify|include|have|enter\s+into|entered\s+into|bring\s+in)\s+'
    r'(?:any\s+)?cornerstone\b|'
    r'\b(?:has|have|had)\s+no\s+cornerstone\b|'
    r'\bno\s+cornerstone\s+investment\s+agreement\b|'
    r'\bnot\s+entered\s+into\s+(?:any\s+)?cornerstone\s+investment\s+agreement\b|'
    r'(?:无|没有|未引入|未设有|不设|未订立|并无)[^。；;\n]{0,40}?基石(?:投资者|投资协议)?'
    r')',
    re.IGNORECASE,
)

# 预编译_at_end_marker节尾搜索
_CRE_SECTION_FOOTER = re.compile(r'([IVX]+)\s*\n?$')

# 预编译_extract_cornerstone_pct模式
_CRE_CORNERSTONE_KEYWORD_PCT = re.compile(r'cornerstone investors?.{0,200}?([0-9]+(?:\.[0-9]+)?)%', re.IGNORECASE | re.DOTALL)
_CRE_PCT_PATTERNS = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in [
    r'represent(?:s|ing)? approximately ([0-9]+(?:\.[0-9]+)?)%',
    r'([0-9]+(?:\.[0-9]+)?)% of (?:the|our) (?:offer|global offering|placing) shares',
    r'([0-9]+(?:\.[0-9]+)?)% of the total offer shares',
]]
_CRE_SHARE_PCT_PATTERNS = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in [
    r'([0-9,]+(?:\.[0-9]+)?)\s*shares?.{0,120}?represent(?:s|ing)? approximately ([0-9]+(?:\.[0-9]+)?)%',
    r'([0-9,]+(?:\.[0-9]+)?)\s*shares?.{0,120}?out of ([0-9,]+(?:\.[0-9]+)?)\s*shares?',
]]

# 预编译_extract_cornerstone_by_regex投资者匹配
_CRE_INVESTOR_REGEX = re.compile(
    r'([A-Z][A-Za-z\s]{5,60}(?:Limited|Ltd|Capital|Fund|Investment|Partners?|Corporation|Inc\.))\s+'
    r'([0-9,]+(?:\.[0-9]+)?)\s+'
    r'([0-9,]+(?:\.[0-9]+)?)\s+'
    r'([0-9,.]+(?:\.[0-9]+)?)\s+'
    r'([0-9,.]+(?:\.[0-9]+)?)',
)

# 预编译表头前缀模式（_strip_header_from_name）
_HEADER_PREFIX_PATTERNS = [re.compile(p, re.IGNORECASE) for p in [
    r'Number\s+of\s+Offer\s+Shares\s+to\s+be\s+(?:acquired|subscribed)',
    r'Approximate\s+%\s+of\s+(?:the\s+)?issued\s+share\s+capital',
    r'Approximate\s+%\s+of\s+(?:the\s+)?Offer\s+(?:Shares|capital|Capital)',
    r'Appropriate\s+%\s+of\s+(?:the\s+)?(?:total\s+)?issued\s+share\s+capital',
    r'Appropriate\s+%\s+of\s+(?:the\s+)?Offer\s+(?:Shares|capital|Capital)',
    r'Appropriate\s+%\s+of\s+(?:the\s+)?total',
    r'%\s+of\s+Shares\s+in\s+issue',
    r'%\s+of\s+(?:the\s+)?issued\s+share\s+capital',
    r'%\s+of\s+Offer\s+Shares',
    r'%\s+of\s+(?:the\s+)?Offer\s+(?:Shares|capital|Capital)',
    r'%\s+of\s+(?:the\s+)?Offer\b',
    r'%\s+of\s+Shares\b',
    r'%\s+of\b',
    r'%\s+(?:Approximate|Appropriate)\b',
    r'%\s+',
    r'Subscription\s+amount',
    r'Investment\s+amount',
    r'Total\s+investment\s+amount',
    r'Cornerstone\s+Investor',
    r'to\s+be\s+(?:subscribed|acquired)',
    r'Shares\s+to\s+be',
    r'Number\s+of',
    r'of\s+(?:the\s+)?Offer\b',
    r'Investment\s+',
    r'Subscription\s+',
    r'Amount\s+',
]]


def _load_investor_profiles():
    """从 YAML 加载基石投资者档案，加载失败时回退到内置数据。"""
    import yaml as _yaml
    yaml_path = _investor_profiles_yaml_path()
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = _yaml.safe_load(f)
        profiles = data.get("investors", [])
        if profiles:
            return profiles
    except Exception:
        pass
    return CornerstoneAnalyzer._BUILTIN_INVESTOR_PROFILES


def _investor_profiles_yaml_path():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "cornerstone_investors.yaml",
    )


def investor_profiles_signature():
    """Return a signature that changes whenever the external profile YAML changes."""
    yaml_path = _investor_profiles_yaml_path()
    try:
        stat = os.stat(yaml_path)
        return (os.path.abspath(yaml_path), stat.st_mtime, stat.st_size)
    except OSError:
        return ("builtin", 0, 0)


class CornerstoneAnalyzer:
    _INVESTOR_PROFILE_SIGNATURE = None

    def __init__(self):
        self._ensure_investor_profiles_current()

    @classmethod
    def _set_investor_profiles(cls, profiles, signature=None):
        cls.INVESTOR_PROFILES = profiles
        cls._INVESTOR_PROFILE_SIGNATURE = signature or investor_profiles_signature()
        cls.S_TIER = [
            (p['name'], p['aliases'])
            for p in cls.INVESTOR_PROFILES
            if p['tier'] == 'S'
        ]
        cls.A_TIER = [
            (p['name'], p['aliases'])
            for p in cls.INVESTOR_PROFILES
            if p['tier'] == 'A'
        ]

    @classmethod
    def _ensure_investor_profiles_current(cls):
        signature = investor_profiles_signature()
        if cls._INVESTOR_PROFILE_SIGNATURE != signature:
            cls._set_investor_profiles(_load_investor_profiles(), signature)

    def test_is_noise(line):
        import re
        _CRE_FLUSH_WHITESPACE = re.compile(r'\s+')
        _CRE_FLUSH_NON_ALPHA = re.compile(r'[^a-zA-Z0-9\$%\-().,]')
        _CRE_FLUSH_CLEAN_PARENS = re.compile(r'\(.*?\)')
        _CRE_FLUSH_GENERIC = re.compile(r'\(?[a-z\s]+\)?\s*limited\)?')
        _CRE_FLUSH_FULL_DIGITS = re.compile(r'^[\d\s,.$%\-]+$')
        _CRE_FLUSH_AMOUNT = re.compile(r'^[\d\s,.]+\s*(million|millions|m|mn|b|bn|billion)s?$')
        _CRE_FLUSH_PARENS_END = re.compile(r'\([0-9]+\)$')
        _HEADER_WORD_SET = frozenset([
            'number', 'of', 'offer', 'shares', 'to', 'be', 'acquired', 'subscribed',
            'approximate', 'appropriate', 'subscription', 'investment', 'amount', 'total',
            'cornerstone', 'investor', 'assuming', 'exercised', 'option', 'completion',
            'global', 'immediately', 'upon', 'issued', 'share', 'capital', 'the',
            'in', 'full', 'not', 'is', 'offering', 'allotment', 'over-allotment',
            'adjustment', 'size', 'based', 'on', 'price', 'millions', 'usd', 'hk$',
            'us$', 'u.s.', 'hk', 'down', 'nearest', 'whole', 'board', 'lot',
            'following', 'rounded', 'subject', 'rounding', 'note', 'notes',
            'issue', '%', 'upon', 'completion',
        ])
        _INVESTOR_KEYWORDS = frozenset([
            'partners', 'capital', 'management', 'investments', 'fund', 'venture',
            'asset', 'group', 'corporation', 'holdings', 'plc', 'inc', 'corp',
            'limited', 'ltd', 'ltd.', 'l.p.', 'lp', 'llc', 'co', 'co.',
            'international', 'global', 'scsp', 'sarl', 'pte', 'trust',
            'foundation', 'pension', 'university', 'hospital', 'healthcare',
            'biotech', 'pharma', 'pharmaceutical', 'laboratory', 'venture',
            'ventures', 'private', 'equity', 'securities', 'financial',
            'action', 'amr', 'hua', 'yuan', 'orient', 'junestar', 'danyuan',
        ])
        _NOISE_KW = [
            'the table below sets forth details of the cornerstone',
            'the table below sets out details of the cornerstone',
            'the tables below set forth',
            'the tables below set out',
            'cornerstone investor',
            'total investment amount',
            'number of offer shares',
            'approximate % of the offer shares',
            'approximate % of the issued share capital',
            'appropriate % of the total',
            'appropriate % of the offer',
            '(usd in millions)',
            'based on the offer price',
            'assuming the over-allotment',
            'assuming the offer size',
            'option is not exercised',
            'option is exercised',
            'offer shares to be acquired',
            'immediately upon',
            'completion of the global offering',
            '(in hk$)',
            'us$in',
            'hk$in',
            'note ',
            'subject to rounding',
            'notes:',
            'appropriate %',
            'of the total',
            'issued share capital',
            'completion of',
            'assuming the',
            'offer size adjustment',
            'over-allotment option',
        ]
        _TABLE_KWS = ('appropriate', 'assuming', 'over-allotment', 'allotment',
                        'offer size', 'adjustment option', 'exercised', 'not exercised',
                        'completion of', 'global offering', 'issued share capital',
                        'approximate %', 'of the total', 'immediately upon',
                        'offer shares', 'subscription amount', 'number of',
                        'option is', 'fully exercised', 'in full',
                        'offer size adjustment', 'over-allotment option')
        _REPEAT_KWS = ('issued share', 'capital', 'immediately', 'upon', 'appropriate', 'approximate')
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
            'cornerstone investors', 'esop', 'employee share option',
            'employee stock ownership', 'pre ipo', 'pre-ipo',
            'appropriate', 'appropriate %', 'total issued share',
            'share capital immediately', 'immediately upon',
            'cornerstone', 'investor', 'investment amount',
            'offer price', 'global offering', 'offer size',
            'over-allotment', 'over allotment',
            'number', 'acquired', 'subscribed', 'to be',
            'of offer', 'of the offer', '% of offer',
            'shares to be', 'offer size adjustment',
            '(us$in', '(hk$in', 'us$in', 'hk$in',
        }
        ll = line.lower()
        if sum(1 for kw in _TABLE_KWS if kw in ll) >= 2:
            return True
        for kw in _REPEAT_KWS:
            if ll.count(kw) >= 2:
                return True
        if 'set out in this prospectus' in ll:
            return True
        if 'cornerstone' in ll and 'number of' in ll and 'offer' in ll:
            return True
        if 'investment amount' in ll and 'offer shares' in ll:
            return True
        if ll.count('shares offering') >= 2:
            return True
        if ll.count('millions)') >= 2:
            return True
        if 'us$ in' in ll or 'hk$ in' in ll:
            return True
        words = ll.split()
        if 1 <= len(words) <= 5:
            cleaned_words = [w for w in (_CRE_FLUSH_PARENS_END.sub('', w) for w in words) if w]
            if cleaned_words and all(w in _HEADER_WORD_SET for w in cleaned_words):
                if not any(w in _INVESTOR_KEYWORDS for w in cleaned_words):
                    return True
        compact = _CRE_FLUSH_WHITESPACE.sub(' ', _CRE_FLUSH_NON_ALPHA.sub(' ', _CRE_FLUSH_CLEAN_PARENS.sub('', ll))).strip()
        if compact.startswith('total') and not any(kw in compact for kw in ['fund', 'capital', 'asset', 'management']):
            return True
        if _CRE_FLUSH_FULL_DIGITS.fullmatch(compact):
            return True
        if compact.startswith('based on the offer price'):
            return True
        if _CRE_FLUSH_AMOUNT.fullmatch(compact):
            return True
        if compact in _NOISE_EXACT or ll in _NOISE_EXACT or any(kw in ll for kw in _NOISE_KW):
            return True
        if compact in ('investment amount', 'number of offer shares', 'offer shares', 'issued share capital',
                       'share capital', 'approximate', 'investment', 'amount', 'shares',
                       'cornerstone investor', 'cornerstone investors', 'cornerstone', 'investor'):
            return True
        if 'million' in compact and ('hk' in compact or 'usd' in compact or 'us' in compact or '$' in ll):
            if 'limited' not in compact and not any(kw in compact for kw in ['partners', 'capital', 'management', 'fund']):
                return True
        table_header_kws = ('usd', 'us$', 'hk$', 'u.s.', 'amount', 'shares', 'offer', 'approximate', '%', 'million')
        header_hits = sum(1 for kw in table_header_kws if kw in compact)
        if header_hits >= 3 and 'limited' not in compact:
            return True
        if ('us$' in compact or 'usd' in compact or 'hk$' in compact) and ('offer' in compact or 'shares' in compact) and 'limited' not in compact:
            return True
        if 'shares' in compact and 'capital' in compact and 'million' in compact and 'limited' not in compact:
            return True
        if 'million' in compact and 'shares' in compact and len(compact.split()) <= 3 and 'limited' not in compact:
            return True
        _TABLE_KWS_NOSPACE = (
            'assuming', 'over-allotment', 'allotment', 'offersize', 'adjustmentoption',
            'exercised', 'notexercised', 'completionof', 'globaloffering',
            'issuedshare', 'sharecapital', 'approximate', 'appropriate', 'ofthetotal',
            'immediatelyupon', 'offershares', 'subscriptionamount', 'numberof',
            'optionis', 'fullyexercised', 'infull', 'offersizeadjustment',
            'over-allotmentoption', 'investmentamount', 'cornerstoneinvestor',
            'thetablebelow', 'setsforth', 'detailsofthe',
            'oftheoffer', 'theglobal', 'us$in', 'hk$in',
        )
        table_kw_hits = sum(ll.count(kw) for kw in _TABLE_KWS_NOSPACE)
        if table_kw_hits >= 3:
            return True
        if _CRE_FLUSH_GENERIC.fullmatch(compact) and len(compact.split()) <= 4 and not any(kw in compact for kw in _INVESTOR_KEYWORDS):
            return True
        if 'esop' in compact or 'employee share' in compact or 'employee stock' in compact:
            return True
        return False

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
            'name': 'Jane Street',
            'tier': 'S',
            'category': '量化做市商',
            'aliases': ['jane street', 'jane street capital', 'jane street group'],
            'role_note': '全球最大做市商之一，2024-2025港股基石最活跃外资，资金体量和定价锚效应极强',
            'sector_tags': ['all'],
        },
        {
            'name': 'Xiaomi',
            'tier': 'S',
            'category': '强产业战略投资者',
            'aliases': ['xiaomi', '小米', '小米集团'],
            'role_note': '强产业生态基石，硬件/AIoT/汽车生态协同价值高',
            'sector_tags': ['hardtech', 'consumer'],
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
            'role_note': '中国头部私募基金，2025-2026年港股基石参投最活跃机构之一',
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
            'aliases': ['icbcubs', 'icbc wealth', 'icbc credit suisse', 'icbc asset management', '工银瑞信', '工银理财', '工银资管'],
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
            'name': 'Citadel Securities',
            'tier': 'A',
            'category': '量化做市商',
            'aliases': ['citadel securities', 'citadel', '城堡证券'],
            'role_note': '全球最大做市商之一，港股基石参投活跃，定价锚效应较强',
            'sector_tags': ['all'],
        },
        {
            'name': 'Point72',
            'tier': 'A',
            'category': '全球多策略对冲基金',
            'aliases': ['point72', 'point 72', 'point72 asset management'],
            'role_note': '全球大型多策略对冲基金，港股基石参投',
            'sector_tags': ['all'],
        },
        {
            'name': 'D1 Capital Partners',
            'tier': 'A',
            'category': '全球多策略对冲基金',
            'aliases': ['d1 capital', 'd1 capital partners', 'd1'],
            'role_note': '全球大型对冲基金，港股基石参投',
            'sector_tags': ['all'],
        },
        {
            'name': '汇添富基金',
            'tier': 'A',
            'category': '知名中资长线/保险/公募',
            'aliases': ['china universal am', 'china universal asset management', '汇添富', '汇添富基金'],
            'role_note': '头部中资公募，2025-2026年港股基石参投活跃',
            'sector_tags': ['all'],
        },
        {
            'name': '南方基金',
            'tier': 'A',
            'category': '知名中资长线/保险/公募',
            'aliases': ['southern fund', 'southern asset management', '南方基金', '南方'],
            'role_note': '头部中资公募，国内资金认可度较好',
            'sector_tags': ['all'],
        },
        {
            'name': '中欧基金',
            'tier': 'A',
            'category': '知名中资长线/保险/公募',
            'aliases': ['zhongou fund', 'china europe fund', 'lombarda china fund', '中欧基金', '中欧'],
            'role_note': '头部中资公募，主动管理能力较强',
            'sector_tags': ['all'],
        },
        {
            'name': '泰康人寿',
            'tier': 'A',
            'category': '保险资金',
            'aliases': ['taikang life', 'taikang life insurance', '泰康人寿', '泰康人寿保险'],
            'role_note': '头部保险资金，2025-2026年险资入场港股基石代表，长线属性强',
            'sector_tags': ['all'],
        },
        {
            'name': '平安人寿',
            'tier': 'A',
            'category': '保险资金',
            'aliases': ['ping an life', 'ping an life insurance', '平安人寿', '平安人寿保险', '中国平安人寿'],
            'role_note': '头部保险资金，2025-2026年险资入场港股基石代表，长线属性强',
            'sector_tags': ['all'],
        },
        {
            'name': '中信证券投资',
            'tier': 'A',
            'category': '券商直投平台',
            'aliases': ['citic securities investment', 'citic investment', '中信证券投资', '中信建投投资'],
            'role_note': '头部券商直投平台，研究/承销资源协同',
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
            'name': 'AMR Action Fund',
            'tier': 'S',
            'category': '新型抗生素专业基金',
            'aliases': ['amr action fund', 'amr action', '抗微生物药物耐药性'],
            'role_note': '全球唯一专注新型抗生素研发的顶级产业基金，由多家跨国药企联合发起，对管线技术含金量背书极强',
            'sector_tags': ['healthcare'],
        },
        {
            'name': 'Wellcome Trust',
            'tier': 'S',
            'category': '医疗专业基金/慈善基金',
            'aliases': ['wellcome trust', 'wellcome'],
            'role_note': '全球最大生物医学研究慈善基金，医疗领域权威背书',
            'sector_tags': ['healthcare'],
        },
        {
            'name': 'Novo Holdings',
            'tier': 'S',
            'category': '医疗专业基金',
            'aliases': ['novo holdings', 'novo nordisk foundation', '诺和诺德基金会', '诺和控股'],
            'role_note': '诺和诺德基金会旗下投资平台，全球最大医疗产业基金之一',
            'sector_tags': ['healthcare'],
        },
        {
            'name': 'Fosun Pharma',
            'tier': 'A',
            'category': '强产业战略投资者',
            'aliases': ['fosun pharma', '复星医药', '复星'],
            'role_note': '国内头部医药集团，产业协同和管线判断力强',
            'sector_tags': ['healthcare'],
        },
        {
            'name': 'CICC Capital',
            'tier': 'A',
            'category': '大型投行/资管平台',
            'aliases': ['cicc capital', '中金资本', 'cicc'],
            'role_note': '国内头部券商直投平台，研究/承销资源协同',
            'sector_tags': ['all'],
        },
        {
            'name': 'Suzhou SIP / 苏州工业园区',
            'tier': 'A',
            'category': '知名中资长线/国资基金',
            'aliases': ['suzhou sip', 'suzhou industrial park', '苏州工业园区', '工业园区', 'sip', 'suzhou yuanhe', '元禾控股', '元禾', 'suzhou工业园'],
            'role_note': '苏州工业园区国资，深度参与Biotech/创新药投资（投过信达、药明康德等）',
            'sector_tags': ['healthcare', 'hardtech'],
        },
        {
            'name': 'Cinda/东方资产',
            'tier': 'A',
            'category': '知名中资长线/国资基金',
            'aliases': ['cinda', 'orient asset', 'china cinda', '信达资产', '东方资产', '中国信达', '中国东方资产'],
            'role_note': '央企背景金融AMC平台，资金实力雄厚，产业认可度强',
            'sector_tags': ['all'],
        },
        {
            'name': '国投创新',
            'tier': 'A',
            'category': '知名中资长线/国资基金',
            'aliases': ['sdic innovation', '国投创新', '国家开发投资集团'],
            'role_note': '国家级产业投资基金，央企背景，产业和政策双重认可',
            'sector_tags': ['hardtech', 'healthcare'],
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
    # 高优先级锚点：表格引导句 / 大写章节标题（最精确，避免正文引用误匹配）
    CORNERSTONE_ANCHORS_HIGH = [
        'the table below sets forth details of the cornerstone',
        'the tables below set forth details of the cornerstone',
        'the table below sets forth details of the cornerstone investment',
        'the cornerstone investors\n',
        'the cornerstone placing\n',
        'cornerstone investor\n',
    ]
    # 标准锚点（fallback）
    CORNERSTONE_ANCHORS = [
        'cornerstone investors',
        'cornerstone placing',
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
        """在 text 中查找 anchors 的最早出现位置，返回 (idx, anchor) 或 (-1, None)。
        优先匹配独立成行的锚点（前后有换行符或段落边界），减少正文引用误匹配。"""
        lower_text = text.lower()
        best_idx = -1
        best_anchor = None
        for anchor in anchors:
            if anchor.endswith('\n'):
                # 带换行符的锚点：优先匹配独立成行
                idx = lower_text.find(anchor)
                if idx >= 0:
                    # 验证前面是否是行首/换行符/空格（允许大写前缀如 "THE "）
                    prev_char = text[idx - 1] if idx > 0 else '\n'
                    if prev_char in '\n\r ' or idx == 0:
                        if best_idx < 0 or idx < best_idx:
                            best_idx = idx
                            best_anchor = anchor
                continue
            # 普通锚点
            idx = text.find(anchor) if any(ord(c) > 127 for c in anchor) else lower_text.find(anchor)
            if idx >= 0 and (best_idx < 0 or idx < best_idx):
                best_idx = idx
                best_anchor = anchor
        return best_idx, best_anchor

    def _cornerstone_context(self, text):
        """返回 (context, has_cornerstone_section)。
        优先使用高优先级锚点（表格引导句 / 独立成行标题），避免正文引用误匹配。
        若首个匹配附近无表格特征，自动 fallback 到下一个匹配。
        跳过目录页（TOC），找到真正的章节边界。"""
        #  helpers: 判断锚点附近是否有基石表格特征
        def _has_table_features(t, pos):
            window = t[pos:pos + 3000].lower()
            return any(marker in window for marker in [
                'the table below sets forth details of the cornerstone',
                'the tables below set forth details of the cornerstone',
                'number of offer shares',
                'investment amount',
                'cornerstone placing',
            ])

        def _is_negative_cornerstone_mention(full_text, pos):
            start = max(0, pos - 180)
            end = min(len(full_text), pos + 260)
            window = _CRE_WHITESPACE.sub(' ', full_text[start:end]).strip()
            return bool(_CRE_NEGATIVE_CORNERSTONE_MENTION.search(window))

        def _find_best_anchor(full_text, anchors_list, search_start=0):
            """返回 (abs_idx, anchor) 或 (-1, None)。优先匹配带表格特征的锚点。"""
            candidates = []
            search_text = full_text[search_start:]
            for anchor in anchors_list:
                if anchor.endswith('\n'):
                    pos = search_text.lower().find(anchor)
                    while pos >= 0:
                        abs_pos = search_start + pos
                        prev_char = full_text[abs_pos - 1] if abs_pos > 0 else '\n'
                        if prev_char in '\n\r ' or abs_pos == 0:
                            candidates.append((abs_pos, anchor))
                        # 继续搜索下一个
                        pos = search_text.lower().find(anchor, pos + 1)
                else:
                    pos = search_text.find(anchor) if any(ord(c) > 127 for c in anchor) else search_text.lower().find(anchor)
                    while pos >= 0:
                        candidates.append((search_start + pos, anchor))
                        pos = search_text.find(anchor, pos + 1) if any(ord(c) > 127 for c in anchor) else search_text.lower().find(anchor, pos + 1)
            if not candidates:
                return -1, None
            # 先按位置排序；优先选择有表格特征且位置合理的
            candidates.sort(key=lambda x: x[0])
            candidates = [
                (abs_pos, anchor)
                for abs_pos, anchor in candidates
                if not _is_negative_cornerstone_mention(full_text, abs_pos)
            ]
            if not candidates:
                return -1, None
            for abs_pos, anchor in candidates:
                if _has_table_features(full_text, abs_pos):
                    return abs_pos, anchor
            # 都没有表格特征，返回第一个
            return candidates[0]

        idx, anchor = _find_best_anchor(text, self.CORNERSTONE_ANCHORS_HIGH)
        if idx < 0:
            idx, anchor = _find_best_anchor(text, self.CORNERSTONE_ANCHORS)
        if idx < 0:
            return "", False

        if len(text) < 10000:
            context = text[idx:idx + 120000]
            return context, True

        toc_region_end = len(text) // 10
        if idx < toc_region_end:
            idx2, anchor2 = _find_best_anchor(text, self.CORNERSTONE_ANCHORS_HIGH, search_start=toc_region_end)
            if idx2 < 0:
                idx2, anchor2 = _find_best_anchor(text, self.CORNERSTONE_ANCHORS, search_start=toc_region_end)
            if idx2 >= 0:
                idx = idx2
            else:
                return "", False

        lines_before = text[:idx].count('\n')
        min_lines_for_body = min(100, len(text) // 500)
        if lines_before < min_lines_for_body:
            return "", False

        end_idx = self._find_section_end(text, idx)
        context = text[idx:min(end_idx, idx + 800000)]
        return context, True

    @staticmethod
    def _source_excerpt(context, max_chars=12000):
        """Return a compact original-text excerpt for manual verification."""
        if not context:
            return ""
        lines = [line.strip() for line in context.splitlines()]
        compact_lines = []
        blank_seen = False
        for line in lines:
            if not line:
                if not blank_seen and compact_lines:
                    compact_lines.append("")
                blank_seen = True
                continue
            blank_seen = False
            compact_lines.append(_CRE_WHITESPACE.sub(' ', line))
        excerpt = "\n".join(compact_lines).strip()
        if len(excerpt) <= max_chars:
            return excerpt
        return excerpt[:max_chars].rstrip() + "\n\n...[excerpt truncated for display]"

    def _find_section_end(self, text, start_idx):
        """找到章节结束位置。"""
        # 章节结束标记：下一个主要章节标题（通常为大写且较短）
        # 或特定关键词如 "UNDERWRITING", "LOCK-UP", "ADDITIONAL INFORMATION"
        end_markers = [
            'UNDERWRITING', 'UNDERWRITERS', 'UNDERWRITING AGREEMENT',
            'LOCK-UP', 'LOCK UP',
            'ADDITIONAL INFORMATION', 'STATUTORY AND GENERAL INFORMATION',
            'APPENDIX', 'DEFINITIONS',
            'FUTURE PLANS', 'USE OF PROCEEDS',
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
                for m in _CRE_SECTION_HEADER.finditer(text[next_block:]):
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
            if profile.get('tier') in ('S', 'A', 'B')
        ]

    # 负面语境关键词：如果投资者名出现在这些语境中，视为"未见/无"
    _NEGATIVE_CTX_PATTERNS = [_CRE_NEGATIVE_CTX_1, _CRE_NEGATIVE_CTX_2]

    def _is_in_negative_context(self, context, hit_idx, alias):
        """检查投资者名是否出现在负面语境中（如"未见GIC"）。"""
        window_start = max(0, hit_idx - 80)
        window_end = min(len(context), hit_idx + len(alias) + 80)
        window = context[window_start:window_end].lower()
        for pattern in self._NEGATIVE_CTX_PATTERNS:
            if pattern.search(window):
                return True
        return False

    def _matched_profiles_with_exclusion(self, context, full_text="", context_start_idx=0):
        """匹配投资者档案，排除落在 pre-IPO/股东章节中的命中。
        同时排除出现在负面语境中的命中（如"未见GIC"）。
        返回的 profile dict 中带有 _source 字段。"""
        if not context:
            return []
        matched = []
        absent_high_quality = []
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
            # 检查是否在负面语境中
            if self._is_in_negative_context(context, hit_idx, hit_alias):
                if profile.get('tier') in ('S', 'A'):
                    absent_high_quality.append({
                        'name': profile['name'],
                        'tier': profile['tier'],
                        'category': profile.get('category'),
                        'reason': '出现在负面语境（未见/无/不包括）',
                    })
                continue
            key = profile['name']
            if key in seen:
                continue
            seen.add(key)
            profile_copy = dict(profile)
            profile_copy['_source'] = source
            matched.append(profile_copy)
        matched.sort(key=lambda item: {'S': 0, 'A': 1, 'B': 2, '弱': 3}.get(item.get('tier'), 4))
        # 将 absent_high_quality 附加到返回结果的上下文（通过类变量临时传递，后续清理）
        self._last_absent_high_quality = absent_high_quality
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

    TIER_SORT_ORDER = {'S': 0, 'A': 1, 'B': 2, '弱': 3, '未知': 4}

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
        if best_only:
            return matched[0] if matched else None
        return matched

    def _best_profile(self, text):
        return self._match_profiles(text, best_only=True)

    def _matched_profiles(self, text):
        return self._match_profiles(text, best_only=False)

    def _effective_tier_score(self, tier, offer_pct=None):
        """获取 tier 基础分数，不再根据认购占比降级（五维模型已有 subscription_strength 维度）"""
        effective_tier = tier or '未知'
        return self.TIER_BASE_SCORE.get(effective_tier, self.TIER_BASE_SCORE['未知'])

    INDEPENDENCE_RULES = [
        (['主权', '养老金', '全球顶级长线资管', '量化做市商'], (95, '独立长线')),
        (['大型投行/资管', '医疗专业基金', '中资长线', '保险资金', '券商直投'], (82, '独立机构')),
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
        if 'all' in tags or '主权' in category or '全球顶级长线资管' in category or '量化做市商' in category or '保险资金' in category:
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
        line = _CRE_CONTROL.sub(' ', line)
        line = line.replace('  ', ' ')
        line = _CRE_WHITESPACE.sub(' ', line)
        line = line.strip(' \t\r\n-–—')
        # Strip PDF dot leaders from table-of-contents formatting (e.g., "Name . . . . . 123")
        line = _CRE_DOT_LEADER.sub(' ', line)
        line = _CRE_WHITESPACE.sub(' ', line).strip()
        return line

    @staticmethod
    def _parse_all_numbers(text):
        if not text:
            return []
        text = text.strip()
        text = _CRE_LEADING_PARENS.sub('', text)
        parts = text.split()
        numbers = []
        for part in parts:
            cleaned = _CRE_LEADING_PARENS.sub('', part)
            match = _CRE_NUMBER.search(cleaned)
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
        if _CRE_PARENS_ONLY.fullmatch(text):
            return True
        if _CRE_NUMERIC_CELL.fullmatch(text):
            return True
        return False

    @staticmethod
    def _parse_cornerstone_number(text):
        if not text:
            return None
        text = text.strip()
        
        match = _CRE_PARENS_CAPTURE.match(text)
        if match:
            text = match.group(1)
        
        text = _CRE_CURRENCY_PREFIX.sub('', text)
        
        match = _CRE_NUMBER.search(text)
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
                'investment_amount_usd_m': None,
            }

        currency, unit = self._detect_cornerstone_amount_context(table_text)
        amount_m = raw_amount
        # 如果数字很大（>10000），无论单位标记是什么，都除以 1,000,000
        # 因为 PDF 转文本后，"(USD in millions)" 可能只是表格标题，实际数据可能是原始金额
        if abs(raw_amount) > 10000:
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
            'investment_amount_usd_m': usd_m,
        }

    def _cornerstone_short_name(self, name):
        if not name:
            return ""
        match = _CRE_CN_QUOTED.search(name)
        if not match:
            match = _CRE_CN_QUOTED.search(name)
        if match:
            return self._normalize_cornerstone_line(match.group(1))

        lowered = name.lower()
        if ' for and on behalf of ' in lowered:
            parts = _CRE_FOR_AND_ON_BEHALF.split(name, maxsplit=1)
            if len(parts) == 2:
                backend = self._normalize_cornerstone_line(parts[1])
                if backend:
                    return backend
                name = parts[0]

        name = _CRE_ALL_PARENS.sub(' ', name)
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
            'the table below sets forth details of the cornerstone investment',
            '下表載列基石配售的詳情',
            '下表載列基石投資者的詳情',
            '下表反映緊隨全球發售完成後',
        ]
        fallback_markers = [
            'the cornerstone investors',
            'cornerstone investors',
            '基石投資者',
            '基石投资者',
            '基石配售',
        ]
        def _looks_like_toc_entry(pos):
            """Check if marker at pos is a table-of-contents entry (dot leaders + page number)."""
            line_end = context.find('\n', pos)
            if line_end < 0:
                line_end = len(context)
            line = context[pos:line_end]
            # TOC entries: Title . . . . . . PageNum
            return bool(_CRE_DOT_LEADER.search(line))

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

        # Skip TOC entries — find the actual section body
        if _looks_like_toc_entry(start_idx):
            # Search for next occurrence after TOC entry
            search_from = context.find('\n', start_idx) + 1
            second_idx = -1
            for marker in fallback_markers:
                idx = lower_context.find(marker, search_from)
                if idx >= 0 and not _looks_like_toc_entry(idx):
                    second_idx = idx
                    break
            if second_idx >= 0:
                start_idx = second_idx

        end_markers = [
            'notes:',
            'the information about our cornerstone investors',
        ]
        end_idx = len(context)
        for marker in end_markers:
            idx = lower_context.find(marker, start_idx)
            if idx >= 0:
                end_idx = min(end_idx, idx)

        table_text = context[start_idx:end_idx]
        lines = [self._normalize_cornerstone_line(line) for line in table_text.splitlines()]
        lines = [line for line in lines if line]

        # 更严格的噪声过滤
        _HEADER_WORD_SET = frozenset([
            'number', 'of', 'offer', 'shares', 'to', 'be', 'acquired', 'subscribed',
            'approximate', 'appropriate', 'subscription', 'investment', 'amount', 'total',
            'cornerstone', 'investor', 'assuming', 'exercised', 'option', 'completion',
            'global', 'immediately', 'upon', 'issued', 'share', 'capital', 'the',
            'in', 'full', 'not', 'is', 'offering', 'allotment', 'over-allotment',
            'adjustment', 'size', 'based', 'on', 'price', 'millions', 'usd', 'hk$',
            'us$', 'u.s.', 'hk', 'down', 'nearest', 'whole', 'board', 'lot',
            'following', 'rounded', 'subject', 'rounding', 'note', 'notes',
            'issue', '%', 'upon', 'completion',
        ])

        _NOISE_KW = [
            'the table below sets forth details of the cornerstone',
            'the table below sets out details of the cornerstone',
            'the tables below set forth',
            'the tables below set out',
            'cornerstone investor',
            'total investment amount',
            'number of offer shares',
            'approximate % of the offer shares',
            'approximate % of the issued share capital',
            'appropriate % of the total',
            'appropriate % of the offer',
            '(usd in millions)',
            'based on the offer price',
            'assuming the over-allotment',
            'assuming the offer size',
            'option is not exercised',
            'option is exercised',
            'offer shares to be acquired',
            'immediately upon',
            'completion of the global offering',
            '(in hk$)',
            'us$in',
            'hk$in',
            'note ',
            'subject to rounding',
            'notes:',
            'appropriate %',
            'of the total',
            'issued share capital',
            'completion of',
            'assuming the',
            'offer size adjustment',
            'over-allotment option',
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
            'cornerstone investors', 'esop', 'employee share option',
            'employee stock ownership', 'pre ipo', 'pre-ipo',
            'appropriate', 'appropriate %', 'total issued share',
            'share capital immediately', 'immediately upon',
            'cornerstone', 'investor', 'investment amount',
            'offer price', 'global offering', 'offer size',
            'over-allotment', 'over allotment',
            'number', 'acquired', 'subscribed', 'to be',
            'of offer', 'of the offer', '% of offer',
            'shares to be', 'offer size adjustment',
            '(us$in', '(hk$in', 'us$in', 'hk$in',
        }

        _TABLE_KWS = ('appropriate', 'assuming', 'over-allotment', 'allotment', 
                        'offer size', 'adjustment option', 'exercised', 'not exercised',
                        'completion of', 'global offering', 'issued share capital',
                        'approximate %', 'of the total', 'immediately upon',
                        'offer shares', 'subscription amount', 'number of',
                        'option is', 'fully exercised', 'in full',
                        'offer size adjustment', 'over-allotment option')

        _REPEAT_KWS = ('issued share', 'capital', 'immediately', 'upon', 'appropriate', 'approximate')

        _INVESTOR_KEYWORDS = frozenset([
            'partners', 'capital', 'management', 'investments', 'fund', 'venture',
            'asset', 'group', 'corporation', 'holdings', 'plc', 'inc', 'corp',
            'limited', 'ltd', 'ltd.', 'l.p.', 'lp', 'llc', 'co', 'co.',
            'international', 'global', 'scsp', 'sarl', 'pte', 'trust',
            'foundation', 'pension', 'university', 'hospital', 'healthcare',
            'biotech', 'pharma', 'pharmaceutical', 'laboratory', 'venture',
            'ventures', 'private', 'equity', 'securities', 'financial',
            'action', 'amr', 'hua', 'yuan', 'orient', 'junestar', 'danyuan',
        ])

        def _is_noise(line):
            ll = line.lower()
            chinese_table_kws = (
                '假設超額配股權', '基石投資者', '基石投资者', '認購金額', '认购金额',
                '發售', '发售', '股份數目', '股份数目', '佔發售股份', '占发售股份',
                '已發行股本', '已发行股本', '概約百分比', '概约百分比',
                '美元', '港元', '基於發售價', '基于发售价', '附註', '附注',
                '下表載列', '下表载列',
            )
            if any(kw in line for kw in chinese_table_kws):
                return True

            if sum(1 for kw in _TABLE_KWS if kw in ll) >= 2:
                return True
            
            for kw in _REPEAT_KWS:
                if ll.count(kw) >= 2:
                    return True
            
            if 'set out in this prospectus' in ll:
                return True
            
            if 'cornerstone' in ll and 'number of' in ll and 'offer' in ll:
                return True
            
            if 'investment amount' in ll and 'offer shares' in ll:
                return True
            
            if ll.count('shares offering') >= 2:
                return True
            
            if ll.count('millions)') >= 2:
                return True
            
            if 'us$ in' in ll or 'hk$ in' in ll:
                return True
            
            # 短行表格标题检测
            words = ll.split()
            if 1 <= len(words) <= 5:
                cleaned_words = [w for w in (_CRE_FLUSH_PARENS_END.sub('', w) for w in words) if w]
                if cleaned_words and all(w in _HEADER_WORD_SET for w in cleaned_words):
                    # 如果短词全是标题词，但其中也包含投资者关键词（如 Global、Capital），
                    # 则不当作纯噪声 — 它可能是名字的一部分
                    if not any(w in _INVESTOR_KEYWORDS for w in cleaned_words):
                        return True
            
            compact = _CRE_FLUSH_WHITESPACE.sub(' ', _CRE_FLUSH_NON_ALPHA.sub(' ', _CRE_FLUSH_CLEAN_PARENS.sub('', ll))).strip()
            
            if compact.startswith('total') and not any(kw in compact for kw in ['fund', 'capital', 'asset', 'management']):
                return True
            if _CRE_FLUSH_FULL_DIGITS.fullmatch(compact):
                return True
            if compact.startswith('based on the offer price'):
                return True
            if _CRE_FLUSH_AMOUNT.fullmatch(compact):
                return True
            if compact in _NOISE_EXACT or ll in _NOISE_EXACT or any(kw in ll for kw in _NOISE_KW):
                return True
            if compact in ('investment amount', 'number of offer shares', 'offer shares', 'issued share capital',
                           'share capital', 'approximate', 'investment', 'amount', 'shares',
                           'cornerstone investor', 'cornerstone investors', 'cornerstone', 'investor'):
                return True
            if 'million' in compact and ('hk' in compact or 'usd' in compact or 'us' in compact or '$' in ll):
                if 'limited' not in compact and not any(kw in compact for kw in ['partners', 'capital', 'management', 'fund']):
                    return True
            table_header_kws = ('usd', 'us$', 'hk$', 'u.s.', 'amount', 'shares', 'offer', 'approximate', '%', 'million')
            header_hits = sum(1 for kw in table_header_kws if kw in compact)
            if header_hits >= 3 and 'limited' not in compact:
                return True
            if ('us$' in compact or 'usd' in compact or 'hk$' in compact) and ('offer' in compact or 'shares' in compact) and 'limited' not in compact:
                return True
            if 'shares' in compact and 'capital' in compact and 'million' in compact and 'limited' not in compact:
                return True
            if 'million' in compact and 'shares' in compact and len(compact.split()) <= 3 and 'limited' not in compact:
                return True
            # 连写表格标题检测（PDF去空格后，列标题连成一行）
            _TABLE_KWS_NOSPACE = (
                'assuming', 'over-allotment', 'allotment', 'offersize', 'adjustmentoption',
                'exercised', 'notexercised', 'completionof', 'globaloffering',
                'issuedshare', 'sharecapital', 'approximate', 'appropriate', 'ofthetotal',
                'immediatelyupon', 'offershares', 'subscriptionamount', 'numberof',
                'optionis', 'fullyexercised', 'infull', 'offersizeadjustment',
                'over-allotmentoption', 'investmentamount', 'cornerstoneinvestor',
                'thetablebelow', 'setsforth', 'detailsofthe',
                'oftheoffer', 'theglobal', 'us$in', 'hk$in',
            )
            table_kw_hits = sum(ll.count(kw) for kw in _TABLE_KWS_NOSPACE)
            if table_kw_hits >= 3:
                return True

            if _CRE_FLUSH_GENERIC.fullmatch(compact) and len(compact.split()) <= 4 and not any(kw in compact for kw in _INVESTOR_KEYWORDS):
                return True
            if 'esop' in compact or 'employee share' in compact or 'employee stock' in compact:
                return True
            # Financial statement lines that should never be cornerstone investors
            _FINANCIAL_NOISE = (
                '年度溢利', '年度亏损', '綜合收益', '綜合虧損', '綜合損益',
                '應付款項', '應收賬款', '貿易應收款', '其他應付款',
                '物業', '設備', '固定資產', '在建工程', '無形資產',
                '虧損撥備', '預期虧損', '預期信貸虧損', '減值虧損',
                '處置', '折舊', '攤銷', '於20', '會計師報告',
                '附錄', '財務報表', '資產負債表',
                'profit', 'loss', 'balance sheet', 'income statement',
                'property', 'plant', 'equipment', 'intangible',
                'payables', 'receivables', 'depreciation', 'amortisation',
            )
            if any(kw in ll for kw in _FINANCIAL_NOISE):
                return True
            return False

        def _split_line_to_name_and_numbers(line):
            tokens = line.split()
            if not tokens:
                return None, []

            start_idx = 0
            if tokens and _CRE_PARENS_ONLY.fullmatch(tokens[0]):
                start_idx = 1

            effective_tokens = tokens[start_idx:]
            if not effective_tokens:
                return None, []

            number_tokens = []
            name_tokens = []
            found_number = False
            for i in range(len(effective_tokens) - 1, -1, -1):
                t = effective_tokens[i]
                is_strict_numeric = self._is_numeric_cell(t)
                has_letters = bool(_CRE_HAS_LETTER.search(t))
                parsed_num = None if has_letters else self._parse_cornerstone_number(t)
                
                if is_strict_numeric or (parsed_num is not None and not has_letters):
                    number_tokens.insert(0, t)
                    found_number = True
                elif found_number:
                    if t.endswith(')') and has_letters and _CRE_PARENS_ONLY.search(t):
                        name_tokens = effective_tokens[:i + 1]
                        break
                    elif not t.endswith(')'):
                        name_tokens = effective_tokens[:i + 1]
                        break
                elif not found_number and has_letters and t.endswith(')') and _CRE_PARENS_ONLY.search(t):
                    # 还没找到数字，但遇到名字+括号（如 Partners(4)），当作名字的一部分
                    continue

            # 启发式：小数字可能是名字的一部分（如 "Big Bend 77"）
            # 但排除以下情况：
            # - 包含 % 的数字（百分比）
            # - 小数（如 10.0，通常是金额）
            if len(number_tokens) >= 2:
                first_raw = number_tokens[0]
                first_num = self._parse_cornerstone_number(first_raw)
                second_num = self._parse_cornerstone_number(number_tokens[1])
                if first_num is not None and second_num is not None:
                    # 排除百分比和小数
                    has_pct = '%' in first_raw
                    is_decimal = '.' in first_raw and first_num < 1000
                    if not has_pct and not is_decimal and first_num < 1000 and second_num > first_num * 10:
                        name_tokens.append(number_tokens.pop(0))

            if not name_tokens and found_number:
                return None, number_tokens
            if not found_number:
                return line, []

            return ' '.join(name_tokens), number_tokens

        rows = []
        name_buffer = []
        numeric_buffer = []
        pending_flush = False  # 标记是否有待flush的混合行

        def _strip_header_from_name(raw_name):
             name = raw_name
             for pattern in _HEADER_PREFIX_PATTERNS:
                 match = pattern.match(name)
                 while match and match.end() > 0:
                     name = name[match.end():].strip()
                     if not name:
                         break
                     match = pattern.match(name)
             while name:
                 first_word = name.split()[0]
                 clean_first = _CRE_STRIP_PARENS.sub('', first_word).lower()
                 if clean_first in _HEADER_WORD_SET:
                     name = ' '.join(name.split()[1:]).strip()
                     if not name:
                         break
                 else:
                     break
             return name

        def flush_row():
            nonlocal name_buffer, numeric_buffer, pending_flush
            logger.debug("cornerstone flush_row name_buf=%s numeric_count=%s", [p[:30] for p in name_buffer], len(numeric_buffer))
            if not name_buffer or len(numeric_buffer) < 3:
                name_buffer = []
                numeric_buffer = []
                pending_flush = False
                return

            cleaned_name_lines = []
            for part in name_buffer:
                if not _is_noise(part) or (part.lower() == 'capital' and cleaned_name_lines):
                    cleaned_name_lines.append(part)
                elif cleaned_name_lines and len(part.split()) <= 4:
                    # name_buffer 中已有有效内容，短词可能是名字续行部分
                    # （如 SCSp、Limited、Global 等被 _is_noise 误判的组件）
                    part_lower = part.lower()
                    if any(kw in part_lower for kw in _INVESTOR_KEYWORDS):
                        cleaned_name_lines.append(part)

            name = self._normalize_cornerstone_line(' '.join(cleaned_name_lines))
            if not name:
                name_buffer = []
                numeric_buffer = []
                pending_flush = False
                return

            name = _strip_header_from_name(name)
            if not name or len(name) > 80:
                name_buffer = []
                numeric_buffer = []
                pending_flush = False
                return

            name_lower = name.lower()
            bad_keywords = ['appropriate', 'assuming', 'completion', 'global offering',
                           'issued share', 'share capital', 'over-allotment', 'offer size']
            if sum(1 for kw in bad_keywords if kw in name_lower) >= 2:
                name_buffer = []
                numeric_buffer = []
                pending_flush = False
                return

            # Reject names that are clearly financial statement items
            _FIN_NAME_KW = (
                '年度溢利', '年度亏损', '綜合收益', '綜合虧損', '應付款項',
                '貿易應收款', '虧損撥備', '預期虧損', '減值虧損',
                '會計師報告', '財務報表', '資產負債表', 'income statement',
                'balance sheet', 'profit loss', 'property plant',
            )
            if any(kw in name for kw in _FIN_NAME_KW):
                name_buffer = []
                numeric_buffer = []
                pending_flush = False
                return

            nums = [self._parse_cornerstone_number(n) for n in numeric_buffer]
            nums = [n for n in nums if n is not None]

            if len(nums) < 3:
                name_buffer = []
                numeric_buffer = []
                pending_flush = False
                return

            num_to_raw = {}
            for raw in numeric_buffer:
                parsed = self._parse_cornerstone_number(raw)
                if parsed is not None:
                    if parsed not in num_to_raw:
                        num_to_raw[parsed] = raw

            # 智能列序识别
            # 1. 优先识别原始文本中带 % 的数字为百分比
            pct_indices = [i for i, raw in enumerate(numeric_buffer) if '%' in raw]
            pcts = []
            pct1_val = None
            pct2_val = None

            if len(pct_indices) >= 2:
                pct1_val = nums[pct_indices[0]] if pct_indices[0] < len(nums) else None
                pct2_val = nums[pct_indices[1]] if pct_indices[1] < len(nums) else None
                if pct1_val is not None:
                    pcts.append(pct1_val)
                if pct2_val is not None:
                    pcts.append(pct2_val)
            else:
                # 利用股数列位置识别百分比
                # 股数特征：大整数(>1000)，在金额之后、百分比之前
                large_int_indices = [(i, n) for i, n in enumerate(nums) if n == int(n) and n > 1000]
                
                shares_idx = None
                shares_val = None
                
                if len(large_int_indices) >= 2:
                    # 多个大整数：第一个是金额（如277,000,000），第二个是股数
                    shares_idx = large_int_indices[1][0]
                    shares_val = large_int_indices[1][1]
                elif len(large_int_indices) == 1:
                    shares_idx = large_int_indices[0][0]
                    shares_val = large_int_indices[0][1]
                
                if shares_idx is not None:
                    # 股数列之后的数字中，0 < n <= 100 的是百分比
                    pct_after_shares = [(i, n) for i, n in enumerate(nums) 
                                       if i > shares_idx and 0 < n <= 100]
                    if len(pct_after_shares) >= 2:
                        pct1_val = pct_after_shares[0][1]
                        pct2_val = pct_after_shares[1][1]
                        pcts.append(pct1_val)
                        pcts.append(pct2_val)
                    elif len(pct_after_shares) == 1:
                        pct1_val = pct_after_shares[0][1]
                        pcts.append(pct1_val)
                else:
                    # 没有大整数，回退到数值范围识别
                    potential_pcts = [(i, n) for i, n in enumerate(nums) if 0 < n <= 100]
                    if len(potential_pcts) >= 2:
                        pct1_val = potential_pcts[0][1]
                        pct2_val = potential_pcts[1][1]
                        pcts.append(pct1_val)
                        pcts.append(pct2_val)
                    elif len(potential_pcts) == 1:
                        pct1_val = potential_pcts[0][1]
                        pcts.append(pct1_val)

            # 确定股数和金额
            non_pcts = [n for n in nums if n not in pcts]

            # 识别金额列：原始文本包含货币前缀（US$, HK$, $）
            currency_raw_indices = [i for i, raw in enumerate(numeric_buffer) if _CRE_CURRENCY_START.match(raw.strip())]
            currency_vals = [nums[i] for i in currency_raw_indices if i < len(nums)]

            # 利用股数列位置确定金额和股数
            large_int_indices = [(i, n) for i, n in enumerate(nums) if n == int(n) and n > 1000]
            
            amount_val = None
            shares_val = None
            
            if currency_vals:
                amount_val = currency_vals[0]
                if len(large_int_indices) >= 1:
                    shares_candidates = [n for i, n in large_int_indices if n != amount_val]
                    shares_val = max(shares_candidates) if shares_candidates else None
                else:
                    remaining = [n for n in non_pcts if n != amount_val]
                    shares_val = max(remaining) if remaining else None
            elif len(large_int_indices) >= 2:
                amount_val = large_int_indices[0][1]
                shares_val = large_int_indices[1][1]
            elif len(large_int_indices) == 1:
                shares_val = large_int_indices[0][1]
                amount_candidates = [n for n in non_pcts if n != shares_val and n not in pcts]
                amount_val = amount_candidates[0] if amount_candidates else None
            elif len(non_pcts) >= 3:
                shares_val = max(non_pcts)
                amount_val = non_pcts[0] if non_pcts[0] != shares_val else non_pcts[1]
            elif len(non_pcts) == 2:
                if non_pcts[0] > non_pcts[1] * 10:
                    shares_val, amount_val = non_pcts[0], non_pcts[1]
                else:
                    amount_val, shares_val = non_pcts[0], non_pcts[1]
            elif len(non_pcts) == 1:
                amount_val = non_pcts[0]
                shares_val = None

            if amount_val is not None and shares_val is not None:
                if amount_val > 1_000_000 and shares_val < 1000:
                    amount_val, shares_val = shares_val, amount_val
                elif amount_val > 100_000 and shares_val < 100:
                    amount_val, shares_val = shares_val, amount_val

            amount_raw = num_to_raw.get(amount_val, numeric_buffer[0]) if amount_val is not None else numeric_buffer[0]

            row = {
                'name': name,
                'short_name': self._cornerstone_short_name(name),
                'offer_shares': int(shares_val or 0),
                'offer_shares_pct': pct1_val,
                'issued_share_pct': pct2_val,
            }
            row.update(self._cornerstone_amount_fields(amount_raw, table_text))
            if (
                row['investment_amount_m'] is not None
                and row['offer_shares'] > 0
                and row['offer_shares_pct'] is not None
                and 0 < row['offer_shares_pct'] <= 100
            ):
                if row['issued_share_pct'] is None or 0 <= row['issued_share_pct'] <= 100:
                    rows.append(row)
            name_buffer = []
            numeric_buffer = []
            pending_flush = False

        for line in lines:
            lower_line = line.lower()
            if line.strip() in ("Fund,", "SCSp(cid:2) (cid:2) (cid:2)", "HuaYuan", "AMRAction"):
                logger.debug(
                    "cornerstone trace line=%s noise=%s nb=%s num=%s pending=%s",
                    line.strip()[:20],
                    _is_noise(line),
                    name_buffer,
                    len(numeric_buffer),
                    pending_flush,
                )
            if _is_noise(line):
                if lower_line == 'capital' and name_buffer and not numeric_buffer:
                    prev_name_lower = ' '.join(name_buffer).lower()
                    investor_kws = list(_INVESTOR_KEYWORDS)
                    prev_has_investor_kw = any(kw in prev_name_lower for kw in investor_kws)
                    if prev_has_investor_kw:
                        name_buffer.append(line)
                    continue
                if pending_flush or len(numeric_buffer) >= 4:
                    flush_row()
                elif numeric_buffer:
                    name_buffer = []
                    numeric_buffer = []
                    pending_flush = False
                continue

            # 尝试将一行分割为名字+数字
            name_part, number_parts = _split_line_to_name_and_numbers(line)
            if name_part and number_parts and len(number_parts) >= 3:
                if pending_flush:
                    # 已经有待flush的行，当前是新投资者
                    flush_row()
                elif name_buffer and not numeric_buffer:
                    # 如果 name_buffer 中的内容看起来都是噪声，清空它
                    if all(_is_noise(p) for p in name_buffer):
                        name_buffer = []
                    # 前面有名字但没有数字，当前行包含完整的名字+数字
                    # 检查前面的名字是否是当前名字的一部分（续行）
                    prev_name = ' '.join(name_buffer).lower().strip()
                    curr_name = name_part.lower().strip()
                    # 判断前面是否是续行：如果包含投资者关键词，认为是续行
                    investor_keywords = list(_INVESTOR_KEYWORDS)
                    prev_has_investor_kw = any(kw in prev_name for kw in investor_keywords)
                    curr_has_investor_kw = any(kw in curr_name for kw in investor_keywords)
                    # 如果前面名字包含投资者关键词，且当前名字也包含，认为是续行
                    if prev_has_investor_kw and curr_has_investor_kw and prev_name != curr_name:
                        # 续行：保留前面的名字并追加当前名字
                        name_buffer.append(name_part)
                    elif len(name_buffer) <= 2 and prev_name and prev_name != curr_name and not prev_has_investor_kw:
                        # 前面可能是上一个投资者的残余，清空
                        name_buffer = [name_part]
                    elif any(not _is_noise(p) for p in name_buffer):
                        name_buffer.append(name_part)
                    else:
                        name_buffer = [name_part]
                    numeric_buffer = number_parts
                    if 'for and on behalf' in name_part.lower():
                        continue
                    flush_row()
                    continue
                
                # 新混合行
                name_buffer = [name_part]
                numeric_buffer = number_parts
                pending_flush = True
                if 'for and on behalf' in name_part.lower():
                    continue
                # 不立即flush，等待看是否有续行
                continue

            if self._is_numeric_cell(line):
                if name_buffer:
                    numeric_buffer.append(line)
                    pending_flush = True
                continue

            # 纯名字行
            if pending_flush and name_buffer and numeric_buffer:
                # 有待flush的行，当前是纯名字行
                # 检查是否是续行（如 "Fund, L.P."）
                line_tokens = line.split()
                has_numbers = any(self._is_numeric_cell(t) or self._parse_cornerstone_number(t) is not None for t in line_tokens)
                line_lower = line.lower()
                
                # 检查 name_buffer 是否已经包含完整的投资者名字
                current_name = ' '.join(name_buffer).lower()
                # 包含明确的公司后缀（如 Limited, Ltd, L.P., PLC）或知名单字机构名
                well_known_single_names = ['blackrock', 'temasek', 'gic', 'qia', 'adia', 'cppib', 'kia']
                has_complete_name = (
                    any(kw in current_name for kw in ['limited', 'ltd', 'l.p.', 'lp', 'plc', 'inc.', 'corp.', 'corporation'])
                    or any(kw == current_name.strip() for kw in well_known_single_names)
                )
                
                # 检查 name_buffer 是否在等待 for and on behalf 的续行
                waiting_for_behalf = 'for and on behalf' in current_name

                # 如果 numeric_buffer 已经有足够数据（>=6个数字），
                # 下一个名字行应该被当作新投资者
                has_sufficient_data = len(numeric_buffer) >= 6

                # 检查当前行是否明显是新投资者
                # 新投资者通常有2个或更多token，且包含投资者类型关键词
                is_new_investor = (
                    len(line_tokens) >= 2
                    and any(kw in line_lower for kw in ['capital', 'asset', 'management', 'investments', 'star', 'group', 'corporation', 'ventures'])
                    and not line_lower.startswith('fund')
                    and not line_lower.startswith('scsp')
                ) or (
                    # Chinese investor name: 3+ chars, has_sufficient_data
                    len(line) >= 3 and has_sufficient_data
                )

                # 检查当前行是否看起来是续行
                # 续行通常很短（<=4个token），且不包含数字
                # 但如果包含 footnote 标记（如 ў），可能更长
                has_footnote = any(c in line for c in ['ў', '©', '®', '™'])
                looks_like_continuation = (
                    (len(line_tokens) <= 4 or has_footnote)
                    and not has_numbers
                    and not _is_noise(line)
                )
                
                # If this is a total/summary row, flush previous and stop
                if lower_line in ('總計', '总计', 'total', '合計', '合计'):
                    flush_row()
                    break

                # 如果在等待 for and on behalf 的续行，且名字还不完整，优先当作续行
                if waiting_for_behalf and not has_complete_name:
                    name_buffer.append(line)
                # 如果已收集到足够数据，任何新名字都触发 flush（优先于续行判断）
                elif has_sufficient_data:
                    flush_row()
                    name_buffer = [line]
                elif looks_like_continuation and not has_complete_name:
                    name_buffer.append(line)
                elif is_new_investor:
                    flush_row()
                    name_buffer = [line]
                else:
                    flush_row()
                    name_buffer = [line]
                continue
            elif numeric_buffer:
                if name_buffer:
                    if len(numeric_buffer) >= 3:
                        flush_row()
                        name_buffer = [line]
                        continue
                    name_buffer.append(line)
                    last_name = ' '.join(name_buffer).lower()
                    if any(suffix in last_name for suffix in ['limited', 'ltd', 'l.p.', 'plc', 'inc.', 'corp.', 'corporation']):
                        flush_row()
                    continue
                if len(numeric_buffer) >= 4:
                    flush_row()
                else:
                    continue

            if lower_line == 'notes:':
                break
            if lower_line in ('總計', '总计', 'total', '合計', '合计'):
                flush_row()
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
        combined = _CRE_CONTROL.sub(' ', combined)
        combined = _CRE_WHITESPACE.sub(' ', combined)

        for m in _CRE_INVESTOR_REGEX.finditer(combined):
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

            direct_matches = []
            direct_profiles = []
            direct_seen = set()
            row_text = f"{row.get('name', '')} {row.get('short_name', '')}"
            for profile in self._matched_profiles(row_text):
                key = (profile.get('name'), profile.get('tier'))
                if key in direct_seen:
                    continue
                direct_seen.add(key)
                direct_profiles.append(profile)
                direct_matches.append(self._profile_match_payload(profile))

            related_matches = []
            related_profiles = []
            seen = set()
            if not direct_profiles:
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
        
        for match in _CRE_CORNERSTONE_KEYWORD_PCT.finditer(context):
            try:
                pct = float(match.group(1))
            except Exception:
                continue
            if 1 <= pct <= 95:
                priority_candidates.append(pct)

        for pattern in _CRE_PCT_PATTERNS:
            for match in pattern.finditer(context):
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

        for pattern in _CRE_SHARE_PCT_PATTERNS:
            for match in pattern.finditer(context):
                try:
                    if pattern is _CRE_SHARE_PCT_PATTERNS[1]:
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

        # 中文招股书 fallback：检测总计行或"占发售股份"附近的百分比
        if not priority_candidates and not candidates:
            cn_patterns = [
                re.compile(r'(?:總計|总计|合计|總額)[\s\S]{0,500}?([0-9]+(?:\.[0-9]+)?)%', re.DOTALL),
                re.compile(r'(?:佔發售股份|占发售股份|佔發售|占发售)[\s\S]{0,300}?([0-9]+(?:\.[0-9]+)?)%', re.DOTALL),
            ]
            for pattern in cn_patterns:
                for match in pattern.finditer(context):
                    try:
                        pct = float(match.group(1))
                    except Exception:
                        continue
                    if 1 <= pct <= 95:
                        priority_candidates.append(pct)

        if priority_candidates:
            # 优先取第一个高置信匹配（避免范围值取最大导致过度乐观）
            return round(priority_candidates[0], 2)
        elif candidates:
            return round(candidates[0], 2)
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
            healthcare_hits = any(keyword in lower_context for keyword in [
                'healthcare', 'medical', 'biotech', 'pharmaceutical', 'clinical',
                'drug', 'patient', 'diagnosis',
            ])
            hardtech_hits = any(keyword in lower_context for keyword in [
                'semiconductor', 'chip', 'wafer', 'foundry', 'robot', 'robotics',
                'automation', 'industrial', 'manufacturing', 'ai chip', 'gpu',
                '科技', '创新', '半导体', '机器人',
            ])
            if hardtech_hits:
                return True
            if healthcare_hits:
                return False
            return any(keyword in lower_context for keyword in [
                'technology', 'tech', 'innovation', 'venture', 'science',
                'high-tech',
            ])
        if sector == 'consumer':
            return any(keyword in lower_context for keyword in [
                'consumer', 'retail', 'brand', 'food', 'beverage', '消费'
            ])
        return None

    def _spv_risk_flags(self, context):
        """检测 SPV/空壳风险，但排除港股招股书标准法律用语"""
        lower_context = context.lower()
        hits = []
        patterns = [
            ('BVI注册主体较多', ['british virgin islands', 'bvi incorporated', 'bvi company', 'bvi limited']),
            ('出现 SPV / 特殊目的载体表述', ['special purpose vehicle', 'spv ', '(spv)', 'spv,', 'spv.', 'special purpose']),
            # 移除 "incorporated on"：这是港股基石描述标准法律用语
            # 改为只检测明确的新设/临近IPO信号
            ('疑似临近 IPO 新设主体', ['newly incorporated', 'recently incorporated',
                                       'incorporated shortly before', 'incorporated for the purpose',
                                       'incorporated specifically']),
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
                'tier_score': self._effective_tier_score(tier, item.get('offer_shares_pct')),
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
        sector = getattr(self, '_last_sector', 'unknown')
        strategic_missing_label = (
            '无产业药企/核心客户型战略基石'
            if sector == 'healthcare'
            else '无产业资本/核心客户型战略基石'
        )
        groups = []
        if any('主权' in cat or '养老金' in cat for cat in categories):
            groups.append('国际主权/养老金')
        if any('全球顶级长线资管' in cat for cat in categories):
            groups.append('顶级资管')
        if any('多策略' in cat or '对冲基金' in cat for cat in categories):
            groups.append('多策略/对冲基金')
        if any('量化做市商' in cat for cat in categories):
            groups.append('量化做市商')
        if any('医疗专业基金' in cat for cat in categories):
            groups.append('医疗基金')
        if any('国资' in cat for cat in categories):
            groups.append('国家队')
        if any('中资长线' in cat or '公募' in cat for cat in categories):
            groups.append('国内公募/长线资金')
        if any('保险资金' in cat for cat in categories):
            groups.append('保险长线资金')
        if any('PE/VC' in cat or '成长基金' in cat for cat in categories):
            groups.append('一线PE/VC')
        if any('产业战略' in cat for cat in categories):
            groups.append('产业资本')
        if any('券商直投' in cat for cat in categories):
            groups.append('券商直投')
        if not groups:
            groups.append('普通财务基石')

        # 添加基石总数和 tier 分布，避免少量基石也能给出看似丰富的组合标签
        tier_counts = {}
        for row in rows:
            tier = row.get('tier', '未知')
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
        total = len(rows)
        tier_info = f"共{total}家基石"
        if total > 0:
            tier_parts = []
            for t in ('S', 'A', 'B', '弱'):
                if t in tier_counts:
                    tier_parts.append(f"{t}级{tier_counts[t]}")
            if tier_parts:
                tier_info += f"({'+'.join(tier_parts)})"

        missing = []
        if not any('主权' in cat or '养老金' in cat for cat in categories):
            missing.append('无国际主权')
        if not any('产业战略' in cat for cat in categories):
            missing.append(strategic_missing_label)
        return f"{tier_info}；{' + '.join(groups)}" + ("；" + "、".join(missing) if missing else "")

    def _build_v2_result(self, cornerstone_rows, matched, cornerstone_pct, sector, sector_match, spv_flags):
        self._last_sector = sector
        profile_rows = self._v2_profile_rows(cornerstone_rows, matched, sector)
        row_weights = []
        for row in profile_rows:
            pct = row.get('offer_shares_pct')
            weight = pct if pct is not None and pct > 0 else 1
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
            if cornerstone_pct < ct.pct_acceptable_low:
                subscription_detail = f'基石占比{cornerstone_pct:.1f}%，低于{ct.pct_acceptable_low:.0f}%安全线，机构参与度不足'
            else:
                subscription_detail = f'基石占比{cornerstone_pct:.1f}%，超过{ct.pct_acceptable_high:.0f}%上限，流通盘过小'

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
            if sector == 'healthcare':
                concerns.append('无产业药企/核心客户型战略基石，产业协同背书不足')
            else:
                concerns.append('无产业资本/核心客户型战略基石，产业协同背书不足')
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
                score = min(score, ct.score_cap_severe_red_flags)
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
                'source_excerpt': '',
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
        result['source_excerpt'] = self._source_excerpt(context)
        # 保留所有 matched_investors（含 pre_ipo_section），但分开标记
        result['all_matched_investors'] = matched
        # 添加负面语境中识别到的高质量投资者（如"未见GIC"）
        absent_hq = getattr(self, '_last_absent_high_quality', [])
        result['absent_high_quality_investors'] = absent_hq
        if absent_hq:
            result['concerns'] = result.get('concerns', []) + [
                f"负面语境识别到高质量投资者缺席: {', '.join(a['name'] for a in absent_hq)}"
            ]
        return result


# 模块级加载：优先从 YAML 读取，失败回退到内置数据；运行中 YAML 变更会自动重载
CornerstoneAnalyzer._set_investor_profiles(_load_investor_profiles(), investor_profiles_signature())


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
