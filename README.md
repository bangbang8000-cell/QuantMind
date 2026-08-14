<h1 align="center">QuantMind</h1>

<p align="center">
  <strong>🚀 开箱即用的 AI 量化交易平台 —— 数据到手，即可训练</strong>
</p>

<p align="center">
  <em>Multi-Market Quantitative Trading Platform · A股 / 港股 / 美股 / 区块链 / 期货</em>
</p>

<p align="center">
  <code>QuantDB 专业数据 → 13 种 AI 模型训练 → 远程 GPU 训练 → 多市场推理 → 信号生成</code>
</p>

<p align="center">
  <a href="#-项目简介">项目简介</a> •
  <a href="#-核心亮点">核心亮点</a> •
  <a href="#-a股数据优势">A股数据优势</a> •
  <a href="#-系统架构">系统架构</a> •
  <a href="#-模型训练">模型训练</a> •
  <a href="#-远程训练">远程训练</a> •
  <a href="#-模型推理">模型推理</a> •
  <a href="#-核心功能">核心功能</a> •
  <a href="#-通达信量化推送">通达信推送</a> •
  <a href="#-技术栈">技术栈</a> •
  <a href="#-快速开始">快速开始</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/Node.js-20+-green.svg" alt="Node.js">
  <img src="https://img.shields.io/badge/TypeScript-5.x-blue.svg" alt="TypeScript">
  <img src="https://img.shields.io/badge/Qlib-Powered-orange.svg" alt="Qlib">
  <img src="https://img.shields.io/badge/GPU-训练-AutoDL.svg" alt="GPU">
  <img src="https://img.shields.io/badge/License-AGPL%20v3-blue.svg" alt="License">
</p>

---

## 📖 项目简介

**QuantMind 开源版** 是一款面向个人量化研究者的本地化金融量化交易平台，基于微软 **Qlib** 量化框架构建，提供从**模型训练 → 回测 → 推理 → 实盘交易**的完整研究闭环。

平台深度集成 **13 种主流机器学习模型**（LightGBM/XGBoost/CatBoost/GRU/LSTM/Transformer 等），支持 **151+ 维量化因子**训练与推理，用户可快速构建 Alpha 策略并在历史数据上验证效果。

**核心特色：**

- **🧠 模型训练与推理**：13 种模型可视化训练，Optuna 自动调参，多周期/多模型融合，远程 GPU 训练；训练完成自动注册、一键推理，多市场（A股/港股/美股/区块链/期货）信号生成
- **📊 QuantDB 专业 A 股数据**：开箱即用的专业数据集合，5000+ 只 A 股、315 维 AI 因子、专业清洗、每日自动更新 —— **数据到位，直接训练**
- **🤖 AI 全流程**：智能策略生成、QuantBot 助手、RD-Agent 自动因子挖掘、多 Agent 投研
- **🔒 本地化部署**：docker compose 一键启动，数据与模型完全本地化，无需云服务，保障研究隐私

适合个人开发者、学术研究者及小团队进行量化策略原型验证与二次开发，是进入金融量化领域的理想起点。


---

## ⚡ 核心亮点

**QuantMind 是"数据到位即可训练"的量化平台** —— 解决了量化入门最大的痛点：**数据难、特征难、训练难、部署难**。

| 痛点 | QuantMind 解法 |
|------|---------------|
| 数据难获取 | **QuantDB 专业数据**，一条命令拉全，无需自己爬 |
| 特征难构建 | **151+ 维特征** 自动生成（动量/波动/流动性/资金流/风格）|
| 训练门槛高 | **13 种模型** 一行配置，前端可视化训练，支持远程 GPU |
| 推理部署难 | 训练完自动注册，一键推理，信号生成闭环 |

**从零到第一个模型，只需 30 分钟。**

---

## 🇨🇳 A股数据优势（QuantDB）

