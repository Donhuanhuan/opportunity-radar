"""HackerNews Top Stories（官方 Firebase API，无需 token）"""
import requests
from radar.config import HEADERS

API = "https://hacker-news.firebaseio.com/v0"


def fetch(limit: int = 30) -> list:
    """抓取 HN 当前 Top N 条"""
    out = []
    try:
        ids = requests.get(f"{API}/topstories.json", headers=HEADERS, timeout=10).json()[:limit]
        for hid in ids:
            item = requests.get(f"{API}/item/{hid}.json", headers=HEADERS, timeout=5).json()
            if not item or not item.get("title"):
                continue
            out.append({
                "source": "HackerNews",
                "title": item.get("title", ""),
                "summary": item.get("text", "")[:200] if item.get("text") else "",
                "url": item.get("url") or f"https://news.ycombinator.com/item?id={hid}",
                "score": item.get("score", 0),
                "comments": item.get("descendants", 0),
            })
    except Exception as e:
        print(f"[HN] 抓取失败: {e}")
    return out