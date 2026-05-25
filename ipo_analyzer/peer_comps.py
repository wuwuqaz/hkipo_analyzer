"""同行对比与相对估值分析模块 — 半动态同行库

依赖: pyyaml (懒加载), 无其他重依赖
"""

import os
import re
import logging
from datetime import date, datetime
from statistics import median

from .utils import _is_num
from .settings import SETTINGS

logger = logging.getLogger(__name__)

_PEER_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "peer_comps.yaml",
)

# 招股书语境中不可能成为同行的通用词 / 标题词
_PROSPECTUS_JUNK_WORDS = {
    "the", "this", "our", "we", "for", "and", "with", "from",
    "based", "such", "these", "other", "also", "each", "may",
    "ltd", "limited", "inc", "corporation", "corp", "holdings",
    "company", "group", "stock", "code", "prospectus",
    "global offering", "offer shares", "public offer",
    "international offering",
    "joint sponsors", "overall coordinators", "global coordinators",
    "joint bookrunners", "joint lead managers",
    "people republic china", "hong kong", "cayman islands",
    "securities and futures commission", "stock exchange",
    "main board", "listing rules", "appendix", "chapter",
    "chairman", "director", "secretary", "registered office",
    "principal place of business", "company address",
    "hong kong", "shanghai", "beijing", "shenzhen",
}

# 有强公司后缀的词 — 识别为公司名的关键信号
_CORPORATE_SUFFIXES = {
    "limited", "ltd", "inc", "corporation", "corp",
    "plc", "ag", "sa", "nv", "llc",
    "holdings", "group",
    "pharma", "biotech", "therapeutics", "biosciences",
    "robotics",
    "medical", "healthcare",
    "laboratories", "laboratory", "lab", "labs",
    "ventures", "capital", "partners",
}

# 中文公司名常见后缀/行业词（用于中文候选）
_CHINESE_CORP_KEYWORDS = {
    "科技", "生物", "医药", "制药", "药业", "医疗",
    "集团", "股份", "有限", "机器人", "智能",
    "半导体", "基因", "细胞", "创新药", "器械",
}


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

def _ensure_yaml():
    try:
        import yaml as _yaml_mod
        return _yaml_mod
    except ImportError:
        logger.warning("pyyaml 未安装，无法加载同行数据库")
        return None


def _load_peer_data(path=None):
    path = path or _PEER_DATA_PATH
    if not os.path.exists(path):
        logger.warning("同行数据库未找到: %s", path)
        return None
    yaml_mod = _ensure_yaml()
    if yaml_mod is None:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml_mod.safe_load(f)
        return data
    except Exception as e:
        logger.warning("同行数据库加载失败: %s", e)
        return None


def _parse_source_date(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            parsed = datetime.strptime(str(value).strip(), fmt).date()
            return parsed if fmt == "%Y-%m-%d" else parsed.replace(day=1)
        except ValueError:
            continue
    return None


def _build_peer_meta(peer_data):
    meta = (peer_data or {}).get("meta", {}) if isinstance(peer_data, dict) else {}
    source_dt = _parse_source_date(meta.get("source_date"))
    age_days = (date.today() - source_dt).days if source_dt else None
    pt = SETTINGS.peer_comps
    stale_after = pt.stale_after_days
    try:
        stale_after = int(meta.get("stale_after_days", pt.stale_after_days))
    except (TypeError, ValueError):
        pass
    return {
        "peer_data_source_date": meta.get("source_date"),
        "peer_data_last_checked_at": meta.get("last_checked_at"),
        "peer_data_quality": meta.get("data_quality"),
        "peer_data_age_days": age_days,
        "peer_data_stale_after_days": stale_after,
        "peer_data_is_stale": age_days is not None and age_days > stale_after,
        "peer_data_update_script": meta.get("update_script"),
    }


_GICS_MAPPING_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "gics_mapping.yaml",
)

_GICS_CACHE = None


def _load_gics_mapping(path=None):
    global _GICS_CACHE
    if _GICS_CACHE is not None:
        return _GICS_CACHE
    path = path or _GICS_MAPPING_PATH
    if not os.path.exists(path):
        return {}
    yaml_mod = _ensure_yaml()
    if yaml_mod is None:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml_mod.safe_load(f)
        mapping = {}
        if isinstance(data, dict):
            for code, val in data.items():
                if code == "meta":
                    continue
                if isinstance(val, dict) and "sector_key" in val and "subsector_key" in val:
                    mapping[str(code)] = (val["sector_key"], val["subsector_key"])
        _GICS_CACHE = mapping
        return mapping
    except Exception as e:
        logger.warning("GICS 映射加载失败: %s", e)
        return {}


def lookup_gics_subsector(gics_code):
    """根据 GICS 代码查找对应的 peer_comps sector/subsector

    支持 2/4/6/8 位 GICS 代码，优先匹配最长的代码（最精确）。
    返回 (sector_key, subsector_key) 或 (None, None)
    """
    if not gics_code:
        return None, None
    code = str(gics_code).strip()
    mapping = _load_gics_mapping()
    if code in mapping:
        return mapping[code]
    for prefix_len in (6, 4, 2):
        prefix = code[:prefix_len]
        if prefix in mapping:
            return mapping[prefix]
    return None, None


def _strip_corp_suffix(name):
    """去掉公司后缀，用于发行人别名匹配"""
    s = name.strip()
    # 排除纯后缀本身
    if s.lower() in ("ltd", "limited", "inc", "corp", "corporation", "holdings", "group", "company"):
        return s
    s_clean = re.sub(r'\s+(Limited|Ltd|Inc|Corporation|Corp|PLC|AG|SA|NV|LLC|Holdings|Group|Company|Co\.,?\s*Ltd|Co\.?\s*Ltd\.?)$', '', s, flags=re.IGNORECASE).strip()
    s_clean = re.sub(r'\s+[,，]\s*', ' ', s_clean).strip()
    return s_clean if s_clean else s


# ---------------------------------------------------------------------------
# 发行人别名收集
# ---------------------------------------------------------------------------

def _build_issuer_aliases(prospectus_info, ipo_data=None):
    """收集发行人所有可能的名称变体，用于排除"""
    raw_names = set()
    if ipo_data:
        raw_names.add(str(ipo_data.get("company_name", "")))
        raw_names.add(str(ipo_data.get("shortname", "")))
        raw_names.add(str(ipo_data.get("hk_code", "")))
    pi = prospectus_info or {}
    raw_names.add(str(pi.get("extracted_company_name", "")))
    raw_names.add(str(pi.get("extracted_english_name", "")))
    for alias in pi.get("company_name_aliases", []):
        if isinstance(alias, str):
            raw_names.add(alias)

    # 清洗：去空、去None
    raw_names = {n.strip() for n in raw_names if n.strip() and n.strip().lower() not in ("--", "未知", "none", "")}

    # 扩展：去后缀的版本
    expanded = set(raw_names)
    for n in raw_names:
        ns = _strip_corp_suffix(n)
        if ns and ns != n:
            expanded.add(ns)

    # 全小写用于匹配
    return {n.lower() for n in expanded}


# ---------------------------------------------------------------------------
# 全库同行名称收集
# ---------------------------------------------------------------------------

def _collect_all_peer_names(peer_data):
    """从整个 peer_comps.yaml 收集同行名称（含别名）"""
    if not peer_data or not isinstance(peer_data, dict):
        return []
    names = []
    for sec_key, sec_data in peer_data.items():
        if sec_key == "meta":
            continue
        for sub_key, sub_data in sec_data.items():
            if sub_key == "meta":
                continue
            for peer in sub_data.get("peers", []):
                n = peer.get("name", "").strip()
                if n:
                    names.append(n)
                for alias in peer.get("aliases", []):
                    a = alias.strip()
                    if a:
                        names.append(a)
    return list(dict.fromkeys(names))  # 去重保序


# ---------------------------------------------------------------------------
# 竞争对手章节提取（保留大小写）
# ---------------------------------------------------------------------------

def _extract_competitor_chunks(text):
    """从招股书中提取竞争/行业格局相关文本块，保留原文大小写"""
    if not text:
        return []

    # 需要排除的章节前缀
    EXCLUDED_SECTIONS = [
        "definitions", "definition", "glossary",
        "summary of the offering", "offering summary",
        "global offering", "international offering",
        "prospectus summary", "summary",
        "directory", "index to",
        "notice to", "important notice",
    ]

    patterns = [
        (r'(?:competition|competitive\s*(?:landscape|position|advantages?|strengths?|environment|dynamics?))', "competition"),
        (r'(?:competitors?)', "competitors"),
        (r'(?:industry\s*(?:overview|structure|landscape))', "industry"),
        (r'(?:market\s*(?:share|position|opportunity))', "market_share"),
        (r'(?:行业竞争|竞争格局|市场参与者|同行业|可比公司)', "chinese_competition"),
    ]

    # 用原文（不是 lower）找位置并截取
    chunks = []
    for pat, source in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            start = max(0, m.start() - 100)
            end = min(len(text), m.end() + 5000)  # 扩大到5000字符，避免截断长竞争章节
            chunk = text[start:end]

            # 排除非目标章节：检查前后 200 字符是否包含排除词
            if any(excl in chunk[:400].lower() for excl in EXCLUDED_SECTIONS):
                continue
            # 排除封面/目录附近（文本头 3000 字符）
            if m.start() < 3000:
                skip_prefixes = ["this document", "this prospectus", "the company", "registered office",
                                 "stock code", "global offering", "number of offer shares",
                                 "joint sponsors", "joint bookrunners", "joint lead managers"]
                if any(chunk[:300].lower().startswith(p) for p in skip_prefixes):
                    continue

            if len(chunk) > 50:
                chunks.append(chunk.strip())

    # 去重：按前 80 字符去重
    seen = set()
    deduped = []
    for c in chunks:
        key = c[:80].lower()
        if key not in seen:
            seen.add(key)
            deduped.append(c)

    return deduped[:8]


# ---------------------------------------------------------------------------
# 公司名提取（保守规则）
# ---------------------------------------------------------------------------

def _has_corp_suffix(word):
    """最后一个词是否公司后缀"""
    if not word:
        return False
    parts = word.strip().split()
    if not parts:
        return False
    return parts[-1].lower() in _CORPORATE_SUFFIXES


