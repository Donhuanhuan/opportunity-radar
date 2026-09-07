# -*- coding: utf-8 -*-
"""一次性运维脚本：清理审核表脏数据
1. 找出所有字段全空的记录 → 删除
2. 小红书赵一鸣那条（待审+演练暂缓）→ 标「拒绝」归档
用法: python scripts/cleanup_audit.py [--apply]
默认只打印不执行，加 --apply 才真删/真改。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from radar.config import (
    FEISHU_APP_ID, FEISHU_APP_SECRET,
    FEISHU_AUDIT_APP_TOKEN, FEISHU_AUDIT_TABLE_ID,
)
from radar.notify.feishu_bitable import BitableClient, _http_post_json, API_BASE

APPLY = "--apply" in sys.argv

client = BitableClient(
    app_id=FEISHU_APP_ID,
    app_secret=FEISHU_APP_SECRET,
    app_token=FEISHU_AUDIT_APP_TOKEN,
)


def delete_records(record_ids):
    """批量删除记录（飞书 batch_delete API）"""
    headers = client._headers()
    url = f"{API_BASE}/bitable/v1/apps/{FEISHU_AUDIT_APP_TOKEN}/tables/{FEISHU_AUDIT_TABLE_ID}/records/batch_delete"
    r = _http_post_json(url, headers, {"records": record_ids})
    if r.get("code") != 0:
        raise RuntimeError(f"批量删除失败: {r}")
    return r


def is_empty(fields: dict) -> bool:
    """除生成时间/状态外所有实质字段都为空 → 视为脏数据"""
    for k, v in fields.items():
        if k in ("生成时间",):
            continue
        if v in (None, "", [], {}):
            continue
        # 状态字段默认"待审"也算空
        if k == "状态" and str(v) in ("待审", ""):
            continue
        return False
    return True


def main():
    records = client.list_records(FEISHU_AUDIT_TABLE_ID)
    print(f"→ 审核表共 {len(records)} 条记录\n")

    empty_ids, xhs_target = [], None
    for rec in records:
        f = rec.get("fields", {})
        rid = rec.get("record_id", "")
        title = f.get("商机标题") or f.get("标题") or ""
        if isinstance(title, list) and title and isinstance(title[0], dict):
            title = title[0].get("text", "")

        if is_empty(f):
            empty_ids.append(rid)
            print(f"[空记录] {rid}")
            continue

        t = str(title)
        note = f.get("审核备注") or ""
        if isinstance(note, list):
            note = ",".join(str(x) for x in note)
        platform = f.get("平台") or ""
        if isinstance(platform, dict):
            platform = platform.get("text", "")
        if "赵一鸣" in t and "小红书" in str(platform):
            xhs_target = (rid, t[:40], str(f.get("状态", "")))
            print(f"[小红书赵一鸣] {rid} | {t[:40]} | 状态={f.get('状态')} | 备注={note[:50]}")

    print(f"\n=== 汇总 ===")
    print(f"空记录: {len(empty_ids)} 条 → {empty_ids}")
    print(f"小红书赵一鸣: {xhs_target}")

    if not APPLY:
        print("\n(预览模式，未执行任何修改。加 --apply 生效)")
        return

    if empty_ids:
        r = delete_records(empty_ids)
        print(f"✅ 已删除 {len(empty_ids)} 条空记录: {r.get('code')}")
    if xhs_target:
        client.update_record(FEISHU_AUDIT_TABLE_ID, xhs_target[0], {
            "状态": "拒绝",
            "审核备注": "热点已过，归档（2026-09-07 复盘决策：小红书配图链路未接入前暂缓）",
        })
        print(f"✅ 小红书赵一鸣已标「拒绝」: {xhs_target[0]}")


if __name__ == "__main__":
    main()
