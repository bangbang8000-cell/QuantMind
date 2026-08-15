---
name: quantmind-deploy
description: "QuantMind 部署与运维 — 一键部署、快速部署、Docker 部署、数据库初始化、部署问题排查。在 QuantBot / Claude Code 中部署 QuantMind、排查部署失败、初始化数据库、检查服务健康、更新部署时使用。触发词：部署、一键部署、快速部署、部署失败、装不上、怎么部署、docker部署、部署问题、数据库初始化、服务起不来"
---

# QuantMind 部署技能

QuantMind 部署运维完整指南。覆盖**部署前准备 → 一键/手动部署 → 部署后检查 → 问题排查 → 更新 → 云端训练**全流程。本技能针对 AI 编程助手编写，每步都给出可直接执行的命令与判断标准，避免"不知道下一步"卡壳。

## 0. 安装技能包（让 AI 帮你部署）

本技能包兼容**主流 AI 编程工具**（Claude Code / Codex / OpenCode / Trae / MarsCode 等），安装后 AI 能自动识别"部署/装不上"等意图并调用本技能指导部署。

### 方式一：Claude Code / QuantBot（原生 SKILL.md）
```bash
# 解压到 Claude Code 全局技能目录
unzip quantmind-operations-skill.zip -d ~/.claude/
# 验证
ls ~/.claude/skills/quantmind-deploy/SKILL.md
```

### 方式二：从项目仓库安装（任何工具）
```bash
# 项目根目录 .claude/skills/ 下即全部技能
cp -r /opt/quantmind/.claude/skills/* ~/.claude/skills/
```

### 方式三：其他主流 AI 工具（OpenCode / Codex / Trae / MarsCode 等）
各工具虽不原生识别 SKILL.md，但都读取 **AGENTS.md**（项目级指令）。把技能包要点导入即可：
```bash
# ① 通用做法：把 SKILL.md 内容并入 AGENTS.md
# 项目根创建/追加 AGENTS.md，把关键流程粘贴进去
cat ~/.claude/skills/quantmind-deploy/SKILL.md >> AGENTS.md

# ② OpenAI Codex
unzip quantmind-operations-skill.zip -d ~/.codex/
# Codex 读取 ~/.codex/AGENTS.md（把本技能要点放入）

# ③ OpenCode
unzip quantmind-operations-skill.zip -d ~/.config/opencode/
# 或在项目根 AGENTS.md 引用本技能要点

# ④ 腾讯 Trae / 字节 MarsCode
# 克隆仓库后把 SKILL.md 要点写入项目 AGENTS.md，AI 即可按流程部署
```

### 让 AI 部署
安装技能后，直接对 AI 助手说：
- "帮我部署 QuantMind" → AI 读取本技能，按"部署前准备→部署→检查"执行
- "部署不上，帮我排查" → AI 按"问题排查"诊断树逐项定位
- "一键部署" → AI 执行 `quick-deploy.sh`

### 推荐编程工具（部署环境）
| 工具 | 用途 | 说明 |
|------|------|------|
| **Claude Code** | AI 编程/部署助手 | 原生支持 SKILL.md，装技能包即自动识别 |
| **OpenCode** | AI 编程助手 | 开源，读 AGENTS.md |
| **OpenAI Codex** | AI 编程助手 | 读 ~/.codex/AGENTS.md |
| **腾讯 Trae / 字节 MarsCode** | AI IDE | 读项目 AGENTS.md |
| **VS Code** | 代码编辑 | 前端/后端调试 |
| **Docker Desktop** | 容器管理 | 本地调试用，服务器用 docker-ce |
| **MobaXterm / Termius** | SSH 终端 | 连服务器执行部署命令 |
| **Git** | 版本管理 | 拉取/更新代码 |

## 架构总览

QuantMind 单机 Docker Compose 部署（`docker-compose.yml`），11+ 服务：

