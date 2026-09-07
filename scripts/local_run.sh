#!/bin/bash
# Make monney · 本地一键启动脚本（路径 B：半本机 agent-browser）
# 用法:
#   ./scripts/local_run.sh scan       跑一次商机雷达（M1）
#   ./scripts/local_run.sh m2         跑一次内容工厂（M2 LLM 生成）
#   ./scripts/local_run.sh m3         跑一次本地发布（M3 发布到小红书/知乎）
#   ./scripts/local_run.sh audit-init 初始化飞书「内容审核」表
#   ./scripts/local_run.sh env-check  检查环境是否就绪（key/cookie/表）
#
# Windows + Git Bash 友好

set -e

# ===== 切到项目根 =====
cd "$(dirname "$0")/.."
PROJECT_ROOT=$(pwd)
echo "📁 项目根: $PROJECT_ROOT"

# ===== 用已装好的 managed python（避开 venv 创建在含空格路径下的 bug）=====
PY="C:\\Users\\30689\\.workbuddy\\binaries\\python\\envs\\default\\Scripts\\python.exe"

# ===== 加载 .env =====
if [ ! -f ".env" ]; then
  echo "❌ .env 不存在，先 cp .env.example .env 并填好"
  exit 1
fi

# 把 .env 内容导出成 shell 变量（临时注入到 python 的环境）
export $(grep -v "^#" .env | xargs)

# ===== 检查依赖（缺则装）=====
echo "🔍 检查 Python 依赖..."
"$PY" -c "import requests, feedparser, dotenv, yaml" 2>/dev/null || {
  echo "📥 装依赖..."
  PIP="C:\\Users\\30689\\.workbuddy\\binaries\\python\\envs\\default\\Scripts\\pip.exe"
  "$PIP" install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
}

# ===== 命令分发 =====
CMD="${1:-scan}"

case "$CMD" in
  scan)
    echo "🚀 [M1] 跑商机雷达..."
    "$PY" -m radar.scan
    ;;
  m2)
    echo "🧠 [M2] 跑内容工厂（拉商机 → LLM 分析 → 生成双版本文案）..."
    "$PY" -m radar.m2_pipeline
    ;;
  m3)
    echo "📤 [M3] 拉已通过审核的草稿 → 发布到小红书/知乎 ..."
    "$PY" -m radar.publish.audit_gate
    ;;
  audit-init)
    echo "📋 初始化飞书「内容审核」表..."
    "$PY" -m radar.publish.feishu_audit init
    ;;
  env-check)
    echo "🩺 环境体检..."
    "$PY" -c "
from dotenv import load_dotenv; load_dotenv()
import os, sys
checks = []
checks.append(('DeepSeek API key', bool(os.environ.get('DEEPSEEK_API_KEY'))))
checks.append(('Feishu App ID', bool(os.environ.get('FEISHU_APP_ID'))))
checks.append(('Feishu Bitable Token', bool(os.environ.get('FEISHU_BITABLE_APP_TOKEN'))))
checks.append(('商机池 TABLE_ID', bool(os.environ.get('FEISHU_BITABLE_TABLE_ID'))))
checks.append(('DRAFTS TABLE_ID', bool(os.environ.get('DRAFTS_BITABLE_TABLE_ID'))))
checks.append(('审核表 TABLE_ID', bool(os.environ.get('FEISHU_AUDIT_TABLE_ID'))))
for name, ok in checks:
    print(('✅' if ok else '⚠️ ') + name)
print('---')
print('PUBLISH_ENABLED:', os.environ.get('PUBLISH_ENABLED','off'))
"
    ;;
  *)
    echo "用法: $0 {scan|m2|m3|audit-init|env-check}"
    exit 1
    ;;
esac

echo ""
echo "✅ done"
