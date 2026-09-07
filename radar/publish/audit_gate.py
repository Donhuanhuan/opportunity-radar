"""内容预审闸

工作流：
1. M2 生成草稿 → 写飞书「内容审核表」状态="待审"
2. 欢欢在飞书打开表 → 改状态="通过"或"拒绝"（可在「审核备注」填理由）
3. AuditGate 定时轮询（或 webhook 触发）→ 找出"通过"的草稿
4. 调用 local_publisher 发布
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
    FEISHU_BITABLE_APP_TOKEN, FEISHU_AUDIT_TABLE_ID,
)
from radar.publish.local_publisher import PublishTask, publish_xiaohongshu, publish_zhihu


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


class AuditGate:
    """飞书审核表读写"""

    def __init__(self):
        if not (FEISHU_APP_ID and FEISHU_APP_SECRET and FEISHU_BITABLE_APP_TOKEN and FEISHU_AUDIT_TABLE_ID):
            raise ValueError(
                "未配置飞书审核表。请设置环境变量：FEISHU_APP_ID / FEISHU_APP_SECRET / "
                "FEISHU_BITABLE_APP_TOKEN / FEISHU_AUDIT_TABLE_ID"
            )
        # 复用 feishu_bitable 的客户端
        from radar.notify.feishu_bitable import BitableClient
        self.client = BitableClient(
            app_id=FEISHU_APP_ID,
            app_secret=FEISHU_APP_SECRET,
            app_token=FEISHU_BITABLE_APP_TOKEN,
        )
        self.table_id = FEISHU_AUDIT_TABLE_ID

    def list_pending(self) -> List[AuditItem]:
        """列出所有「待审」草稿"""
        records = self.client.list_records(self.table_id, filter_conjuncts=[
            {"field_name": "状态", "operator": "is", "value": AuditDecision.PENDING.value}
        ])
        return [self._record_to_item(r) for r in records]

    def list_approved(self) -> List[AuditItem]:
        """列出所有「通过」待发布草稿"""
        records = self.client.list_records(self.table_id, filter_conjuncts=[
            {"field_name": "状态", "operator": "is", "value": AuditDecision.APPROVED.value}
        ])
        return [self._record_to_item(r) for r in records]

    def mark_status(self, record_id: str, status: AuditDecision, note: str = ""):
        """更新状态"""
        fields = {"状态": status.value}
        if note:
            fields["审核备注"] = (fields.get("审核备注", "") + "\n" + note).strip()
        self.client.update_record(self.table_id, record_id, fields)

    def process_approved(self, dry_run: bool = False) -> dict:
        """拉所有「通过」的草稿，发布，更新状态"""
        approved = self.list_approved()
        print(f"→ 拉到 {len(approved)} 个待发布草稿")

        results = {"published": 0, "failed": 0, "details": []}
        for item in approved:
            task = item.to_publish_task()
            if task.platform == "xiaohongshu":
                log = publish_xiaohongshu(task, dry_run=dry_run)
            elif task.platform == "zhihu":
                log = publish_zhihu(task, dry_run=dry_run)
            else:
                results["details"].append({"draft_id": item.draft_id, "error": "未知平台"})
                continue

            # 任何步骤失败 → 标记失败
            success = all(s.get("ok") for s in log.get("steps", [])) and not log.get("dry_run")
            if dry_run:
                self.mark_status(item.record_id, AuditDecision.PENDING, "[dry-run] 未实际发布")
                results["details"].append({"draft_id": item.draft_id, "dry_run": True})
            elif success:
                self.mark_status(item.record_id, AuditDecision.PUBLISHED, f"已发布 @ {time.strftime('%Y-%m-%d %H:%M')}")
                results["published"] += 1
            else:
                self.mark_status(item.record_id, AuditDecision.FAILED, "发布过程中出错")
                results["failed"] += 1
            results["details"].append({"draft_id": item.draft_id, "success": success})

        return results

    def _record_to_item(self, record: dict) -> AuditItem:
        f = record.get("fields", {})
        return AuditItem(
            record_id=record.get("record_id", ""),
            draft_id=f.get("草稿ID", ""),
            platform=f.get("平台", "xiaohongshu"),
            title=f.get("标题", ""),
            body=f.get("正文", ""),
            images=f.get("图片", []) or [],
            hashtags=f.get("标签", []) or [],
            status=f.get("状态", AuditDecision.PENDING.value),
            note=f.get("审核备注", ""),
            created_at=f.get("生成时间", ""),
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
        for item in gate.list_pending():
            print(f"[{item.status}] {item.draft_id} | {item.platform} | {item.title[:40]}")
    elif args.list == "approved":
        for item in gate.list_approved():
            print(f"[{item.status}] {item.draft_id} | {item.platform} | {item.title[:40]}")
    elif args.list == "all":
        for item in gate.list_pending() + gate.list_approved():
            print(f"[{item.status}] {item.draft_id} | {item.platform} | {item.title[:40]}")
    elif args.poll:
        result = gate.process_approved(dry_run=args.dry_run)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()