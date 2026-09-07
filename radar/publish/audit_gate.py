"""内容预审闸

工作流：
1. M2 生成草稿 → 写飞书「内容审核表」状态="待审"
2. 欢欢在飞书打开表 → 改状态="通过"或"拒绝"（可在「审核备注」填理由）
3. AuditGate 定时轮询（或 webhook 触发）→ 找出"通过"的草稿
4. 调用 local_publisher.publish() 发布
5. 更新状态为"已发"或"失败"

CLI：
  python -m radar.publish.audit_gate --poll     # 轮询一次
  python -m radar.publish.audit_gate --list     # 列出待审草稿
  python -m radar.publish.audit_gate --mark-id xxx --status 已发
"""
import json
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional

from radar.config import (
    FEISHU_APP_ID, FEISHU_APP_SECRET,
    FEISHU_AUDIT_APP_TOKEN, FEISHU_AUDIT_TABLE_ID,
)
from radar.publish.local_publisher import PublishTask, publish
from radar.notify.feishu_bitable import BitableClient


class AuditDecision(str, Enum):
    PENDING = "待审"
    APPROVED = "通过"
    REJECTED = "拒绝"
    PUBLISHED = "已发"
    FAILED = "失败"


@dataclass
class AuditItem:
    record_id: str       # 飞书 record_id
    draft_id: str
    platform: str
    title: str
    body: str
    images: list
    hashtags: list
    status: str
    note: str
    created_at: str

    def to_publish_task(self) -> PublishTask:
        return PublishTask(
            draft_id=self.draft_id,
            platform=self.platform,
            title=self.title,
            body=self.body,
            images=self.images or [],
            hashtags=self.hashtags or [],
        )


def _field_text(value):
    """把飞书单选/多选字段值统一转成字符串"""
    if isinstance(value, dict):
        return value.get("text", "")
    if isinstance(value, list):
        parts = []
        for v in value:
            if isinstance(v, dict):
                parts.append(v.get("text", ""))
            else:
                parts.append(str(v))
        return ",".join(parts)
    return str(value)


class AuditGate:
    """飞书审核表读写 + 发布调度"""

    def __init__(self):
        if not (FEISHU_APP_ID and FEISHU_APP_SECRET and FEISHU_AUDIT_APP_TOKEN and FEISHU_AUDIT_TABLE_ID):
            raise ValueError(
                "未配置飞书审核表。请设置环境变量：FEISHU_APP_ID / FEISHU_APP_SECRET / "
                "FEISHU_AUDIT_APP_TOKEN / FEISHU_AUDIT_TABLE_ID"
            )
        self.client = BitableClient(
            app_id=FEISHU_APP_ID,
            app_secret=FEISHU_APP_SECRET,
            app_token=FEISHU_AUDIT_APP_TOKEN,
        )
        self.table_id = FEISHU_AUDIT_TABLE_ID

    def list_by_status(self, status: str) -> List[AuditItem]:
        """按状态过滤"""
        records = self.client.search_records(self.table_id, {"状态": status}, limit=500)
        return [self._record_to_item(r) for r in records]

    def mark_status(self, record_id: str, status: AuditDecision, note: str = ""):
        """更新状态"""
        fields = {"状态": status.value}
        if note:
            fields["审核备注"] = note
        self.client.update_record(self.table_id, record_id, fields)

    def process_approved(self, dry_run: bool = False) -> dict:
        """拉所有「通过」的草稿，发布，更新状态"""
        approved = self.list_by_status(AuditDecision.APPROVED.value)
        print(f"→ 拉到 {len(approved)} 个待发布草稿")

        results = {"published": 0, "failed": 0, "details": []}
        for item in approved:
            task = item.to_publish_task()
            log = publish(task, dry_run=dry_run)

            success = all(s.get("ok") for s in log.get("steps", [])) and log.get("result", {}).get("ok")
            if dry_run:
                self.mark_status(item.record_id, AuditDecision.PENDING, "[dry-run] 未实际发布")
                results["details"].append({"draft_id": item.draft_id, "dry_run": True})
            elif success:
                self.mark_status(item.record_id, AuditDecision.PUBLISHED, f"已发布 @ {time.strftime('%Y-%m-%d %H:%M')}")
                results["published"] += 1
            else:
                err = log.get("result", {}).get("error", "未知错误")
                self.mark_status(item.record_id, AuditDecision.FAILED, err)
                results["failed"] += 1
            results["details"].append({"draft_id": item.draft_id, "success": success, "log": log})

        return results

    def _record_to_item(self, record: dict) -> AuditItem:
        f = record.get("fields", {})
        platform = _field_text(f.get("平台", "xiaohongshu")).lower()
        if platform in ("小红书", "xiaohongshu"):
            platform = "xiaohongshu"
        elif platform in ("知乎", "zhihu"):
            platform = "zhihu"

        tags = _field_text(f.get("标签", ""))
        hashtags = [t.strip().lstrip("#") for t in tags.split(",") if t.strip()]

        return AuditItem(
            record_id=record.get("record_id", ""),
            draft_id=_field_text(f.get("草稿ID", "")),
            platform=platform,
            title=_field_text(f.get("标题", "")),
            body=_field_text(f.get("正文", "")),
            images=f.get("图片", []) or [],
            hashtags=hashtags,
            status=_field_text(f.get("状态", AuditDecision.PENDING.value)),
            note=_field_text(f.get("审核备注", "")),
            created_at=_field_text(f.get("生成时间", "")),
        )


def main():
    import argparse
    parser = argparse.ArgumentParser(description="内容预审闸")
    parser.add_argument("--list", choices=["pending", "approved", "all"], help="列出草稿")
    parser.add_argument("--poll", action="store_true", help="轮询：拉已通过→发布→更新状态")
    parser.add_argument("--dry-run", action="store_true", help="跑一遍但不真发")
    args = parser.parse_args()

    gate = AuditGate()

    if args.list == "pending":
        for item in gate.list_by_status(AuditDecision.PENDING.value):
            print(f"[{item.status}] {item.draft_id} | {item.platform} | {item.title[:40]}")
    elif args.list == "approved":
        for item in gate.list_by_status(AuditDecision.APPROVED.value):
            print(f"[{item.status}] {item.draft_id} | {item.platform} | {item.title[:40]}")
    elif args.list == "all":
        for item in gate.list_by_status(AuditDecision.PENDING.value) + gate.list_by_status(AuditDecision.APPROVED.value):
            print(f"[{item.status}] {item.draft_id} | {item.platform} | {item.title[:40]}")
    elif args.poll:
        result = gate.process_approved(dry_run=args.dry_run)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
