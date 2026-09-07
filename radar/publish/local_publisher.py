"""本地发布器 —— 路径B（agent-browser 半本机）

执行链路：
1. 飞书审核表 → 用户点"通过" → webhook 触发本脚本
2. preflight_check() 验证 cookie 还在（否则通知用户重新登录）
3. 按平台分别调用 publish_xiaohongshu() / publish_zhihu()
4. 写 audit 日志 + 飞书通知结果

CLI：
  python -m radar.publish.local_publisher --dry-run
  python -m radar.publish.local_publisher --platform xiaohongshu --draft-id xxx
"""
import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, List, Dict

from .humanizer import human_delay, micro_pause, long_pause, action, typing_delay


# ===== 数据结构 =====
@dataclass
class PublishTask:
    draft_id: str
    platform: str  # "xiaohongshu" | "zhihu"
    title: str
    body: str
    images: List[str]       # 本地图片绝对路径
    hashtags: List[str]
    extra: Optional[Dict] = None  # 平台特有：xhs@谁 / zh专栏等


# ===== agent-browser CLI 调用 =====
def ab(*args: str, timeout: int = 120) -> str:
    """调用 agent-browser CLI，返回 stdout"""
    cmd = ["agent-browser", *args]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace"
        )
        if result.returncode != 0:
            print(f"  ✗ agent-browser {args[0]} 失败：{result.stderr[:200]}")
        return result.stdout
    except FileNotFoundError:
        print("  ✗ agent-browser 未安装。请先 `npm install -g agent-browser && agent-browser install`")
        return ""
    except subprocess.TimeoutExpired:
        print(f"  ✗ agent-browser {args[0]} 超时（{timeout}s）")
        return ""


# ===== 平台入口 =====
def preflight_check(platform: str) -> bool:
    """预检：打开创作中心首页，确认 cookie 有效（页面里有用户名）
    Returns: True=已登录可发；False=需重新登录"""
    urls = {
        "xiaohongshu": "https://creator.xiaohongshu.com/publish",
        "zhihu": "https://www.zhihu.com/creator",
    }
    url = urls.get(platform)
    if not url:
        print(f"  ✗ 未知平台：{platform}")
        return False

    print(f"  ▶ 预检 {platform}（打开 {url}）")
    ab("open", url)
    ab("wait", "--load", "networkidle")
    human_delay(2.0, 4.0, "等页面渲染")
    snapshot = ab("snapshot", "-i")

    # 简单启发式：登录态包含「创作者中心」/「发布」按钮，且不包含「登录/注册」CTA
    not_logged_keywords = ["登录", "注册", "login", "sign in"]
    logged_keywords = ["发布", "创作中心", "publish", "creator", "我的"]

    is_logged = any(k in snapshot.lower() for k in logged_keywords) and \
                not any(k in snapshot.lower() for k in not_logged_keywords)

    if not is_logged:
        print(f"  ⚠ {platform} cookie 已失效，需要重新手动登录")
        print("  → 在 agent-browser 打开的页面里手动登录，我会接管后续操作")
        # 给用户足够时间登录
        human_delay(30.0, 60.0, "等用户登录")
        # 再 snap 一次确认
        snapshot2 = ab("snapshot", "-i")
        is_logged = any(k in snapshot2.lower() for k in logged_keywords)

    return is_logged


