"""飞书多维表格推送（兼容 requests / urllib 双模式）

支持双表：
1. 商机池（FEISHU_BITABLE_APP_TOKEN + TABLE_ID） —— send_opportunities()
2. 内容草稿（DRAFTS_BITABLE_APP_TOKEN + TABLE_ID） —— send_drafts()
3. 本地落盘（JSONL） —— append_jsonl() 永远可用，作为草稿的最终兜底
"""
import json
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
    DRAFTS_BITABLE_APP_TOKEN, DRAFTS_BITABLE_TABLE_ID,
    HEADERS,
)

API_BASE = "https://open.feishu.cn/open-apis"
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DRAFTS_JSONL = DATA_DIR / "drafts.jsonl"

# === Token 模块级缓存 ===
_TOKEN_CACHE = {"token": None, "expire_at": 0}


# ============ BitableClient：实例化客户端（用于建表等高级操作）============

class BitableClient:
    """飞书多维表格客户端 + API 封装

    用法：
        client = BitableClient(app_id, app_secret, app_token)
        client.create_table("内容审核", schema_dict)  # 返回 {"table_id": "..."}
    """
    def __init__(self, app_id: str = None, app_secret: str = None, app_token: str = None):
        self.app_id = app_id or FEISHU_APP_ID
        self.app_secret = app_secret or FEISHU_APP_SECRET
        self.app_token = app_token or FEISHU_BITABLE_APP_TOKEN
        if not (self.app_id and self.app_secret and self.app_token):
            raise RuntimeError("BitableClient: app_id / app_secret / app_token 不能为空")

    def _headers(self) -> dict:
        return {**HEADERS, "Authorization": f"Bearer {_get_tenant_token()}"}

    def create_table(self, table_name: str, schema: dict, default_name_field: str = None) -> dict:
        """在 app_token 下新建一张表

        schema: {字段名: {type: 1|3|4|5|15, property: {...}}, ...}
            1 = text, 3 = single-select, 4 = multi-select, 5 = date, 15 = url
        返回 {"table_id": "..."}
        """
        # 1. 先建表（只带 table.name + 默认 "文本" 主字段）
        body = {
            "table": {
                "name": table_name,
                "default_column_name": default_name_field or (list(schema.keys())[0] if schema else "标题"),
            }
        }
        r = _http_post_json(
            f"{API_BASE}/bitable/v1/apps/{self.app_token}/tables",
            self._headers(), body,
        )
        if r.get("code") != 0:
            raise RuntimeError(f"建表失败: {r}")
        table_id = r["data"]["table_id"]

        # 2. 逐字段添加（飞书要求循环单字段对象，不能传 fields:[]）
        for field_name, spec in schema.items():
            field_body = {
                "field_name": field_name,
                "type": spec.get("type", 1),
            }
            prop = spec.get("property") or {}
            if prop:
                field_body["property"] = prop
            r2 = _http_post_json(
                f"{API_BASE}/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields",
                self._headers(), field_body,
            )
            if r2.get("code") != 0:
                print(f"⚠️ 字段 {field_name} 创建失败: {r2}")
                continue

        return {"table_id": table_id, "name": table_name}

    def list_records(self, table_id: str, page_size: int = 500) -> list:
        """列出表中所有记录"""
        url = f"{API_BASE}/bitable/v1/apps/{self.app_token}/tables/{table_id}/records"
        records = []
        page_token = None
        while True:
            params = {"page_size": min(page_size, 500)}
            if page_token:
                params["page_token"] = page_token
            r = _http_get_json(url, self._headers(), params=params)
            if r.get("code") != 0:
                raise RuntimeError(f"拉记录失败: {r}")
            items = r["data"].get("items", [])
            records.extend(items)
            if not r["data"].get("has_more"):
                break
            page_token = r["data"].get("page_token")
        return records

    def search_records(self, table_id: str, filters: dict = None, limit: int = 500) -> list:
        """按字段值过滤记录（简单内存过滤；复杂场景建议改用飞书 filter API）

        filters: {"状态": "通过"}
        """
        all_records = self.list_records(table_id)
        if not filters:
            return all_records[:limit]
        results = []
        for rec in all_records:
            fields = rec.get("fields", {})
            match = True
            for k, v in filters.items():
                fv = fields.get(k)
                # 单选字段可能是 dict {"text":"..."} 或 list
                if isinstance(fv, dict):
                    fv = fv.get("text", "")
                elif isinstance(fv, list) and fv and isinstance(fv[0], dict):
                    fv = ",".join(x.get("text", "") for x in fv)
                if str(fv) != str(v):
                    match = False
                    break
            if match:
                results.append(rec)
                if len(results) >= limit:
                    break
        return results

    def create_record(self, table_id: str, fields: dict) -> dict:
        """新建单条记录（返回含 record_id 的 record 对象）"""
        url = f"{API_BASE}/bitable/v1/apps/{self.app_token}/tables/{table_id}/records"
        body = {"fields": fields}
        r = _http_post_json(url, self._headers(), body)
        if r.get("code") != 0:
            raise RuntimeError(f"创建记录失败: {r}")
        return r["data"]["record"]

    def update_record(self, table_id: str, record_id: str, fields: dict) -> dict:
        """更新单条记录

        fields: {"状态": "已发", "审核备注": "成功"}
        """
        url = f"{API_BASE}/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/{record_id}"
        body = {"fields": fields}
        return _http_put_json(url, self._headers(), body)


# === 内容草稿表 schema（17 字段）===
DRAFTS_TABLE_SCHEMA = {
    "商机标题":     {"type": 1, "property": {}},                              # text（主字段）
    "商机链接":     {"type": 15, "property": {}},                             # url
    "xhs标题":      {"type": 1, "property": {}},
    "xhs正文":      {"type": 1, "property": {}},
    "xhs标签":      {"type": 4, "property": {}},                              # multi-select
    "xhs配图":      {"type": 1, "property": {}},
    "xhs发布要点":  {"type": 1, "property": {}},
    "zh标题1_理性": {"type": 1, "property": {}},
    "zh标题2_悬念": {"type": 1, "property": {}},
    "zh标题3_实用": {"type": 1, "property": {}},
    "zh正文":       {"type": 1, "property": {}},
    "zh关键点":     {"type": 1, "property": {}},
    "zh配图":       {"type": 1, "property": {}},
    "zh发布要点":   {"type": 1, "property": {}},
    "状态":         {"type": 3, "property": {                                 # single-select
        "options": [
            {"name": "待发", "color": 0},
            {"name": "已发小红书", "color": 5},
            {"name": "已发知乎", "color": 5},
            {"name": "双发", "color": 2},
            {"name": "跳过", "color": 7},
        ]
    }},
    "生成时间":     {"type": 5, "property": {"date_formatter": "yyyy-MM-dd HH:mm"}},
}


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


def _http_get_json(url: str, headers: dict, params: dict = None, timeout: int = 10) -> dict:
    if _HAS_REQUESTS:
        r = requests.get(url, headers=headers, params=params, timeout=timeout)
        return r.json()
    full_url = url
    if params:
        from urllib.parse import urlencode
        full_url = f"{url}?{urlencode(params)}"
    req = urllib.request.Request(full_url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _http_put_json(url: str, headers: dict, body: dict, timeout: int = 10) -> dict:
    if _HAS_REQUESTS:
        r = requests.put(url, headers=headers, json=body, timeout=timeout)
        return r.json()
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={**headers, "Content-Type": "application/json"}, method="PUT")
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
    app_token = app_token or DRAFTS_BITABLE_APP_TOKEN
    table_id  = table_id  or DRAFTS_BITABLE_TABLE_ID
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
