"""Greenshoe (over-allotment option) analyzer for Hong Kong IPOs.

Detects whether an IPO has a greenshoe mechanism and evaluates
its impact on post-listing price stability.
"""
from __future__ import annotations

import re
from typing import Any, Optional


class GreenshoeAnalyzer:
    """绿鞋机制（超额配股权）分析。
    
    绿鞋机制允许承销商在上市后30天内：
    - 破发时：用超额配股资金买入托底
    - 上涨时：全额行使超额配股权增发
    
    这是港股IPO重要的后市稳定机制。
    """
    
    GREENSHOE_PATTERNS = [
        re.compile(r"超额配股|超額配股|over.allotment|greenshoe", re.IGNORECASE),
        re.compile(r"稳价操作|穩價操作|price stabiliz", re.IGNORECASE),
        re.compile(r"可额外发售.*(?:股份|股)", re.IGNORECASE),
        re.compile(r"额外发行.*(?:股份|股)", re.IGNORECASE),
    ]
    
    NO_GREENSHOE_PATTERNS = [
        re.compile(r"无.*超额配股|沒有.*超額配股|no.*over.allotment", re.IGNORECASE),
        re.compile(r"不.*超额配股|不.*超額配股", re.IGNORECASE),
    ]
    
    STABILIZER_PATTERNS = [
        re.compile(r"([\u4e00-\u9fa5]{2,15}(?:公司|银行|证券))担任稳价操作"),
        re.compile(r"([\u4e00-\u9fa5]{2,15}(?:公司|银行|证券))稳价操作"),
        re.compile(r"稳价操作人[:：]\s*([\u4e00-\u9fa5A-Za-z0-9\s]{2,30})"),
    ]
    
    DEFAULT_GREENSHOE_RATIO = 0.15
    STABILIZATION_PERIOD_DAYS = 30
    
    def analyze(self, prospectus_info: dict[str, Any]) -> dict[str, Any]:
        text = prospectus_info.get("_extracted_text") or ""
        global_offer = prospectus_info.get("global_offer_shares")
        
        has_greenshoe = self._detect_greenshoe(text)
        stabilizer = self._detect_stabilizer(text)
        greenshoe_shares = self._calc_greenshoe_shares(global_offer, has_greenshoe)
        impact_score = self._calc_impact_score(has_greenshoe, stabilizer)
        
        if has_greenshoe is True:
            detail = f"有绿鞋机制，超额配股{self.DEFAULT_GREENSHOE_RATIO*100:.0f}%，稳价期{self.STABILIZATION_PERIOD_DAYS}天"
            if stabilizer:
                detail += f"，稳价操作人：{stabilizer}"
        elif has_greenshoe is False:
            detail = "无绿鞋机制"
        else:
            detail = "绿鞋信息未明确"
        
        return {
            "has_greenshoe": has_greenshoe,
            "greenshoe_ratio": self.DEFAULT_GREENSHOE_RATIO if has_greenshoe else None,
            "greenshoe_shares": greenshoe_shares,
            "stabilization_period_days": self.STABILIZATION_PERIOD_DAYS if has_greenshoe else None,
            "stabilizer": stabilizer,
            "impact_score": impact_score,
            "detail": detail,
        }
    
    def _detect_greenshoe(self, text: str) -> Optional[bool]:
        if not text:
            return None
        
        for pattern in self.NO_GREENSHOE_PATTERNS:
            if pattern.search(text):
                return False
        
        for pattern in self.GREENSHOE_PATTERNS:
            if pattern.search(text):
                return True
        
        return None
    
    def _detect_stabilizer(self, text: str) -> Optional[str]:
        if not text:
            return None
        
        for pattern in self.STABILIZER_PATTERNS:
            match = pattern.search(text)
            if match:
                stabilizer = match.group(1) if match.lastindex else match.group(0)
                return stabilizer.strip()
        
        return None
    
    def _calc_greenshoe_shares(self, global_offer: Optional[int], has_greenshoe: Optional[bool]) -> Optional[int]:
        if not has_greenshoe or global_offer is None:
            return None
        return int(global_offer * self.DEFAULT_GREENSHOE_RATIO)
    
    def _calc_impact_score(self, has_greenshoe: Optional[bool], stabilizer: Optional[str]) -> int:
        if has_greenshoe is not True:
            return 0
        
        score = 2
        
        if stabilizer:
            if any(bank in stabilizer for bank in ("中金", "中信", "摩根", "高盛", "摩根士丹利", "大摩", "瑞银", "UBS")):
                score += 1
        
        return min(5, score)
