"""头条热榜（toutiao.com/hot-event/hot-board）

社会民生热点最广的国内源：覆盖消费/职场/民生/社会事件，
HotValue 即热度值，情绪浓度高、适合图文选题。
"""
import requests

URLS = [
    "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://www.toutiao.com/",
}


def fetch(limit: int = 20) -> list:
    for url in URLS:
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code != 200:
                continue
            data = r.json().get("data", [])
            out = []
            for item in data[:limit]:
                title = (item.get("Title") or "").strip()
                if not title:
                    continue
                hot = int(item.get("HotValue", 0) or 0)
                label = item.get("Label", "") or ""  # 如「热」「新」「荐」
                out.append({
                    "source": "头条热榜",
                    "title": title[:80],
                    "summary": f"头条热榜 · {label} · 热度 {hot}" if label else f"头条热榜 · 热度 {hot}",
                    "url": item.get("Url", "") or f"https://www.toutiao.com/trending/{item.get('ClusterId', '')}/",
                    "score": hot,  # 真实热度量级（供 log 归一）
                    "comments": 0,
                })
            if out:
                return out
        except Exception as e:
            print(f"[Toutiao] 抓取失败: {e}")
            continue
    return []
