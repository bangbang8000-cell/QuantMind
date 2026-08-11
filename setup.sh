#!/bin/bash
# QuantMind 一键部署脚本
# 用法: chmod +x setup.sh && ./setup.sh

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

echo ""
echo "========================================="
echo "  QuantMind 一键部署"
echo "========================================="
echo ""

# -------------------------------------------
# 1. 环境检查
# -------------------------------------------
info "检查系统环境..."

if ! command -v docker &>/dev/null; then
    error "未检测到 Docker，请先安装: https://docs.docker.com/get-docker/"
fi

if ! docker compose version &>/dev/null && ! docker-compose version &>/dev/null; then
    error "未检测到 Docker Compose，请先安装: https://docs.docker.com/compose/install/"
fi

DOCKER_VERSION=$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo "unknown")
ok "Docker ${DOCKER_VERSION}"

# 检测 compose 命令
if docker compose version &>/dev/null; then
    COMPOSE_CMD="docker compose"
else
    COMPOSE_CMD="docker-compose"
fi
ok "Compose: ${COMPOSE_CMD}"

# -------------------------------------------
# 2. 配置 .env
# -------------------------------------------
if [ -f .env ]; then
    warn ".env 文件已存在，跳过生成（如需重新配置请先删除 .env）"
else
    info "生成 .env 配置文件..."

    # 生成随机密钥
    SECRET_KEY=$(openssl rand -hex 32 2>/dev/null || head -c 64 /dev/urandom | od -An -tx1 | tr -d ' \n' | head -c 64)
    JWT_SECRET=$(openssl rand -hex 32 2>/dev/null || head -c 64 /dev/urandom | od -An -tx1 | tr -d ' \n' | head -c 64)
    DB_PASSWORD=$(openssl rand -base64 16 2>/dev/null | tr -dc 'a-zA-Z0-9' | head -c 20 || echo "quantmind$(date +%s)")

    cp .env.example .env

    # 替换默认值
    sed -i "s/CHANGE_ME_GENERATE_YOUR_OWN_SECRET_KEY/${SECRET_KEY}/" .env
    sed -i "s/CHANGE_ME_GENERATE_YOUR_OWN_JWT_SECRET/${JWT_SECRET}/" .env
    sed -i "s/CHANGE_ME_DB_PASSWORD/${DB_PASSWORD}/" .env

    ok ".env 已生成（密钥已随机化）"
fi

# -------------------------------------------
# 3. 创建必要目录
# -------------------------------------------
info "创建数据目录..."
mkdir -p data db models logs strategy_templates user_pools_local
ok "目录就绪"

# -------------------------------------------
# 4. 构建镜像（自动选择 torch 版本与最快源）
# -------------------------------------------
# 加载公共 torch 选择函数（CPU/GPU 检测 + 测速选源）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/setup/torch_select.sh
source "${SCRIPT_DIR}/scripts/setup/torch_select.sh"

info "检测 torch 版本（CPU/GPU）..."
select_torch_config
info "构建 Docker 镜像（torch=${TORCH_DEVICE}，首次约 5-15 分钟）..."
if [ -n "$TORCH_CPU_INDEX_URL" ]; then
    ${COMPOSE_CMD} build --progress=plain \
        --build-arg "TORCH_DEVICE=${TORCH_DEVICE}" \
        --build-arg "TORCH_CPU_INDEX_URL=${TORCH_CPU_INDEX_URL}"
else
    ${COMPOSE_CMD} build --progress=plain \
        --build-arg "TORCH_DEVICE=${TORCH_DEVICE}"
fi
ok "镜像构建完成"

