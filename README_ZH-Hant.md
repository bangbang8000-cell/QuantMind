<div align="center">

**🌐 語言切換 Language** · [中文](README.md) · [English](README_EN.md) · [繁體中文](#)

</div>

<h1 align="center">QuantMind</h1>

<p align="center">
  <strong>🚀 開箱即用的 AI 量化交易平台 —— 資料到手，即可訓練</strong>
</p>

<p align="center">
  <em>Multi-Market Quantitative Trading Platform · A股 / 港股 / 美股 / 區塊鏈 / 期貨</em>
</p>

<p align="center">
  <code>QuantDB 專業資料 → 13 種 AI 模型訓練 → 遠端 GPU 訓練 → 多市場推論 → 訊號產生</code>
</p>

<p align="center">
  <a href="#-核心亮點">核心亮點</a> •
  <a href="#-a股資料優勢">A股資料優勢</a> •
  <a href="#-系統架構">系統架構</a> •
  <a href="#-模型訓練">模型訓練</a> •
  <a href="#-遠端訓練">遠端訓練</a> •
  <a href="#-模型推論">模型推論</a> •
  <a href="#-核心功能">核心功能</a> •
  <a href="#-技術棧">技術棧</a> •
  <a href="#-快速開始">快速開始</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/Node.js-20+-green.svg" alt="Node.js">
  <img src="https://img.shields.io/badge/TypeScript-5.x-blue.svg" alt="TypeScript">
  <img src="https://img.shields.io/badge/Qlib-Powered-orange.svg" alt="Qlib">
  <img src="https://img.shields.io/badge/GPU-訓練-AutoDL.svg" alt="GPU">
  <img src="https://img.shields.io/badge/License-AGPL%20v3-blue.svg" alt="License">
</p>

---

## 📖 專案簡介

**QuantMind 開源版** 是一款面向個人量化研究者的在地化金融量化交易平台，基於微軟 **Qlib** 量化框架構建，提供從**模型訓練 → 回測 → 推論 → 實盤交易**的完整研究閉環。

深度整合 **13 種主流機器學習模型**（LightGBM/XGBoost/CatBoost/GRU/LSTM/Transformer 等），支援 **151+ 維量化因子**訓練與推論，可快速構建 Alpha 策略並在歷史資料上驗證。

**核心特色：**

- **🧠 模型訓練與推論**：13 種模型視覺化訓練、Optuna 自動調參、多週期/多模型融合、遠端 GPU 訓練；訓練完成自動註冊、一鍵推論、多市場（A股/港股/美股/區塊鏈/期貨）訊號產生
- **📊 QuantDB 專業 A 股資料**：開箱即用的專業資料集，5000+ 檔 A 股、315 維 AI 因子、專業清洗、每日自動更新 —— **資料到位，直接訓練**
- **🤖 AI 全流程**：智能策略產生、QuantBot 助手、RD-Agent 自動因子挖掘、多 Agent 投研
- **🔒 在地化部署**：docker compose 一鍵啟動，資料與模型完全在地化，無需雲端服務

---

## ⚡ 核心亮點

**QuantMind 是「資料到位即可訓練」的量化平台** —— 解決了量化入門最大的痛點：**資料難、特徵難、訓練難、部署難**。

| 痛點 | QuantMind 解法 |
|------|---------------|
| 資料難取得 | **QuantDB 專業資料**，一條指令拉全，無需自己爬 |
| 特徵難構建 | **151+ 維特徵** 自動產生 |
| 訓練門檻高 | **13 種模型** 前端視覺化訓練，支援遠端 GPU |
| 推論部署難 | 訓練完自動註冊，一鍵推論，訊號產生閉環 |

**從零到第一個模型，只需 30 分鐘。**

---

## 🇨🇳 A股資料優勢（QuantDB）

> 資料來源：**[https://quantdb.quantmind.cloud/](https://quantdb.quantmind.cloud/)**

### QuantDB A 股資料（量化級專業資料）

**覆蓋面**：全市場 5000+ 檔 A 股、20+ 年歷史、完整財務三表

**量化因子體系（151+ / 315 維 AI 因子）**：

| 類別 | 說明 | 典型因子 |
|------|------|---------|
| 動量因子 | 過去 N 日收益、趨勢 | mom_ret_5d / 20d / 60d |
| 波動率因子 | 波動幅度、風險 | vol_std_20 / vol_atr_14 |
| 流動性因子 | 成交量、換手率 | liq_volume / liq_turnover |
| 基本面因子 | 估值、盈利 | fun_pe / fun_pb / fun_roe |
| 風格因子 | 市值、價值 | style_bp / style_ep_ttm |
| 籌碼因子 | 持倉結構 | chip_* |
| 技術因子 | KDJ/MACD/RSI | tech_* |

**專業清洗**：前/後復權、停牌/退市、漲跌停、ST、假日填充、防倖存者偏差

**高效能儲存**：Parquet + DuckDB，千萬行秒級載入

**核心價值：把時間花在模型上，而不是資料上。**

---

## 🏗️ 系統架構

### 架構總覽

<div align="center">

**Layered Microservices · QuantDB Data Hub · GPU Training Cluster**

</div>

<table>
<tr>
<th align="center" width="33%">🎨 表現層</th>
<th align="center" width="33%">🧠 服務層 (FastAPI)</th>
<th align="center" width="33%">⚙️ 基礎層</th>
</tr>
<tr>
<td>

**前端（Electron + React + TS）**

市場分析 · 智能策略 · 模型訓練  
模型管理 · 回測中心 · 模擬交易  
QuantBot · 投研平台 · RSS · 通達信

</td>
<td>

**API `:8000`** — 認證 / 策略 / 社區  
**Engine `:8001`** — Qlib / **訓練推論** / Alpha  
**Trade `:8002`** — 訂單 / 風控 / 模擬盤  
**Stream `:8003`** — 即時行情 / WebSocket

</td>
<td>

**QuantDB** — 專業資料中樞  
**訓練引擎** — Qlib + Optuna  
**AutoDL GPU** — 遠端訓練  
**PostgreSQL + Redis** — 持久化  
**Celery** — 非同步任務

</td>
</tr>
</table>

---

## 🧠 模型訓練

**13 種專業模型**，覆蓋傳統機器學習到深度學習，前端視覺化配置。

### 13 種訓練模型

| 類別 | 模型 | 優勢 |
|------|------|------|
| **樹模型** | LightGBM | 極速訓練，A股 IC 最穩定 |
| | XGBoost | 異構整合，與 LGB 互補 |
| | CatBoost | 原生支援行業類別特徵 |
| | RandomForest | Bagging 基線 |
| **線性** | Ridge | sanity check |
| **深度學習** | GRU / LSTM / ALSTM | 時序建模 |
| | Transformer / TabNet / TCN | 長程依賴 / 表格 / 卷積 |
| | NativeTFT / MLP | 自研輕量 TFT / 基線 |

### 專業訓練能力

- **🎯 多週期**：一次訓練 T+1/3/5/10，ICIR 加權融合
- **🔬 Optuna 自動調參**：TPE 採樣
- **📐 截面預處理**：Z-score + 縮尾 + 中位數填充
- **🧪 WFA 穩定性**：Walk-Forward 驗證
- **🧬 Stacking 整合**：時序 OOF + Ridge
- **🛡️ 防洩漏**：嚴格時間切分、標籤防洩漏

---

## 🖥️ 遠端訓練（AutoDL GPU）

**本地 CPU 太慢？一鍵推送到 AutoDL GPU 訓練，模型自動回傳。**

```
本地 API → 推送特徵快照+config → AutoDL 啟動容器
  → GPU 訓練 → 模型回傳 → 自動註冊 ready
```

---

## 🔮 模型推論

- **🌐 多市場**：A股/港股/美股/區塊鏈/期貨
- **📅 批量推論**：單日 / 區間回溯 / 全量
- **🧬 融合推論**：多模型 / 多週期動態加權
- **📊 生產監控**：每日回填真實 IC

---

## ✨ 核心功能

| 模組 | 說明 |
|------|------|
| 📈 市場分析 | 全市場行情分析 |
| 🧠 智能策略 | AI 輔助 Qlib 策略 |
| 🤖 AI-IDE | 策略程式碼編輯器 |
| 📊 回測中心 | Qlib 高效能回測 |
| 🟦 QuantBot | 自然語言量化助手 |
| 🎓 模型訓練 | 13 模型 + Optuna + 遠端 GPU |
| 🗂️ 模型管理 | 生命週期、生產監控、A/B |
| 🔬 投研平台 | 多 Agent 研究（TradingAgents）|
| 💰 模擬交易 | 全鏈路模擬盤 |
| 📡 通達信推送 | 選股推送到通達信 |
| 📰 RSS 資訊流 | Huntly + RSSHub |

---

## 🧩 Skills & 智能體

- **Claude Code Skills**：20+ 量化技能包（資料/策略/訓練/分析）
- **QuantBot**：意圖識別 → 自動執行
- **RD-Agent**：微軟自動因子挖掘
- **TradingAgents**：7 分析師多 Agent 投研

---

## 🛠️ 技術棧

| 領域 | 技術 |
|------|------|
| 量化框架 | Qlib、Backtrader |
| 機器學習 | LightGBM、XGBoost、CatBoost、Optuna |
| 深度學習 | PyTorch、GRU/LSTM/Transformer/TCN |
| 資料 | **QuantDB**、Parquet、DuckDB |
| 因子挖掘 | RD-Agent、AlphaAgent |
| 後端 | Python、FastAPI、SQLAlchemy、Celery |
| 資料庫 | PostgreSQL、Redis |
| 前端 | Electron、React、TypeScript、Ant Design |
| 部署 | Docker、AutoDL GPU、Nginx |

---

## 🚀 快速開始

### 💻 多系統部署

| 系統 | 說明 |
|------|------|
| Ubuntu / Debian | 推薦 Linux 部署 |
| Windows + WSL2 | Docker Desktop + WSL2 |
| macOS | Docker Desktop |
| 雲伺服器 | 任意 Docker 環境 |

### 🧠 記憶體建議

| 用途 | 建議 |
|------|------|
| 模型訓練 | **64GB 以上** |
| 推論 / 回測 | **32GB 以上** |

### 🚀 一鍵部署（5 步）

```bash
# 1. 克隆
git clone https://github.com/qusong0627/QuantMind.git
cd QuantMind

# 2. 配置環境變數
cp .env.example .env

# 3. 啟動所有服務
docker-compose up -d

# 4. 同步 QuantDB A股資料
docker exec quantmind python backend/scripts/quantdb_daily_sync.py

# 5. 訪問
# 前端: http://localhost:3000
# API:  http://localhost:8000
```

---

## 🤝 開源理念

**QuantMind 開源的初心 —— 讓量化交易平民化，而非機構專屬。**

量化交易一直被機構壟斷，門檻來自兩塊：**資料底座**和**技術底座**。

- **資料底座**：專業行情/財務/因子資料，機構花數百萬購買，個人卻要自己爬、自己清洗
- **技術底座**：模型訓練、回測、推理、部署，機構有專業團隊，個人卻要從零搭起

**QuantMind 用開源解決這兩大底座：**

| 底座 | 機構做法 | QuantMind 開源解法 |
|------|---------|------------------|
| 資料底座 | 百萬級購買專業資料 | **QuantDB 專業資料**，註冊即可拉取 |
| 特徵底座 | 團隊研發 151+ 因子 | **315 維 AI 因子** 自動產生 |
| 訓練底座 | 專業 ML 工程師調參 | **13 種 AI 模型** + Optuna 自動調參 |
| 推理底座 | 機構級部署團隊 | 訓練完自動註冊、一鍵推理 |

> **我們相信：量化不應該是有錢人的遊戲。** 把複雜的資料、特徵、訓練、推理變成開箱即用的能力，讓每個普通投資者都能用 AI 武裝自己 —— **資料到位，直接訓練，人人可量化。**

**資料驅動 · 開源共享 · 量化平民化 · AI 賦能每一個投資者**

---

## 👥 適合人群

個人量化研究者 · 學術研究者 · 股票愛好者 · 小團隊

---

## 🔍 關鍵詞

量化交易 · A股量化 · 多因子模型 · 因子挖掘 · Alpha策略 · 機器學習選股 · 深度學習選股 · LightGBM · XGBoost · LSTM · Transformer · Qlib · 股票預測 · 策略回測 · 模型訓練 · AI炒股 · QuantDB · 量化平台 · 開源量化

---

## QQ 群

<p align="center">
  <img src="docs/images/1097406397.png" alt="QuantMind QQ 群二維碼" width="260">
</p>

---

<p align="center">
  <strong>QuantMind</strong> — 讓量化交易更簡單
</p>