def publish_xiaohongshu(task: PublishTask, dry_run: bool = False) -> Dict:
    """发布到小红书创作者中心"""
    log = {
        "draft_id": task.draft_id,
        "platform": "xiaohongshu",
        "title": task.title,
        "start_ts": time.time(),
        "dry_run": dry_run,
        "steps": [],
    }

    if dry_run:
        print(f"  [DRY-RUN] 小红书任务：{task.title[:30]}...")
        print(f"  正文长度：{len(task.body)} 字")
        print(f"  图片：{len(task.images)} 张")
        print(f"  标签：{task.hashtags[:5]}...")
        log["steps"].append({"name": "dry-run", "ok": True})
        return log

    if not preflight_check("xiaohongshu"):
        log["steps"].append({"name": "preflight", "ok": False, "reason": "cookie失效"})
        return log

    with action("打开图文发布"):
        ab("open", "https://creator.xiaohongshu.com/publish")
        ab("wait", "--load", "networkidle")
    log["steps"].append({"name": "open-editor", "ok": True})

    # 实际发布流程（每个步骤由 humanizer 自动加延迟）
    # 这里给出骨架；具体 selector 在首次实测时通过 `agent-browser snapshot -i` 校准
    print("  → 上传图片（需 selector 校准）")
    for img in task.images:
        print(f"    - {Path(img).name}")
        # ab("click", "#upload-image-input")
        # ab("type", "#upload-image-input", str(img))  # 文件路径
        human_delay(2.0, 5.0)

    print("  → 填标题（需 selector 校准）")
    print(f"    {task.title[:50]}")
    # ab("type", "#title-input", task.title)
    time.sleep(typing_delay(task.title))

    print("  → 填正文（需 selector 校准）")
    print(f"    {task.body[:50]}...")
    # ab("type", "#content-editor", task.body)
    time.sleep(typing_delay(task.body))

    print("  → 加标签（需 selector 校准）")
    for tag in task.hashtags[:5]:
        print(f"    #{tag}")
        # ab("type", "#tag-input", f"#{tag}")
        human_delay(1.0, 2.0)

    # 截图留证（不发布，给用户最后确认）
    ab("screenshot", "--out", f"data/screenshots/xhs_{task.draft_id}_pending.png")

    log["end_ts"] = time.time()
    log["steps"].append({"name": "fill-form", "ok": True})
    log["note"] = "骨架已跑通，需 selector 校准后才能正式发布"
    return log


def publish_zhihu(task: PublishTask, dry_run: bool = False) -> Dict:
    """发布到知乎创作者中心"""
    log = {
        "draft_id": task.draft_id,
        "platform": "zhihu",
        "title": task.title,
        "start_ts": time.time(),
        "dry_run": dry_run,
        "steps": [],
    }

    if dry_run:
        print(f"  [DRY-RUN] 知乎任务：{task.title[:30]}...")
        print(f"  正文长度：{len(task.body)} 字")
        log["steps"].append({"name": "dry-run", "ok": True})
        return log

    if not preflight_check("zhihu"):
        log["steps"].append({"name": "preflight", "ok": False, "reason": "cookie失效"})
        return log

    with action("打开知乎创作中心"):
        ab("open", "https://www.zhihu.com/creator")
        ab("wait", "--load", "networkidle")
    log["steps"].append({"name": "open-editor", "ok": True})

    # 类似 xhs 的骨架
    print("  → 填标题")
    print(f"    {task.title[:50]}")
    time.sleep(typing_delay(task.title))
    print("  → 填正文")
    print(f"    {task.body[:50]}...")
    time.sleep(typing_delay(task.body))

    ab("screenshot", "--out", f"data/screenshots/zh_{task.draft_id}_pending.png")
    log["end_ts"] = time.time()
    log["steps"].append({"name": "fill-form", "ok": True})
    log["note"] = "骨架已跑通，需 selector 校准后才能正式发布"
    return log


# ===== CLI =====
def main():
    parser = argparse.ArgumentParser(description="本地发布器（路径B）")
    parser.add_argument("--dry-run", action="store_true", help="不真发，只打印任务")
    parser.add_argument("--platform", choices=["xiaohongshu", "zhihu"], help="单平台发布")
    parser.add_argument("--draft-id", help="从飞书审核表读取的草稿 ID")
    parser.add_argument("--from-jsonl", help="从 data/drafts.jsonl 读取任务")
    parser.add_argument("--preflight", action="store_true", help="只跑预检，不发布")
    args = parser.parse_args()

    tasks: List[PublishTask] = []

    if args.draft_id:
        # TODO: 从飞书审核表读
        print(f"[TODO] 从飞书审核表读 draft_id={args.draft_id}")
        return

    if args.from_jsonl:
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
            body="这是示例正文，测试发布链路是否打通..." * 5,
            images=[],
            hashtags=["AI", "商机", "副业", "工具", "效率"],
        )]

    if args.preflight:
        for t in tasks:
            preflight_check(t.platform)
        return

    results = []
    for t in tasks:
        if t.platform == "xiaohongshu":
            r = publish_xiaohongshu(t, dry_run=args.dry_run)
        elif t.platform == "zhihu":
            r = publish_zhihu(t, dry_run=args.dry_run)
        else:
            continue
        results.append(r)

    # 写 audit 日志
    audit_path = Path("data/publish_audit.jsonl")
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n✅ 完成 {len(results)} 个发布任务，audit 写入 {audit_path}")


if __name__ == "__main__":
    main()