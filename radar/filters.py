"""过滤器：关键词 + 打分"""
import math
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
    """相关度打分：真实热度(log 归一)为主导 + 主题词 +5/个 + 情绪词 +3/个

    国内热榜的 score 是真实热度量级（百万~千万级），直接比较会让关键词加成失效，
    故用 log10 归一（2000万热度≈73分、50万≈57分），关键词加成在小数位体现区分。
    """
    for it in items:
        raw = it.get("score") or 0
        if raw and raw > 0:
            base = round(min(100.0, 10.0 * math.log10(float(raw))), 1)
        else:
            base = 30.0  # 源未带热度时的保底分
        text = (it.get("title", "") + it.get("summary", "")).lower()
        hot_hits = sum(1 for kw in KEYWORDS_HOT if kw.lower() in text)
        demand_hits = sum(1 for kw in KEYWORDS_DEMAND if kw.lower() in text)
        it["score"] = round(base + hot_hits * 8 + demand_hits * 5, 1)
        it["tags"] = []
        if hot_hits or raw:
            it["tags"].append("🔥 热门")
        if demand_hits:
            it["tags"].append("💬 热议")
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