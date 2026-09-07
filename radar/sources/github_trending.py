"""GitHub Trending（每日热门项目）"""
import re
import requests
from radar.config import HEADERS

URL = "https://github.com/trending"


def fetch(limit: int = 25) -> list:
    out = []
    try:
        r = requests.get(URL, headers=HEADERS, timeout=10)
        # 解析 article.Box-row
        pattern = re.compile(
            r'<article class="Box-row">(.*?)</article>',
            re.DOTALL
        )
        for m in pattern.finditer(r.text)[:limit]:
            block = m.group(1)
            # 提取 h2 链接
            href_m = re.search(r'<h2[^>]*>\s*<a[^>]*href="(/[^"]+)"', block)
            if not href_m:
                continue
            href = "https://github.com" + href_m.group(1)
            name = href_m.group(1).strip("/").replace("/", " / ")
            # 描述
            desc_m = re.search(r'<p class="col-9[^"]*">(.*?)</p>', block, re.DOTALL)
            desc = re.sub(r'<[^>]+>', '', desc_m.group(1)).strip() if desc_m else ""
            # stars today
            star_m = re.search(r'(\d[\d,]*)\s+stars\s+today', block)
            stars_today = star_m.group(1).replace(",", "") if star_m else "0"
            out.append({
                "source": "GitHub Trending",
                "title": name,
                "summary": desc[:200] or "GitHub 今日热门项目",
                "url": href,
                "score": int(stars_today or 0),
                "comments": 0,
            })
    except Exception as e:
        print(f"[GH] 抓取失败: {e}")
    return out