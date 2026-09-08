#!/usr/bin/env python3
"""失败自动补执行 watchdog（标准库实现，零第三方依赖）。

用途：每天北京时间 9:00(UTC 01:00) 的「商机雷达」主任务若失败/未触发，
本脚本在补跑轮次被调用时通过 GitHub API 重新 dispatch 一次主 workflow。

调度：.github/workflows/retry_daily.yml
  - 北京 10:20（UTC 02:20）第 1 轮检查
  - 北京 12:00（UTC 04:00）第 2 轮检查
判定规则（针对当日 UTC 01:00 起的主 workflow runs）：
  1. 已存在 success            -> 当日产出成功，不补跑
  2. 有 run 还在 queued/运行中  -> 等下一轮再看，不补跑
  3. 失败次数 < MAX_ATTEMPTS   -> 补跑一次（原始 schedule 占 1 次，最多补 2 次）
  4. 失败次数达到上限           -> 停止并返回非 0，便于在 Actions UI 看到告警

环境变量：
  GITHUB_REPOSITORY  自动注入（owner/repo）
  GH_TOKEN           自动注入（secrets.GITHUB_TOKEN，需要 actions: write 权限）
可选：--dry-run 只打印判定不触发 dispatch（本地验证用）
"""
import datetime
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
WORKFLOW = "radar.yml"  # 主任务 workflow 文件名
MAX_ATTEMPTS = int(os.environ.get("MAX_ATTEMPTS", "3"))  # 原始 1 次 + 最多 2 次补跑
DRY = "--dry-run" in sys.argv


def api(method: str, path: str, body: dict | None = None):
    req = urllib.request.Request(API + path, method=method)
    token = os.environ.get("GH_TOKEN", "")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]


def main() -> int:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        print("GITHUB_REPOSITORY 未设置，跳过")
        return 0
    if DRY:
        print("(dry-run 模式：只判定，不触发补跑)")

    # 当日 UTC 01:00 = 北京 9:00 主任务起点
    now = datetime.datetime.now(datetime.timezone.utc)
    day_start = now.replace(hour=1, minute=0, second=0, microsecond=0)
    since = day_start.strftime("%Y-%m-%dT%H:%M:%SZ")

    code, data = api(
        "GET", f"/repos/{repo}/actions/workflows/{WORKFLOW}/runs?per_page=100"
    )
    if code != 200:
        print(f"查询 run 失败 HTTP {code}: {data}")
        return 1

    runs = [
        r for r in data.get("workflow_runs", []) if (r.get("created_at") or "") >= since
    ]
    success = [r for r in runs if r.get("conclusion") == "success"]
    in_progress = [r for r in runs if r.get("status") in ("queued", "in_progress", "waiting")]
    failed = [r for r in runs if r.get("status") == "completed" and r.get("conclusion") != "success"]

    print(
        f"当日 {WORKFLOW} runs={len(runs)} success={len(success)} "
        f"in_progress={len(in_progress)} failed={len(failed)}"
    )

    if success:
        print("当日任务已成功产出，无需补跑")
        return 0
    if in_progress:
        print("有任务仍在运行，等待下一轮检查")
        return 0

    attempts = len(failed)
    if attempts >= MAX_ATTEMPTS:
        print(f"已失败 {attempts} 次（上限 {MAX_ATTEMPTS}），今日不再补跑，请人工介入")
        return 1
    if attempts == 0:
        print("当日主任务未触发（cron 未运行），触发补跑")
    else:
        print(f"当日已失败 {attempts} 次，触发补跑（第 {attempts + 1}/{MAX_ATTEMPTS} 次）")

    if DRY:
        return 0
    s, b = api(
        "POST",
        f"/repos/{repo}/actions/workflows/{WORKFLOW}/dispatches",
        {"ref": "main"},
    )
    print("dispatch:", s, b)
    if s != 204:
        print("补跑触发失败：请确认 retry workflow 有 actions: write 权限")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
