"""飞书审核表 schema 定义 + 初始化脚本

字段清单（10 字段）：
1. 草稿ID        text          主键，唯一
2. 商机标题      text          来自 M1 商机池
3. 商机链接      url           来自 M1 商机池
4. 平台          select        小红书 / 知乎
5. 标题          text          内容标题（可改）
6. 正文          text          内容正文（可改）
7. 标签          multi-select  话题标签
8. 状态          select        待审 / 通过 / 拒绝 / 已发 / 失败
9. 审核备注      text          你的批注
10. 生成时间     date          自动生成

CLI：
  python -m radar.publish.feishu_audit init
"""
import sys
import time

from radar.config import (
    FEISHU_APP_ID, FEISHU_APP_SECRET,
    FEISHU_BITABLE_APP_TOKEN,
)


SCHEMA = {
    "草稿ID":       {"type": 1, "property": {}},                              # text
    "商机标题":     {"type": 1, "property": {}},
    "商机链接":     {"type": 15, "property": {}},                              # url
    "平台":         {"type": 3, "property": {                                  # single-select
        "options": [
            {"name": "小红书", "color": 0},
            {"name": "知乎", "color": 0},
        ]
    }},
    "标题":         {"type": 1, "property": {}},
    "正文":         {"type": 1, "property": {}},
    "标签":         {"type": 4, "property": {                                  # multi-select
        "options": [
            {"name": "AI"}, {"name": "SaaS"}, {"name": "出海"},
            {"name": "工具"}, {"name": "效率"}, {"name": "副业"},
            {"name": "变现"}, {"name": "短视频"}, {"name": "跨境"},
        ]
    }},
    "状态":         {"type": 3, "property": {                                  # single-select
        "options": [
            {"name": "待审", "color": 1},    # 蓝
            {"name": "通过", "color": 2},    # 绿
            {"name": "拒绝", "color": 3},    # 红
            {"name": "已发", "color": 5},    # 紫
            {"name": "失败", "color": 4},    # 黄
        ]
    }},
    "审核备注":     {"type": 1, "property": {}},
    "生成时间":     {"type": 5, "property": {"date_formatter": "yyyy-MM-dd HH:mm"}},  # date
}


def init_table():
    """初始化「内容审核」表（在已有多维表格下新建第二个表）"""
    from radar.notify.feishu_bitable import BitableClient

    client = BitableClient(
        app_id=FEISHU_APP_ID,
        app_secret=FEISHU_APP_SECRET,
        app_token=FEISHU_BITABLE_APP_TOKEN,
    )

    # 1. 新建表
    print("→ 创建「内容审核」表...")
    table = client.create_table(
        table_name="内容审核",
        schema=SCHEMA,
    )
    table_id = table.get("table_id")
    print(f"✅ 表格已创建：table_id = {table_id}")
    print()
    print("=" * 60)
    print(f"请把下面的环境变量加到 .env / GitHub Secrets：")
    print(f"FEISHU_AUDIT_TABLE_ID={table_id}")
    print("=" * 60)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="飞书审核表工具")
    parser.add_argument("action", choices=["init", "schema"], help="init=建表; schema=打印 schema")
    args = parser.parse_args()

    if args.action == "schema":
        import json
        print(json.dumps(SCHEMA, ensure_ascii=False, indent=2))
    elif args.action == "init":
        if not (FEISHU_APP_ID and FEISHU_APP_SECRET and FEISHU_BITABLE_APP_TOKEN):
            print("✗ 缺 FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_BITABLE_APP_TOKEN")
            sys.exit(1)
        init_table()


if __name__ == "__main__":
    main()