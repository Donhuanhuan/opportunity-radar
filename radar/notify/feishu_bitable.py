"""飞书多维表格推送（兼容 requests / urllib 双模式）

支持双表：
1. 商机池（FEISHU_BITABLE_APP_TOKEN + TABLE_ID） —— send_opportunities()
2. 内容草稿（DRAFTS_BITABLE_APP_TOKEN + TABLE_ID） —— send_drafts()
3. 本地落盘（JSONL） —— append_jsonl() 永远可用，作为草稿的最终兜底
"""
import json
import os
import time
from datetime import datetime
from pathlib import Path

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    requests = None
    _HAS_REQUESTS = False
    import urllib.request

from radar.config import (
    FEISHU_APP_ID, FEISHU_APP_SECRET,
    FEISHU_BITABLE_APP_TOKEN, FEISHU_BITABLE_TABLE_ID,
    HEADERS,
)

API_BASE = "https://open.feishu.cn/open-apis"
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DRAFTS_JSONL = DATA_DIR / "drafts.jsonl"

# === Token 模块级缓存 ===
_TOKEN_CACHE = {"token": None, "expire_at": 0}

# === source 归一化映射 ===
_SOURCE_MAP = {
    "hackernews": "hackernews", "hn": "hackernews",
    "github": "github", "github trending": "github",
    "product hunt": "producthunt", "producthunt": "producthunt",
    "kr36": "kr36", "36氪": "kr36",
    "weibo": "weibo", "微博热搜": "weibo", "微博": "weibo",
}


def _norm_source(raw: str) -> str:
    if not raw:
        return ""
    return _SOURCE_MAP.get(str(raw).strip().lower(), str(raw).strip().lower())


