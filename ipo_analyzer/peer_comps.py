"""同行对比与相对估值分析模块 — 半动态同行库

依赖: pyyaml (懒加载), 无其他重依赖
"""

import os
import re
import logging
from datetime import date, datetime
from statistics import median
from typing import Optional

from .utils import _is_num, _contains_any, _infer_sector
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
            end = min(len(text), m.end() + 2000)
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
    ]
    if any(phrase in lower for phrase in _GENERIC_PHRASES):
        return True
    # 英文候选超过6个单词
    words = name.strip().split()
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

        # 排除纯后缀片段：如 "Bio Limited"、"Tech Inc"（仅后缀+1个短词）
        words = lower.split()
        if len(words) <= 2 and words[-1] in pure_suffixes:
            # 排除只有 1 个词+后缀 且 前一词是短词/通用词的
            if len(words) == 1:
                continue
            if len(words) == 2 and (len(words[0]) <= 4 or words[0] in junk_lower):
                continue

        # 排除发行人别名
        if lower in issuer_aliases:
            continue
        # 排除部分匹配：候选名包含发行人别名的一个完整词
        if issuer_aliases:
            candidate_words = set(words)
            should_skip = False
            for alias in issuer_aliases:
                alias_words = set(alias.split())
                if candidate_words & alias_words:
                    # 如果超过一半的词相同，排除
                    overlap = len(candidate_words & alias_words)
                    if overlap >= len(candidate_words) / 2 and overlap > 0:
                        should_skip = True
                        break
            if should_skip:
                continue

        # 排除已在同行库里
        if lower in all_peer_lower:
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