# -------------------------------------------
# 4.5 训练方式选择（本地 / AutoDL 远程 GPU）
# -------------------------------------------
info "训练方式选择..."
warn "请选择模型训练方式："
echo "  [1] 仅本地训练（默认，无需 AutoDL）"
echo "  [2] 本地 + AutoDL 远程 GPU 训练（将特征快照推送到 GPU 节点训练，模型回传本机）"
printf "  请选择 (1/2，默认 1): "
read -r TRAIN_MODE_CHOICE
if [ "${TRAIN_MODE_CHOICE:-1}" = "2" ]; then
    ok "启用 AutoDL 远程 GPU 训练"
    # 多节点配置写入 config/training_nodes.yaml（每台 AutoDL 一条）
    NODES_YAML="${SCRIPT_DIR}/config/training_nodes.yaml"
    [ -d "${SCRIPT_DIR}/config" ] || mkdir -p "${SCRIPT_DIR}/config"

    # 已存在则备份（不覆盖已有节点配置）
    if [ -f "$NODES_YAML" ] && ! grep -q "id: autodl-1" "$NODES_YAML" 2>/dev/null; then
        warn "发现已有 config/training_nodes.yaml，将追加新节点（不覆盖）"
    fi

    # 生成基础 YAML（若不存在）
    if [ ! -f "$NODES_YAML" ]; then
        cat > "$NODES_YAML" << 'YAMLHEAD'
# QuantMind AutoDL 远程 GPU 训练节点配置
nodes:
YAMLHEAD
    fi

    node_idx=0
    while true; do
        node_idx=$((node_idx + 1))
        node_id="autodl-${node_idx}"
        echo ""
        info "配置第 ${node_idx} 台 AutoDL 节点（${node_id}）"
        printf "  节点 IP/域名（留空结束）: "
        read -r node_host
        [ -z "$node_host" ] && break
        printf "  SSH 端口（默认 22）: "
        read -r node_port; [ -z "$node_port" ] && node_port=22
        printf "  SSH 用户（默认 root）: "
        read -r node_user; [ -z "$node_user" ] && node_user=root
        printf "  SSH 认证方式 (1=密码 2=私钥，默认 1): "
        read -r node_auth
        if [ "${node_auth:-1}" = "2" ]; then
            printf "  SSH 私钥路径: "
            read -r node_key
            node_pass=""
        else
            printf "  SSH 密码: "
            read -r node_pass
            node_key=""
        fi
        printf "  节点显示名（默认 AutoDL GPU ${node_idx}）: "
        read -r node_name; [ -z "$node_name" ] && node_name="AutoDL GPU ${node_idx}"
        printf "  远端工作目录（默认 /workspace）: "
        read -r node_workdir; [ -z "$node_workdir" ] && node_workdir=/workspace
        printf "  GPU 数量 all/0/1/2（默认 all）: "
        read -r node_gpus; [ -z "$node_gpus" ] && node_gpus=all

        # 追加节点到 YAML
        cat >> "$NODES_YAML" << EOF
  - id: ${node_id}
    name: "${node_name}"
    host: "${node_host}"
    port: ${node_port}
    user: "${node_user}"
    ssh_password: "${node_pass}"
    ssh_key: "${node_key}"
    work_dir: "${node_workdir}"
    docker_image: "quantmind-train:latest"
    gpus: "${node_gpus}"