def _is_pure_junk(name):
    """是否纯无用词/标题词"""
    lower = name.lower().strip()
    if lower in _PROSPECTUS_JUNK_WORDS:
        return True
    if lower.startswith("joint ") or lower.startswith("overall "):
        return True
    if lower in ("people's republic of china", "people republic china",
                 "the people's republic of china", "hong kong"):
        return True
    if lower.endswith(" act") or lower.endswith(" ordinance"):
        return True
    # 通用语义短语过滤
    _GENERIC_PHRASES = [
        'currently', 'existing', 'personnel', 'industry', 'position',
        'capabilities', 'recruiting', 'drugs or any new', 'employee',
        'specialist technology', 'large biopharmaceutical',
        'us in recruiting', 'development capabilities', 'allow us',
        'enable us', 'driven by', 'growing demand', 'increasing demand',
        'market is', 'market size', 'expected to', 'continue to',
        'performed well', 'strong growth', 'significant growth',
        'visual perception technology', 'robot visual perception',
        'intelligent robot visual perception', 'service robot visual',
        'robotics visual perception', 'commercial service robot',
        'biotechnology companies', 'pharmaceutical companies',
        'biopharmaceutical companies', 'drug companies',
        'medical device companies', 'healthcare companies',
    ]
    if any(phrase in lower for phrase in _GENERIC_PHRASES):
        return True
    industry_words = {
        'robot', 'robotic', 'robotics', 'visual', 'perception', 'technology',
        'technologies', 'sensor', 'sensors', 'algorithm', 'module', 'modules',
        'intelligent', 'commercial', 'service',
    }
    words = [w.strip(' ,.;:()[]').lower() for w in name.strip().split()]
    if len(words) >= 3 and len(set(words) - industry_words) == 0:
        return True
    # 英文候选超过6个单词
    if len(words) > 6:
        return True
    # 包含换行符
    if '\n' in name:
        return True
    return False


def _extract_potential_company_names(text, issuer_aliases=None):
    """从竞争章节文本中提取疑似公司名（保守规则）"""
    if not text:
        return []

    issuer_aliases = issuer_aliases or set()
    candidates = []

    # --- 规则1：带公司后缀的英文名 ---
    # 匹配 (Optional前缀) + (2-5个单词) + (公司后缀)
    for m in re.finditer(
        r'(?:[A-Z][a-z]{1,40}\s+){1,4}(?:Limited|Ltd|Inc|Corporation|Corp|PLC|AG|SA|NV|LLC|Holdings|Group|Pharma|Biotech|Therapeutics|Biosciences|Technology|Technologies|Robotics|Medical|Healthcare|Laboratories|Laboratory|Innovations?|Ventures|Capital|Partners)',
        text
    ):
        name = m.group(0).strip()
        lower = name.lower()
        # 过滤
        if len(name) < 6:
            continue
        if _is_pure_junk(name):
            continue
        if lower in issuer_aliases:
            continue
        candidate = {
            "name": name,
            "confidence": "high",
            "reason": "带公司后缀的同行候选",
            "source": "competition_text",
        }
        candidates.append(candidate)

    # --- 规则2：竞争语境中的公司名 ---
    # "competitors include A, B and C" / "compete with A" / "such as A" 等
    context_patterns = [
        r'(?:competitors?\s+(?:include|such as|like|are|comprise)\s+)([A-Z][A-Za-z\s,]+?)(?:\.|;|and\s+other)',
        r'(?:compete\s+(?:with|against)\s+)([A-Z][A-Za-z\s]+?)(?:\.|;|,|in\s+the)',
        r'(?:market\s+(?:participants?|players?)\s+(?:include|such as|like)\s+)([A-Z][A-Za-z\s,]+?)(?:\.|;|and\s+other)',
        r'(?:comparable\s+companies?\s+(?:include|such as)\s+)([A-Z][A-Za-z\s,]+?)(?:\.|;|and\s+other)',
        r'(?:peer\s+companies?\s+(?:include|such as)\s+)([A-Z][A-Za-z\s,]+?)(?:\.|;|and\s+other)',
        r'(?:主要(?:竞争对手|竞争者)[^。]{0,30}?)([A-Za-z一-鿿]{2,30}(?:科技|生物|医药|制药|医疗|机器人|智能|半导体)[^。]{0,20}?)',
        r'(?:可比(?:公司|企业)[^。]{0,30}?)([A-Za-z一-鿿]{2,30}(?:科技|生物|医药|制药|医疗|机器人|智能|半导体)[^。]{0,20}?)',
    ]
    for pat in context_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            raw = m.group(1).strip()
            # 按逗号或 "and" 分割
            parts = re.split(r'\s*[,，、]\s*|\s+and\s+', raw)
            for part in parts:
                part = part.strip()
                if not part or len(part) < 4:
                    continue
                if _is_pure_junk(part):
                    continue
                if part.lower() in issuer_aliases:
                    continue
                # 去重
                existing = {c["name"].lower() for c in candidates}
                if part.lower() in existing:
                    continue
                candidates.append({
                    "name": part,
                    "confidence": "medium",
                    "reason": "竞争语境中提及",
                    "source": "competition_context",
                })

    # --- 规则3：中文公司名 ---
    for m in re.finditer(
        r'[一-鿿]{2,20}(?:科技|生物|医药|制药|药业|医疗|集团|股份|有限|机器人|智能|半导体|基因|细胞|创新药|器械)',
        text
    ):
        name = m.group(0).strip()
        if len(name) < 3:
            continue
        if name in ("本公司", "公司", "集团公司", "股份有限公司", "有限责任公司"):
            continue
        lower = name.lower()
        if lower in issuer_aliases:
            continue
        existing = {c["name"].lower() for c in candidates}
        if lower in existing:
            continue
        # 中文候选直接当作高置信度
        candidates.append({
            "name": name,
            "confidence": "medium",
            "reason": "中文公司名匹配",
            "source": "chinese_name",
        })

    # 去重
    seen = set()
    deduped = []
    for c in candidates:
        k = c["name"].lower().strip()
        if k and k not in seen:
            seen.add(k)
            deduped.append(c)
    return deduped[:20]


# ---------------------------------------------------------------------------
# 候选过滤
# ---------------------------------------------------------------------------

def _normalize_chinese_for_matching(text):
    """将常见繁体字转换为简体字，用于中文名称匹配

    覆盖港股招股书常见繁体字（公司名/行业术语），去重后约50个映射。
    港股名称常见繁→简对照。
    """
    trad_to_simp = {
        # 医药/生物科技
        '藥': '药', '醫': '医', '療': '疗', '健': '健', '康': '康',
        '發': '发', '展': '展', '研': '研', '製': '制', '劑': '剂',
        # 企业/金融
        '務': '务', '資': '资', '產': '产', '業': '业', '財': '财',
        '銀': '银', '險': '险', '投': '投', '控': '控', '團': '团',
        # 地理/国际
        '國': '国', '際': '际', '東': '东', '無': '无', '錫': '锡',
        '華': '华', '廈': '厦', '灣': '湾', '區': '区', '歐': '欧',
        '亞': '亚', '美': '美', '洲': '洲',
        # 通用商业
        '電': '电', '風': '风', '開': '开', '質': '质', '問': '问',
        '題': '题', '場': '场', '學': '学', '體': '体', '係': '系',
        '術': '术', '網': '网', '絡': '络', '軟': '软', '設': '设',
        '備': '备', '車': '车', '機': '机', '構': '构', '導': '导',
        '圖': '图', '數': '数', '據': '据', '庫': '库', '雲': '云',
        '智': '智', '能': '能', '源': '源', '動': '动', '力': '力',
        '環': '环', '保': '保', '農': '农', '林': '林', '漁': '渔',
        '牧': '牧', '礦': '矿', '鐵': '铁', '鋼': '钢',
        # 公司后缀
        '份': '份', '限': '限', '責': '责', '任': '任', '公': '公',
        '司': '司', '有': '有',
    }
    result = []
    for ch in text:
        result.append(trad_to_simp.get(ch, ch))
    return ''.join(result)


def _filter_peer_candidates(candidates, all_peer_names, issuer_aliases):
    """严格过滤候选同行"""
    all_peer_lower = {n.strip().lower() for n in all_peer_names if n.strip()}
    junk_lower = {w.lower() for w in _PROSPECTUS_JUNK_WORDS}
    pure_suffixes = {"limited", "ltd", "inc", "corp", "corporation", "holdings", "group", "plc"}
    result = []
    seen = set()

    for c in candidates:
        name = c["name"].strip()
        lower = name.lower()

        # 排除空/过短
        if len(name) < 4:
            continue

        # 排除纯无用词/通用短语
        if _is_pure_junk(name):
            continue

        # 排除纯后缀片段：如 "Bio Limited"、"Tech Inc"（仅后缀+1个短词）
        words = lower.split()
        if len(words) <= 2 and words[-1] in pure_suffixes:
            # 排除只有 1 个词+后缀 且 前一词是短词/通用词的
            if len(words) == 1:
                continue
            if len(words) == 2 and (len(words[0]) <= 4 or words[0] in junk_lower):
                continue

        # 排除发行人别名（精确匹配）
        if lower in issuer_aliases:
            continue
        # 排除部分匹配：候选名与发行人别名有过多词重叠
        # 但排除常见行业词干扰（Tech、Bio、Medical、International 等）
        if issuer_aliases:
            candidate_words = set(words)
            industry_noise = {'tech', 'bio', 'medical', 'health', 'intl', 'international',
                              'global', 'group', 'holdings', 'corp', 'limited', 'ltd', 'inc'}
            should_skip = False
            for alias in issuer_aliases:
                alias_words = set(alias.split()) - industry_noise
                candidate_meaningful = candidate_words - industry_noise
                if not alias_words or not candidate_meaningful:
                    continue
                overlap = len(candidate_meaningful & alias_words)
                # 如果候选名的有意义词超过一半与发行人别名重叠，排除
                if overlap >= len(candidate_meaningful) / 2 and overlap > 0:
                    should_skip = True
                    break
            if should_skip:
                continue

        # 排除已在同行库里（完整匹配或子串匹配）
        if lower in all_peer_lower:
            continue
        # 排除包含已收录同行名称的候选（如"無錫藥明康德新藥開發股份有限"包含"药明康德"）
        skip_for_peer = False
        lower_normalized = _normalize_chinese_for_matching(lower)
        for peer_name in all_peer_lower:
            if peer_name in lower or lower in peer_name:
                # 要求匹配长度至少为4个字符，避免短词误过滤
                if len(peer_name) >= 4:
                    skip_for_peer = True
                    break
            # 简体化后再次匹配（处理繁体名称）
            peer_normalized = _normalize_chinese_for_matching(peer_name)
            if peer_normalized in lower_normalized or lower_normalized in peer_normalized:
                if len(peer_normalized) >= 4:
                    skip_for_peer = True
                    break
        if skip_for_peer:
            continue

        # 只保留 high / medium
        if c.get("confidence") not in ("high", "medium"):
            continue

        # 去重（大小写不敏感）
        if lower in seen:
            continue
        seen.add(lower)
        result.append(name)

    return result[:8]


def _unmatched_candidates(competitor_chunks, all_peer_names, issuer_aliases=None):
    """从竞争章节文本中提取且不在同行库/发行人名单中的候选"""
    if not competitor_chunks:
        return []
    combined = " ".join(competitor_chunks)
    raw = _extract_potential_company_names(combined, issuer_aliases=issuer_aliases)
    return _filter_peer_candidates(raw, all_peer_names, issuer_aliases or set())


