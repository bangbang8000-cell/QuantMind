# QuantMind 服务器部署指南

## 快速部署（推荐）

在服务器上执行以下命令：

```bash
# 一键部署
curl -fsSL https://gitee.com/qusong0627/QuantMind/raw/master/deploy/quick-deploy.sh | sudo bash
```

## 完整离线包部署（CDN 镜像 + Qlib 数据）

适用于无法稳定拉取 Docker Hub、或希望先下载完整镜像和 Qlib 数据再部署的 Ubuntu 22.04/24.04 服务器。
脚本会依次更新系统、安装 Docker/Compose、下载并校验离线包、导入镜像、安装 Qlib 数据、拉取代码、重建本地服务镜像并启动服务。

CDN 发布包：

- `https://cdn.quantmind.cloud/quantmind-images.tar.zst`
- `https://cdn.quantmind.cloud/qlib-cn_data.tar.zst`

在项目根目录执行：

```bash
sudo bash deploy/offline-deploy.sh
```

也可以不预先克隆代码，直接执行：

```bash
curl -fsSL https://gitee.com/qusong0627/QuantMind/raw/master/deploy/offline-deploy.sh | sudo bash
```

默认安装目录为 `/opt/quantmind`，下载包缓存目录为 `/opt/quantmind-downloads`，Qlib 数据最终位于 `/opt/quantmind/db/qlib_data`。

若需切换 CDN 或指定版本，可覆盖默认值：

```bash
sudo QUANTMIND_IMAGES_URL='https://example.com/quantmind-images.tar.zst' \
  QUANTMIND_QLIB_URL='https://example.com/qlib-cn_data.tar.zst' \
  QUANTMIND_REF='v1.9.0-beta' \
  bash deploy/offline-deploy.sh
```

脚本不会覆盖已有的 Qlib 数据；确认更新数据包时，额外设置 `QUANTMIND_REPLACE_QLIB=true`。

## 指定服务器IP

脚本会自动检测服务器IP，优先级如下：
1. 命令行参数：`sudo ./deploy.sh 192.168.1.100`
2. 环境变量：`export QUANTMIND_SERVER_IP=192.168.1.100 && sudo ./deploy.sh`
3. 自动检测：公网IP → 局域网IP → localhost

### 本机部署（无公网IP）

```bash
# 方式1：使用localhost
sudo ./deploy.sh localhost

# 方式2：使用局域网IP
sudo ./deploy.sh 192.168.1.100

# 方式3：让脚本自动检测
sudo ./deploy.sh
```

## 手动部署

### 1. 克隆代码

```bash
sudo git clone https://gitee.com/qusong0627/QuantMind.git /opt/quantmind
cd /opt/quantmind
```

### 2. 执行部署脚本

```bash
sudo chmod +x deploy/deploy.sh
sudo ./deploy/deploy.sh
```

## 部署步骤说明

### 第一阶段：系统准备
- 更新系统依赖
- 安装 Docker & Docker Compose

### 第二阶段：代码部署
- 从 Gitee 克隆代码
- 配置环境变量
- 创建数据目录

### 第三阶段：服务部署
- 构建 Docker 镜像（quantmind-oss 核心镜像，可选镜像由 compose 自动构建）
- 启动全部服务：PostgreSQL、Redis、QuantMind（4 业务服务）、Celery（worker/beat）、Web 前端、数据网关、数据看板、资讯聚合、RSSHub、QwenPaw
- 初始化数据库并创建默认管理员

### 第四阶段：验证
- 健康检查
- 防火墙配置

## 访问地址

部署完成后，根据部署方式访问：

| 服务 | 地址 |
|-----|------|
| Web 前端 | http://服务器IP:3000 |
| 后端 API | http://服务器IP:8000 |
| Engine | http://服务器IP:8001 |
| Trade | http://服务器IP:8002 |
| Stream | http://服务器IP:8003 |
| 数据网关 | http://服务器IP:8004 |
| 数据看板 | http://服务器IP:8501 |
| 资讯聚合 | http://服务器IP:8090 |
| RSSHub | http://服务器IP:1200 |
| QwenPaw | http://服务器IP:8089 |

> 本机部署时，使用 `http://localhost` 访问各服务。
> 桌面客户端（Electron）下载后直接连接后端 API 地址即可，无需服务器端前端。

## 默认账号

- 用户名：`admin`
- 密码：需要通过 API 重置

## 常用命令

```bash
# 查看所有服务状态
docker compose -f /opt/quantmind/docker-compose.yml ps

# 查看后端日志
docker compose -f /opt/quantmind/docker-compose.yml logs -f quantmind

# 重启所有服务
docker compose -f /opt/quantmind/docker-compose.yml restart

# 重启单个服务
docker compose -f /opt/quantmind/docker-compose.yml restart <服务名>
```

## 目录结构

```
/opt/quantmind/
├── backend/            # 后端代码
├── electron/           # 前端代码
├── docker-compose.yml
├── .env                # 环境配置
└── data/               # 数据目录
    ├── postgres/       # 数据库数据
    ├── redis/          # Redis 数据
    ├── logs/           # 日志
    ├── models/         # 模型文件
    └── qlib_data/      # Qlib 数据
```

## 端口说明

| 端口 | 服务 | 说明 |
|-----|------|------|
| 3000 | Web Frontend | Web 前端（容器）|
| 8000 | API | 后端 API |
| 8001 | Engine | 回测引擎 |
| 8002 | Trade | 交易服务 |
| 8003 | Stream | 实时行情 |
| 8004 | Data Gateway | 多数据源金融数据网关 |
| 5432 | PostgreSQL | 数据库 |
| 6379 | Redis | 缓存 |
| 8501 | Dashboard | 数据看板 (Streamlit) |
| 8090 | Huntly | 财经资讯聚合 |
| 1200 | RSSHub | RSS 源生成 |
| 8089 | QwenPaw | QuantBot 聊天机器人 |

## 故障排查

### 后端无法启动

```bash
# 查看日志
docker compose logs quantmind

# 检查数据库连接
docker exec quantmind-db pg_isready -U quantmind

# 检查 Redis 连接
docker exec quantmind-redis redis-cli ping
```

### Web 前端无法访问

```bash
# 检查 web 容器状态
docker compose -f /opt/quantmind/docker-compose.yml ps web

# 查看 web 容器日志
docker compose -f /opt/quantmind/docker-compose.yml logs web

# 重启 web 容器
docker compose -f /opt/quantmind/docker-compose.yml restart web
```

## 更新部署

```bash
cd /opt/quantmind

# 拉取最新代码
git pull origin master

# 重新构建并启动
docker compose build
docker compose up -d
```

## 一键更新脚本（推荐）

脚本位置：`deploy/update.sh`

特点：
- 自动从 Gitee 拉取最新代码
- 自动重建后端容器（quantmind、celery-worker、celery-beat + 可选服务）
- 不执行数据库初始化，不删除数据库数据
- 不重建 db/redis 容器
- 可选服务（web/data-gateway/dashboard/huntly/rsshub/qwenpaw）更新失败仅警告

```bash
cd /opt/quantmind
sudo bash deploy/update.sh
```

可选参数：

```bash
# 强制覆盖本地修改后更新（谨慎）
sudo bash deploy/update.sh --force-sync
```

## 卸载

```bash
# 停止并移除所有服务
docker compose -f /opt/quantmind/docker-compose.yml down

# 删除数据（谨慎操作）
rm -rf /opt/quantmind
```