| 容器 | 服务 | 端口 | 说明 |
|------|------|------|------|
| `quantmind-db` | PostgreSQL 15 | 5432 | 主数据库 |
| `quantmind-redis` | Redis 7 | 6379 | 缓存/消息（DB 0-5 分配） |
| `quantmind` | 后端主服务 | 8000-8003 | api/engine/trade/stream 四合一 |
| `quantmind-celery` | Celery Worker | — | 异步任务（回测/同步/推理） |
| `quantmind-celery-beat` | Celery Beat | — | 定时调度 |
| `quantmind-web` | 前端 Web | 80 | Nginx 托管 React 构建产物 |
| `quantmind-data-gateway` | 数据网关 | — | 行情/资金流聚合 |
| `quantmind-dashboard` | Dashboard | — | 数据概览 |
| `quantmind-huntly` | Huntly | 8090 | RSS 新闻存储/阅读器 |
| `quantmind-rsshub` | RSSHub | 1200 | 通用网站订阅 |
| `qwenpaw` | QwenPaw | — | AI 代理（可选） |

## 1. 部署前准备（重要，先做完再部署）

### 1.1 环境要求（多系统 + 硬件）
| 项目 | 要求 | 说明 |
|------|------|------|
| **系统** | Ubuntu 22.04 LTS 或 24.04 LTS | **部署脚本仅支持 Ubuntu 22.04+**，其他系统会被拒绝 |
| **Windows** | Docker Desktop + WSL2 后端 | 在 WSL2 终端内执行 `docker compose` |
| **macOS** | Docker Desktop 直接运行 | 兼容 |
| **云服务器** | 任意 Docker 环境 | 单机即可 |
| **CPU 架构** | **仅 x86_64 / AMD64** | **ARM（aarch64）不支持**——微软 Qlib 框架仅发布 x86_64，ARM 无法装 Qlib |
| **CPU** | 4 核以上 | 推荐 8 核（训练/回测耗 CPU） |
| **内存** | 16GB 以上（运行） | 模型训练推荐 **64GB+**，推理/回测 **32GB+**；内存不足会 OOM 训练卡死 |
| **磁盘** | 100GB 以上可用 | 数据 + 镜像 + 特征快照（~15GB）+ 模型 |

> ⚠️ 训练机建议 ≥64GB 内存；若只有 32GB，缩小时间窗/特征数避免 OOM。

### 1.2 网络检查（部署前必测）
国内服务器常需配置镜像源。部署脚本会自动选 Docker/PyPI/APT 镜像源，也可手动指定。
```bash
# 检查 DNS + 各仓库连通性（任一失败先解决再部署）
curl -fsSL --connect-timeout 5 https://gitee.com >/dev/null && echo "gitee OK" || echo "gitee FAIL"
curl -fsSL --connect-timeout 5 https://registry.npmmirror.com >/dev/null && echo "npm OK" || echo "npm FAIL"
curl -fsSL --connect-timeout 5 https://pypi.org >/dev/null && echo "pypi OK" || echo "pypi FAIL"
docker info >/dev/null 2>&1 && echo "docker OK" || echo "docker 未安装（部署脚本会装）"
```
**网络差时的应对**：
- 手动指定镜像源：`QUANTMIND_MIRROR=aliyun sudo bash deploy.sh`（或 `tuna`/`huaweicloud`）
- Docker 镜像源：`/etc/docker/daemon.json` 配置 `registry-mirrors`（阿里云/腾讯云镜像加速）
- PyPI 源：`PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/`（构建镜像时 `--build-arg`）

### 1.3 提前决定要填写的内容
部署脚本会**交互式**问你以下内容，提前准备好答案：

| 部署时问什么 | 示例答案 | 说明 |
|---|---|---|
| 服务器 IP | `192.168.1.100` / `localhost` | 无公网 IP 用 localhost 或局域网 IP |
| 选择镜像源 | 国内选阿里云/中科大 | 网络差时自动选，也可 `QUANTMIND_MIRROR=` 指定 |
| 是否确认部署 | `y` | 确认后开始安装 |
| （可选）QuantDB API Key | `qdb_xxx` | **部署后**在后台填，见 [[quantdb-sdk]] |