# ---------------------------------------------------------------------------
# 已收录同行识别
# ---------------------------------------------------------------------------

def _find_mentioned_companies(text, competitor_chunks, subsector_data):
    if not subsector_data:
        return []
    peers = subsector_data.get("peers", [])
    mentioned = []
    combined = ((text or "") + " " + " ".join(competitor_chunks)).lower()
    seen = set()
    for peer in peers:
        name = peer.get("name", "").lower()
        ticker = peer.get("ticker", "")
        # 检查名称 + 别名
        search_names = [name]
        for alias in peer.get("aliases", []):
            search_names.append(alias.strip().lower())
        matched = False
        for sn in search_names:
            if sn in combined and sn not in seen:
                seen.add(sn)
                mentioned.append({**peer, "matched_by": "招股书明确提及"})
                matched = True
                break
        if matched:
            continue
        if not ticker or ticker == "private":
            continue
        tb = ticker.lower().replace(".hk", "")
        if tb.isdigit() and re.search(rf'(?<!\d){re.escape(tb)}(?:\.hk)?(?!\d)', combined):
            mentioned.append({**peer, "matched_by": "招股书提及代码"})
    return mentioned


# ---------------------------------------------------------------------------
# 赛道匹配（支持全局 fallback）
# ---------------------------------------------------------------------------

def _match_subsector_in_sector(sector_data, combined_text, threshold=None):
    if threshold is None:
        threshold = SETTINGS.peer_comps.match_confidence_medium
    matches = []
    for sk, sd in sector_data.items():
        if sk == "meta":
            continue
        kws = sd.get("keywords", [])
        hits = sum(1 for kw in kws if kw.lower() in combined_text)
        if hits >= threshold:
            matches.append((sk, sd, hits))
    return matches


def _extract_keywords_subsector(prospectus_info, text, peer_data=None):
    sector = prospectus_info.get("sector", "unknown")
    if peer_data is None:
        peer_data = _load_peer_data()
    if not peer_data or not isinstance(peer_data, dict):
        return "unknown", None, None, [], 0

    gics_code = prospectus_info.get("gics_industry_code") or prospectus_info.get("gics_sector_code")
    gics_sec, gics_sub = lookup_gics_subsector(gics_code)

    biz = prospectus_info.get("business_breakdown", {}) or {}
    seg_text = " ".join(s.get("name", "") for s in biz.get("segments", []))
    rnd = prospectus_info.get("rnd_pipeline", {}) or {}
    rd_text = rnd.get("pipeline_quality_label", "") or ""
    hardtech_text = " ".join([
        str(biz.get("business_model_label", "")),
        str(biz.get("segment_moat_label", "")),
        " ".join(rnd.get("hardtech_moat_reasons", []) or []),
        str(rnd.get("industry_rank", "")),
        str(rnd.get("market_size_notes", "")),
    ])
    combined = " ".join([
        text or "", seg_text, rd_text,
        hardtech_text,
        prospectus_info.get("sector", ""),
        str(biz.get("growth_source", "")),
    ]).lower()
    all_matches = []
    matched_sector = sector if sector in peer_data else None
    if matched_sector:
        matches = _match_subsector_in_sector(peer_data[matched_sector], combined)
        for sk, sd, hits in matches:
            all_matches.append((matched_sector, sk, sd, hits))
    for sec_key, sec_data in peer_data.items():
        if sec_key == "meta" or sec_key == matched_sector:
            continue
        matches = _match_subsector_in_sector(sec_data, combined)
        for sk, sd, hits in matches:
            all_matches.append((sec_key, sk, sd, hits))
    if not all_matches:
        for sec_key, sec_data in peer_data.items():
            if sec_key == "meta":
                continue
            for sk, sd in sec_data.items():
                if sk == "meta":
                    continue
                kws = sd.get("keywords", [])
                hit_count = sum(1 for kw in kws if kw.lower() in combined)
                is_core = sec_key.replace("_", " ") in combined.lower()
                if hit_count >= 2 or is_core:
                    all_matches.append((sec_key, sk, sd, hit_count))
            if all_matches:
                break

    def _gics_boost(sec, sub):
        if gics_sec and gics_sub:
            return 3 if sec == gics_sec and sub == gics_sub else 0
        return 0

    all_matches.sort(key=lambda x: x[3] + _gics_boost(x[0], x[1]), reverse=True)
    if all_matches:
        best_sec, best_sk, best_sd, best_hits = all_matches[0]
        if gics_sec and gics_sub:
            gics_sub_data = peer_data.get(gics_sec, {}).get(gics_sub)
            if gics_sub_data:
                gics_kw = gics_sub_data.get("keywords", [])
                gics_hit = sum(1 for kw in gics_kw if kw.lower() in combined)
                gics_score = gics_hit + 3
                if gics_score > best_hits:
                    return gics_sec, gics_sub, gics_sub_data, [(m[0], m[1]) for m in all_matches] + [(gics_sec, gics_sub)], gics_score
        return best_sec, best_sk, best_sd, [(m[0], m[1]) for m in all_matches], best_hits
    return "unknown", None, None, [], 0


# ---------------------------------------------------------------------------
# 中位数 / 稀缺性 / 评分
# ---------------------------------------------------------------------------

def _is_hk_peer(peer):
    """判断是否为港股同行（.HK 结尾或纯数字代码）"""
    ticker = str(peer.get("ticker", "")).strip().upper()
    if not ticker or ticker == "PRIVATE":
        return False
    return ticker.endswith(".HK") or ticker.isdigit()


def _peer_market_key(peer):
    """识别上市地市场，用于分市场同行估值。"""
    ticker = str(peer.get("ticker", "")).strip().upper()
    if not ticker or ticker == "PRIVATE" or peer.get("type") == "private":
        return "private"
    if ticker.endswith(".HK") or ticker.isdigit():
        return "hk"
    if ticker.endswith((".SH", ".SZ", ".SS")) or re.match(r"^[036]\d{5}$", ticker):
        return "a_share"
    if re.match(r"^[A-Z][A-Z0-9.-]{0,9}$", ticker):
        return "us"
    return "other"


def _peer_market_label(peer):
    return {
        "hk": "港股",
        "a_share": "A股",
        "us": "美股",
        "private": "未上市",
        "other": "其他",
    }.get(_peer_market_key(peer), "其他")


def _with_peer_market(peer):
    p = dict(peer)
    p["market_key"] = _peer_market_key(p)
    p["market"] = _peer_market_label(p)
    return p


def _is_quantitative_peer(peer):
    return (
        peer.get("type") == "listed"
        and not (peer.get("ps") is None and peer.get("pe") is None and peer.get("market_cap_hkd_million") is None)
        and peer.get("data_quality") != "low"
        and not peer.get("needs_refresh", False)
    )


def _split_peer_samples(matched_peers):
    """将 peers 分为 quantitative（可参与中位数计算）和 qualitative（仅参考）

    策略：
    - 使用全部高质量上市同行作为综合 quantitative 样本；
    - 港股/A股/美股的分市场强弱判断由 market_peer_stats 负责；
    - 只有一个可用样本时允许输出，但 quantitative_basis 标记为 single_reference。

    返回: (quantitative_peers, qualitative_peers, quantitative_basis,
           quantitative_peer_count, qualitative_peer_count)
    """
    all_listed_quant = [p for p in matched_peers if _is_quantitative_peer(p)]

    if len(all_listed_quant) >= 2:
        quantitative_peers = all_listed_quant
        quantitative_basis = "composite_listed_peers"
    elif len(all_listed_quant) == 1:
        quantitative_peers = all_listed_quant
        quantitative_basis = "single_reference"
    else:
        quantitative_peers = []
        quantitative_basis = "none"

    quantitative_keys = set()
    for p in quantitative_peers:
        quantitative_keys.add((str(p.get("ticker", "")), str(p.get("name", ""))))

    qualitative_peers = []
    for p in matched_peers:
        key = (str(p.get("ticker", "")), str(p.get("name", "")))
        if key in quantitative_keys:
            continue
        qualitative_peers.append(p)

    return quantitative_peers, qualitative_peers, quantitative_basis, len(quantitative_peers), len(qualitative_peers)


def _calc_peer_medians(peers, exclude_private=True):
    ps_v, pe_v, pb_v, mc_v = [], [], [], []
    for p in peers:
        if exclude_private and p.get("type") == "private":
            continue
        if _is_num(p.get("ps")):
            ps_v.append(p["ps"])
        if _is_num(p.get("pe")):
            pe_v.append(p["pe"])
        if _is_num(p.get("pb")):
            pb_v.append(p["pb"])
        if _is_num(p.get("market_cap_hkd_million")):
            mc_v.append(p["market_cap_hkd_million"])
    return {
        "peer_median_ps": round(median(ps_v), 2) if len(ps_v) >= 2 else (ps_v[0] if ps_v else None),
        "peer_median_ps_is_median": len(ps_v) >= 2,
        "peer_median_pe": round(median(pe_v), 2) if len(pe_v) >= 2 else (pe_v[0] if pe_v else None),
        "peer_median_pe_is_median": len(pe_v) >= 2,
        "peer_median_pb": round(median(pb_v), 2) if len(pb_v) >= 2 else (pb_v[0] if pb_v else None),
        "peer_median_pb_is_median": len(pb_v) >= 2,
        "peer_median_market_cap": round(median(mc_v), 2) if len(mc_v) >= 2 else (mc_v[0] if mc_v else None),
        "peer_median_market_cap_is_median": len(mc_v) >= 2,
        "peer_ps_count": len(ps_v),
        "peer_pe_count": len(pe_v),
        "peer_pb_count": len(pb_v),
        "peer_market_cap_count": len(mc_v),
    }


def _calc_company_market_cap_metric(company_mc, peer_median_mc):
    """市值对比：当 PS/PE 不可用时，提供市值相对大小作为参考"""
    if not _is_num(company_mc) or not _is_num(peer_median_mc) or peer_median_mc <= 0:
        return None
    return round(company_mc / peer_median_mc * 100, 1)


