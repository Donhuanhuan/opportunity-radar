"""微博热搜榜

官方桌面接口 weibo.com/ajax/side/hotSearch 通常需要登录 cookie，匿名请求常拿不到数据。
策略：依次尝试官方接口 → 第三方聚合镜像（vvhan/oioweb），全部失败则返回空（容忍空源，
不阻塞整条流水线）。如持续 0 条，可考虑后续用本机 Edge 登录态抓取。
"""
import requests

# 依次尝试：官方 → vvhan → oioweb
URLS = [
    ("weibo-official", "https://weibo.com/ajax/side/hotSearch"),
    ("vvhan", "https://api.vvhan.com/api/hotlist/wbHot"),
    ("oioweb", "https://api.oioweb.cn/api/common/HotList?type=weibo"),
]

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://weibo.com/",
}


def fetch(limit: int = 20) -> list:
    out = []
    for name, url in URLS:
        try:
            r = requests.get(url, headers=BROWSER_HEADERS, timeout=6)
            if r.status_code != 200:
                continue
            j = r.json()
            if name == "weibo-official":
                data = (j.get("data") or {}).get("realtime", [])
                for item in data[:limit]:
                    word = (item.get("word") or "").strip()
                    if not word:
                        continue
                    out.append({
                        "source": "微博热搜",
                        "title": word[:80],
                        "summary": (item.get("note") or "微博热搜词")[:200],
                        "url": f"https://s.weibo.com/weibo?q=%23{word}%23",
                        "score": int(item.get("num", 0) or 0),
                        "comments": 0,
                    })
                if out:
                    return out
            else:
                arr = j.get("data") or []
                ok = j.get("success") or j.get("code") in (200, 1) or arr
                for item in (arr if ok else [])[:limit]:
                    title = (item.get("title") or item.get("word") or "").strip()
                    if not title:
                        continue
                    hot = int(item.get("hot", item.get("num", 0)) or 0)
                    out.append({
                        "source": "微博热搜",
                        "title": title[:80],
                        "summary": f"微博热搜 · 热度 {hot}" if hot else "微博热搜词",
                        "url": f"https://s.weibo.com/weibo?q=%23{title}%23",
                        "score": hot,
                        "comments": 0,
                    })
                if out:
                    return out
        except Exception as e:
            print(f"[Weibo/{name}] 抓取失败: {e}")
            continue
    return out
