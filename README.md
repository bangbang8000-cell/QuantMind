<div align="center">

**🌐 语言切换 Language** · [中文](#) · [English](README_EN.md) · [繁體中文](README_ZH-Hant.md)

</div>

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

**QuantMind 开源版** 是一款面向专业量化研究者的 **AI 驱动量化交易平台**，采用机构级技术栈（微软 Qlib + 深度学习 + 自动化因子挖掘），提供从**模型训练 → 回测 → 推理 → 实盘交易**的完整研究闭环。

**QuantMind 不是传统手工因子量化，而是让机器学习模型自动学习市场规律**——深度集成 **13 种主流 AI 模型**（LightGBM/XGBoost/CatBoost/GRU/LSTM/Transformer 等），支持 **151+ 维量化特征**训练与推理，前沿技术、机构级标准，用户可快速构建 Alpha 策略并在历史数据上验证。

**核心特色：**

- **🧠 AI 模型训练与推理（前沿技术）**：13 种 ML/DL 模型可视化训练、Optuna 自动调参、多周期/多模型融合、远程 GPU 训练；训练完成自动注册、一键推理，多市场（A股/港股/美股/区块链/期货）信号生成
- **📊 QuantDB 专业 A 股数据**：开箱即用的专业数据集合，5000+ 只 A 股、315 维 AI 因子、专业清洗、每日自动更新 —— **数据到位，直接训练**
- **🤖 AI 全流程自动化**：RD-Agent 自动因子挖掘、QuantBot 智能助手、多 Agent 投研、智能策略生成
- **🔒 本地化部署**：docker compose 一键启动，数据与模型完全本地化，无云依赖，保障研究隐私

适合个人量化研究者、学术团队及专业机构进行策略原型验证与二次开发，是进入 AI 量化领域的理想起点。


---

## ⚡ 核心亮点

**QuantMind 是 AI 驱动的量化平台 —— 不是传统手工因子选股，而是让机器学习模型自动学习市场规律。**

传统量化靠人肉调因子、经验判断；QuantMind 用 **13 种 AI 模型自动从 151+ 特征中学习**，让 LightGBM、LSTM、Transformer 等模型**自动发现**有效规律，摆脱人工经验的局限。

| 对比维度 | 传统因子量化 | QuantMind AI 量化 |
|---------|------------|------------------|
| **信号来源** | 手工设计因子 | 机器学习自动学习 |
| **模型** | 线性打分 | 13 种 ML/DL 模型 |
| **非线性** | 难捕捉 | 树模型 + 神经网络天然捕捉 |
| **时序依赖** | 忽略 | LSTM/GRU/Transformer 建模 |
| **调参** | 人工试错 | Optuna 自动搜索 |
| **集成** | 简单加权 | Stacking + 动态融合 |

| 痛点 | QuantMind 解法 |
|------|---------------|
| 数据难获取 | **QuantDB 专业数据**，一条命令拉全 |
| 特征难构建 | **151+ 维特征** 自动生成 |
| 训练门槛高 | **13 种 AI 模型** 前端可视化训练 + 远程 GPU |
| 推理部署难 | 训练完自动注册，一键推理 |

**从零到第一个 AI 模型，只需 30 分钟。**

---

## 🇨🇳 A股数据优势（QuantDB）

> 数据来源：**[https://quantdb.quantmind.cloud/](https://quantdb.quantmind.cloud/)**

QuantMind 的 A 股数据由 **QuantDB 专业数据服务**提供，这是本平台的核心竞争力 —— **你不需要自己爬数据、清洗数据、对齐复权，数据到位直接训练**。

### 📊 QuantDB A 股数据（量化级专业数据）

**覆盖面**：
- **全市场 5000+ 只 A 股**（沪深京），含主板/创业板/科创板/北交所
- **20+ 年历史数据**，2016-2026 连续日线/分钟线
- **完整财务三表**：利润表、资产负债表、现金流量表、分红、拆股

**量化因子体系（151+ 维 / 315 维 AI 因子）**：

| 因子类别 | 说明 | 典型因子 |
|---------|------|---------|
| **动量因子** | 过去 N 日收益、乖离、趋势 | mom_ret_5d / 20d / 60d |
| **波动率因子** | 波动幅度、风险、Parkinson | vol_std_20 / vol_atr_14 |
| **流动性因子** | 成交量、换手率、Amihud | liq_volume / liq_turnover |
| **基本面因子** | 估值、盈利、成长 | fun_pe / fun_pb / fun_roe |
| **风格因子** | 市值、价值、成长暴露 | style_bp / style_ep_ttm |
| **资金流因子** | 主力资金、北向资金 | 资金流向特征 |
| **筹码因子** | 持仓结构、股东变化 | chip_* |
| **技术因子** | KDJ/MACD/RSI 等 | tech_* |
| **行业因子** | 申万一级行业 | ind_code_l1 |

**专业清洗**：
- ✅ 前复权/后复权处理，停牌/退市标记
- ✅ 涨跌停、ST/*ST、假日填充（volume=0 识别）
- ✅ 全市场对齐，**无幸存者偏差**处理，标签防泄漏

**高性能存储**：
- Parquet 列式存储 + DuckDB 查询，**1000 万行秒级加载**
- 训练直接读本地 parquet，无需数据库

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

<div align="center">

**Layered Microservices · QuantDB Data Hub · GPU Training Cluster**

</div>

<table>
<tr>
<th align="center" width="33%">🎨 表现层 <br/><sub>Presentation</sub></th>
<th align="center" width="33%">🧠 服务层 <br/><sub>Microservices (FastAPI)</sub></th>
<th align="center" width="33%">⚙️ 基础层 <br/><sub>Infrastructure</sub></th>
</tr>
<tr>
<td>

**前端（Electron + React + TS）**

市场分析 · 智能策略 · 模型训练  
模型管理 · 回测中心 · 模拟交易  
QuantBot · 投研平台 · RSS · 通达信

</td>
<td>

**API `:8000`** — 认证 / 策略 / 社区  
**Engine `:8001`** — Qlib回测 / **训练推理** / Alpha  
**Trade `:8002`** — 订单 / 风控 / 模拟盘  
**Stream `:8003`** — 实时行情 / WebSocket

</td>
<td>

**QuantDB** — 专业数据中枢  
**训练引擎** — Qlib + Optuna  
**AutoDL GPU** — 远程训练集群  
**PostgreSQL + Redis** — 持久化  
**Celery** — 异步任务调度

</td>
</tr>
</table>

### 数据流（量化研究闭环）

```
QuantDB 数据源
   ↓
特征工程（151+ 维 / 315 AI 因子）
   ↓
特征快照（Parquet 列式存储）
   ↓
13 种模型训练（Optuna 调参 / Stacking 集成 / 远程 GPU）
   ↓
模型注册（版本管理 · 生产监控 · A/B 对比 · 软门禁）
   ↓
多市场推理（截面排序 · 信号生成 · 融合加权）
   ↓
回测验证 → 策略部署 → 模拟盘 → 通达信推送
```

### 架构设计要点

| 维度 | 设计 |
|------|------|
| **微服务隔离** | 4 服务独立进程，独立扩容，故障隔离 |
| **数据本地化** | QuantDB parquet 本地化，训练读盘秒级，无需数据库 |
| **异步任务** | Celery 调度数据同步/特征/推理/回填，避免阻塞 |
| **远程 GPU** | AutoDL 远程训练，自动推送快照 + 回传模型 |
| **全链路监控** | 训练日志流、生产 IC 回填、漂移告警、节点状态 |

---

## 🧠 模型训练

QuantMind 内置 **13 种专业模型**，覆盖从传统机器学习到深度学习的完整谱系，前端可视化配置，开箱即用。

### 13 种训练模型

QuantMind 内置 **13 种专业模型**，覆盖传统机器学习到深度学习完整谱系。每种模型经 A 股实测调优，前端可视化配置，开箱即用。

#### 🌲 树模型（Tree Models）— 快且稳，量化基线首选

<table>
<tr>
<th align="center" width="22%">模型</th>
<th align="center" width="40%">专业优势</th>
<th align="center" width="38%">最佳特征 / 场景</th>
</tr>
<tr>
<td align="center"><strong>LightGBM</strong><br/><sub>🌳 首选基线</sub></td>
<td>直方图算法极速训练（3 分钟内）；A 股实证 IC 最稳定；对量价因子非线性捕捉强；低内存</td>
<td><b>动量 + 波动 + 流动性</b><br/>mom_ret_* · vol_std_* · liq_turnover<br/>建议第一个模型必跑</td>
</tr>
<tr>
<td align="center"><strong>XGBoost</strong><br/><sub>🌳 异构互补</sub></td>
<td>level-wise 分裂与 LGB 互补；对资金流因子捕捉更优；与 LGB Stacking 集成提升 10-15% ICIR</td>
<td><b>LGB 基础 + 资金流/微结构</b><br/>flow_vpin · flow_pressure<br/>与 LGB 做集成效果最佳</td>
</tr>
<tr>
<td align="center"><strong>CatBoost</strong><br/><sub>🌳 类别友好</sub></td>
<td>有序提升防过拟合；<b>原生支持行业类别特征</b>（无需 one-hot）；对风格因子交互捕捉好</td>
<td><b>开启"行业作为特征"</b><br/>ind_code_l1 · style_bp · style_ep<br/>行业信息增益最大</td>
</tr>
<tr>
<td align="center"><strong>RandomForest</strong><br/><sub>🌳 Bagging 基线</sub></td>
<td>Bagging 思想降方差；<b>验证 Boosting 价值</b>——RF 与 LGB 接近说明信号线性；LGB 更优说明非线性重要</td>
<td><b>诊断用</b><br/>任意特征<br/>判断是否值得投入复杂模型</td>
</tr>
</table>

#### 📏 线性模型（Linear）— sanity check

<table>
<tr>
<th align="center" width="22%">模型</th>
<th align="center" width="40%">专业优势</th>
<th align="center" width="38%">最佳特征 / 场景</th>
</tr>
<tr>
<td align="center"><strong>Ridge</strong><br/><sub>📏 线性基线</sub></td>
<td>线性回归 + L2 正则；<b>判断信号线性度</b>——Ridge IC>0.03 说明有线性信号；IC≈0 说明信号在非线性交互</td>
<td><b>已标准化特征</b><br/>全特征<br/>必跑诊断基线，不用于实战</td>
</tr>
</table>

#### 🤖 深度学习（Deep Learning）— 捕捉时序与非线性

<table>
<tr>
<th align="center" width="22%">模型</th>
<th align="center" width="40%">专业优势</th>
<th align="center" width="38%">最佳特征 / 场景</th>
</tr>
<tr>
<td align="center"><strong>GRU</strong><br/><sub>🤖 DL 入门首选</sub></td>
<td>门控循环单元；DL 中性价比最高；GPU 训练约 10-20 分钟；适合中小数据量</td>
<td><b>波动率时序衰减</b><br/>vol_std_* · vol_parkinson<br/>动量反转模式</td>
</tr>
<tr>
<td align="center"><strong>LSTM</strong><br/><sub>🤖 长程记忆</sub></td>
<td>多门控记忆更长；适合 >5 年大窗口；但 A 股实测提升有限（<5%），GRU 好则不必试</td>
<td><b>长历史窗口因子</b><br/>mom_ret_60d · vol_*<br/>大数据集</td>
</tr>
<tr>
<td align="center"><strong>ALSTM</strong><br/><sub>🤖 注意力增强</sub></td>
<td>注意力自动学习重要时间步；<b>捕捉事件驱动</b>（业绩公告前后）；结果略不稳定</td>
<td><b>事件/公告类特征</b><br/>基本面公告<br/>GRU 效果好（IC>0.05）再尝试</td>
</tr>
<tr>
<td align="center"><strong>Transformer</strong><br/><sub>🤖 长程依赖</sub></td>
<td>自注意力全局长程依赖；捕捉跨周期因子组合；<b>需 ≥100 万行数据收敛</b></td>
<td><b>多样特征组合</b><br/>短期动量 + 长期风格<br/>数据量大才用</td>
</tr>
<tr>
<td align="center"><strong>TabNet</strong><br/><sub>🤖 表格专用</sub></td>
<td>表格数据 SOTA；<b>自带特征选择</b>（mask 机制）；无需时序窗口；像"可学习的树模型"</td>
<td><b>资金流 + 微结构</b><br/>flow_* · microstructure<br/>特征探索利器</td>
</tr>
<tr>
<td align="center"><strong>TCN</strong><br/><sub>🤖 时间卷积</sub></td>
<td>因果卷积比 RNN 快 50%；<b>捕捉波动率突变与量能异动</b>；kernel 可调捕捉更长期依赖</td>
<td><b>异动类特征</b><br/>vol_jump_zadj · liq_volume_ratio<br/>需频繁重训时优先</td>
</tr>
<tr>
<td align="center"><strong>NativeTFT</strong><br/><sub>🤖 自研轻量 TFT</sub></td>
<td>GRU 时序 + 注意力 + 门控残差；比 pytorch_forecasting TFT <b>轻 10 倍</b>；无额外依赖</td>
<td><b>动量 + 波动率时序组合</b><br/>GRU 好想试注意力时用</td>
</tr>
<tr>
<td align="center"><strong>MLP</strong><br/><sub>🤖 神经网络基线</sub></td>
<td>全连接最简网络；<b>验证时序建模价值</b>——MLP IC 接近 GRU 说明时序不重要，直接用树模型</td>
<td><b>任意扁平特征</b><br/>诊断基线<br/>判断是否值得用 RNN</td>
</tr>
</table>

#### ✨ 专业训练能力

<div align="center">

| 能力 | 说明 |
|------|------|
| 🎯 **多周期训练** | 一次训练 T+1/3/5/10 四周期，自动 ICIR 加权融合 |
| 🔬 **Optuna 自动调参** | TPE 采样自动搜索最优超参，以 Rank ICIR 为目标 |
| 📐 **截面预处理** | per-date Z-score + 分位缩尾 + 中位数填充，专业多因子标准 |
| 🧪 **WFA 稳定性** | Walk-Forward 滚动窗口验证模型稳定性 |
| 🔍 **因子筛选** | IC/ICIR 筛选 + 相关性去冗余 + 稳定性检验 |
| 🧬 **Stacking 集成** | 时序 OOF + Ridge 元学习器，多模型融合 |
| 🛡️ **防泄漏** | 严格时间切分、标签防泄漏、ST/停牌过滤 |

</div>

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

## 🛠️ 核心技术（机构级 AI 量化）

QuantMind 采用**机构级 AI 量化技术栈**，覆盖从数据到模型到部署的全链路：

<div align="center">

### 🤖 AI 核心能力

</div>

<table>
<tr>
<th align="center" width="33%">🧠 AI 建模引擎</th>
<th align="center" width="33%">📊 数据处理平台</th>
<th align="center" width="33%">⚡ 训练基础设施</th>
</tr>
<tr>
<td>

- **13 种 ML/DL 模型**（LGB/XGB/CatBoost/GRU/LSTM/Transformer/TCN...）
- **Optuna 自动超参搜索**（TPE 采样）
- **WFA Walk-Forward 稳定性诊断**
- **Stacking 多模型集成**（OOF + Ridge）
- **多周期 ICIR 加权融合**

</td>
<td>

- **QuantDB 专业数据**（315 AI 因子）
- **151+ 维特征工程**（动量/波动/流动性/风格/筹码）
- **截面预处理**（Z-score + 缩尾 + 中性化）
- **因子筛选**（IC/ICIR + 去冗余）
- **Parquet + DuckDB** 秒级读取

</td>
<td>

- **Qlib 微软量化框架**
- **PyTorch 深度学习**
- **AutoDL 远程 GPU 集群**
- **Docker 容器化编排**
- **Celery 异步任务调度**

</td>
</tr>
</table>

### 🔥 技术亮点

| 技术 | 亮点 |
|------|------|
| **AI 因子挖掘** | RD-Agent（微软）自动进化因子，LLM 驱动生成 → 回测 → 优胜劣汰 |
| **多 Agent 投研** | TradingAgents 7 分析师 + 辩论模块，自动生成研究报告 |
| **AI 助手** | QuantBot 意图识别自动执行 + QwenPaw 多轮对话 |
| **Claude Skills** | 20+ 量化技能包，覆盖数据/策略/训练/分析 |
| **通达信对接** | 选股结果一键推送到通达信，双击闪电下单 |
| **生产监控** | 每日回填真实 Rank IC，漂移检测 + 信号失效告警 |

### 🛠️ 技术栈速览

| 领域 | 技术 |
|------|------|
| 量化框架 | **Qlib（微软）**、Backtrader、自研回测引擎 |
| 机器学习 | LightGBM、XGBoost、CatBoost、scikit-learn、**Optuna** |
| 深度学习 | **PyTorch**、GRU/LSTM/Transformer/TabNet/TCN |
| 数据 | **QuantDB**、Parquet、**DuckDB**、pandas、pyarrow |
| 因子挖掘 | **RD-Agent**、AlphaAgent |
| 后端 | Python 3.10、**FastAPI**、SQLAlchemy、Celery |
| 数据库 | PostgreSQL、Redis（6 库隔离）|
| 前端 | Electron、React 18、TypeScript、Vite、Ant Design |
| AI 助手 | QwenPaw、Claude Code Skills、LLM 意图识别 |
| 部署 | Docker、Docker Compose、**AutoDL GPU**、Nginx |

---

## 🚀 快速开始

### 💻 环境要求（多系统支持）

| 系统 | 说明 |
|------|------|
| **Ubuntu / Debian** | 推荐 Linux 部署，性能最佳 |
| **Windows + WSL2** | 装 Docker Desktop + WSL2 后端即可 |
| **macOS** | Docker Desktop 直接运行 |
| **云服务器** | 任意 Docker 环境，单机即可 |

**核心依赖**：
- Docker + Docker Compose（无需单独装 Python/Node，全容器化）
- Windows 用户建议 **WSL2**（性能 + 兼容性最佳）

### 🧠 内存建议（重要）

| 用途 | 推荐内存 | 说明 |
|------|---------|------|
| **模型训练** | **64GB 以上** | 千万级特征加载 + 深度学习训练 |
| **推理 / 策略回测** | **32GB 以上** | 全市场 5000+ 股票推理 |

> ⚠️ **内存不足会导致训练卡死/被杀**（OOM）。建议训练机 ≥64GB，若只有 32GB 请缩小时间窗或特征数。

> 🔧 **平台支持**：当前完整版支持 **x86_64 / AMD64**（Intel/AMD）。**ARM 服务器（aarch64）暂不支持完整版**——因微软 Qlib 框架仅发布 x86_64 版本，ARM 无法安装。ARM 用户请用 x86 云服务器或 x86 主机。

### 🚀 一键部署（5 步）

```bash
# 1. 克隆仓库
git clone https://github.com/qusong0627/QuantMind.git
cd QuantMind

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，设置 DB_PASSWORD、SECRET_KEY 等

# 3. 启动所有服务
docker compose up -d

# 4. 拉取 QuantDB A股数据（可选，已内置基础数据）
#    注册 QuantDB 后直接拉取，或用内置同步脚本
docker exec quantmind python backend/scripts/quantdb_daily_sync.py

# 5. 访问
# 前端: http://localhost:3000   （WEB_PORT 可改）
# API:  http://localhost:8000
# 训练任务: docker logs quantmind 查看
```

### ⚙️ Docker 命令兼容（不同系统/版本）

> **命令说明**：本仓库统一使用 `docker compose`（新版标准，Docker 20.10+ / v2+）。
> 旧版 Docker 用 `docker-compose`（带连字符），如遇 `command not found` 请改用 `docker compose` 或升级 Docker。

| 系统 | Docker 安装 | 启动命令 | 说明 |
|------|------------|---------|------|
| **Ubuntu/Debian** | `apt install docker.io docker-compose-plugin` | `docker compose up -d` | 推荐，性能最佳 |
| **Windows** | Docker Desktop (WSL2 后端) | `docker compose up -d` | 在 WSL2 终端内执行 |
| **macOS** | Docker Desktop | `docker compose up -d` | 直接运行 |
| **旧版 Docker** | 独立 compose | `docker-compose up -d` | v1 旧命令 |

### 🔗 访问链接

| 服务 | 地址 | 说明 |
|------|------|------|
| **前端 Web** | `http://localhost:3000` | 改端口：`WEB_PORT=8080 docker compose up -d` |
| **API** | `http://localhost:8000` | FastAPI 接口 |
| **API 文档** | `http://localhost:8000/docs` | Swagger 交互式文档 |
| **后端日志** | `docker logs -f quantmind` | 训练/推理日志 |
| **容器状态** | `docker ps` | 11 个服务状态 |

### 🔧 部署排错（常见问题）

| 问题 | 解决方案 |
|------|---------|
| 端口被占用 | `WEB_PORT=8080 docker compose up -d` 改端口 |
| 内存不足 | 关闭其他容器，或 `--memory` 限制 + 缩数据窗 |
| WSL2 无法启动 | `wsl --set-default-version 2`，确保内核更新 |
| 数据不完整 | 跑 `docker exec quantmind python backend/scripts/quantdb_daily_sync.py` |
| 训练被杀（ExitCode 137）| 内存不足（OOM），需 ≥64GB 或缩小数据量 |

### 🐍 数据同步（多市场）

```bash
# A股 QuantDB 日度同步（主力数据源）
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
docker compose up -d

# 4. 注册 QuantDB 并拉取 A股数据（或运行内置同步脚本）
docker exec quantmind python backend/scripts/quantdb_daily_sync.py
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

**QuantMind 开源的初心 —— 让量化交易平民化，而非机构专属。**

量化交易一直被机构垄断，门槛来自两块：**数据底座**和**技术底座**。

- **数据底座**：专业行情/财务/因子数据，机构花数百万购买，个人却要自己爬、自己清洗、自己造轮子
- **技术底座**：模型训练、回测、推理、部署，机构有专业团队，个人却要从零搭起

**QuantMind 用开源解决这两大底座：**

| 底座 | 机构做法 | QuantMind 开源解法 |
|------|---------|------------------|
| **数据底座** | 百万级购买专业数据 | **QuantDB 专业数据**，注册即可拉取，开箱即用 |
| **特征底座** | 团队研发 151+ 因子 | **315 维 AI 因子** 自动生成 |
| **训练底座** | 专业 ML 工程师调参 | **13 种 AI 模型** + Optuna 自动调参 |
| **推理底座** | 机构级部署团队 | 训练完自动注册、一键推理 |

> **我们相信：量化不应该是有钱人的游戏。** 把复杂的数据、特征、训练、推理变成开箱即用的能力，让每个普通投资者都能用 AI 武装自己——**数据到位，直接训练，人人可量化。**

**数据驱动 · 开源共享 · 量化平民化 · AI 赋能每一个投资者**

---

## 👥 适合人群

- **个人量化研究者** — 快速验证 Alpha 策略、因子挖掘
- **学术研究者** — 研究 A 股多因子模型、深度学习选股
- **股票爱好者** — 想用 AI 辅助选股、但不想从零搭数据/训练
- **小团队** — 量化策略原型验证与二次开发

---

## 🔍 关键词

量化交易 · 量化投资 · A股量化 · 港股量化 · 美股量化 · 多因子模型 · 因子挖掘 · Alpha策略 · 机器学习选股 · 深度学习选股 · LightGBM · XGBoost · CatBoost · LSTM · Transformer · Qlib · 股票预测 · 选股模型 · 策略回测 · 模型训练 · AI炒股 · 智能选股 · QuantDB · 量化数据 · 网格交易 · 程序化交易 · 量化平台 · 开源量化

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