def _calc_market_peer_stats(quantitative_peers, company_ps, company_pe, company_pb, scarcity):
    market_order = ("hk", "a_share", "us", "other")
    grouped = {k: [] for k in market_order}
    for peer in quantitative_peers:
        key = _peer_market_key(peer)
        if key == "private":
            continue
        grouped.setdefault(key if key in grouped else "other", []).append(_with_peer_market(peer))

    stats = {}
    for key in market_order:
        peers = grouped.get(key, [])
        medians = _calc_peer_medians(peers)
        ps_median = medians["peer_median_ps"]
        pe_median = medians["peer_median_pe"]
        pb_median = medians["peer_median_pb"]
        ps_premium = None
        pe_premium = None
        pb_premium = None
        if _is_num(company_ps) and _is_num(ps_median) and ps_median > 0:
            ps_premium = round((company_ps - ps_median) / ps_median * 100, 1)
        if _is_num(company_pe) and _is_num(pe_median) and pe_median > 0:
            pe_premium = round((company_pe - pe_median) / pe_median * 100, 1)
        if _is_num(company_pb) and _is_num(pb_median) and pb_median > 0:
            pb_premium = round((company_pb - pb_median) / pb_median * 100, 1)

        if len(peers) >= 2:
            position = _calc_valuation_position(company_ps, ps_median, scarcity, ps_premium)
        elif len(peers) == 1:
            position = "单一样本参考"
        else:
            position = "样本不足，仅作定性参考"

        stats[key] = {
            "market": {"hk": "港股", "a_share": "A股", "us": "美股", "other": "其他"}[key],
            "peer_count": len(peers),
            "peer_median_ps": ps_median,
            "peer_median_pe": pe_median,
            "peer_median_pb": pb_median,
            "peer_ps_count": medians["peer_ps_count"],
            "peer_pe_count": medians["peer_pe_count"],
            "peer_pb_count": medians["peer_pb_count"],
            "relative_ps_premium_pct": ps_premium,
            "relative_pe_premium_pct": pe_premium,
            "relative_pb_premium_pct": pb_premium,
            "valuation_position": position,
            "peers": peers,
        }
    return stats


def _market_position_bucket(position):
    position = str(position or "")
    if "明显偏贵" in position or "偏贵" in position:
        return "expensive"
    if "相对低估" in position:
        return "cheap"
    if "合理" in position:
        return "fair"
    return None


def _financial_fx_to_hkd(currency):
    currency = str(currency or "RMB").upper().strip()
    if currency in ("RMB", "CNY", "CNH"):
        return SETTINGS.fx.rmb_to_hkd
    if currency == "USD":
        return SETTINGS.fx.usd_to_hkd
    return 1.0


def _calc_company_valuation_metrics(prospectus_info):
    valuation = prospectus_info.get("valuation", {}) or {}
    company_ps = valuation.get("ps_ratio")
    company_pe = valuation.get("pe_ratio") or valuation.get("adjusted_pe_ratio")
    company_pb = valuation.get("pb_ratio")

    mc = prospectus_info.get("market_cap_hkd_million")
    fx = _financial_fx_to_hkd(prospectus_info.get("financial_currency", "RMB"))
    revenue_hkd = None
    profit_hkd = None
    revenue = prospectus_info.get("revenue")
    net_profit = prospectus_info.get("net_profit")
    if _is_num(revenue):
        revenue_hkd = revenue * fx
    if _is_num(net_profit):
        profit_hkd = net_profit * fx

    if company_ps is None and _is_num(mc) and _is_num(revenue_hkd) and revenue_hkd > 0:
        company_ps = round(mc / revenue_hkd, 2)
    if company_pe is None and _is_num(mc) and _is_num(profit_hkd) and profit_hkd > 0:
        company_pe = round(mc / profit_hkd, 2)
    return company_ps, company_pe, company_pb


def _calc_scarcity_score(prospectus_info, matched_peers, sector):
    """稀缺性评分：衡量市场上同类公司的稀缺程度（与 _calc_peer_score 的行业加分互补）

    _calc_peer_score 的行业加分反映行业投资吸引力，
    此处的行业加分仅反映该行业在港股上市公司数量稀少的程度。
    """
    score = 0
    rnd = prospectus_info.get("rnd_pipeline", {}) or {}
    ca = prospectus_info.get("cornerstone_analysis", {}) or {}

    # --- 维度1: 港股同行数量（最高+2）---
    listed = [p for p in matched_peers if p.get("type") == "listed"]
    if len(listed) <= 2:
        score += 2
    elif len(listed) <= 4:
        score += 1

    # --- 维度2: 技术壁垒（最高+2）---
    moat = rnd.get("technology_moat_score", 0)
    if moat >= 7:
        score += 2
    elif moat >= 5:
        score += 1

    # --- 维度3: 基石投资者质量（最高+2）---
    cornerstone_rows = ca.get("cornerstone_investors") or []
    tiers = {row.get("tier", "") for row in cornerstone_rows if row.get("tier")}
    if not tiers:
        matched_inv = ca.get("matched_investors", [])
        tiers = {m.get("tier", "") for m in matched_inv if m.get("tier")}
    if "S" in tiers:
        score += 2
    elif "A" in tiers:
        score += 1

    # --- 维度4: 营收增长（最高+1）---
    rev = prospectus_info.get("revenue")
    rev_y1 = prospectus_info.get("revenue_y1")
    if _is_num(rev) and _is_num(rev_y1) and rev_y1 > 0:
        g = (rev - rev_y1) / rev_y1
        if g > 1.0:
            score += 1
        elif g > 0.5:
            score += 0.5

    # --- 新增维度5: 市场份额/行业地位（最高+3）---
    market_share = prospectus_info.get("market_share_data") or []
    dominant_pct = prospectus_info.get("dominant_share_pct")
    dominant_rank = None
    if market_share:
        for ms in market_share:
            if ms.get("rank") is not None and ms.get("share_pct") is not None:
                if dominant_rank is None or ms["rank"] < dominant_rank:
                    dominant_rank = ms["rank"]

    if dominant_rank is not None:
        if dominant_rank == 1:
            score += 3
        elif dominant_rank <= 3:
            score += 2
        else:
            score += 1
    elif _is_num(dominant_pct) and dominant_pct > 10:
        if dominant_pct > 30:
            score += 3
        elif dominant_pct > 15:
            score += 2
        else:
            score += 1

    # --- 新增维度6: 相对市场地位（同行收入排名，最高+2）---
    rmp = prospectus_info.get("relative_market_position") or {}
    rmp_rank = rmp.get("rank")
    rmp_peer_count = rmp.get("peer_count", 0)
    if rmp_rank is not None and rmp_peer_count >= 3:
        if rmp_rank == 1:
            score += 2
        elif rmp_rank <= 2:
            score += 1

    # --- 新增维度7: 行业集中度（最高+1）---
    conc = prospectus_info.get("market_concentration") or {}
    cr3 = conc.get("cr3_pct")
    if _is_num(cr3) and cr3 >= 60:
        score += 1

    # 医疗赛道港股上市公司较少，适度加分
    if sector == "healthcare":
        score += 1

    return min(10, score)


def _calc_peer_score(scarcity, relative_premium, revenue, revenue_y1, sector):
    pt = SETTINGS.peer_comps
    score = min(5, scarcity)
    if relative_premium is not None:
        if relative_premium < pt.premium_fair:
            score += 5
        elif relative_premium < -10:
            score += 4
        elif relative_premium < 10:
            score += 3
        elif relative_premium < pt.premium_high:
            score += 1
        else:
            pass  # 高溢价不加分

    if _is_num(revenue) and _is_num(revenue_y1) and revenue_y1 > 0:
        g = (revenue - revenue_y1) / revenue_y1
        if g > 1.0:
            score += 3
        elif g > 0.5:
            score += 2
        elif g > 0.3:
            score += 1

    if sector == "healthcare":
        score += 2
    elif sector == "hardtech":
        score += 1

    score = min(15, score)

    if relative_premium is not None:
        if relative_premium > pt.premium_overpriced:
            score = min(score, 5)
        elif relative_premium > pt.premium_high:
            score = min(score, 7)

    return score


def _calc_valuation_position(company_ps, peer_median_ps, scarcity, premium):
    pt = SETTINGS.peer_comps
    if not _is_num(company_ps) or not _is_num(peer_median_ps) or peer_median_ps <= 0:
        return "偏高但稀缺赛道" if scarcity >= 7 else "缺失"
    if premium is not None:
        if premium > pt.premium_overpriced:
            return "明显偏贵"
        if premium > pt.premium_expensive:
            return "偏贵但可解释" if scarcity >= 5 else "偏贵"
        if premium > pt.premium_fair:
            return "合理"
        return "相对低估"
    return "缺失"


def _calc_business_line_weighted_peer_ps(prospectus_info, matched_peers, subsector_key):
    """For mixed robotics issuers, value perception and mower lines separately."""
    if subsector_key not in ("robotics_visual_perception", "robotics_factory_automation"):
        return None
    biz = prospectus_info.get("business_breakdown") or {}
    segments = biz.get("segments") or []
    if not segments:
        return None

    groups = {
        "robot_body": {
            "label": "机器人本体",
            "segment_keywords": ("robot body", "industrial robot", "scara", "six-axis", "parallel robot", "wafer handling", "机器人本体", "工业机器人"),
            "peer_tags": ("industrial robot", "robot body", "robotics", "automation", "cobot"),
        },
        "robot_solution": {
            "label": "机器人解决方案",
            "segment_keywords": ("robotic solution", "automation system", "agv", "amr", "factory automation", "机器人解决方案", "自动化系统", "移动机器人"),
            "peer_tags": ("automation", "system integration", "agv", "amr", "robotics"),
        },
        "robot_component": {
            "label": "关键部件",
            "segment_keywords": ("controller", "vision system", "control", "控制器", "视觉系统"),
            "peer_tags": ("controller", "vision", "sensor", "sensing", "automation"),
        },
    }
    if subsector_key == "robotics_visual_perception":
        groups = {
            "visual_perception": {
                "label": "视觉感知业务",
                "segment_keywords": ("visual", "perception", "sensor", "algorithm"),
                "peer_tags": ("lidar", "perception", "sensor"),
            },
            "robot_lawn_mower": {
                "label": "割草机器人业务",
                "segment_keywords": ("lawn", "mower"),
                "peer_tags": ("mower", "cleaning robot", "smart home"),
            },
        }

    details = []
    weighted_sum = 0.0
    weight_total = 0.0
    for group_key, cfg in groups.items():
        share = 0.0
        matched_segment_names = []
        for seg in segments:
            name = str(seg.get("name") or "").lower()
            if any(kw in name for kw in cfg["segment_keywords"]):
                seg_share = seg.get("share_pct")
                if _is_num(seg_share):
                    share += float(seg_share)
                    matched_segment_names.append(seg.get("name"))
        if share <= 0:
            continue

        peer_ps_values = []
        peer_names = []
        for peer in matched_peers:
            if peer.get("type") != "listed" or not _is_num(peer.get("ps")):
                continue
            tags = {str(t).lower() for t in peer.get("tags", [])}
            if tags & {t.lower() for t in cfg["peer_tags"]}:
                peer_ps_values.append(float(peer["ps"]))
                peer_names.append(peer.get("name"))
        if not peer_ps_values:
            continue
        group_median = round(median(peer_ps_values), 2) if len(peer_ps_values) >= 2 else round(peer_ps_values[0], 2)
        if len(peer_ps_values) >= 2:
            weighted_sum += group_median * share
            weight_total += share
        details.append({
            "group": group_key,
            "label": cfg["label"],
            "share_pct": round(share, 1),
            "peer_median_ps": group_median,
            "peer_count": len(peer_ps_values),
            "single_sample": len(peer_ps_values) < 2,
            "peer_names": peer_names[:6],
            "segment_names": matched_segment_names[:6],
        })

    if not details or weight_total <= 0:
        return None
    weighted_peer_ps = round(weighted_sum / weight_total, 2)
    return {
        "weighted_peer_ps": weighted_peer_ps,
        "business_line_peer_valuation": details,
    }