def _http_post_json(url: str, headers: dict, body: dict, timeout: int = 10) -> dict:
    """统一封装：requests 优先，缺则 urllib"""
    if _HAS_REQUESTS:
        r = requests.post(url, headers=headers, json=body, timeout=timeout)
        return r.json()
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={**headers, "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _http_get_json(url: str, headers: dict, timeout: int = 10) -> dict:
    if _HAS_REQUESTS:
        r = requests.get(url, headers=headers, timeout=timeout)
        return r.json()
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _get_tenant_token() -> str:
    now = time.time()
    if _TOKEN_CACHE["token"] and _TOKEN_CACHE["expire_at"] - now > 300:
        return _TOKEN_CACHE["token"]

    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        raise RuntimeError(
            "缺少 FEISHU_APP_ID / FEISHU_APP_SECRET，请在 .env 或 GitHub Secret 配齐"
        )

    data = _http_post_json(
        f"{API_BASE}/auth/v3/tenant_access_token/internal",
        {},
        {"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
    )
    if data.get("code") != 0:
        raise RuntimeError(f"获取 tenant_access_token 失败: {data}")
    _TOKEN_CACHE["token"] = data["tenant_access_token"]
    _TOKEN_CACHE["expire_at"] = now + data.get("expire", 7200)
    return _TOKEN_CACHE["token"]


def _auth_headers() -> dict:
    return {**HEADERS, "Authorization": f"Bearer {_get_tenant_token()}"}


# ============ 商机池 ============

def _build_opportunity_fields(it: dict) -> dict:
    """把一条商机转成多维表格 fields"""
    tags = it.get("tags", []) or []
    title = it.get("title", "")
    return {
        "文本":    title[:500],
        "title":   title[:500],
        "url":     {"link": it.get("url", ""), "text": (title[:50] or "查看")},
        "source":  _norm_source(it.get("source", "")),
        "score":   int(it.get("score", 0)),
        "tags":    tags,
        "summary": (it.get("summary") or "")[:1000],
        "date":    int(datetime.now().timestamp() * 1000),
        "status":  "待评估",
    }


def send_opportunities(items: list, app_token: str = None, table_id: str = None) -> bool:
    """把当日 Top N 商机批量写入商机池表"""
    app_token = app_token or FEISHU_BITABLE_APP_TOKEN
    table_id = table_id or FEISHU_BITABLE_TABLE_ID
    if not app_token or not table_id:
        print("[FeishuBitable] 商机池未配置 APP_TOKEN/TABLE_ID，跳过")
        return False
    if not items:
        print("[FeishuBitable] 商机池无内容，跳过")
        return False
    try:
        headers = _auth_headers()
    except Exception as e:
        print(f"[FeishuBitable] {e}")
        return False

    url = f"{API_BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/records"
    ok, fail = 0, 0
    for it in items:
        try:
            data = _http_post_json(url, headers, {"fields": _build_opportunity_fields(it)})
            if data.get("code") == 0:
                ok += 1
            else:
                fail += 1
                print(f"[FeishuBitable] 商机写入失败: {it.get('title','')[:40]} → {data.get('msg', '')[:80]}")
        except Exception as e:
            fail += 1
            print(f"[FeishuBitable] 商机异常: {str(e)[:80]}")
    print(f"[FeishuBitable] 商机池写入完成: ✅{ok} ❌{fail}")
    return fail == 0


# 兼容旧名字
def send_daily(items: list) -> bool:
    """兼容旧调用名（v1.1 用），等价于 send_opportunities"""
    return send_opportunities(items)


# ============ 内容草稿 ============

def _build_draft_fields(content: dict) -> dict:
    """把 content_factory.generate_one 输出转成「内容草稿」表 fields

    字段映射（按草稿表 schema）：
    - 商机标题（主字段）= 原商机标题
    - 商机链接 = {link, text}
    - xhs标题 / xhs正文 / xhs标签 / xhs配图 / xhs发布要点
    - zh标题1_理性 / zh标题2_悬念 / zh标题3_实用 / zh正文 / zh关键点 / zh配图 / zh发布要点
    - 状态 = "待发"
    - 生成时间 = int timestamp ms
    """
    it = content.get("analysis", {})
    xhs = content.get("xhs", {})
    zh = content.get("zh", {})
    title = content.get("title", "")

    fields = {
        "商机标题": title[:500],
        "商机链接": {"link": content.get("url", ""), "text": title[:50] or "查看"},
        "xhs标题":     (xhs.get("title") or "")[:300],
        "xhs正文":     (xhs.get("body") or "")[:3000],
        "xhs标签":     xhs.get("hashtags") or [],
        "xhs配图":     "\n".join(xhs.get("image_prompts") or [])[:2000],
        "xhs发布要点": (xhs.get("publish_tip") or "")[:500],
    }
    titles = zh.get("titles") or ["", "", ""]
    while len(titles) < 3:
        titles.append("")
    fields.update({
        "zh标题1_理性": titles[0][:300],
        "zh标题2_悬念": titles[1][:300],
        "zh标题3_实用": titles[2][:300],
        "zh正文":       (zh.get("body") or "")[:5000],
        "zh关键点":     "\n".join(zh.get("key_points") or [])[:2000],
        "zh配图":       "\n".join(zh.get("image_prompts") or [])[:2000],
        "zh发布要点":   (zh.get("publish_tip") or "")[:500],
        "状态":     "待发",
        "生成时间": int(datetime.now().timestamp() * 1000),
    })
    return fields


def append_jsonl(content: dict) -> Path:
    """把草稿追加到本地 JSONL（兜底，永远可用）"""
    DATA_DIR.mkdir(exist_ok=True, parents=True)
    with open(DRAFTS_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(content, ensure_ascii=False) + "\n")
    return DRAFTS_JSONL


def send_drafts(content: dict, app_token: str = None, table_id: str = None) -> bool:
    """写一条内容草稿到「内容草稿」表（同时本地 JSONL 落盘）"""
    # 1. 本地落盘永远先做
    jsonl_path = append_jsonl(content)

    # 2. 多维表格写入（可选）
    app_token = app_token or os.getenv("DRAFTS_BITABLE_APP_TOKEN", "")
    table_id  = table_id  or os.getenv("DRAFTS_BITABLE_TABLE_ID", "")
    if not app_token or not table_id:
        print(f"[FeishuBitable] 内容草稿表未配置 APP_TOKEN/TABLE_ID → 仅本地 JSONL 落盘到 {jsonl_path}")
        return True

    try:
        headers = _auth_headers()
    except Exception as e:
        print(f"[FeishuBitable] {e} → 本地已落盘")
        return False

    url = f"{API_BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/records"
    try:
        data = _http_post_json(url, headers, {"fields": _build_draft_fields(content)})
        if data.get("code") == 0:
            print(f"[FeishuBitable] ✅ 内容草稿已写入多维表格 + 本地 JSONL")
            return True
        print(f"[FeishuBitable] ❌ 内容草稿多维表格写入失败: {data.get('msg', '')[:120]}")
        print(f"[FeishuBitable]    本地 JSONL 仍保留在 {jsonl_path}")
        return False
    except Exception as e:
        print(f"[FeishuBitable] 异常: {str(e)[:120]}")
        return False
