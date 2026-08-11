#!/bin/bash
# torch 构建参数智能选择（CPU/GPU + 测速选最快源）
#
# 被 setup.sh / build-autodl.sh source 使用。
# 输出到环境变量：
#   TORCH_DEVICE       cpu | gpu
#   TORCH_CPU_INDEX_URL    CPU 版 torch 的最快下载源（TORCH_DEVICE=cpu 时有效）
#
# 用法：
#   source scripts/setup/torch_select.sh
#   select_torch_config
#   echo "TORCH_DEVICE=${TORCH_DEVICE}"

select_torch_config() {
    # 复用 setup.sh 的配色/日志函数（若未定义则兜底）
    if ! declare -f info >/dev/null 2>&1; then
        info()  { echo -e "\033[0;36m[INFO]\033[0m $1"; }
        ok()    { echo -e "\033[0;32m[OK]\033[0m $1"; }
        warn()  { echo -e "\033[0;33m[WARN]\033[0m $1"; }
    fi

    # 1. 检测 NVIDIA GPU
    local HAS_GPU=0
    local GPU_NAME=""
    if command -v nvidia-smi &>/dev/null && nvidia-smi >/dev/null 2>&1; then
        HAS_GPU=1
        GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
        ok "检测到 NVIDIA GPU: ${GPU_NAME:-unknown}"
    else
        warn "未检测到 NVIDIA GPU（若无 GPU，推荐 CPU 版，构建快、镜像小）"
    fi

    # 2. 决定 TORCH_DEVICE（检测到 GPU 时询问，默认 CPU）
    TORCH_DEVICE=cpu
    if [ "$HAS_GPU" = "1" ]; then
        local GPU_CHOICE
        warn "检测到 GPU。选择 torch 版本："
        echo "  [1] GPU 版（完整 CUDA，构建慢、镜像 ~24GB，适合训练/推理加速）"
        echo "  [2] CPU 版（构建快、镜像 ~15GB，无 GPU 加速）"
        printf "  请选择 (1/2，默认 2): "
        read -r GPU_CHOICE
        if [ "${GPU_CHOICE:-2}" = "1" ]; then
            TORCH_DEVICE=gpu
            ok "已选择 GPU 版 torch"
        else
            warn "已选择 CPU 版 torch（后续需要 GPU 时可重新构建）"
        fi
    else
        TORCH_DEVICE=cpu
        info "无 GPU，使用 CPU 版 torch"
    fi

    # 3. 测速选择最快的 CPU torch 源（仅 CPU 版需要）
    TORCH_CPU_INDEX_URL=""
    if [ "$TORCH_DEVICE" = "cpu" ]; then
        info "测速选择最快的 CPU torch 下载源..."
        local TORCH_CPU_SOURCES=(
            "https://download.pytorch.org/whl/cpu"
            "https://mirrors.aliyun.com/pytorch-wheels/cpu"
            "https://mirror.sjtu.edu.cn/pytorch-wheels/cpu"
        )
        local BEST_SPEED=0
        local BEST_SOURCE=""
        local TORCH_WHEEL_PATH="torch-2.9.1%2Bcpu-cp310-cp310-manylinux_2_28_x86_64.whl"
        local src SPEED SPEED_INT
        for src in "${TORCH_CPU_SOURCES[@]}"; do
            SPEED=$(timeout 8 curl -s -o /dev/null -w "%{speed_download}" \
                --max-time 6 "${src}/${TORCH_WHEEL_PATH}" 2>/dev/null || echo 0)
            SPEED_INT=$(printf "%.0f" "${SPEED:-0}" 2>/dev/null || echo 0)
            echo "    ${src} → $(echo "${SPEED:-0}" | awk '{printf "%.1f", $1/1024/1024}') MB/s"
            if [ "$SPEED_INT" -gt "$BEST_SPEED" ]; then
                BEST_SPEED=$SPEED_INT
                BEST_SOURCE=$src
            fi
        done
        if [ -n "$BEST_SOURCE" ]; then
            TORCH_CPU_INDEX_URL=$BEST_SOURCE
            ok "最快源: ${BEST_SOURCE} ($(echo "$BEST_SPEED" | awk '{printf "%.1f", $1/1024/1024}') MB/s)"
        else
            warn "所有源测速失败，使用默认阿里云源"
            TORCH_CPU_INDEX_URL="https://mirrors.aliyun.com/pytorch-wheels/cpu"
        fi
    fi
}
