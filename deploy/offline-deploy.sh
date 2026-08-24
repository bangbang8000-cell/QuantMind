#!/usr/bin/env bash
# QuantMind 离线镜像一键部署
#
# 默认 CDN 地址：
#   https://cdn.quantmind.cloud/quantmind-images.tar.zst
#   https://cdn.quantmind.cloud/qlib-cn_data.tar.zst
# 可用 QUANTMIND_IMAGES_URL / QUANTMIND_QLIB_URL 覆盖默认地址。
# 可选环境变量：
#   QUANTMIND_IMAGES_SHA256 / QUANTMIND_QLIB_SHA256  下载包 SHA-256
#   QUANTMIND_REPO_URL    代码仓库地址（默认 Gitee）
#   QUANTMIND_REF         要部署的 Git 分支或 tag（默认 master）
#   QUANTMIND_REPLACE_QLIB=true  覆盖已有 db/qlib_data（谨慎）
#   QUANTMIND_COMPOSE_OVERLAY  已验证 docker-compose.yml 的本地路径（可选）
#   QUANTMIND_DEPLOY_OVERLAY_DIR  受控 Dockerfile 覆盖目录（可选）

set -euo pipefail

PROJECT_DIR="${QUANTMIND_PROJECT_DIR:-/opt/quantmind}"
DOWNLOAD_DIR="${QUANTMIND_DOWNLOAD_DIR:-/opt/quantmind-downloads}"
STAGING_DIR="${QUANTMIND_STAGING_DIR:-/opt/quantmind-staging}"
REPO_URL="${QUANTMIND_REPO_URL:-https://gitee.com/qusong0627/QuantMind.git}"
REF="${QUANTMIND_REF:-master}"
COMPOSE_OVERLAY="${QUANTMIND_COMPOSE_OVERLAY:-}"
DEPLOY_OVERLAY_DIR="${QUANTMIND_DEPLOY_OVERLAY_DIR:-}"
IMAGES_URL="${QUANTMIND_IMAGES_URL:-https://cdn.quantmind.cloud/quantmind-images.tar.zst}"
QLIB_URL="${QUANTMIND_QLIB_URL:-https://cdn.quantmind.cloud/qlib-cn_data.tar.zst}"
# 与上述 CDN 当前发布包对应。发布新包时须同步更新此处，或通过环境变量覆盖。
IMAGES_SHA256="${QUANTMIND_IMAGES_SHA256:-36c3bc5ffd3c68b5d131893d0970d33045999d27d19b74025ef6d7b61a348892}"
QLIB_SHA256="${QUANTMIND_QLIB_SHA256:-7165081b35defb5f54dc22d9a6aaeb129fc5db3f8479c5da1aa1ad581a14bbe8}"

log() { printf '[offline-deploy] %s\n' "$*"; }
die() { log "错误: $*" >&2; exit 1; }

require_root() { [[ ${EUID} -eq 0 ]] || die '请使用 sudo bash deploy/offline-deploy.sh'; }
require_ubuntu() {
    . /etc/os-release
    [[ ${ID:-} == ubuntu ]] || die '仅支持 Ubuntu'
}
require_url() { [[ -n "$1" ]] || die "缺少环境变量 $2"; }

download() {
    local url="$1" destination="$2" expected_sha="${3:-}"
    mkdir -p "$(dirname "$destination")"

    # 已下载且校验通过的包直接复用，避免重跑时 curl -C - 对完整文件
    # 返回 HTTP 416，也避免重复下载数 GB 的镜像包。
    if [[ -n "$expected_sha" && -f "$destination" ]] \
        && echo "${expected_sha}  ${destination}" | sha256sum --check --status; then
        log "复用已校验下载包: $(basename "$destination")"
        return 0
    fi
    log "下载 $(basename "$destination")"
    curl --fail --location --continue-at - --retry 3 --retry-delay 3 \
        "$url" -o "$destination"
    [[ -s "$destination" ]] || die "下载结果为空: $destination"
    if [[ -n "$expected_sha" ]]; then
        echo "${expected_sha}  ${destination}" | sha256sum --check --status \
            || die "SHA-256 校验失败: $destination"
    fi
}

install_runtime() {
    log '步骤 1/7：更新系统并安装依赖'
    apt-get update -y
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        ca-certificates curl git gnupg lsb-release zstd

    log '步骤 2/7：安装 Docker 和 Docker Compose'
    if ! command -v docker >/dev/null 2>&1; then
        DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io
    fi
    if ! docker compose version >/dev/null 2>&1; then
        # Ubuntu 源在不同版本中使用过两个包名。
        DEBIAN_FRONTEND=noninteractive apt-get install -y docker-compose-plugin 2>/dev/null \
            || DEBIAN_FRONTEND=noninteractive apt-get install -y docker-compose-v2
    fi
    systemctl enable --now docker
    docker compose version >/dev/null || die 'Docker Compose 不可用'
}

