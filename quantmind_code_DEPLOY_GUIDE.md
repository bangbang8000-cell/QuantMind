# QuantMind 代码包部署说明

本包为 QuantMind 量化交易平台的**完整源代码**(约 20MB),不含市场数据与模型产物。使用 Docker 一键部署。

## 一、环境要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Linux / macOS / Windows(WSL2) |
| Docker | 20.10+ 与 Docker Compose v2 |
| 内存 | 8GB+(推荐 16GB) |
| 磁盘 | 50GB+(含构建镜像与数据) |
| 网络 | **需要联网**(构建时从 PyPI 下载依赖,含 torch 约 900MB) |
| NVIDIA GPU | 可选(用于训练加速,无 GPU 也可运行) |

> 注意:本包不含本地 torch wheel(`docker/torch_wheels/` 被忽略),构建时统一从 PyPI 安装 `torch==2.9.1`。首次构建需下载约 1.5GB 依赖,耗时 10-20 分钟。

## 二、快速部署

```bash
# 1. 解压
tar xzf quantmind_code_clean.tar.gz
cd quantmind_code_clean

# 2. 一键部署（自动生成 .env、构建镜像、启动服务）
chmod +x setup.sh
./setup.sh
```

`setup.sh` 会自动完成:
1. 检查 Docker 环境
2. 生成 `.env`(随机化 SECRET_KEY / JWT / DB_PASSWORD)
3. 创建数据目录(`data/ db/ models/ logs/` 等)
4. 构建 Docker 镜像(首次 10-20 分钟)
5. 启动所有服务
6. 等待核心服务就绪

## 三、服务访问

| 服务 | 地址 | 说明 |
|------|------|------|
| Web 前端 | http://localhost:3000 | 主界面 |
| API 文档 | http://localhost:8000/docs | FastAPI 接口文档 |
| Huntly | http://localhost:8090 | 资讯聚合 |
| RSSHub | http://localhost:1200 | RSS 生成 |

**默认管理员账号**:
- 用户名:`admin`
- 密码:`admin123`(登录后请立即修改)

## 四、常用命令

```bash
docker compose ps           # 查看服务状态
docker compose logs -f quantmind   # 查看后端日志
docker compose restart      # 重启服务
docker compose down         # 停止服务(保留数据)
```

## 五、市场数据

本包为纯代码,**不含行情数据**。部署后数据目录为空,需要准备数据:

- **A股数据**:`data/quantdb/`(QuantDB 格式 parquet,约 28GB)
- 从原环境拷贝 `data/` 目录,或参考 `README.md` 的 Releases 数据包下载方式
- 无数据时服务可正常启动,但行情/K线/回测功能无数据可用

## 六、注意事项

1. **首次构建联网**:构建镜像需从 PyPI(默认阿里云镜像源 `mirrors.aliyun.com`)下载依赖。若在境外,构建可能慢,可修改 `docker/Dockerfile.oss` 顶部的 `PIP_INDEX_URL`。
2. **数据与代码分离**:`data/`、`models/`、`db/` 通过 docker volume 挂载,升级代码不会覆盖数据。
3. **前端访问**:若访问 `localhost:3000` 白屏,确认 `quantmind-web` 容器已启动:`docker compose ps`。
4. **GPU 可选**:`docker-compose.yml` 中 GPU 配置默认注释,有 GPU 需取消注释 `deploy.resources.reservations.devices` 并安装 `nvidia-container-toolkit`。
5. **AutoDL 远程训练**:默认未配置。需在 `.env` 设置 `TRAINING_AUTODL_HOST` 等(见 `.env.example`)。
6. **API Key**:AI 策略生成、因子挖掘、投研分析等 AI 功能需在 `.env` 配置 `DASHSCOPE_API_KEY` / `AI_IDE_LLM_API_KEY`。未配置不影响核心功能。

## 七、包内容说明

包含:
- `backend/` — FastAPI 后端(api 8000 / engine 8001 / trade 8002 / stream 8003)
- `electron/` — Electron + React 前端
- `docker/` — Dockerfile.oss(后端镜像)、Dockerfile.autodl(AutoDL 训练)
- `config/` — 数据源路由、模型配置
- `scripts/` — 数据同步、部署脚本
- `alphaagent/`、`rd-agent/`、`TradingAgents-astock/` — 因子挖掘 / 投研框架

不含(已在 .gitignore 排除):
- `models/`、`data/`、`logs/` — 运行时产物
- `analysis/`、`research/`、`scratch/`、`examples/` 等分析/临时目录
- 本地 torch wheel、模型预测文件

## 八、版本

代码对应 git commit:`9e8ebf9`(含北交所 920 修复、PSI 双通道、目录清理、Dockerfile torch 修复)。
