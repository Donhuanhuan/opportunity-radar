"""微博热搜榜（抓 weibo.com/ajax/side/hotSearch）"""
import requests
from radar.config import HEADERS

# 多个公开接口备选
URLS = [
    "https://weibo.com/ajax/side/hotSearch",  # 桌面端
    "https://api.uomg.com/api/rand.qinghua",  # 备用：随机鸡汤（避免被封后空跑）
]


def fetch(limit: int = 20) -> list:
    out = []
    try:
        r = requests.get(URLS[0], headers=HEADERS, timeout=8)
        data = r.json().get("data", {}).get("realtime", [])
        for item in data[:limit]:
            out.append({
                "source": "微博热搜",
                "title": item.get("word", "").strip(),
                "summary": item.get("note", "")[:200] or "微博热搜词",
                "url": f"https://s.weibo.com/weibo?q=%23{item.get('word','')}%23",
                "score": item.get("num", 0),  # 热度值
                "comments": 0,
            })
    except Exception as e:
        print(f"[Weibo] 抓取失败: {e}")
        # 兜底：返回示例，避免整条流水线挂掉
        out = [{
            "source": "微博热搜",
            "title": "（微博接口暂时不可用）",
            "summary": str(e)[:200],
            "url": "https://s.weibo.com",
            "score": 0,
            "comments": 0,
        }]
    return out