### 1.4 部署前备份
```bash
# 若已有旧数据/旧部署，先备份
sudo cp -r /opt/quantmind/data /opt/quantmind/data.bak.$(date +%Y%m%d)
```

## 2. 一键部署（推荐）

```bash
# 需要 root 权限；默认固定到发布 tag v1.9.0-beta（可复现、可校验）
curl -fsSL https://gitee.com/qusong0627/QuantMind/raw/v1.9.0-beta/deploy/quick-deploy.sh | sudo bash

# 使用最新 master（不推荐生产）
QUANTMIND_DEPLOY_TAG=master curl -fsSL https://gitee.com/qusong0627/QuantMind/raw/master/deploy/quick-deploy.sh | sudo bash

# 校验 deploy.sh 完整性（生产建议设置 SHA256）
QUANTMIND_DEPLOY_SHA256=<sha256> QUANTMIND_DEPLOY_TAG=v1.9.0-beta sudo bash quick-deploy.sh
```

**部署 6 阶段**：
1. **系统准备**：更新依赖、装 Docker & Compose v2.19+、Node 20、Nginx
2. **代码部署**：从 Gitee 克隆到 `/opt/quantmind`、配置 `.env`、创建数据目录
3. **后端部署**：构建 Docker 镜像、启动 PG/Redis/QuantMind、**执行 `db_init.sql` 初始化数据库**
4. **前端部署**：npm 依赖 + 构建 + PM2 启动
5. **Nginx 配置**：反向代理
6. **验证**：健康检查 + 防火墙

## 3. 快速部署（已下载脚本）

```bash
sudo bash deploy/quick-deploy.sh
# 指定服务器 IP（公网/局域网/localhost 自动检测）
sudo bash deploy/deploy.sh localhost
sudo bash deploy/deploy.sh 192.168.1.100
QUANTMIND_SERVER_IP=192.168.1.100 sudo bash deploy/deploy.sh
```

## 4. 手动部署

```bash
sudo git clone https://gitee.com/qusong0627/QuantMind.git /opt/quantmind
cd /opt/quantmind
sudo chmod +x deploy/deploy.sh
sudo ./deploy/deploy.sh
```

## 5. 数据库初始化（关键）

**deploy.sh 自动执行 `backend/shared/db_init.sql`**（含 users 等全部核心表）：
- 容器内路径 `/app/backend/shared/db_init.sql`（由 `./backend:/app/backend` 挂载提供）
- 优先从 quantmind 容器执行 psql，失败则从 db 容器执行
- 若存在 `data/quantmind_init.sql` 则补充初始化数据

```bash
# 手动执行数据库初始化
docker exec quantmind bash -c "psql -h db -U quantmind -d quantmind -f /app/backend/shared/db_init.sql --quiet -v ON_ERROR_STOP=0"
```

**初始化后必须验证 users 表存在**（最常见部署失败点）：
```bash
docker exec quantmind-db psql -U quantmind -d quantmind -c "\dt users"
# 期望看到 users 表；若不存在说明 db_init.sql 没跑成功
```

## 6. 部署后检查（按顺序，每步都过再继续）

### 6.1 容器健康
```bash
docker compose -f /opt/quantmind/docker-compose.yml ps
# 期望 quantmind/quantmind-celery/quantmind-celery-beat/quantmind-web/quantmind-db/quantmind-redis 都 Up
```

### 6.2 数据库 & Redis
```bash
docker exec quantmind-db pg_isready -U quantmind          # 期望 "accepting connections"
docker exec quantmind-redis redis-cli ping                # 期望 "PONG"
```

### 6.3 后端 API 健康
```bash
curl -s http://localhost:8000/api/v1/health
# 期望返回 {"status":"healthy", ...} 含 api/engine/trade/stream 四服务
```

### 6.4 登录验证（关键：验证 users 表 + 认证链路）
```bash
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123","tenant_id":"default"}'
# 期望返回 access_token；若 401/500 → users 表问题（见排查）
```

