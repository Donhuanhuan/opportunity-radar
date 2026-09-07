"""36氪 / IT桔子 RSS 抓取"""
import feedparser
import requests

RSS_URLS = [
    "https://36kr.com/feed",                    # 36氪
    "https://www.iyiou.com/rss",                # 亿欧
    "https://www.jiqizhixin.com/rss",           # 机器之心
]


def fetch(limit_per_feed: int = 10) -> list:
    out = []
    for url in RSS_URLS:
        try:
            feed = feedparser.parse(url)
            source_name = feed.feed.get("title", url.split("//")[1].split("/")[0])
            for e in feed.entries[:limit_per_feed]:
                out.append({
                    "source": source_name,
                    "title": e.get("title", "").strip(),
                    "summary": (e.get("summary", "") or e.get("description", ""))[:200],
                    "url": e.get("link", ""),
                    "score": 0,
                    "comments": 0,
                })
        except Exception as ex:
            print(f"[RSS] {url} 抓取失败: {ex}")
    return out