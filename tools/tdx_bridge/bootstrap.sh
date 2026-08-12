#!/bin/bash
# 通达信交易桥 - Linux 启动脚本
# 用法: ./bootstrap.sh [auto|http|file_sync]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:-auto}"

echo "[bridge-linux] 启动模式: $MODE"

# 激活虚拟环境
if [ -f "${SCRIPT_DIR}/.venv/bin/activate" ]; then
    source "${SCRIPT_DIR}/.venv/bin/activate"
fi

# 设置环境变量 (可用配置文件覆盖)
if [ -z "${BRIDGE_AUTH_TOKEN:-}" ]; then
    export BRIDGE_AUTH_TOKEN="${BRIDGE_AUTH_TOKEN:-}"
    read -rp "BRIDGE_AUTH_TOKEN (64位hex): " BRIDGE_AUTH_TOKEN
fi
if [ -z "${SHARED_DIR:-}" ]; then
    export SHARED_DIR="/mnt/tdx-shared"
fi

# 确认共享目录可访问
if [ ! -d "${SHARED_DIR}/trade_plans/pending" ]; then
    echo "[bridge-linux] 创建共享目录..."
    mkdir -p "${SHARED_DIR}/trade_plans/pending" \
             "${SHARED_DIR}/trade_plans/processed" \
             "${SHARED_DIR}/trade_plans/failed" \
             "${SHARED_DIR}/execution_reports"
fi

cd "$SCRIPT_DIR"
exec python3 -m src.main --mode "$MODE" --config config.yaml