def _build_summary(vp, subsector_key, matched_peers, company_ps, peer_median_ps, peer_median_pe, company_pe):
    if vp == "缺失":
        return "无足够同行数据，无法进行相对估值判断"
    listed = sum(1 for p in matched_peers if p.get("type") == "listed")
    parts = [f"细分赛道: {subsector_key}" if subsector_key else "细分赛道: 未明确"]
    parts.append(f"匹配{listed}家已上市同行")
    if _is_num(company_ps) and _is_num(peer_median_ps):
        prem = (company_ps - peer_median_ps) / peer_median_ps * 100
        parts.append(f"PS: {company_ps:.1f}x vs 同行中位数 {peer_median_ps:.1f}x ({prem:+.0f}%)")
    m = {
        "明显偏贵": "相对同行估值偏高",
        "偏贵但可解释": "相对同行偏高但有稀缺性/成长性支撑",
        "偏贵": "相对同行估值偏高",
        "合理": "相对同行估值合理",
        "相对低估": "相对同行可能低估",
        "偏高但稀缺赛道": "绝对值高但赛道稀缺",
    }
    parts.append(m.get(vp, vp))
    return "；".join(parts)


def _best_hits_to_confidence(best_hits):
    pt = SETTINGS.peer_comps
    if best_hits >= pt.match_confidence_high:
        return "high"
    if best_hits >= pt.match_confidence_medium:
        return "medium"
    if best_hits == 1:
        return "low"
    return "none"


# ---------------------------------------------------------------------------
# PeerComparableAnalyzer
# ---------------------------------------------------------------------------