> 数据来源：**[https://quantdb.quantmind.cloud/](https://quantdb.quantmind.cloud/)**

QuantMind 的 A 股数据由 **QuantDB 专业数据服务**提供，这是本平台的核心竞争力之一 —— **你不需要自己爬数据、清洗数据、对齐复权**。

### QuantDB A 股数据特点

- **📊 覆盖全市场 5000+ 只 A 股**，含完整行情、财报、估值、资金流
- **✅ 专业清洗**：已处理复权、停牌、涨跌停、ST 标记、假日填充
- **🧮 高质量特征**：直接提供 **315 维 AI 因子** 与标准化特征，无需自研
- **🚀 高性能存储**：Parquet 列式存储 + DuckDB 查询，秒级加载 1000 万行
- **🔄 每日自动更新**：`quantdb_daily_sync` 一条命令增量同步

### 相比自建数据的优势

| 维度 | 自建（baostock/akshare）| QuantDB |
|------|------------------------|---------|
| 数据清洗 | 需自行处理复权/停牌 | 已专业清洗 |
| 特征计算 | 需自行写 151 维特征 | 自带 315 维 AI 因子 |
| 一致性 | 多源不一致 | 单一权威源 |
| 更新时间 | 手动维护 | 每日自动同步 |
| 起跑速度 | 数天准备 | **开箱即用** |

**核心价值：把时间花在模型上，而不是数据上。**

---

## 🏗️ 系统架构

### 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                      前端 (Electron + React + TS)            │
│  市场分析 · 智能策略 · 模型训练 · 模型管理 · 回测中心 · 模拟盘  │
│  QuantBot · 投研平台 · RSS信息流 · 通达信推送 · 后台管理        │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP / WebSocket
┌──────────────────────────▼──────────────────────────────────┐
│                    后端微服务 (FastAPI)                       │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐            │
│  │ API :8000│ │Engine:8001│ │Trade:8002│ │Stream:8003│       │
│  │用户/策略 │ │Qlib/训练 │ │订单/风控 │ │行情推送  │          │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘            │
└───────┬──────────────────┬──────────────────┬───────────────┘
        │                  │                  │
  ┌─────▼─────┐     ┌──────▼──────┐    ┌──────▼──────┐
  │ QuantDB   │     │ 训练引擎     │    │ AutoDL GPU  │
  │ 数据服务   │     │ Qlib+Optuna │    │ 远程训练节点 │
  └───────────┘     └─────────────┘    └─────────────┘
```

### 核心服务

| 服务 | 端口 | 职责 |
|------|------|------|
| **api** | 8000 | 用户认证、策略管理、社区、新闻代理 |
| **engine** | 8001 | Qlib 回测、AI 策略生成、**模型训练/推理**、Alpha Agent |
| **trade** | 8002 | 订单管理、持仓、风控、**模拟交易** |
| **stream** | 8003 | 实时行情、WebSocket 推送 |

### 数据流

```
QuantDB 数据 → 特征工程(151+维) → 特征快照(Parquet) → 模型训练
     → 模型注册 → 推理(多市场) → 信号生成 → 回测/策略/模拟盘
```

---

## 🧠 模型训练

QuantMind 内置 **13 种专业模型**，覆盖从传统机器学习到深度学习的完整谱系，前端可视化配置，开箱即用。

### 13 种训练模型

| 类别 | 模型 | 优势 |
|------|------|------|
| **树模型** | LightGBM | 极速训练，A股 IC 最稳定，首选基线 |
| | XGBoost | 异构集成，与 LGB 互补 |
| | CatBoost | 原生支持行业类别特征 |
| | RandomForest | Bagging 基线，验证 Boosting 价值 |
| **线性** | Ridge | sanity check，判断信号线性度 |
| **深度学习** | GRU | 时序建模性价比最高，DL 入门首选 |
| | LSTM | 长程记忆，适合大窗口 |
| | ALSTM | 注意力增强，捕捉事件驱动 |
| | Transformer | 自注意力，长程依赖 |
| | TabNet | 表格数据专用，自带特征选择 |
| | TCN | 时间卷积，训练快 |
| | NativeTFT | 自研轻量 TFT，GRU+注意力 |
| | MLP | 神经网络基线，验证时序建模价值 |

### 专业训练能力

- **🎯 多周期训练**：一次训练 T+1/3/5/10 四周期，自动 ICIR 加权融合
- **🔬 Optuna 自动调参**：TPE 采样自动搜索最优超参，以 Rank ICIR 为目标
- **📐 截面预处理**：per-date Z-score + 分位缩尾 + 中位数填充，专业多因子标准
- **🧪 WFA 稳定性诊断**：Walk-Forward 滚动窗口验证模型稳定性
- **🔍 因子筛选**：IC/ICIR 筛选 + 相关性去冗余 + 稳定性检验
- **🧬 Stacking 集成**：时序 OOF + Ridge 元学习器，多模型融合
- **🛡️ 防泄漏**：严格时间切分、标签防泄漏、ST/停牌过滤

### 模型管理（专业级）

- **生产监控**：每日回填真实 Rank IC，漂移检测 + 信号失效告警
- **A/B 对比**：两个模型训练指标 + 生产 IC + 特征差异对比
- **软门禁**：test ICIR 不达标保持候选，人工评估后激活
- **多市场**：CN/HK/US/CRYPTO/FUTURES 独立模型空间

---

## 🖥️ 远程训练（AutoDL GPU）

**本地 CPU 训练太慢？一键推送到 AutoDL GPU 训练，模型自动回传。**

- **🚀 GPU 加速**：深度学习模型在 RTX/A100 上训练提速 10-50 倍
- **📦 自动推送**：特征快照 + 训练脚本自动 rsync 到远程节点
- **🔄 双向同步**：配置/代码自动同步，模型训练完成自动回传注册
- **📊 节点管理**：多节点并行，实时状态监控

```
本地 API → 推送特征快照+config → AutoDL 启动训练容器
  → GPU 训练 → 模型 scp 回传 → 自动注册 ready
```

---

## 🔮 模型推理

训练完成的模型自动进入推理链路，**多市场、批量、融合推理**全覆盖。

- **🌐 多市场推理**：A股/港股/美股/区块链/期货独立推理，市场自适应特征
- **📅 批量推理**：单日 / 区间回溯 / 全量批量，自动调度
- **🧬 融合推理**：多模型 / 多周期动态加权融合（生产 IC 权重）
- **📡 信号生成**：推理分数 → 截面排名 → 买入/卖出信号 → 落库
- **📊 生产监控**：每日回填真实 IC，模型效果一目了然
- **🛡️ 推理兜底**：数据缺失自动降级，行情源多级回退

---

## ✨ 核心功能

QuantMind 提供 **12+ 专业功能模块**：

| 模块 | 说明 |
|------|------|
| **📈 市场分析** | 全市场行情、板块、个股多维分析 |
| **🧠 智能策略** | AI 辅助生成 Qlib 策略，自然语言交互 |
| **🤖 AI-IDE** | 策略代码 AI 编辑器 |
| **📊 回测中心** | Qlib 高性能回测，多策略对比，参数优化 |
| **🟦 QuantBot** | 自然语言量化助手，意图识别驱动 |
| **🎓 模型训练** | 13 模型 + Optuna + 远程 GPU 训练 |
| **🗂️ 模型管理** | 生命周期、生产监控、A/B 对比 |
| **🔬 投研平台** | 多 Agent A 股研究报告（TradingAgents）|
| **💰 模拟交易** | 全链路模拟盘，T+1/涨跌停/风控 |
| **📡 通达信量化推送** | 选股结果一键推送到通达信（板块+预警+消息）|
| **📰 RSS 信息流** | 财经资讯聚合（Huntly + RSSHub）|
| **🟣 Alpha 研究** | 因子挖掘与 Alpha 策略研究 |
| **👤 个人中心 / 后台管理** | 用户与系统管理 |

---

## 📡 通达信量化推送

**模型选股结果，一键推送到通达信，实盘软件内直接操作。**

- **🟦 自定义板块推送**：Top N 选股自动写入通达信自定义板块，盘中即见
- **⚠️ 预警信号**：带买入价 / 分数排名 / 选股理由，通达信内**双击闪电下单**
- **📨 界面消息**：推送选股通知到通达信消息中心
- **🔄 实时推送**：推理完成后自动推送（`ENABLE_TDX_PUSH=true`）
- **⚙️ 通达信滚动交易**：分数阈值选股 + 自动买卖（`tdx_rolling_trade`）

```
模型推理 → Top N 选股 → 通达信板块 + 预警 + 消息 → 双击下单
```

---

## 📰 RSS 信息流

内置 **Huntly + RSSHub** 财经资讯聚合：

- **📡 多源聚合**：数十个财经 RSS 源自动抓取
- **🤖 智能推荐**：结合持仓/自选股的相关资讯推送
- **🔔 实时更新**：定时自动刷新，重要新闻不遗漏
- **🔗 新闻代理**：API 服务统一代理，前端直接消费

---

## 🧩 Skills & 智能体

### Claude Code Skills（20+ 专业技能包）

QuantMind 内置丰富的 AI 技能，覆盖量化全流程：

- **数据类**：`stock-market-analysis`、`quantdb-sdk`、`global-stock-data`、`a-stock-data`
- **策略类**：`smart-strategy-stock-picking`、`backtest-center`、`strategy-*`
- **训练类**：`simulation-trading`、`model-training`、`batch-inference-analysis`
- **分析类**：`alphagbm-*`（财报/估值/情绪/期权）、`financial-analysis`
- **运营类**：`quantmind-operations`、`deployment-patterns`

### QuantBot 智能助手

自然语言驱动的量化助手，**意图识别 → 自动执行**：
- 查行情、看持仓、跑回测、训练模型 —— 一句话搞定
- 集成 QwenPaw，多轮对话理解
- 对接交易所实时数据

### RD-Agent 自动因子挖掘

基于微软 **RD-Agent** 的自动化因子进化框架：
- **多市场因子集**：A股/港股/美股/加密 独立因子库
- **自动进化**：LLM 驱动因子生成 → 回测评估 → 优胜劣汰
- **AlphaAgent**：因子编码专家系统，自动生成可复用因子

### TradingAgents 多 Agent 投研

7 个 AI 分析师 + 辩论模块的 A 股研究框架：
- 多角色分析（技术/基本面/情绪等）
- Agent 辩论提升结论可靠性
- 自动生成结构化研究报告

---

## 🛠️ 技术栈

### 核心技术

| 领域 | 技术 |
|------|------|
| **量化框架** | Qlib（微软）、Backtrader、自研回测引擎 |
| **机器学习** | LightGBM、XGBoost、CatBoost、scikit-learn、Optuna |
| **深度学习** | PyTorch、GRU/LSTM/Transformer/TabNet/TCN |
| **数据** | **QuantDB**、Parquet、DuckDB、pandas、pyarrow |
| **因子挖掘** | RD-Agent、AlphaAgent |
| **后端** | Python 3.10、FastAPI、SQLAlchemy、Celery |
| **数据库** | PostgreSQL、Redis（6 库隔离）|
| **前端** | Electron、React 18、TypeScript、Vite、Ant Design |
| **可视化** | ECharts、Recharts |
| **AI 助手** | QwenPaw、Claude Code Skills、LLM 意图识别 |
| **通达信对接** | 通达信板块/预警推送、滚动交易 |
| **部署** | Docker、Docker Compose、AutoDL GPU、Nginx |

### 数据技术

- **QuantDB SDK**：专业行情/财报/估值数据查询
- **Parquet 列式存储**：千万级数据秒级加载
- **DuckDB**：本地高性能 SQL 分析
- **151+ 维特征工程**：动量/波动/流动性/资金流/风格/筹码

---

## 🚀 快速开始

### 环境要求

- Python 3.10+、Node.js 20+、Docker + Docker Compose
- 可选：NVIDIA GPU（深度学习训练）

### 一键部署

```bash
# 1. 克隆仓库
git clone https://github.com/qusong0627/QuantMind.git
cd QuantMind

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，设置 DB_PASSWORD、SECRET_KEY 等

# 3. 启动所有服务
docker-compose up -d

# 4. 下载 QuantDB 数据（A股）
wget <QuantDB 数据包>
tar xzf quantdb_data.tar.gz -C data/

# 5. 访问
# 前端: http://localhost:3080
# API:  http://localhost:8000
```

### 数据同步

```bash
# A股 QuantDB 日度同步
docker exec quantmind python backend/scripts/quantdb_daily_sync.py

# 港股/美股/区块链/期货
# 对应 quantus/quanthk/quantbc/quantfutures 同步脚本
```

### 快速训练一个模型

```
前端 → 模型训练 → 选 LightGBM → 选特征 → 选时间窗 → 开始训练
  → 3 分钟出模型 → 自动注册 → 一键推理 → 看信号
```

---

## 📦 部署指南

### 生产环境

```bash
# 1. 克隆代码
git clone https://github.com/qusong0627/QuantMind.git

# 2. 配置环境变量（.env）
# 3. 启动服务
docker-compose up -d

# 4. 下载数据（从 Releases 下载数据包解压到 data/）
# 5. 初始化数据库（首次启动自动建表 + 默认 admin）
# 6. 构建股票索引
```

### 开发环境

```bash
# 后端单服务
SERVICE_MODE=api python backend/main_oss.py

# 前端
cd electron && npm install && npm run dev:web
```

---

## 📚 项目结构

```
backend/
├── main_oss.py                 # 统一服务入口（api/engine/trade/stream）
├── shared/                     # 跨服务共享（DB/Redis/配置/日志）
├── services/
│   ├── api/                    # API 服务：认证/策略/社区/新闻
│   ├── engine/                 # 引擎：Qlib回测/AI策略/模型训练/推理
│   │   ├── training/           # 训练编排（本地 Docker + AutoDL 远程）
│   │   ├── inference/          # 推理引擎 + 模板
│   │   ├── rd_agent/           # RD-Agent 因子挖掘
│   │   ├── trading_agents/     # 多 Agent 投研
│   │   ├── data_platform/      # 多市场数据平台（QuantDB hub）
│   │   └── qlib_app/           # Qlib 回测应用
│   ├── trade/                  # 交易：订单/持仓/风控/模拟盘
│   └── stream/                 # 实时行情推送
├── scripts/                    # 数据同步/特征计算脚本
└── tests/                      # 测试

electron/                       # 前端（Electron + React）
├── src/
│   ├── pages/                  # 各功能页（训练/模型/回测/投研...）
│   ├── features/               # 功能模块
│   └── services/               # API 服务

docker/                         # Docker 镜像
scripts/                        # 数据/运维脚本
docs/                           # 文档（含模型训练完全指南）
```

---

## ⏰ 定时任务

| 任务 | 时间 | 说明 |
|------|------|------|
| 数据同步 | 每日 22:30 | QuantDB 全量增量同步 |
| Qlib 缓存 | 每日 22:40 | 重建 Qlib 二进制缓存 |
| 特征快照 | 每日 22:50 | 更新特征 Parquet |
| 自动推理 | 每日 00:00 | 活跃策略自动推理 |
| 质量回填 | 每日 02:30 | 回填真实 IC + 融合权重刷新 |
| 平滑历史 | 每日 03:00 | 时间平滑历史构建 |

---

## 🤝 开源理念

QuantMind 开源的**根本目的**：

> **让专业量化能力触手可及。** 用 QuantDB 的专业数据解决数据难题，数据来源有了，直接训练即可 —— 把复杂的量化基建（数据、特征、训练、推理）变成开箱即用的能力，让每个开发者都能专注在策略本身。

**数据驱动 · 开箱即用 · 多市场覆盖 · AI 赋能**

---

## QQ 群

<p align="center">
  <img src="docs/images/1097406397.png" alt="QuantMind QQ 群二维码" width="260">
</p>

---

<p align="center">
  <strong>QuantMind</strong> — 让量化交易更简单
</p>
<p align="center">
  <em>Data-Driven · AI-Powered · Multi-Market Quantitative Trading Platform</em>
</p>
