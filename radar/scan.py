#!/usr/bin/env python3
"""
商机雷达主入口
用法:
  python -m radar.scan                    # 完整跑一遍
  python -m radar.scan --source hackernews  # 只跑指定源
  python -m radar.scan --dry-run          # 抓取但不推送
"""
import sys
import argparse
from datetime import datetime

from radar.config import SOURCES, NOTIFY_CHANNELS, TOP_N
from radar.sources import hackernews, github_trending, producthunt, kr36, weibo
from radar.notify import feishu, email
from radar.filters import filter_block, score_relevance, dedupe, top_n


SOURCE_MODULES = {
    "hackernews": hackernews,
    "github_trending": github_trending,
    "producthunt": producthunt,
    "kr36": kr36,
    "weibo": weibo,
}

NOTIFY_MODULES = {
    "feishu": feishu,
    "email": email,
}


def run(sources: list, dry_run: bool = False) -> list:
    print(f"🔭 商机雷达启动 @ {datetime.now().isoformat()}")
    print(f"📡 启用信号源: {', '.join(sources)}")

    all_items = []
    for src in sources:
        mod = SOURCE_MODULES.get(src)
        if not mod:
            print(f"⚠️  未知源: {src}")
            continue
        try:
            raw = mod.fetch()
            print(f"  ✅ [{src}] 抓取 {len(raw)} 条")
            all_items.extend(raw)
        except Exception as e:
            print(f"  ❌ [{src}] 异常: {e}")

    # 过滤 + 打分 + 去重 + TopN
    items = filter_block(all_items)
    items = score_relevance(items)
    items = dedupe(items)
    items = top_n(items, TOP_N)
    print(f"🎯 命中 {len(items)} 条（已过滤违规 + Top{TOP_N}）")

    # 推送
    if not dry_run:
        for ch in NOTIFY_CHANNELS:
            mod = NOTIFY_MODULES.get(ch)
            if mod:
                mod.send_daily(items)
    else:
        print("🔕 dry-run 模式，跳过推送")
        for it in items:
            print(f"  - [{it['source']}] {it['title']} (score={it['score']})")

    return items


def main():
    parser = argparse.ArgumentParser(description="商机雷达 - 自动发现互联网商机")
    parser.add_argument("--source", help="只跑指定源（逗号分隔）")
    parser.add_argument("--dry-run", action="store_true", help="只抓取不推送")
    parser.add_argument("--top", type=int, default=TOP_N, help="Top N 条数")
    args = parser.parse_args()

    sources = args.source.split(",") if args.source else SOURCES
    if args.top:
        global TOP_N
        TOP_N = args.top

    items = run(sources, dry_run=args.dry_run)
    print(f"🏁 完成，输出 {len(items)} 条")
    return 0 if items else 1


if __name__ == "__main__":
    sys.exit(main())