### 6.5 前端访问
```bash
curl -s -I http://localhost | head -1   # 期望 200 OK
```

### 6.6 登录后台 + 配置数据源
1. 浏览器访问 `http://服务器IP`，用 admin 登录
2. 后台「数据管理」配置 **QuantDB API Key**（见 [[quantdb-sdk]]）
3. 触发一次数据同步（见 [[quantmind-operations]] 第 3 节）

## 7. 更新部署

```bash
cd /opt/quantmind
# 一键更新脚本（拉代码 + 重建后端容器，不动数据库）
sudo bash deploy/update.sh
# 强制覆盖本地修改（谨慎）
sudo bash deploy/update.sh --force-sync

# 手动更新
git pull origin master
docker compose build
docker compose up -d
```

## 8. 云端 GPU 训练（AutoDL）

模型训练可跑在 **AutoDL 远程 GPU 节点**（本地 Docker 是 CPU 训练）。

### AutoDL 训练节点配置
```bash
# 列出训练节点（本地 Docker + AutoDL 远程 GPU）
curl -s -H "$AUTH" "$BASE/api/v1/admin/models/training-nodes"
# 测试节点连接（SSH + docker 可用性）
curl -s -X POST -H "$AUTH" -H "$CT" "$BASE/api/v1/admin/models/training-nodes/test" \
  -d '{"node_id":"autodl-1"}'
# 新增/更新节点配置（SSH 凭据等）
curl -s -X POST -H "$AUTH" -H "$CT" "$BASE/api/v1/admin/models/training-nodes/config" \
  -d '{"node_id":"autodl-1","host":"<ip>","port":22,"user":"root","ssh_key":"<key>","description":"AutoDL 4卡A100"}'
# 节点实时状态（CPU/GPU/内存/训练容器）
curl -s -H "$AUTH" "$BASE/api/v1/admin/models/training-nodes/{node_id}/status"
# 节点详情 / 删除
curl -s -H "$AUTH" "$BASE/api/v1/admin/models/training-nodes/{node_id}/detail"
curl -s -X DELETE -H "$AUTH" "$BASE/api/v1/admin/models/training-nodes/{node_id}"
```

### AutoDL 远程训练镜像
```bash
# 在 AutoDL 节点从 git 直接构建（独立轻量镜像，仅训练依赖）
docker build --build-arg TORCH_DEVICE=gpu -f docker/autodl/Dockerfile -t quantmind-train:latest .
# 或一键远程构建脚本
bash scripts/setup/build-autodl-remote.sh
```

### 远程训练流程
1. **配节点**：`training-nodes/config` 存 AutoDL 节点 SSH 配置（`config/training_nodes.yaml`，含 SSH 凭据，gitignore 不入仓库）
2. **测连接**：`training-nodes/test` 验证 SSH + docker
3. **启动训练**：`run-training` 时选 `node_id=autodl-x`（GPU 训练）
4. **看状态**：`training-runs/{run_id}` 轮询；节点实时状态 `training-nodes/{node_id}/status`
5. **模型回传**：训练完模型 scp 回传注册到 `/models`

## 9. 问题排查（诊断树，按顺序走）

### 9.1 先看这 3 条命令的输出（快速定位）
```bash
# 1. 容器状态（谁没起来）
docker compose -f /opt/quantmind/docker-compose.yml ps

# 2. 后端日志（报什么错）
docker compose -f /opt/quantmind/docker-compose.yml logs --tail=100 quantmind

# 3. 数据库连接
docker exec quantmind-db pg_isready -U quantmind
```

