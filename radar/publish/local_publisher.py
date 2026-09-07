"""本地发布器 —— 路径 B（本机 Playwright 服务）

执行链路：
1. 飞书审核表 → 用户点"通过" → webhook/轮询触发本脚本
2. 按平台封装任务，调用本机服务 http://localhost:19000/publish
3. 本机服务复用用户 Edge 登录态，在本地浏览器里完成发布
4. 写 audit 日志 + 更新飞书审核表状态

环境变量：
  LOCAL_PUBLISHER_URL=http://localhost:19000  默认
  PUBLISH_DRY_RUN=1                           只演练不点发布

CLI：
  python -m radar.publish.local_publisher --dry-run
  python -m radar.publish.local_publisher --platform xiaohongshu --draft-id xxx
  python -m radar.publish.local_publisher --from-jsonl data/drafts.jsonl
"""
import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, List, Dict

import requests

from radar.config import FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_BITABLE_APP_TOKEN, FEISHU_AUDIT_TABLE_ID
from radar.notify.feishu_bitable import BitableClient
from .humanizer import human_delay


LOCAL_PUBLISHER_URL = os.environ.get("LOCAL_PUBLISHER_URL", "http://localhost:19000").rstrip("/")


@dataclass
class PublishTask:
    draft_id: str
    platform: str  # "xiaohongshu" | "zhihu"
    title: str
    body: str
    images: List[str] = None       # 本地图片绝对路径
    hashtags: List[str] = None
    extra: Optional[Dict] = None  # 平台特有

    def __post_init__(self):
        if self.images is None:
            self.images = []
        if self.hashtags is None:
            self.hashtags = []


def check_local_service(timeout: int = 5) -> bool:
    """检查本机发布服务是否存活"""
    try:
        r = requests.get(f"{LOCAL_PUBLISHER_URL}/health", timeout=timeout)
        data = r.json()
        ok = data.get("ok") and data.get("edge") and data.get("userData")
        if not ok:
            print(f"  ⚠ 本机服务健康检查异常：{data}")
        return ok
    except Exception as e:
        print(f"  ✗ 本机服务未启动或无法连接：{e}")
        print(f"  → 请先运行：D:\\WorkBuddy\\Make monney\\本地发布服务\\start.cmd")
        return False


def call_local_service(task: PublishTask, dry_run: bool = False) -> Dict:
    """调本机 webhook 完成发布"""
    payload = {
        "platform": task.platform,
        "title": task.title,
        "body": task.body,
        "tags": task.hashtags,
        "coverImage": task.images[0] if task.images else None,
        "dryRun": dry_run,
    }
    try:
        r = requests.post(f"{LOCAL_PUBLISHER_URL}/publish", json=payload, timeout=120)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        return {"ok": False, "error": str(e)}


def update_audit_status(record_id: str, status: str, note: str = "") -> bool:
    """更新飞书审核表状态"""
    if not FEISHU_AUDIT_TABLE_ID:
        print("  ⚠ FEISHU_AUDIT_TABLE_ID 未配置，跳过飞书回写")
        return False
    try:
        client = BitableClient()
        client.update_record(FEISHU_AUDIT_TABLE_ID, record_id, {
            "状态": status,
            "审核备注": note,
        })
        return True
    except Exception as e:
        print(f"  ✗ 更新飞书审核表失败：{e}")
        return False


def publish(task: PublishTask, dry_run: bool = False) -> Dict:
    """发布一条任务，返回日志"""
    log = {
        "draft_id": task.draft_id,
        "platform": task.platform,
        "title": task.title,
        "start_ts": time.time(),
        "dry_run": dry_run,
        "steps": [],
    }

    if not check_local_service():
        log["steps"].append({"name": "health-check", "ok": False})
        return log

    print(f"  ▶ 发布 {task.platform}: {task.title[:40]}...")
    result = call_local_service(task, dry_run=dry_run)
    log["result"] = result
    log["end_ts"] = time.time()

    if result.get("ok"):
        log["steps"].append({"name": "publish", "ok": True, "status": result.get("result", {}).get("status")})
        print(f"  ✅ {task.platform} 处理完成：{result}")
    else:
        log["steps"].append({"name": "publish", "ok": False, "error": result.get("error")})
        print(f"  ✗ {task.platform} 失败：{result.get('error')}")

    return log