import_images() {
    local archive="$DOWNLOAD_DIR/quantmind-images.tar.zst"
    log '步骤 3/7：从 CDN 下载离线镜像包'
    download "$IMAGES_URL" "$archive" "$IMAGES_SHA256"
    zstd --test --quiet "$archive" || die '镜像包 zstd 校验失败'

    local image
    local images_ready=true
    for image in \
        quantmind-oss:latest quantmind-web:latest \
        quantmind-data-gateway:latest quantmind-dashboard:latest \
        postgres:15-alpine redis:7-alpine \
        lcomplete/huntly:latest diygod/rsshub:latest agentscope/qwenpaw:latest; do
        if ! docker image inspect "$image" >/dev/null 2>&1; then
            images_ready=false
            break
        fi
    done
    if $images_ready; then
        log '复用已导入的 Docker 镜像'
        return 0
    fi

    log '步骤 4/7：解压并导入 Docker 镜像'
    # 流式导入，不产生同等大小的中间 .tar 文件。
    zstd --decompress --stdout "$archive" | docker load

    for image in \
        quantmind-oss:latest quantmind-web:latest \
        quantmind-data-gateway:latest quantmind-dashboard:latest \
        postgres:15-alpine redis:7-alpine \
        lcomplete/huntly:latest diygod/rsshub:latest agentscope/qwenpaw:latest; do
        docker image inspect "$image" >/dev/null 2>&1 \
            || die "离线镜像包未包含必需镜像: $image"
    done
}

stage_qlib_data() {
    local archive="$DOWNLOAD_DIR/qlib-cn_data.tar.zst"
    rm -rf "$STAGING_DIR"
    mkdir -p "$STAGING_DIR"

    log '步骤 5/7：下载并解压 Qlib 数据包'
    download "$QLIB_URL" "$archive" "$QLIB_SHA256"
    zstd --test --quiet "$archive" || die 'Qlib 数据包 zstd 校验失败'
    zstd --decompress --stdout "$archive" | tar --extract --file - --directory "$STAGING_DIR"
    [[ -f "$STAGING_DIR/cn_data/calendars/day.txt" ]] \
        || die 'Qlib 数据包结构异常：缺少 cn_data/calendars/day.txt'
}

has_qlib_features() {
    local qlib_dir="$1"
    [[ -f "$qlib_dir/calendars/day.txt" && -d "$qlib_dir/features" ]] \
        && find "$qlib_dir/features" -type f -print -quit 2>/dev/null | grep -q .
}

checkout_code() {
    log '步骤 6/7：下载最新代码'
    if [[ -e "$PROJECT_DIR" && ! -d "$PROJECT_DIR/.git" ]]; then
        die "部署目录已存在且不是 Git 仓库: $PROJECT_DIR"
    fi
    if [[ -d "$PROJECT_DIR/.git" ]]; then
        git -C "$PROJECT_DIR" fetch origin "$REF"
        git -C "$PROJECT_DIR" checkout --detach "origin/$REF" 2>/dev/null \
            || git -C "$PROJECT_DIR" checkout --detach "$REF"
    else
        git clone --branch "$REF" --depth 1 "$REPO_URL" "$PROJECT_DIR"
    fi

    # 发布分支尚未合并部署修复时，允许由受控的本地文件覆盖 Compose。
    # 该入口只覆盖此单一文件，避免把服务器上的任意目录复制进代码仓库。
    if [[ -n "$COMPOSE_OVERLAY" ]]; then
        [[ -f "$COMPOSE_OVERLAY" ]] || die "Compose 覆盖文件不存在: $COMPOSE_OVERLAY"
        cp "$COMPOSE_OVERLAY" "$PROJECT_DIR/docker-compose.yml"
        log "已应用 Compose 覆盖文件"
    fi
    if [[ -n "$DEPLOY_OVERLAY_DIR" ]]; then
        [[ -d "$DEPLOY_OVERLAY_DIR" ]] || die "部署覆盖目录不存在: $DEPLOY_OVERLAY_DIR"
        local relative_path
        for relative_path in \
            docker/Dockerfile.oss \
            docker/Dockerfile.web \
            docker/Dockerfile.data-gateway \
            docker/Dockerfile.dashboard; do
            if [[ -f "$DEPLOY_OVERLAY_DIR/$relative_path" ]]; then
                install -D -m 0644 "$DEPLOY_OVERLAY_DIR/$relative_path" \
                    "$PROJECT_DIR/$relative_path"
            fi
        done
        log "已应用 Dockerfile 覆盖层"
    fi

    local qlib_target="$PROJECT_DIR/db/qlib_data"
    if [[ -e "$qlib_target" ]]; then
        # 新克隆仓库可能包含空目录或说明文件；只有检测到真实 Qlib 数据时才
        # 要求显式授权覆盖，避免把占位目录误判为用户数据。
        if has_qlib_features "$qlib_target"; then
            if [[ ${QUANTMIND_REPLACE_QLIB:-false} != true ]]; then
                log "检测到有效 Qlib 数据，复用现有目录: $qlib_target"
                rm -rf "$STAGING_DIR"
                return 0
            fi
        fi
        rm -rf "$qlib_target"
    fi
    mkdir -p "$PROJECT_DIR/db"
    mv "$STAGING_DIR/cn_data" "$qlib_target"
}

build_and_start() {
    log '步骤 7/7：基于最新代码重新构建并启动服务'
    cd "$PROJECT_DIR"
    # 核心镜像按最新代码重建。web/data-gateway/dashboard 已在离线包中提供
    # 成品镜像，直接复用可避免为可选服务拉取额外构建基础镜像。
    docker compose build quantmind
    docker compose up -d --pull never
    docker compose ps
}

main() {
    require_root
    require_ubuntu
    require_url "$IMAGES_URL" QUANTMIND_IMAGES_URL
    require_url "$QLIB_URL" QUANTMIND_QLIB_URL
    install_runtime
    import_images
    stage_qlib_data
    checkout_code
    build_and_start
    log "完成：代码=$PROJECT_DIR，Qlib 数据=$PROJECT_DIR/db/qlib_data"
}

main "$@"
