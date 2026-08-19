#!/usr/bin/env bash
# ==============================================================================
# QuantMind AutoDL / 远程 GPU 算力节点一键初始化脚本
# ==============================================================================
# 用途：
#   在远程 GPU 主机或 AutoDL 实例上快速配置独立的 QuantMind 训练环境
# 用法：
#   bash setup-autodl.sh
# ==============================================================================

set -eo pipefail

echo "========================================================"
echo "🚀 开始初始化 QuantMind 独立训练环境 (AutoDL / 远程 GPU)"
echo "========================================================"

WORK_DIR="${TRAINING_WORK_DIR:-/workspace}"
mkdir -p "${WORK_DIR}/data/features" "${WORK_DIR}/data/quantdb" "${WORK_DIR}/models" "${WORK_DIR}/logs"

# 1. 检查 Python 环境
echo "📦 检查 Python 环境..."
python_bin="$(command -v python3 || command -v python || true)"
if [ -z "$python_bin" ]; then
    echo "❌ 未找到 Python 环境，请先安装 Python 3.10+"
    exit 1
fi
echo "✅ Python 路径: $($python_bin --version) ($python_bin)"

# 2. 配置国内 PyPI 镜像源加速
export PIP_INDEX_URL="${PIP_INDEX_URL:-https://mirrors.aliyun.com/pypi/simple/}"
export PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST:-mirrors.aliyun.com}"

echo "📥 安装 / 校验核心训练依赖..."
$python_bin -m pip install --upgrade pip --quiet
$python_bin -m pip install --no-cache-dir \
    numpy pandas pyarrow scipy scikit-learn \
    lightgbm xgboost catboost optuna pyyaml \
    requests psutil shap --quiet

# 3. 检查 PyTorch 与 CUDA 状态
echo "🔍 检查 GPU 与 PyTorch CUDA 状态..."
$python_bin -c "
import torch
print(f'PyTorch Version: {torch.__version__}')
print(f'CUDA Available: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'Device Count: {torch.cuda.device_count()}')
    print(f'Device Name: {torch.cuda.get_device_name(0)}')
    print(f'VRAM Total: {torch.cuda.get_device_properties(0).total_memory / (1024**3):.1f} GB')
else:
    print('⚠️ 未检测到可用的 CUDA 设备，将使用 CPU 训练')
"

# 4. 检测 NVIDIA SMI
if command -v nvidia-smi &> /dev/null; then
    echo "✅ nvidia-smi 检测正常:"
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
else
    echo "⚠️ 未找到 nvidia-smi 命令行工具"
fi

# 5. 磁盘空间检查
echo "💾 磁盘空间检查 (${WORK_DIR}):"
df -h "${WORK_DIR}" | awk 'NR==2{print "   总计: "$2" | 已用: "$3" | 可用: "$4" ("$5")"}'

echo "========================================================"
echo "🎉 QuantMind 训练环境已就绪！"
echo "工作目录: ${WORK_DIR}"
echo "========================================================"