def pull_approved_tasks(limit: int = 3) -> List[PublishTask]:
    """从飞书审核表拉「通过」状态的记录"""
    if not FEISHU_AUDIT_TABLE_ID:
        print("✗ FEISHU_AUDIT_TABLE_ID 未配置")
        return []

    client = BitableClient()
    # 状态 = 通过
    records = client.search_records(FEISHU_AUDIT_TABLE_ID, {"状态": "通过"}, limit=limit)
    tasks = []
    for rec in records:
        fields = rec.get("fields", {})
        platform = fields.get("平台", "")
        if isinstance(platform, dict):  # 单选字段可能是 dict
            platform = platform.get("text", "")
        platform = platform.lower()
        if platform in ("小红书", "xiaohongshu"):
            platform = "xiaohongshu"
        elif platform in ("知乎", "zhihu"):
            platform = "zhihu"
        else:
            continue

        title = fields.get("标题", "")
        body = fields.get("正文", "")
        tags = fields.get("标签", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.replace("#", "").split(",") if t.strip()]

        tasks.append(PublishTask(
            draft_id=rec.get("record_id"),
            platform=platform,
            title=title,
            body=body,
            hashtags=tags,
        ))
    return tasks


def main():
    parser = argparse.ArgumentParser(description="本地发布器（路径 B：本机 Playwright 服务）")
    parser.add_argument("--dry-run", action="store_true", help="不真发，只演练")
    parser.add_argument("--platform", choices=["xiaohongshu", "zhihu"], help="单平台发布")
    parser.add_argument("--draft-id", help="从飞书审核表读取的草稿 record_id")
    parser.add_argument("--from-jsonl", help="从 data/drafts.jsonl 读取任务")
    parser.add_argument("--pull-audit", action="store_true", help="拉审核表中「通过」的任务并发")
    args = parser.parse_args()

    dry_run = args.dry_run or os.environ.get("PUBLISH_DRY_RUN") == "1"
    tasks: List[PublishTask] = []

    if args.pull_audit:
        print("→ 从飞书审核表拉「通过」任务...")
        tasks = pull_approved_tasks(limit=int(os.environ.get("PUBLISH_DAILY_LIMIT", "3")))
        print(f"  拉到 {len(tasks)} 条待发布任务")
    elif args.draft_id:
        # TODO: 从飞书审核表读单条
        print(f"[TODO] 从飞书审核表读 draft_id={args.draft_id}")
        return
    elif args.from_jsonl:
        path = Path(args.from_jsonl)
        if not path.exists():
            print(f"✗ {path} 不存在")
            sys.exit(1)
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            tasks.append(PublishTask(**data))
    else:
        # 示例 dry-run 任务
        tasks = [PublishTask(
            draft_id="demo-001",
            platform=args.platform or "xiaohongshu",
            title="示例：用 AI 帮你批量整理商机（7 天实测）",
            body="这是示例正文，测试发布链路是否打通。" * 5,
            images=[],
            hashtags=["AI", "商机", "副业", "工具", "效率"],
        )]

    if not tasks:
        print("没有待发布任务，退出")
        return

    results = []
    for t in tasks:
        r = publish(t, dry_run=dry_run)
        results.append(r)
        human_delay(2.0, 5.0, "任务间隔")

    # 写 audit 日志
    audit_path = Path("data/publish_audit.jsonl")
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n✅ 完成 {len(results)} 个发布任务，audit 写入 {audit_path}")


if __name__ == "__main__":
    main()