class PeerComparableAnalyzer:
    """同行对比与相对估值分析器"""

    def __init__(self, peer_data_path=None):
        raw = _load_peer_data(peer_data_path)
        self.peer_data = raw
        self.meta = _build_peer_meta(raw) if raw else {}
        self._all_peer_names = None

    @property
    def all_peer_names(self):
        if self._all_peer_names is None:
            self._all_peer_names = _collect_all_peer_names(self.peer_data)
        return self._all_peer_names

    def _extract_market_share_data(self, text):
        if not text:
            return []
        # 规范化: PDF提取常在中文字符间插入换行
        text = re.sub(r'(?<=[\u4e00-\u9fff])\s*\n\s*(?=[\u4e00-\u9fff，。、；：])', '', text)
        logger.debug("_extract_market_share_data: text_len=%d", len(text))
        results = []
        seen_segments = set()

        def _find_segment(context, lang="en"):
            """从上下文中提取细分市场/行业名称"""
            # 优先尝试: 中文 "在X市场/行业/领域"
            zh_pat = re.search(
                r'(?:在|於|于)'
                r'([A-Za-z0-9\u4e00-\u9fff（）()、及與与\-\s]{2,50}?)'
                r'(?:市[場场]|行[業业]|領域|领域)',
                context,
            )
            if zh_pat:
                return re.sub(r'\s+', '', zh_pat.group(1)).strip("，。；：、 ")
            # 英文 "in the X market/sector"
            seg_pat = re.search(
                r'(?:in\s+the\s+|of\s+the\s+|within\s+the\s+|across\s+the\s+)'
                r'([\w\u4e00-\u9fff\s]{2,40}?)(?:\s+market|市[場场]|行[業业]|sector|segment|industry)',
                context, re.IGNORECASE,
            )
            if seg_pat:
                return seg_pat.group(1).strip()
            # 从 "全球消费级3D打印机市场" 等直接提取，保留数字/空格打断的英文缩写
            direct_zh_matches = re.findall(
                r'((?:全球|中國|中国|香港|亞洲|亚洲|亞太|亚太|國內|国内)?'
                r'[A-Za-z0-9\u4e00-\u9fff（）()、及與与\-\s]{2,50}?)'
                r'(?:市[場场]|行[業业]|領域|领域)',
                context,
            )
            direct_zh_matches = [
                re.sub(r'\s+', '', name).strip("，。；：、的之")
                for name in direct_zh_matches
            ]
            direct_zh_matches = [
                name for name in direct_zh_matches
                if name and name not in ("整个", "全球", "中国", "国内", "海外", "该", "此", "本", "其")
                and not name.endswith(("佔有率", "占有率", "份額", "份额"))
            ]
            if direct_zh_matches:
                name = max(direct_zh_matches, key=len)
                metric_segment = re.findall(
                    r'\d{4}年([A-Za-z0-9\u4e00-\u9fff（）()、及與与\-\s]{2,30}?)(?:GMV|收益|收入)',
                    name,
                )
                if metric_segment:
                    name = metric_segment[-1]
                region = re.search(r'(全球|中國|中国|香港|亞洲|亚洲|亞太|亚太|國內|国内).+', name)
                if region:
                    name = region.group(0)
                if len(name) > 30:
                    name = name[-30:]
                    name = re.sub(r'^.*?[，。；：]', '', name)
                if name and name not in ("整个", "全球", "中国", "国内", "海外", "该", "此", "本", "其"):
                    return name
            # 新增: 从 "X market/industry" 直接提取
            direct_en = re.search(
                r'\b([A-Z][a-z]+(?:\s+[A-Z]?[a-z]+)*)\s+(?:market|industry|sector)\b',
                context,
            )
            if direct_en:
                return direct_en.group(1).strip()
            return "unknown"

        def _find_source(context):
            if re.search(r'frost\s*&\s*sullivan', context, re.IGNORECASE):
                return "Frost & Sullivan"
            if re.search(r'弗若斯特(?:沙利文|利文)', context):
                return "Frost & Sullivan"
            if re.search(r'IDC|Gartner|灼识|沙利文', context, re.IGNORECASE):
                m = re.search(r'(IDC|Gartner|灼识(?:咨询)?|沙利文)', context)
                return m.group(1) if m else None
            return None

        def _add_share_result(segment, share_pct, rank=None, source=None):
            key = (segment.lower(), share_pct, rank)
            if key not in seen_segments:
                seen_segments.add(key)
                results.append({
                    "segment": segment,
                    "share_pct": share_pct,
                    "rank": rank,
                    "source": source,
                })

        def _merge_or_add(segment, share_pct=None, rank=None, source=None):
            """尝试合并到已有同 segment+同share_pct 记录，否则新增"""
            for r_item in results:
                if r_item["segment"].lower() == segment.lower():
                    # 相同 share_pct 或 rank 时合并；不同份额则独立新增
                    same_share = (share_pct is not None and r_item["share_pct"] is not None
                                  and abs(r_item["share_pct"] - share_pct) < 0.01)
                    same_rank = (rank is not None and r_item["rank"] is not None
                                 and r_item["rank"] == rank)
                    if same_share or same_rank:
                        if share_pct is not None and r_item["share_pct"] is None:
                            r_item["share_pct"] = share_pct
                        if rank is not None and r_item["rank"] is None:
                            r_item["rank"] = rank
                        if source and not r_item["source"]:
                            r_item["source"] = source
                        return
                    # 如果既有 share_pct 又有 rank，且两者都匹配才合并
                    if share_pct is not None and rank is not None:
                        if same_share and same_rank:
                            if source and not r_item["source"]:
                                r_item["source"] = source
                            return
                    # 都不匹配 → 继续查找，都不匹配则 fall through 到新增
            _add_share_result(segment, share_pct, rank, source)

        # --- 市占率百分比模式 ---
        share_patterns = [
            # 原有英文模式
            r'(?:market\s+share\s+(?:of|was|is|at|reached)|accounted\s+for)\s+(?:approximately\s+|about\s+|around\s+)?([\d.]+)\s*%',
            # 繁体+简体: "市占率为X%" / "市場佔有率為X%" / 缩写 "市占率X%"
            r'(?:市[場场]?[占佔]有率|市[占佔]率|[市市]场占有率)\s*(?:約|约|約為|约为|達到|达到|為|为)?\s*([\d.]+)\s*%',
            # 繁体+简体: "市场份额为X%" / "市場份額為X%"
            r'(?:市[場场]份[额額]|[市市]场份额)\s*(?:約|约|約為|约为|達到|达到|為|为|为约)?\s*([\d.]+)\s*%',
            # 新增: "holds/approximately X% of the market"
            r'(?:holds?|had|has|with)\s+(?:approximately\s+|about\s+|around\s+)?([\d.]+)\s*%\s*(?:of\s+the\s+|market)',
            # 新增: "X% market share"
            r'([\d.]+)\s*%\s+market\s+share',
            # 新增: "占/佔市场份额约X%"
            r'[占佔]\s*(?:了\s*)?(?:其\s*)?(?:市[場场]|行業|行业)\s*(?:份[额額]|市場)\s*(?:約|约|約為|约为|達到|达到|為|为|的)?\s*([\d.]+)\s*%',
            # 新增: "市场占有率为X%" / "市場佔有率為X%"
            r'(?:市[場场][占佔]有率|市[占佔]率|[市市]场占有率)\s*(?:約|约|約為|约为|達到|达到|為|为)?\s*([\d.]+)\s*%',
            # 新增: "X%的市场份额/占有率"
            r'([\d.]+)\s*%\s*(?:的\s*)?(?:市场\s*)?(?:份[额額]|占[有率]|佔有率|占有率)',
            # 新增: "占据X%" / "佔據X%"
            r'[占佔][据據]?\s*(?:了\s*)?([\d.]+)\s*%',
            # 新增: "representing/approximately X%"
            r'(?:representing|constituting|comprising)\s+(?:approximately\s+)?([\d.]+)\s*%',
        ]
        for pat in share_patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                try:
                    share_pct = float(m.group(1))
                except (ValueError, IndexError):
                    continue
                if share_pct > 100:
                    continue
                start = max(0, m.start() - 200)
                end = min(len(text), m.end() + 100)
                context = text[start:end]
                segment = _find_segment(context)
                source = _find_source(context)
                _merge_or_add(segment, share_pct=share_pct, source=source)

        # --- 排名模式 ---
        rank_patterns = [
            (r'ranked\s+(\d+)(?:st|nd|rd|th)\s+in', "en"),
            (r'排名第\s*(\d+)', "zh"),
            # 新增: "the Nth largest"
            (r'the\s+(\d+)(?:st|nd|rd|th)\s+largest', "en"),
            # 新增: "第N大"
            (r'第\s*(\d+)\s*大', "zh"),
            # 新增: "one of the leading / among the top N"
            (r'among\s+the\s+top\s+(\d+)', "en"),
            (r'top\s+(\d+)\s+(?:player|provider|company|participant)', "en"),
            # 新增: 繁体/简体 "全球第N大"
            (r'全球第\s*(\d+)\s*[大]', "zh"),
        ]
        for pat, lang in rank_patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                try:
                    rank = int(m.group(1))
                except (ValueError, IndexError):
                    continue
                if rank > 100:
                    continue
                start = max(0, m.start() - 200)
                end = min(len(text), m.end() + 100)
                context = text[start:end]
                segment = _find_segment(context, lang)
                source = _find_source(context)
                _merge_or_add(segment, rank=rank, source=source)

        # --- "领先/leading" 定性描述 ---
        leading_patterns = [
            (r'(?:one\s+of\s+)?(?:the\s+)?(?:leading|largest|dominant|major)\s+'
             r'(?:player|provider|company|participant|operator)s?\s+in\s+the\s+'
             r'([\w\u4e00-\u9fff\s]{2,40}?)(?:\s+market|行业|市场|sector|segment|industry)', "en"),
            (r'(?:是|作為)\s*(?:中國|全球|國内|国内|亞太|亚太|亞洲|亚洲)?\s*(?:領先|领先|最大|主要|龍頭|龙头|頭部|头部)\s*的\s*'
             r'([\u4e00-\u9fff]{2,30}?)(?:公司|企業|企业|廠商|厂商|供應商|供应商|服務商|服务商|運營商|运营商|參與者|参与者)', "zh"),
        ]
        for pat, lang in leading_patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                segment = m.group(1).strip()
                if len(segment) < 2:
                    continue
                start = max(0, m.start() - 200)
                end = min(len(text), m.end() + 100)
                context = text[start:end]
                source = _find_source(context)
                _merge_or_add(segment, rank=1, source=source)

        logger.debug("_extract_market_share_data: found %d results", len(results))
        return results

    def _extract_market_size_data(self, text):
        if not text:
            return []
        results = []
        seen_segments = set()
        size_patterns = [
            r'market\s+size[^.]*?(?:RMB|HKD|USD)\s*([\d,]+\.?\d*)\s*(?:billion|million|bn|m)\b',
            r'市场规模[^.]*?(?:人民币|港币|美元|RMB|HKD|USD)\s*([\d,]+\.?\d*)\s*(?:亿|万亿|十亿|百万|billion|million)\b',
        ]
        for pat in size_patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                raw_num = m.group(1).replace(",", "")
                try:
                    num_val = float(raw_num)
                except (ValueError, IndexError):
                    continue
                start = max(0, m.start() - 150)
                end = min(len(text), m.end() + 50)
                context = text[start:end]
                unit_mult = 1.0
                if re.search(r'billion|bn|十亿', context, re.IGNORECASE):
                    unit_mult = 1000.0  # billion/十亿 = 1000 million
                elif re.search(r'亿(?![十百千万])', context, re.IGNORECASE):
                    unit_mult = 100.0   # 1亿 = 100 million
                elif re.search(r'million', context, re.IGNORECASE):
                    unit_mult = 1.0
                size_million = num_val * unit_mult
                segment = "unknown"
                seg_pat = re.search(
                    r'(?:in\s+the\s+|of\s+the\s+|在|)([\w\u4e00-\u9fff\s]{2,40}?)(?:\s+market|市场|行业|sector|segment)',
                    context, re.IGNORECASE,
                )
                if seg_pat:
                    segment = seg_pat.group(1).strip()
                source = None
                if re.search(r'frost\s*&\s*sullivan', context, re.IGNORECASE):
                    source = "Frost & Sullivan"
                key = (segment.lower(), size_million)
                if key not in seen_segments:
                    seen_segments.add(key)
                    results.append({
                        "segment": segment,
                        "size_2025_million": size_million,
                        "cagr_pct": None,
                        "source": source,
                    })
        cagr_patterns = [
            r'CAGR[^.]*?([\d.]+)\s*%',
            r'复合年增长率[^.]*?([\d.]+)\s*%',
            r'年复合增长率[^.]*?([\d.]+)\s*%',
        ]
        for pat in cagr_patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                try:
                    cagr_val = float(m.group(1))
                except (ValueError, IndexError):
                    continue
                start = max(0, m.start() - 150)
                end = min(len(text), m.end() + 50)
                context = text[start:end]
                segment = "unknown"
                seg_pat = re.search(
                    r'(?:in\s+the\s+|of\s+the\s+|在|)([\w\u4e00-\u9fff\s]{2,40}?)(?:\s+market|市场|行业|sector|segment)',
                    context, re.IGNORECASE,
                )
                if seg_pat:
                    segment = seg_pat.group(1).strip()
                source = None
                if re.search(r'frost\s*&\s*sullivan', context, re.IGNORECASE):
                    source = "Frost & Sullivan"
                matched = False
                for r_item in results:
                    if r_item["segment"].lower() == segment.lower() and r_item["cagr_pct"] is None:
                        r_item["cagr_pct"] = cagr_val
                        if source and not r_item["source"]:
                            r_item["source"] = source
                        matched = True
                        break
                if not matched:
                    key = (segment.lower(), cagr_val)
                    if key not in seen_segments:
                        seen_segments.add(key)
                        results.append({
                            "segment": segment,
                            "size_2025_million": None,
                            "cagr_pct": cagr_val,
                            "source": source,
                        })
        return results

    def _extract_market_concentration(self, text):
        """提取行业集中度数据 (CR3/CR5/前N大参与者合计份额)

        返回: {"cr3_pct": float|None, "cr5_pct": float|None, "top_n_share": list[dict]}
        """
        if not text:
            return {"cr3_pct": None, "cr5_pct": None, "top_n_share": []}

        # 规范化: PDF提取的中文文本中常有换行符插入，先合并
        text_norm = re.sub(r'(?<=[\u4e00-\u9fff])\s*\n\s*(?=[\u4e00-\u9fff，。、；：])', '', text)

        top_n_share = []
        seen = set()

        # 中文数字 → 阿拉伯数字映射
        _CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
                    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

        def _parse_n(s):
            """解析中文或阿拉伯数字"""
            try:
                return int(s)
            except ValueError:
                return _CN_NUM.get(s)

        def _add_top_n(n, pct):
            if n is None:
                return
            key = (n, pct)
            if key not in seen and 1 <= n <= 20 and 0 < pct <= 100:
                seen.add(key)
                top_n_share.append({"top_n": n, "combined_share_pct": pct})

        # "the top N players/companies account for X%"
        cr_en_patterns = [
            r'(?:the\s+)?top\s+(\d+)\s+(?:player|company|participant|competitor|provider|operator)s?\s+'
            r'(?:account(?:ed)?\s+for|represent|comprising|held|had|with)\s+'
            r'(?:approximately\s+|about\s+|around\s+)?([\d.]+)\s*%',
            r'(?:the\s+)?(\d+)\s+(?:largest|leading)\s+(?:player|company|participant)s?\s+'
            r'(?:account(?:ed)?\s+for|represent)\s+(?:approximately\s+)?([\d.]+)\s*%',
            r'(?:top|leading)\s+(\d+)\s+.*?(?:合计|总共|共)\s*(?:占|占据)\s*([\d.]+)\s*%',
        ]
        for pat in cr_en_patterns:
            for m in re.finditer(pat, text_norm, re.IGNORECASE):
                try:
                    n = int(m.group(1))
                    pct = float(m.group(2))
                except (ValueError, IndexError):
                    continue
                _add_top_n(n, pct)

        # 中文: "前N大/前N名 合计占 X%" (支持简体+繁体+中文数字)
        cr_zh_patterns = [
            # (pattern, is_one_group) - True 表示只有1个捕获组(pct)，N隐含为1
            (r'最大\s*(?:參與者|参与者)\s*(?:佔據|占据|佔|占)\s*(?:總|总)?\s*(?:GMV\s*)?(?:超過|超过)?\s*(?:了\s*)?(?:約|约)?\s*([\d.]+)\s*%', True),
            # 标准双组模式: (N, pct)
            (r'前\s*([\d一二三四五六七八九十]+)\s*(?:大|名|位|家|強)\s*(?:參與者|参与者|公司|企業|企业|廠商|厂商|供應商|供应商)?\s*(?:合計|合计|總共|总共|共|累計|累计)?\s*'
             r'(?:[占佔]|佔據|占据|擁有|拥有)\s*(?:了\s*)?(?:超過|超过\s*)?(?:其\s*)?(?:市場\s*份额|市场\s*份額|市場\s*份額|市场\s*份额)?\s*(?:的\s*)?(?:約|约|約為|约为|達到|达到|為|为)?\s*([\d.]+)\s*%', False),
            (r'前\s*([\d一二三四五六七八九十]+)\s*(?:大|名|位|家)\s*.*?(?:市場份额|市场份額|占有率|佔有率)\s*(?:合計|合计|總共|总共|共)?\s*(?:為|为|達到|达到|約|约)?\s*([\d.]+)\s*%', False),
            (r'(?:其餘|其余|而其餘|而其餘的)\s*(?:前\s*([\d一二三四五六七八九十]+)\s*[大名家]?\s*[參与参與与]與?者?)\s*(?:各[占佔]|各佔)\s*(?:約|约)?\s*([\d.]+)\s*%', False),
            (r'前\s*([\d一二三四五六七八九十]+)\s*[大名家位]\s*(?:參與者|参与者)\s*各\s*[占佔]\s*(?:約|约)?\s*([\d.]+)\s*%', False),
        ]
        for pat, is_one_group in cr_zh_patterns:
            for m in re.finditer(pat, text_norm, re.IGNORECASE):
                is_each = bool(re.search(r'各\s*[占佔]', m.group(0)))
                try:
                    if is_one_group:
                        n = 1
                        pct = float(m.group(1))
                    else:
                        n = _parse_n(m.group(1))
                        pct = float(m.group(2))
                except (ValueError, IndexError):
                    continue
                if n is None:
                    continue
                if is_each:
                    continue
                _add_top_n(n, pct)

        # CR3/CR5 专用
        cr_cr_patterns = [
            r'CR(\d+)\s*(?:=|：|:|为|达到|约|约为)?\s*([\d.]+)\s*%',
            r'(?:concentration\s+ratio|集中度)\s*(?:CR)?(\d+)\s*(?:=|：|:|is|was|at)?\s*([\d.]+)\s*%',
        ]
        for pat in cr_cr_patterns:
            for m in re.finditer(pat, text_norm, re.IGNORECASE):
                try:
                    n = int(m.group(1))
                    pct = float(m.group(2))
                except (ValueError, IndexError):
                    continue
                key = (n, pct)
                if key not in seen and n in (3, 5) and 0 < pct <= 100:
                    seen.add(key)
                    top_n_share.append({"top_n": n, "combined_share_pct": pct})

        cr3_pct = None
        cr5_pct = None
        for item in top_n_share:
            if item["top_n"] == 3 and cr3_pct is None:
                cr3_pct = item["combined_share_pct"]
            if item["top_n"] == 5 and cr5_pct is None:
                cr5_pct = item["combined_share_pct"]

        return {"cr3_pct": cr3_pct, "cr5_pct": cr5_pct, "top_n_share": top_n_share}

    def _extract_competitive_landscape_via_llm(self, text):
        """用 LLM 从竞争格局段落提取结构化市场份额数据。

        返回: list[dict] 每项包含 segment, company, share_pct, rank, source
        """
        try:
            import httpx as _httpx
        except ImportError:
            return []

        api_key = os.environ.get('LLM_API_KEY', '')
        if not api_key:
            return []

        # 从全文中截取竞争格局相关段落
        chunks = _extract_competitor_chunks(text)
        if not chunks:
            return []
        # 合并去重，限制长度
        combined = "\n---\n".join(chunks)
        if len(combined) > 6000:
            combined = combined[:6000]

        base_url = os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
        model = os.environ.get('LLM_MODEL', 'gpt-4o-mini')

        system_prompt = (
            "你是港股IPO分析师。从招股书竞争格局文本中提取市场份额数据。"
            "只输出JSON数组，不要其他内容。每项格式："
            '{"segment":"细分市场名","company":"公司名","share_pct":数字,"rank":数字或null,"source":"数据来源或null"}'
            "\n如果文本中没有具体份额数据，输出空数组 []"
        )
        user_prompt = f"请从以下招股书竞争格局文本中提取所有公司/参与者的市场份额数据：\n\n{combined}"

        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 1500,
        }

        try:
            with _httpx.Client(timeout=30.0) as client:
                resp = client.post(url, headers=headers, json=body)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"].strip()
                # 提取 JSON 数组
                json_match = re.search(r'\[.*\]', content, re.DOTALL)
                if json_match:
                    import json
                    parsed = json.loads(json_match.group())
                    if isinstance(parsed, list):
                        # 过滤合理数据
                        valid = []
                        for item in parsed[:20]:
                            if not isinstance(item, dict):
                                continue
                            sp = item.get("share_pct")
                            if sp is not None:
                                try:
                                    sp = float(sp)
                                    if sp > 100 or sp < 0:
                                        sp = None
                                except (ValueError, TypeError):
                                    sp = None
                            rk = item.get("rank")
                            if rk is not None:
                                try:
                                    rk = int(rk)
                                    if rk > 100 or rk < 1:
                                        rk = None
                                except (ValueError, TypeError):
                                    rk = None
                            valid.append({
                                "segment": str(item.get("segment", "unknown"))[:50],
                                "company": str(item.get("company", "unknown"))[:80],
                                "share_pct": sp,
                                "rank": rk,
                                "source": item.get("source"),
                            })
                        return valid
        except Exception as e:
            logger.debug("LLM竞争格局提取失败: %s", e)
        return []

    def _calc_relative_market_position(self, company_revenue, matched_peers, financial_currency="RMB"):
        """从同行收入反推发行人相对市场地位。

        使用同行库中同赛道已上市公司的收入排名作为代理指标。
        返回: {"rank": int, "peer_count": int, "revenue_percentile": float|None, "relative_share_pct": float|None}
        """
        if not _is_num(company_revenue) or company_revenue <= 0:
            return {"rank": None, "peer_count": 0, "revenue_percentile": None, "relative_share_pct": None}

        fx = _financial_fx_to_hkd(financial_currency)
        company_rev_hkd = company_revenue * fx

        peer_revenues = []
        for p in matched_peers:
            rev = p.get("revenue_million")
            if _is_num(rev) and rev > 0:
                peer_revenues.append(rev)

        if not peer_revenues:
            return {"rank": None, "peer_count": 0, "revenue_percentile": None, "relative_share_pct": None}

        all_revs = sorted([company_rev_hkd] + peer_revenues, reverse=True)
        rank = all_revs.index(company_rev_hkd) + 1
        peer_count = len(peer_revenues)
        total = sum(peer_revenues) + company_rev_hkd
        relative_share_pct = round(company_rev_hkd / total * 100, 1) if total > 0 else None
        # 收入百分位: 比多少比例的同行收入高
        revenue_percentile = round((peer_count - (rank - 1)) / peer_count * 100, 1) if peer_count > 0 else None

        return {
            "rank": rank,
            "peer_count": peer_count,
            "revenue_percentile": revenue_percentile,
            "relative_share_pct": relative_share_pct,
        }

    def analyze(self, prospectus_info, text='', ipo_data=None):
        """执行同行对比分析"""
        result = {
            "subsector": None,
            "matched_sector": None,
            "peer_keywords": [],
            "all_subsector_matches": [],
            "match_confidence": "none",
            "extracted_competitors": [],
            "prospectus_peer_candidates": [],
            "unmatched_peer_candidates": [],
            "matched_peers": [],
            "quantitative_peers": [],
            "qualitative_peers": [],
            "quantitative_basis": "none",
            "quantitative_peer_count": 0,
            "qualitative_peer_count": 0,
            "comparison_mode": "by_market",
            "primary_comparison_market": "composite",
            "market_peer_stats": {
                "hk": {"market": "港股", "peer_count": 0, "valuation_position": "样本不足，仅作定性参考", "peers": []},
                "a_share": {"market": "A股", "peer_count": 0, "valuation_position": "样本不足，仅作定性参考", "peers": []},
                "us": {"market": "美股", "peer_count": 0, "valuation_position": "样本不足，仅作定性参考", "peers": []},
                "other": {"market": "其他", "peer_count": 0, "valuation_position": "样本不足，仅作定性参考", "peers": []},
            },
            "company_ps": None, "company_pe": None, "company_pb": None,
            "peer_median_ps": None, "peer_median_pe": None, "peer_median_pb": None,
            "peer_ps_count": 0, "peer_pe_count": 0,
            "relative_ps_premium_pct": None, "relative_pe_premium_pct": None,
            "weighted_peer_ps": None,
            "relative_weighted_ps_premium_pct": None,
            "weighted_valuation_position": None,
            "business_line_peer_valuation": [],
            "peer_candidate_filter_warnings": [],
            "valuation_position": "缺失",
            "scarcity_score": 0, "peer_score": 0,
            "market_share_data": [],
            "market_size_data": [],
            "dominant_segment": None,
            "dominant_share_pct": None,
            "scarcity_detail": None,
            "scarcity_specific_point": None,
            "scarcity_peers_count": None,
            "summary": "", "warnings": [],
            "semantic_id": "peer_comparison",
        }

        if not self.peer_data:
            result["warnings"].append("同行数据库未加载")
            return result

        # 发行人别名（用于排除）
        issuer_aliases = _build_issuer_aliases(prospectus_info, ipo_data)
        all_peer_names = self.all_peer_names

        # 1. 提取竞争章节
        try:
            comp_chunks = _extract_competitor_chunks(text)
        except Exception as e:
            logger.warning("竞争章节提取失败: %s", e)
            comp_chunks = []

        # 1.5. 市场份额 / 市场规模 / 集中度提取（在赛道匹配之前，确保始终运行）
        try:
            ms_result = self._extract_market_share_data(text)
            result["market_share_data"] = ms_result
        except Exception as e:
            logger.warning("市场份额提取异常: %s", e)

        try:
            result["market_size_data"] = self._extract_market_size_data(text)
        except Exception as e:
            logger.warning("市场规模提取异常: %s", e)

        try:
            result["market_concentration"] = self._extract_market_concentration(text)
        except Exception as e:
            logger.warning("行业集中度提取异常: %s", e)

        if len(result.get("market_share_data") or []) < 2:
            try:
                llm_data = self._extract_competitive_landscape_via_llm(text)
                if llm_data:
                    result["llm_market_share_data"] = llm_data
                    existing_keys = {
                        (ms.get("segment", "").lower(), ms.get("share_pct"))
                        for ms in result.get("market_share_data") or []
                    }
                    for item in llm_data:
                        key = (item.get("segment", "unknown").lower(), item.get("share_pct"))
                        if key not in existing_keys:
                            result.setdefault("market_share_data", []).append({
                                "segment": item.get("segment", "unknown"),
                                "share_pct": item.get("share_pct"),
                                "rank": item.get("rank"),
                                "source": item.get("source") or "LLM提取",
                            })
                            existing_keys.add(key)
            except Exception as e:
                logger.debug("LLM竞争格局提取异常: %s", e)

        # 计算 dominant segment（提前到赛道匹配前）
        dominant = None
        for ms in result.get("market_share_data") or []:
            if ms.get("share_pct") is not None:
                dominant_unknown = (dominant or {}).get("segment") in (None, "", "unknown")
                ms_known = ms.get("segment") not in (None, "", "unknown")
                if (
                    dominant is None
                    or ms["share_pct"] > dominant["share_pct"]
                    or (ms["share_pct"] == dominant["share_pct"] and dominant_unknown and ms_known)
                ):
                    dominant = ms
        if dominant:
            result["dominant_segment"] = dominant["segment"]
            result["dominant_share_pct"] = dominant["share_pct"]

        # 2. 赛道匹配
        try:
            matched_sector, sk, sd, all_matches, best_hits = _extract_keywords_subsector(
                prospectus_info, text, self.peer_data,
            )
        except Exception as e:
            logger.warning("赛道匹配异常: %s", e)
            matched_sector, sk, sd, all_matches, best_hits = "unknown", None, None, [], 0

        # 无论是否匹配到赛道，都尝试提取未收录候选
        try:
            result["unmatched_peer_candidates"] = _unmatched_candidates(
                comp_chunks, all_peer_names, issuer_aliases=issuer_aliases,
            )
        except Exception as e:
            logger.warning("未收录候选提取异常: %s", e)

        if not sk or not sd:
            result["warnings"].append("未匹配到细分赛道")
            # 即使未匹配赛道，仍保留已提取的市场占有率数据
            detail_parts = []
            if result.get("dominant_segment") and result.get("dominant_share_pct") is not None:
                detail_parts.append(f"在{result['dominant_segment']}市场份额{result['dominant_share_pct']}%")
            if dominant and dominant.get("rank") is not None:
                detail_parts.append(f"排名第{dominant['rank']}")
            conc = result.get("market_concentration") or {}
            if conc.get("cr3_pct") is not None:
                detail_parts.append(f"CR3={conc['cr3_pct']}%")
            elif conc.get("cr5_pct") is not None:
                detail_parts.append(f"CR5={conc['cr5_pct']}%")
            if detail_parts:
                result["scarcity_detail"] = " + ".join(detail_parts)
            return result

        result["matched_sector"] = matched_sector
        result["subsector"] = sk
        result["peer_keywords"] = sd.get("keywords", [])
        result["all_subsector_matches"] = [(s, ss) for s, ss in all_matches]
        result["match_confidence"] = _best_hits_to_confidence(best_hits)

        # 3. 识别已收录同行
        try:
            mentioned = _find_mentioned_companies(text, comp_chunks, sd)
        except Exception as e:
            logger.warning("同行识别异常: %s", e)
            mentioned = []

        # 4. 整理同行列表
        all_peers_raw = sd.get("peers", [])
        seen = set()
        matched = []
        for m in mentioned:
            if m.get("name") not in seen:
                matched.append(m)
                seen.add(m["name"])
        for p in all_peers_raw:
            n = p.get("name", "")
            if n in seen:
                continue
            seen.add(n)
            matched.append({
                **p,
                "matched_by": "行业数据库匹配" if n not in {m.get("name") for m in mentioned}
                else "招股书明确提及",
            })
        matched = [_with_peer_market(p) for p in matched]

        result["matched_peers"] = matched
        result["extracted_competitors"] = [
            m["name"] for m in matched if m.get("matched_by", "").startswith("招股书")
        ]

        # 区分 quantitative / qualitative peers
        quantitative_peers, qualitative_peers, quantitative_basis, q_count, ql_count = _split_peer_samples(matched)
        result["quantitative_peers"] = quantitative_peers
        result["qualitative_peers"] = qualitative_peers
        result["quantitative_basis"] = quantitative_basis
        result["quantitative_peer_count"] = q_count
        result["qualitative_peer_count"] = ql_count
        if q_count < 2:
            result["peer_sample_warning"] = f"quantitative peers 仅 {q_count} 家，不参与强估值判断，仅作定性参考"
        else:
            result["peer_sample_warning"] = None

        # 5. 公司 PS/PE
        company_ps, company_pe, company_pb = _calc_company_valuation_metrics(prospectus_info)
        result["company_ps"] = company_ps
        result["company_pe"] = company_pe
        result["company_pb"] = company_pb
        result["market_peer_stats"] = _calc_market_peer_stats(
            quantitative_peers, company_ps, company_pe, company_pb, scarcity=0,
        )

        # 6-7. 同行中位数 + 相对溢价 (仅基于 quantitative peers)
        medians = _calc_peer_medians(quantitative_peers)
        result.update(medians)
        peer_median_ps = result["peer_median_ps"]
        peer_median_pe = result["peer_median_pe"]
        if _is_num(company_ps) and _is_num(peer_median_ps) and peer_median_ps > 0:
            result["relative_ps_premium_pct"] = round(
                (company_ps - peer_median_ps) / peer_median_ps * 100, 1
            )
        if _is_num(company_pe) and _is_num(peer_median_pe) and peer_median_pe > 0:
            result["relative_pe_premium_pct"] = round(
                (company_pe - peer_median_pe) / peer_median_pe * 100, 1
            )

        weighted = _calc_business_line_weighted_peer_ps(prospectus_info, matched, sk)
        if weighted:
            result.update(weighted)
            weighted_peer_ps = result.get("weighted_peer_ps")
            if _is_num(company_ps) and _is_num(weighted_peer_ps) and weighted_peer_ps > 0:
                result["relative_weighted_ps_premium_pct"] = round(
                    (company_ps - weighted_peer_ps) / weighted_peer_ps * 100, 1
                )
                result["weighted_valuation_position"] = _calc_valuation_position(
                    company_ps, weighted_peer_ps, scarcity=0,
                    premium=result["relative_weighted_ps_premium_pct"],
                )

        # 市值对比（当 PS/PE 不可用或作为补充参考）
        company_mc = prospectus_info.get("market_cap_hkd_million")  # 尽可能使用
        if company_ps is None and _is_num(company_mc):
            peer_mc = result.get("peer_median_market_cap")
            result["relative_market_cap_pct"] = _calc_company_market_cap_metric(company_mc, peer_mc)
            result["company_market_cap_vs_peer_pct"] = result.get("relative_market_cap_pct")
        elif company_ps is not None:
            peer_mc = result.get("peer_median_market_cap")
            result["relative_market_cap_pct"] = _calc_company_market_cap_metric(company_mc, peer_mc)

        # 8. 相对市场地位（需要 matched_peers，在赛道匹配后才能算）
        try:
            company_revenue = prospectus_info.get("revenue")
            result["relative_market_position"] = self._calc_relative_market_position(
                company_revenue, matched, prospectus_info.get("financial_currency", "RMB"),
            )
        except Exception as e:
            logger.debug("相对市场地位计算异常: %s", e)

        # 将提取的市场份额数据注入 prospectus_info 供稀缺性评分使用
        prospectus_info_for_scoring = {**prospectus_info}
        prospectus_info_for_scoring["market_share_data"] = result.get("market_share_data") or []
        prospectus_info_for_scoring["dominant_share_pct"] = result.get("dominant_share_pct")
        prospectus_info_for_scoring["relative_market_position"] = result.get("relative_market_position")
        prospectus_info_for_scoring["market_concentration"] = result.get("market_concentration")

        # 9. 稀缺性 / 评分 / 估值定位
        try:
            scarcity = _calc_scarcity_score(prospectus_info_for_scoring, matched, matched_sector)
        except Exception:
            scarcity = 0
        result["scarcity_score"] = scarcity
        result["market_peer_stats"] = _calc_market_peer_stats(
            quantitative_peers, company_ps, company_pe, company_pb, scarcity,
        )

        try:
            rev = prospectus_info.get("revenue")
            rev_y1 = prospectus_info.get("revenue_y1")
            premium_for_score = result.get("relative_weighted_ps_premium_pct")
            if premium_for_score is None:
                premium_for_score = result["relative_ps_premium_pct"]
            peer_scr = _calc_peer_score(
                scarcity, premium_for_score, rev, rev_y1, matched_sector,
            )
        except Exception:
            peer_scr = 0
        result["peer_score"] = peer_scr

        if len(quantitative_peers) < 2:
            result["valuation_position"] = "样本不足，仅作定性参考"
        else:
            result["valuation_position"] = _calc_valuation_position(
                company_ps, peer_median_ps, scarcity, result["relative_ps_premium_pct"]
            )
        if result.get("weighted_valuation_position") not in (None, "缺失"):
            result["valuation_position"] = result["weighted_valuation_position"]

        strong_market_buckets = {
            _market_position_bucket(v.get("valuation_position"))
            for k, v in result["market_peer_stats"].items()
            if k in ("hk", "a_share", "us") and v.get("peer_count", 0) >= 2
        }
        strong_market_buckets.discard(None)
        if len(strong_market_buckets) >= 2:
            result["warnings"].append("跨市场估值分化，需结合上市地流动性/主题溢价解读")

        # 10. 总结
        try:
            result["summary"] = _build_summary(
                result["valuation_position"], sk, matched,
                company_ps, peer_median_ps, peer_median_pe, company_pe,
            )
            if result.get("weighted_peer_ps"):
                result["summary"] += (
                    f"；按业务占比加权同行PS {result['weighted_peer_ps']:.1f}x"
                    f"({result.get('relative_weighted_ps_premium_pct', 0):+.0f}%)"
                )
        except Exception:
            result["summary"] = f"细分赛道: {sk}；同行对比完成"

        # 合并候选
        result["prospectus_peer_candidates"] = list(dict.fromkeys(
            result["extracted_competitors"] + result["unmatched_peer_candidates"]
        ))[:25]

        # 11. 警告
        if result["peer_ps_count"] == 0:
            result["warnings"].append("quantitative peers 缺少有效PS数据")
        if company_ps is None:
            result["warnings"].append("公司PS不可用，相对估值仅做定性参考")
        if result["peer_ps_count"] < 2:
            result["warnings"].append("quantitative peers 样本量不足，中位数参考价值有限")
        rev = prospectus_info.get("revenue")
        if _is_num(rev) and rev < 500 and matched_sector in ("healthcare", "hardtech"):
            result["warnings"].append("收入基数小，PS可能失真，需结合管线/技术阶段/平台价值判断")
            if result["valuation_position"] not in ("缺失", "样本不足，仅作定性参考"):
                result["valuation_position"] = f"PS辅助({result['valuation_position']})"

        if self.meta.get("peer_data_is_stale"):
            result["warnings"].append(
                f"同行数据已过期({self.meta.get('peer_data_age_days', '?')}天)，建议通过同行库管理页更新"
            )

        hk_listed = [p for p in matched if _is_hk_peer(p) and p.get("type") == "listed"]
        result["scarcity_peers_count"] = len(hk_listed) if hk_listed else q_count

        # 生成稀缺性详情：整合市场份额、排名、集中度、相对市场地位
        detail_parts = []
        if result["dominant_segment"] and result["dominant_share_pct"] is not None:
            detail_parts.append(f"在{result['dominant_segment']}市场份额{result['dominant_share_pct']}%")
        if dominant and dominant.get("rank") is not None:
            detail_parts.append(f"排名第{dominant['rank']}")
        if dominant and dominant.get("source"):
            detail_parts.append(f"数据来源: {dominant['source']}")
        # 行业集中度
        conc = result.get("market_concentration") or {}
        if conc.get("cr3_pct") is not None:
            detail_parts.append(f"CR3={conc['cr3_pct']}%")
        elif conc.get("cr5_pct") is not None:
            detail_parts.append(f"CR5={conc['cr5_pct']}%")
        # 相对市场地位
        rmp = result.get("relative_market_position") or {}
        if rmp.get("rank") is not None and rmp.get("peer_count", 0) > 0:
            detail_parts.append(f"同行收入排名{rmp['rank']}/{rmp['peer_count']}")
        subsector_label = sk or ""
        if subsector_label:
            detail_parts.append(f"细分赛道: {subsector_label}")
        if detail_parts:
            result["scarcity_detail"] = " + ".join(detail_parts)
        elif result["scarcity_peers_count"] is not None:
            result["scarcity_detail"] = f"港股可比分量约{result['scarcity_peers_count']}家"

        # 稀缺性具体描述（保留原有逻辑，增加集中度和相对排名）
        if result["scarcity_peers_count"] is not None and result["scarcity_peers_count"] <= 3:
            peer_desc = f"港股可比分量仅{result['scarcity_peers_count']}家"
            if result["dominant_share_pct"] is not None and result["dominant_share_pct"] >= 20:
                result["scarcity_specific_point"] = (
                    f"{peer_desc}，且公司在{result['dominant_segment']}市场份额{result['dominant_share_pct']}%，稀缺性突出"
                )
            elif rmp.get("rank") is not None and rmp["rank"] <= 2 and rmp.get("peer_count", 0) >= 2:
                result["scarcity_specific_point"] = (
                    f"{peer_desc}，公司在同行中收入排名第{rmp['rank']}，赛道稀缺"
                )
            else:
                result["scarcity_specific_point"] = f"{peer_desc}，港股中纯粹对标公司很少"
        elif result["dominant_share_pct"] is not None and result["dominant_share_pct"] >= 50:
            result["scarcity_specific_point"] = (
                f"在{result['dominant_segment']}市场份额{result['dominant_share_pct']}%，港股中纯粹对标公司很少"
            )
        elif rmp.get("rank") is not None and rmp["rank"] == 1 and rmp.get("peer_count", 0) >= 3:
            result["scarcity_specific_point"] = (
                f"在{rmp['peer_count']}家同行中收入规模排名第1，行业龙头地位"
            )

        return result
