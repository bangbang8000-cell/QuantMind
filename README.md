# QuantMind OSS

QuantMind 是面向 A 股研究、模型训练、推理、回测与模拟交易的一体化量化平台。

![QuantMind 市场看板](docs/images/Dashboard.png)

## 产品预览

从市场数据到模型、信号、回测和交易，QuantMind 将日常量化研究工作流整合在同一套界面中。

### 市场监控与资讯

![市场看板](docs/images/Dashboard.png)

<table>
  <tr>
    <td width="50%"><strong>AI-IDE 策略工作区</strong><br><img src="docs/images/AI-IDE.png" alt="AI-IDE 策略工作区"></td>
    <td width="50%"><strong>RSS 资讯流</strong><br><img src="docs/images/RSS.png" alt="RSS 资讯流"></td>
  </tr>
</table>

### 模型与研究闭环

<table>
  <tr>
    <td width="50%"><strong>智能因子挖掘</strong><br><img src="docs/images/FactorMining.png" alt="智能因子挖掘"></td>
    <td width="50%"><strong>模型训练工场</strong><br><img src="docs/images/ModelTraining.png" alt="模型训练工场"></td>
  </tr>
  <tr>
    <td width="50%"><strong>批量推理与选股</strong><br><img src="docs/images/ModelInference.png" alt="批量推理与选股"></td>
    <td width="50%"><strong>Qlib 回测中心</strong><br><img src="docs/images/QuickBacktest.png" alt="Qlib 回测中心"></td>
  </tr>
</table>

### 核心能力

- 市场分析、资金流、RSS 资讯与 QuantBot
- Qlib 模型训练、模型资产管理、批量推理与选股
- 回测中心、策略工作区与因子研究
- 模拟实盘、风险检查与交易回放

<details>
  <summary>查看系统架构</summary>
  <br>
  <img src="docs/images/architecture.svg" alt="QuantMind 系统架构">
</details>

## 部署

支持 Ubuntu 22.04 / 24.04。生产环境推荐完整离线部署，离线包包含服务镜像、业务数据、模型、Qlib 数据和 PostgreSQL 备份。

### 完整离线部署（推荐）

上传 `quantmind-offline` 目录到 CDN 后，在目标服务器执行：

```bash
curl -fsSL https://gitee.com/qusong0627/QuantMind/raw/master/deploy/offline-deploy.sh | sudo bash
```

默认从 `https://cdn.quantmind.cloud/quantmind-offline` 下载。部署完成后访问：

- API：`http://<服务器 IP>:8000/docs`
- Web：`http://<服务器 IP>:3000`
- Dashboard：`http://<服务器 IP>:8501`

可指定离线包地址和代码分支：

```bash
sudo QUANTMIND_OFFLINE_BASE_URL='https://example.com/quantmind-offline' \
  QUANTMIND_REF='master' \
  bash deploy/offline-deploy.sh
```

已有业务数据默认不会覆盖。需要强制恢复时，显式添加：

```bash
QUANTMIND_REPLACE_QLIB=true \
QUANTMIND_REPLACE_BUSINESS_DATA=true \
QUANTMIND_REPLACE_DATABASE=true \
QUANTMIND_REPLACE_QWENPAW_DATA=true
```

### 在线部署

适用于可以从代码仓库和镜像仓库稳定下载的服务器：

```bash
curl -fsSL https://gitee.com/qusong0627/QuantMind/raw/master/deploy/deploy.sh | sudo bash
```

默认安装到 `/opt/quantmind`。已有代码目录时，脚本会拒绝覆盖未提交修改；确认覆盖可加 `--force`。

### 一键更新

在已部署服务器的项目目录执行：

```bash
sudo bash deploy/update.sh
```

更新脚本会拉取最新代码、重建核心后端镜像、重启核心服务并检查健康状态；不会删除 PostgreSQL、Redis、模型或 Qlib 数据。

```bash
sudo bash deploy/update.sh --ref NEXT
sudo bash deploy/update.sh --force
```

更多离线包恢复说明见 [deploy/README.md](deploy/README.md)。

## 本地开发

```bash
# 后端测试
python backend/run_tests.py unit

# 前端开发
cd electron
npm install
npm run dev
npm run typecheck
```

后端服务统一由 `backend/main_oss.py` 启动：API（8000）、引擎（8001）、交易（8002）和行情流（8003）。

## 项目结构

```text
backend/       FastAPI 服务、Qlib 引擎与共享模块
electron/      Electron + React 客户端
dashboard/     Streamlit 监控看板
db/qlib_data/  Qlib 本地数据目录
deploy/        在线、离线部署和更新脚本
docker-compose.yml
```

## 贡献与声明

提交前请运行与改动匹配的测试。股票代码在内部统一使用前缀格式，例如 `SH600036`。

本项目仅供研究与学习，不构成任何投资建议。
