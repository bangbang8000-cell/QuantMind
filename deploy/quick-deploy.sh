#!/bin/bash
# QuantMind 快速部署脚本
# 在服务器上运行此脚本即可完成部署

set -euo pipefail

echo "========================================"
echo "  QuantMind 快速部署"
echo "========================================"

# 检查 root 权限
if [[ $EUID -ne 0 ]]; then
    echo "错误: 需要 root 权限"
    echo "请使用: sudo bash $0"
    exit 1
fi

# 下载部署脚本（使用临时目录，避免提前占用 /opt/quantmind）
TMP_DEPLOY_DIR="$(mktemp -d /tmp/quantmind-deploy.XXXXXX)"
DEPLOY_SCRIPT="$TMP_DEPLOY_DIR/deploy.sh"
# 默认固定到发布 tag（而非动态 master），确保部署可复现、可校验。
# 可用环境变量覆盖：
#   QUANTMIND_DEPLOY_TAG=master         （使用最新 master，不推荐生产）
#   QUANTMIND_DEPLOY_SHA256=xxx         （校验 deploy.sh 哈希）
QUANTMIND_DEPLOY_TAG="${QUANTMIND_DEPLOY_TAG:-v1.9.0-beta}"
DEPLOY_URL="https://gitee.com/qusong0627/QuantMind/raw/${QUANTMIND_DEPLOY_TAG}/deploy/deploy.sh"
EXPECTED_SHA256="${QUANTMIND_DEPLOY_SHA256:-}"
cleanup() {
    rm -rf "$TMP_DEPLOY_DIR"
}
trap cleanup EXIT

echo "下载部署脚本 (tag=${QUANTMIND_DEPLOY_TAG})..."
curl -fsSL "$DEPLOY_URL" -o "$DEPLOY_SCRIPT"

if [[ -n "$EXPECTED_SHA256" ]]; then
    ACTUAL_SHA256="$(sha256sum "$DEPLOY_SCRIPT" | awk '{print $1}')"
    if [[ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]]; then
        echo "错误: deploy.sh 校验失败"
        echo "期望: $EXPECTED_SHA256"
        echo "实际: $ACTUAL_SHA256"
        exit 1
    fi
    echo "deploy.sh 校验通过"
else
    echo "警告: 未设置 QUANTMIND_DEPLOY_SHA256，已跳过 deploy.sh 完整性校验"
    echo "建议生产部署设置: QUANTMIND_DEPLOY_SHA256=\$(curl -fsSL $DEPLOY_URL | sha256sum | awk '{print \$1}')"
fi

# 添加执行权限
chmod +x "$DEPLOY_SCRIPT"

# 执行部署（交互式）
echo "开始部署..."
bash "$DEPLOY_SCRIPT"