def _extract_keywords_subsector(prospectus_info, prospectus_text, peer_data=None):
    sector = prospectus_info.get("sector", "unknown")
    if peer_data is None:
        peer_data = _load_peer_data()
    if not peer_data or not isinstance(peer_data, dict):
        return "unknown", None, None, [], 0
    biz = prospectus_info.get("business_breakdown", {}) or {}
    seg_text = " ".join(s.get("name", "") for s in biz.get("segments", []))
    rnd = prospectus_info.get("rnd_pipeline", {}) or {}
    rd_text = rnd.get("pipeline_quality_label", "") or ""
    combined = " ".join([
        prospectus_text or "", seg_text, rd_text,
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
                for kw in kws:
                    if kw.lower() in combined:
                        all_matches.append((sec_key, sk, sd, 1))
                        break
            if all_matches:
                break
    all_matches.sort(key=lambda x: x[3], reverse=True)
    if all_matches:
        best_sec, best_sk, best_sd, best_hits = all_matches[0]
        return best_sec, best_sk, best_sd, [(m[0], m[1]) for m in all_matches], best_hits
    return "unknown", None, None, [], 0


# ---------------------------------------------------------------------------
# 中位数 / 稀缺性 / 评分
# ---------------------------------------------------------------------------

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
        "peer_median_pe": round(median(pe_v), 2) if len(pe_v) >= 2 else (pe_v[0] if pe_v else None),
        "peer_median_pb": round(median(pb_v), 2) if len(pb_v) >= 2 else (pb_v[0] if pb_v else None),
        "peer_median_market_cap": round(median(mc_v), 2) if len(mc_v) >= 2 else (mc_v[0] if mc_v else None),
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


def _calc_scarcity_score(prospectus_info, matched_peers, sector):
    score = 0
    rnd = prospectus_info.get("rnd_pipeline", {}) or {}
    ca = prospectus_info.get("cornerstone_analysis", {}) or {}
    listed = [p for p in matched_peers if p.get("type") == "listed"]
    if len(listed) <= 2:
        score += 3
    elif len(listed) <= 4:
        score += 1
    moat = rnd.get("technology_moat_score", 0)
    if moat >= 7:
        score += 3
    elif moat >= 5:
        score += 1
    if sector == "healthcare":
        score += 2
    cornerstone_rows = ca.get("cornerstone_investors") or []
    tiers = {row.get("tier", "") for row in cornerstone_rows}
    if not tiers:
        matched_inv = ca.get("matched_investors", [])
        tiers = {m.get("tier", "") for m in matched_inv}
    if "S" in tiers:
        score += 2
    elif "A" in tiers:
        score += 1
    rev = prospectus_info.get("revenue")
    rev_y1 = prospectus_info.get("revenue_y1")
    if _is_num(rev) and _is_num(rev_y1) and rev_y1 > 0:
        g = (rev - rev_y1) / rev_y1
        if g > 1.0:
            score += 2
        elif g > 0.5:
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

    def analyze(self, prospectus_info, prospectus_text, ipo_data=None):
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
            "company_ps": None, "company_pe": None, "company_pb": None,
            "peer_median_ps": None, "peer_median_pe": None, "peer_median_pb": None,
            "peer_ps_count": 0, "peer_pe_count": 0,
            "relative_ps_premium_pct": None, "relative_pe_premium_pct": None,
            "valuation_position": "缺失",
            "scarcity_score": 0, "peer_score": 0,
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
            comp_chunks = _extract_competitor_chunks(prospectus_text)
        except Exception as e:
            logger.warning("竞争章节提取失败: %s", e)
            comp_chunks = []

        # 2. 赛道匹配
        try:
            matched_sector, sk, sd, all_matches, best_hits = _extract_keywords_subsector(
                prospectus_info, prospectus_text, self.peer_data,
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
            return result

        result["matched_sector"] = matched_sector
        result["subsector"] = sk
        result["peer_keywords"] = sd.get("keywords", [])
        result["all_subsector_matches"] = [(s, ss) for s, ss in all_matches]
        result["match_confidence"] = _best_hits_to_confidence(best_hits)

        # 3. 识别已收录同行
        try:
            mentioned = _find_mentioned_companies(prospectus_text, comp_chunks, sd)
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

        result["matched_peers"] = matched
        result["extracted_competitors"] = [
            m["name"] for m in matched if m.get("matched_by", "").startswith("招股书")
        ]

        # 区分 quantitative / qualitative peers
        quantitative_peers = [
            p for p in matched
            if p.get("type") == "listed"
            and not (p.get("ps") is None and p.get("pe") is None and p.get("market_cap_hkd_million") is None)
            and p.get("data_quality") != "low"
            and not p.get("needs_refresh", False)
        ]
        qualitative_peers = [p for p in matched if p not in quantitative_peers]
        result["quantitative_peers"] = quantitative_peers
        result["qualitative_peers"] = qualitative_peers

        # 5. 公司 PS/PE
        valuation = prospectus_info.get("valuation", {}) or {}
        company_ps = valuation.get("ps_ratio")
        company_pe = valuation.get("pe_ratio") or valuation.get("adjusted_pe_ratio")
        company_pb = valuation.get("pb_ratio")
        if company_ps is None and company_pe is None:
            mc = prospectus_info.get("market_cap_hkd_million")
            rev = prospectus_info.get("revenue")
            np_val = prospectus_info.get("net_profit")
            if _is_num(mc) and _is_num(rev) and rev > 0:
                company_ps = round(mc / rev, 2)
            if _is_num(mc) and _is_num(np_val) and np_val > 0:
                company_pe = round(mc / np_val, 2)
        result["company_ps"] = company_ps
        result["company_pe"] = company_pe
        result["company_pb"] = company_pb

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

        # 市值对比（当 PS/PE 不可用或作为补充参考）
        company_mc = prospectus_info.get("market_cap_hkd_million") or company_ps  # 尽可能使用
        if company_ps is None and _is_num(company_mc):
            peer_mc = result.get("peer_median_market_cap")
            result["relative_market_cap_pct"] = _calc_company_market_cap_metric(company_mc, peer_mc)
            result["company_market_cap_vs_peer_pct"] = result.get("relative_market_cap_pct")
        elif company_ps is not None:
            peer_mc = result.get("peer_median_market_cap")
            result["relative_market_cap_pct"] = _calc_company_market_cap_metric(company_mc, peer_mc)

        # 8-10. 稀缺性 / 评分 / 估值定位
        try:
            scarcity = _calc_scarcity_score(prospectus_info, matched, matched_sector)
        except Exception:
            scarcity = 0
        result["scarcity_score"] = scarcity

        try:
            rev = prospectus_info.get("revenue")
            rev_y1 = prospectus_info.get("revenue_y1")
            peer_scr = _calc_peer_score(
                scarcity, result["relative_ps_premium_pct"], rev, rev_y1, matched_sector,
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

        # 11. 总结
        try:
            result["summary"] = _build_summary(
                result["valuation_position"], sk, matched,
                company_ps, peer_median_ps, peer_median_pe, company_pe,
            )
        except Exception:
            result["summary"] = f"细分赛道: {sk}；同行对比完成"

        # 合并候选
        result["prospectus_peer_candidates"] = list(dict.fromkeys(
            result["extracted_competitors"] + result["unmatched_peer_candidates"]
        ))[:25]

        # 12. 警告
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

        return result
