"""Product Hunt 今日榜（抓首页 HTML，无需 token）"""
import re
import requests
from radar.config import HEADERS

URL = "https://www.producthunt.com/"


def fetch(limit: int = 20) -> list:
    out = []
    try:
        r = requests.get(URL, headers=HEADERS, timeout=10)
        # 简化版：抓 data-test="post-item-title" 标题 + 链接
        # PH 页面结构常变，建议改为 GraphQL API（需 token）
        pattern = re.compile(
            r'<a[^>]+href="(/posts/[^"]+)"[^>]*>([^<]+)</a>',
            re.IGNORECASE
        )
        seen = set()
        for m in pattern.finditer(r.text):
            href, title = m.group(1), m.group(2).strip()
            if "/posts/" in href and href not in seen and title:
                seen.add(href)
                out.append({
                    "source": "Product Hunt",
                    "title": title,
                    "summary": "PH 今日热门产品",
                    "url": "https://www.producthunt.com" + href,
                    "score": 0,
                    "comments": 0,
                })
                if len(out) >= limit:
                    break
    except Exception as e:
        print(f"[PH] 抓取失败: {e}")
    return out