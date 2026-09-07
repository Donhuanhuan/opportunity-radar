#!/bin/bash
# 本地一键启动脚本
# 用法: ./scripts/local_run.sh [--dry-run]

set -e

cd "$(dirname "$0")/.."

# 创建虚拟环境（如不存在）
if [ ! -d ".venv" ]; then
  echo "📦 创建虚拟环境..."
  python3 -m venv .venv
fi

# 激活虚拟环境
source .venv/bin/activate

# 安装依赖
echo "📥 安装依赖..."
pip install -r requirements.txt

# 加载 .env
if [ -f .env ]; then
  export $(cat .env | grep -v "^#" | xargs)
fi

# 执行
echo "🚀 启动商机雷达..."
python -m radar.scan "$@"