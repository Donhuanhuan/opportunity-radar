#!/usr/bin/env python3
"""
M2 内容工厂入口

调用方式：
1. 跑完 M1 后用：    python -m radar.m2_pipeline --from-scan-stdout < /tmp/items.json
2. 直接喂 JSON：    python -m radar.m2_pipeline --items-file <path>
3. 单元测试：       python -m radar.m2_pipeline --sample

输入：M1 产出的 items（list of dict，含 title/score/source/url/summary/tags）
输出：每条 item 一份双版本文案 → 「内容草稿」飞书多维表格 + 本地 JSONL 落盘

无 LLM key 时自动降级为「模板式生成」，流程永远跑得通。
"""
import argparse
import json
import os
import sys
from datetime import datetime
from typing import Iterable

from content_factory import analyze as do_analyze
from content_factory import generate as do_generate
from radar.notify import feishu_bitable


def _stream_items(args) -> Iterable[dict]:
    """根据 args 决定 items 来源"""
    if args.items_file:
        with open(args.items_file, encoding="utf-8") as f:
            return json.load(f)
    if args.sample:
        return [
            {
                "title": "Cursor launches Agent Mode for autonomous coding",
                "url": "https://cursor.com/blog/agent",
                "source": "hackernews",
                "score": 92,
                "summary": "AI code editor Cursor releases autonomous agent that can read and modify entire projects, supports multi-file edits.",
                "tags": ["hot", "demand"],
            },
            {
                "title": "Show HN: I built a SaaS that replaced my $4k/mo VA",
                "url": "https://example.com/saas",
                "source": "producthunt",
                "score": 75,
                "summary": "Single founder built and launched a $99/mo SaaS automation tool that handles what his VA used to.",
                "tags": ["demand"],
            },
        ]
    # 默认：从 stdin 读
    raw = sys.stdin.read().strip()
    if not raw:
        return []
    return json.loads(raw)


def run(items: list, dry_run: bool = False, top: int = None) -> dict:
    """主流程：每条 item → analyze → generate → send_drafts"""
    if top:
        items = items[:top]

    print(f"🧠 M2 内容工厂启动 @ {datetime.now().isoformat()}")
    print(f"📥 输入: {len(items)} 条商机")
    if not items:
        print("⚠️ 0 条，跳过")
        return {"ok": 0, "fail": 0, "llm_used": "n/a"}

    llm_used_counter = {}
    ok, fail = 0, 0
    produced = []

    for i, item in enumerate(items, 1):
        title = item.get("title", "")[:60]
        print(f"\n━━━ [{i}/{len(items)}] {title} ━━━")
        try:
            a = do_analyze(item)
            content = do_generate(item, a)
            llm_used_counter[a.get("llm_used", "rules")] = llm_used_counter.get(a.get("llm_used", "rules"), 0) + 1

            if dry_run:
                print(f"  🔕 dry-run: 仅生成，未写入多维表格")
                print(f"  📝 xhs title: {content['xhs'].get('title', '')}")
                print(f"  📝 zh  title: {content['zh'].get('titles', [''])[0]}")
                produced.append(content)
                ok += 1
                continue

            # 写入草稿表（同时本地 JSONL 落盘）
            feishu_bitable.send_drafts(content)
            produced.append(content)
            ok += 1
        except Exception as e:
            fail += 1
            print(f"  ❌ 异常: {str(e)[:120]}")

    summary = {
        "ok": ok,
        "fail": fail,
        "llm_used": llm_used_counter,
        "produced_count": len(produced),
        "drafts_path": str(feishu_bitable.DRAFTS_JSONL),
    }
    print(f"\n🏁 M2 完成: ✅{ok} ❌{fail}")
    print(f"📊 LLM 使用: {llm_used_counter}")
    if not dry_run:
        print(f"💾 草稿本地落盘: {feishu_bitable.DRAFTS_JSONL}")
    return summary


def main():
    parser = argparse.ArgumentParser(description="M2 内容工厂")
    parser.add_argument("--items-file", help="从 JSON 文件读取 items")
    parser.add_argument("--from-scan-stdout", action="store_true", help="从 stdin 读取")
    parser.add_argument("--sample", action="store_true", help="用内置样例")
    parser.add_argument("--dry-run", action="store_true", help="生成但不写表")
    parser.add_argument("--top", type=int, default=3, help="最多处理前 N 条（M2 默认前 3 条以控成本）")
    args = parser.parse_args()

    items = list(_stream_items(args))
    summary = run(items, dry_run=args.dry_run, top=args.top)
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