### 9.2 诊断树
```
部署后不能访问？
├─ curl localhost:8000/api/v1/health 失败
│   ├─ 容器没起来 → docker compose ps 看状态 → docker compose logs quantmind 看报错
│   ├─ 端口被占 → netstat -tlnp | grep 8000 → 释放冲突端口
│   └─ 数据库连不上 → docker exec quantmind-db pg_isready → 重启 db 容器
├─ health OK 但登录失败（401/500）
│   ├─ users 表不存在 → docker exec quantmind-db psql -U quantmind -d quantmind -c "\dt users"
│   │     → 无表则手动执行 db_init.sql（见第 5 节）
│   └─ SECRET_KEY 不一致 → 检查 .env 的 JWT_SECRET_KEY，重启后端
├─ 登录成功但前端打不开
│   ├─ curl -s -I http://localhost 失败 → nginx -t → systemctl restart nginx
│   ├─ PM2 没起 → pm2 status → pm2 restart quantmind-web
│   └─ 前端构建问题 → cd /opt/quantmind/electron && npm install && npm run dashboard:build
└─ 都正常但页面报"数据缺失"
    ├─ 未配 QuantDB API Key → 后台「数据管理」填 Key（见 [[quantdb-sdk]]）
    └─ 未同步数据 → [[quantmind-operations]] 第 3 节触发同步
```

### 9.3 常见问题速查表

| 现象 | 原因 | 处理 |
|---|---|---|
| **用户表不存在 / 登录失败** | db_init.sql 未执行 | 手动执行 db_init.sql（见第 5 节）；确认 `\dt users` |
| **Docker Compose 版本过低** | 需 v2.19+ | `docker compose version`，装 docker-compose-plugin |
| **镜像拉取慢/失败** | 网络源 | 脚本自动选 Docker/PyPI/APT 镜像源，可手动 `--build-arg` 指定 |
| **torch 安装失败** | GPU/CPU 兼容 | Dockerfile 支持 `TORCH_DEVICE=cpu/gpu/skip`（skip 适合纯行情/交易） |
| **容器起不来** | 端口冲突 / 配置 | `docker compose logs quantmind` 看日志 |
| **数据库连接失败** | PG 未就绪 | `docker exec quantmind-db pg_isready -U quantmind` |
| **前端 502** | Nginx/PM2 | `nginx -t` + `pm2 status` + `pm2 restart quantmind-web` |
| **quantdb-sdk 安装失败** | 版本兼容 | Dockerfile 用 `quantdb-sdk>=0.3.1`，换源重装 |
| **北向/南向无数据** | 未同步 | 跑 `quantdb_north_sync` / `quanthk_south_sync` |
| **GPU 训练不生效** | 未配 AutoDL 节点 | `training-nodes/config` 配置后选 node_id |
| **AutoDL 节点连不上** | SSH 配置错 | `training-nodes/test` 诊断 SSH/docker |

### 9.4 AI 助手部署常见坑（给编程 AI 的提示）

| AI 常犯错误 | 正确做法 |
|---|---|
| 跳过交互式确认 | `quick-deploy.sh` 是交互式，用 `echo y | sudo bash ...` 或确认到 `--yes` |
| 忽略系统版本 | 必须先 `check_system`（仅 Ubuntu 22.04+） |
| 不检查 users 表 | 部署后必查 `\dt users`，这是登录失败主因 |
| 直接 `docker-compose` | 新版用 `docker compose`（带空格） |
| 忘配 QuantDB Key | 部署完成≠能用，还需在后台填 API Key + 同步数据 |
| 端口冲突硬上 | 先 `netstat -tlnp` 看占用，改 compose 端口 |
| 忘重启容器 | 改 `.env`/代码后要 `docker compose restart` 才生效 |
| 直接用 gitee master | 生产固定 `v1.9.0-beta` tag，可复现 |

## 数据目录（持久化）

```
/opt/quantmind/data/
├── postgres/       # 数据库数据
├── redis/          # Redis 数据
├── quantdb/        # QuantDB A股 parquet
├── quantus/        # 美股 parquet
├── quanthk/        # 港股 parquet
├── quantbc/        # 区块链 parquet
├── quantfutures/   # 期货 parquet
├── logs/           # 日志
└── models/         # 模型文件
```

## 相关技能

- **[[quantmind-operations]]** — 部署后数据同步、模型训练、推理
- **[[quantdb-sdk]]** — QuantDB 数据源配置（API Key）
- **[[simulation-trading]]** — 部署后模拟盘验证