EOF
        ok "已添加节点 ${node_id}（${node_host}）"

        # 兼容单台：第一台也写入 .env（供旧编排器 / 构建脚本读取）
        if [ "$node_idx" = "1" ]; then
            ENV_FILE="${ENV_FILE:-.env}"
            [ -f "$ENV_FILE" ] || touch "$ENV_FILE"
            grep -q "^TRAINING_AUTODL_HOST=" "$ENV_FILE" 2>/dev/null || \
                printf "TRAINING_AUTODL_HOST=%s\nTRAINING_AUTODL_SSH_PORT=%s\nTRAINING_AUTODL_USER=%s\nTRAINING_AUTODL_SSH_PASSWORD=%s\nTRAINING_AUTODL_SSH_KEY=%s\nTRAINING_AUTODL_WORK_DIR=%s\nTRAINING_AUTODL_NODE_NAME=%s\nTRAINING_AUTODL_DOCKER_IMAGE=quantmind-train:latest\nTRAINING_AUTODL_GPUS=%s\n" \
                    "$node_host" "$node_port" "$node_user" "$node_pass" "$node_key" "$node_workdir" "$node_name" "$node_gpus" >> "$ENV_FILE"
        fi
    done

    ok "AutoDL 节点配置已写入 ${NODES_YAML}"
    if [ "$node_idx" = "0" ]; then
        warn "未配置任何节点，前端仅显示本地训练"
    fi

    # 询问是否构建 AutoDL 训练镜像
    warn "AutoDL 节点是 GPU。推荐在 AutoDL 上远程构建（利用远端网络，避免本地推送大镜像）。"
    printf "  是否现在构建 AutoDL 训练镜像 quantmind-train:latest？(y/N，默认 N): "
    read -r BUILD_AUTODL
    if [ "${BUILD_AUTODL:-n}" = "y" ] || [ "${BUILD_AUTODL:-n}" = "Y" ]; then
        # shellcheck source=scripts/setup/build-autodl-remote.sh
        source "${SCRIPT_DIR}/scripts/setup/build-autodl-remote.sh"
        build_autodl_remote
    else
        info "跳过 AutoDL 镜像构建。后续需要时可运行: source scripts/setup/build-autodl-remote.sh && build_autodl_remote"
    fi
else
    info "仅本地训练"
fi

# -------------------------------------------
# 5. 启动服务
# -------------------------------------------
info "启动所有服务..."
${COMPOSE_CMD} up -d

# 等待核心服务就绪
info "等待服务就绪..."
MAX_WAIT=120
ELAPSED=0
while [ $ELAPSED -lt $MAX_WAIT ]; do
    if ${COMPOSE_CMD} ps quantmind 2>/dev/null | grep -q "healthy\|running"; then
        break
    fi
    sleep 3
    ELAPSED=$((ELAPSED + 3))
    echo -n "."
done
echo ""

if [ $ELAPSED -ge $MAX_WAIT ]; then
    warn "服务启动超时（${MAX_WAIT}s），请检查日志: ${COMPOSE_CMD} logs quantmind"
else
    ok "核心服务已启动"
fi

# -------------------------------------------
# 6. 初始化（RD-Agent + 数据检查）
# -------------------------------------------
info "运行初始化脚本..."
${COMPOSE_CMD} exec -T quantmind bash /app/scripts/setup/init.sh --no-data-sync 2>/dev/null || warn "初始化脚本执行异常，请手动运行: docker exec quantmind bash /app/scripts/setup/init.sh"

# -------------------------------------------
# 7. 显示结果
# -------------------------------------------
echo ""
echo "========================================="
echo -e "  ${GREEN}QuantMind 部署完成！${NC}"
echo "========================================="
echo ""
echo "  访问地址:"
echo "    Web 前端:  http://localhost:3000"
echo "    API:       http://localhost:8000"
echo "    Huntly:    http://localhost:8090"
echo "    RSSHub:    http://localhost:1200"
echo ""
echo "  默认管理员:"
echo "    用户名: admin"
echo "    密码:   admin123"
echo ""
echo "  常用命令:"
echo "    查看状态:  ${COMPOSE_CMD} ps"
echo "    查看日志:  ${COMPOSE_CMD} logs -f quantmind"
echo "    停止服务:  ${COMPOSE_CMD} down"
echo "    重启服务:  ${COMPOSE_CMD} restart"
echo ""
echo "  下一步:"
echo "    1. 登录后修改默认密码"
echo "    2. 在 .env 中配置 AI API Key（DeepSeek/Qwen）"
echo "    3. 下载数据包: https://oss.quantmindai.cn/data-download.html"
echo "    4. 详细文档: docs/部署指南.md"
echo ""
