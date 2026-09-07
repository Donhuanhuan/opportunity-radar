"""过滤器：关键词 + 打分"""
from typing import List, Dict
from radar.config import KEYWORDS_HOT, KEYWORDS_DEMAND, KEYWORDS_BLOCK


def filter_block(items: List[Dict]) -> List[Dict]:
    """过滤违规内容"""
    return [
        it for it in items
        if not any(kw.lower() in (it.get("title", "") + it.get("summary", "")).lower()
                   for kw in KEYWORDS_BLOCK)
    ]


def score_relevance(items: List[Dict]) -> List[Dict]:
    """相关度打分：热门词 +5 / 个，需求词 +3 / 个"""
    for it in items:
        text = (it.get("title", "") + it.get("summary", "")).lower()
        hot_hits = sum(1 for kw in KEYWORDS_HOT if kw.lower() in text)
        demand_hits = sum(1 for kw in KEYWORDS_DEMAND if kw.lower() in text)
        # 兜底分（保留所有有效项）
        it["score"] = 10 + hot_hits * 5 + demand_hits * 3
        it["tags"] = []
        if hot_hits:
            it["tags"].append("🔥 热门")
        if demand_hits:
            it["tags"].append("💰 变现")
    return items


def dedupe(items: List[Dict]) -> List[Dict]:
    """按 title 去重"""
    seen = set()
    out = []
    for it in items:
        key = it.get("title", "")[:40].strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(it)
    return out


def top_n(items: List[Dict], n: int) -> List[Dict]:
    """按 score 排序取 Top N"""
    return sorted(items, key=lambda x: x.get("score", 0), reverse=True)[:n]