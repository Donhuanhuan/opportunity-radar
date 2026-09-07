"""飞书机器人 Webhook 推送"""
import json
import requests
from datetime import datetime
from radar.config import FEISHU_WEBHOOK


def build_card(items: list) -> dict:
    """构造飞书富文本卡片消息"""
    today = datetime.now().strftime("%Y-%m-%d")
    elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"📡 **商机雷达日报** · {today}\n共扫描 {len(items)} 条命中商机"
            }
        },
        {"tag": "hr"},
    ]

    for i, it in enumerate(items, 1):
        title = it.get("title", "")
        url = it.get("url", "")
        source = it.get("source", "")
        score = it.get("score", 0)
        tags = " ".join(it.get("tags", []))
        summary = (it.get("summary") or "")[:120]

        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**{i}. [{title}]({url})**\n"
                    f"> 🏷 {source} · 📊 score: {score} · {tags}\n"
                    f"> {summary}"
                )
            }
        })

    elements.append({"tag": "hr"})
    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": "🔗 [GitHub Actions 自动运行] · 商机雷达 v1.0"
        }
    })

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"📡 商机雷达日报 · {today}"},
                "template": "green"
            },
            "elements": elements
        }
    }


def send_daily(items: list) -> bool:
    """发送日报到飞书"""
    if not FEISHU_WEBHOOK:
        print("[Feishu] 未配置 FEISHU_WEBHOOK，跳过")
        return False
    if not items:
        print("[Feishu] 无内容，跳过")
        return False
    payload = build_card(items)
    try:
        r = requests.post(FEISHU_WEBHOOK, json=payload, timeout=10)
        ok = r.json().get("StatusCode") == 0 or r.status_code == 200
        print(f"[Feishu] 推送{'成功' if ok else '失败'}: {r.text[:200]}")
        return ok
    except Exception as e:
        print(f"[Feishu] 推送异常: {e}")
        return False