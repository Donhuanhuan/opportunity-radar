"""知乎热榜（api.zhihu.com/topstory/hot-list）

国内情绪热点的"深度讨论场"：热榜话题自带社会情绪（共鸣/焦虑/好奇/愤怒），
适合内容选题。公开接口无需登录，反爬压力小。
"""
import re
import requests

URLS = [
    "https://api.zhihu.com/topstory/hot-list?limit=20",
    "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total?limit=20&desktop=true",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://www.zhihu.com/hot",
}


def _parse_heat(text: str) -> int:
    """从「1234.5 万热度」这类文案提取数值（返回热度原始量级）"""
    m = re.search(r"([\d.]+)\s*(万)?", text or "")
    if not m:
        return 0
    try:
        v = float(m.group(1))
        return int(v * 10000) if m.group(2) else int(v)
    except ValueError:
        return 0


def fetch(limit: int = 20) -> list:
    for url in URLS:
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code != 200:
                continue
            data = r.json().get("data", [])
            out = []
            for idx, item in enumerate(data[:limit]):
                target = item.get("target", {}) or {}
                title = (target.get("title") or "").strip()
                if not title:
                    continue
                # 热度：detail_text 带「万热度」，解析失败用排名倒序兜底
                raw_heat = _parse_heat(item.get("detail_text", ""))
                if raw_heat <= 0:
                    raw_heat = max(100 - idx * 4, 1)  # 排名兜底分
                qid = target.get("id", "")
                link = target.get("url", "") or (f"https://www.zhihu.com/question/{qid}" if qid else "https://www.zhihu.com/hot")
                out.append({
                    "source": "知乎热榜",
                    "title": title[:80],
                    "summary": (target.get("excerpt", "") or item.get("detail_text", "") or "知乎热榜话题")[:200],
                    "url": link,
                    "score": raw_heat,  # 真实热度量级（供 log 归一）
                    "comments": int(target.get("answer_count", 0) or 0),
                })
            if out:
                return out
        except Exception as e:
            print(f"[ZhihuHot] 抓取失败: {e}")
            continue
    return []
