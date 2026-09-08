#!/usr/bin/env python3
"""立即发布指定的「通过」记录（按 record_id 白名单，不碰其余记录）

用法：
  python scripts/publish_selected.py <record_id> [<record_id> ...]

安全闸与 audit_gate.process_approved 一致：
  - 仅处理状态=「通过」且在白名单里的记录
  - PUBLISH_ENABLED != on 或本机 19000 服务不可用 → 整轮跳过，不改状态
  - 每条发布成功 → 状态「已发」；失败 → 「失败」+ 错误备注
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from radar.publish.audit_gate import AuditDecision, AuditGate
from radar.publish.local_publisher import check_local_service, publish
from radar.config import PUBLISH_ENABLED


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    list_only = "--list-only" in sys.argv
    wanted = args
    if not wanted:
        print("用法: python scripts/publish_selected.py [--list-only] <record_id> [...]")
        return 2

    gate = AuditGate()
    approved = gate.list_by_status(AuditDecision.APPROVED.value)
    targets = [it for it in approved if it.record_id in wanted]
    found = {it.record_id for it in targets}
    missing = set(wanted) - found
    if missing:
        print(f"✗ 白名单里 {len(missing)} 条不是「通过」状态或不存在: {sorted(missing)}")
        print("  （已通过的记录才可发布；其余状态不处理）")
        return 2
    if not targets:
        print("无匹配记录")
        return 2

    for it in targets:
        print(f"→ 待发布 [{it.platform}] {it.title[:50]}  (record {it.record_id})")

    if list_only:
        print("(--list-only 仅核对，不发布)")
        return 0

    if PUBLISH_ENABLED != "on":
        print(f"✗ PUBLISH_ENABLED={PUBLISH_ENABLED}（非 on），跳过真发")
        return 1
    if not check_local_service():
        print("✗ 本机发布服务(19000)不可用，跳过（审核状态保持不变）")
        return 1

    rc = 0
    for item in targets:
        task = item.to_publish_task()
        print(f"\n=== 发布 [{item.platform}] {item.title[:40]} ===")
        log = publish(task)
        ok = all(s.get("ok") for s in log.get("steps", [])) and log.get("result", {}).get("ok")
        if ok:
            note = f"已发布 @ {time.strftime('%Y-%m-%d %H:%M')}"
            gate.mark_status(item.record_id, AuditDecision.PUBLISHED, note)
            print(f"✅ 发布成功 → 状态「已发」")
        else:
            err = log.get("result", {}).get("error", "未知错误")
            gate.mark_status(item.record_id, AuditDecision.FAILED, str(err)[:500])
            print(f"❌ 发布失败 → 状态「失败」: {err}")
            rc = 1
    print(f"\n完成，发布成功 {'是' if rc == 0 else '否'}（失败详情见上）")
    return rc


if __name__ == "__main__":
    sys.exit(main())
