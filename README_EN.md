<div align="center">

**🌐 Language** · [中文](README.md) · [English](#) · [繁體中文](README_ZH-Hant.md)

</div>

<h1 align="center">QuantMind</h1>

<p align="center">
  <strong>🚀 Production-Ready AI Quantitative Trading Platform — Data In, Train Immediately</strong>
</p>

<p align="center">
  <em>Multi-Market Quantitative Trading Platform · A-Share / HK / US / Crypto / Futures</em>
</p>

<p align="center">
  <code>QuantDB Professional Data → 13 AI Models → Remote GPU Training → Multi-Market Inference → Signal Generation</code>
</p>

<p align="center">
  <a href="#-highlights">Highlights</a> •
  <a href="#-a-share-data">A-Share Data</a> •
  <a href="#-architecture">Architecture</a> •
  <a href="#-model-training">Model Training</a> •
  <a href="#-remote-training">Remote Training</a> •
  <a href="#-inference">Inference</a> •
  <a href="#-features">Features</a> •
  <a href="#-tech-stack">Tech Stack</a> •
  <a href="#-quick-start">Quick Start</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/Node.js-20+-green.svg" alt="Node.js">
  <img src="https://img.shields.io/badge/TypeScript-5.x-blue.svg" alt="TypeScript">
  <img src="https://img.shields.io/badge/Qlib-Powered-orange.svg" alt="Qlib">
  <img src="https://img.shields.io/badge/GPU-Training-AutoDL.svg" alt="GPU">
  <img src="https://img.shields.io/badge/License-AGPL%20v3-blue.svg" alt="License">
</p>

---

## 📖 Introduction

**QuantMind Open Source Edition** is an **AI-driven quantitative trading platform** for professional quant researchers, built with institutional-grade tech (Microsoft Qlib + Deep Learning + Automated Factor Mining), providing a complete research loop: **Model Training → Backtesting → Inference → Live Trading**.

**QuantMind is NOT traditional manual factor selection — it lets ML models automatically learn market patterns.** Deeply integrated with **13 mainstream AI models** (LightGBM/XGBoost/CatBoost/GRU/LSTM/Transformer, etc.), supporting **151+ quant features** for training and inference — cutting-edge, institution-grade.

**Core Highlights:**

- **🧠 AI Model Training & Inference (Cutting-Edge)**: 13 ML/DL models visualized training, Optuna auto-tuning, multi-horizon/multi-model fusion, remote GPU training; auto-registration after training, one-click inference, multi-market (A-Share/HK/US/Crypto/Futures) signal generation
- **📊 QuantDB Professional A-Share Data**: production-ready data — 5000+ A-Share stocks, 315 AI factors, professionally cleaned, daily auto-update — **Data ready, train immediately**
- **🤖 AI Full Automation**: RD-Agent auto factor mining, QuantBot assistant, multi-agent research, AI strategy generation
- **🔒 Local Deployment**: one-command docker compose, fully local data & models, no cloud dependency

Ideal for individual quant researchers, academic teams, and professional institutions for strategy prototyping and secondary development.

---

## ⚡ Highlights

**QuantMind is an AI-driven quant platform — NOT traditional manual factor selection. ML models automatically learn market patterns.**

| Dimension | Traditional Factor Quant | QuantMind AI Quant |
|---------|------------|------------------|
| **Signal Source** | Manual factor design | ML auto-learning |
| **Models** | Linear scoring | 13 ML/DL models |
| **Nonlinearity** | Hard to capture | Trees + NNs naturally |
| **Temporal Dependency** | Ignored | LSTM/GRU/Transformer |
| **Tuning** | Manual trial | Optuna auto-search |
| **Ensemble** | Simple weighting | Stacking + dynamic fusion |

| Pain Point | QuantMind Solution |
|------|---------------|
| Data hard to get | **QuantDB professional data**, one command |
| Features hard to build | **151+ factors** auto-generated |
| Training hard | **13 AI models** visualized + remote GPU |
| Inference hard | Auto-register, one-click inference |

**From zero to first AI model in just 30 minutes.**

---

## 🇨🇳 A-Share Data Advantage (QuantDB)

> Data Source: **[https://quantdb.quantmind.cloud/](https://quantdb.quantmind.cloud/)**

QuantMind's A-Share data comes from **QuantDB professional data service** — you don't need to crawl, clean, or adjust for dividends. **Data ready, train directly.**

### QuantDB A-Share Data

**Coverage:**
- **5000+ A-Share stocks** (Shanghai/Shenzhen/Beijing), main/GEM/STAR/BSE boards
- **20+ years of history**, 2016-2026 continuous daily/minute data
- **Full financial statements**: income, balance sheet, cash flow, dividends, splits

**Quant Factor System (151+ / 315 AI factors):**

| Category | Description | Typical Factors |
|---------|------|---------|
| **Momentum** | Past N-day return, trend | mom_ret_5d / 20d / 60d |
| **Volatility** | Volatility, risk, Parkinson | vol_std_20 / vol_atr_14 |
| **Liquidity** | Volume, turnover, Amihud | liq_volume / liq_turnover |
| **Fundamental** | Valuation, profitability, growth | fun_pe / fun_pb / fun_roe |
| **Style** | Market cap, value, growth | style_bp / style_ep_ttm |
| **Fund Flow** | Main capital, northbound flow | fund flow features |
| **Chip** | Holder structure, shareholder changes | chip_* |
| **Technical** | KDJ/MACD/RSI etc. | tech_* |
| **Industry** | CSRC level-1 industry | ind_code_l1 |

**Professional Cleaning:**
- ✅ Forward/backward adjusted, suspension/delisting marked
- ✅ Price limit, ST/*ST, holiday fill (volume=0 detection)
- ✅ Full-market alignment, **survivorship-bias handled**, label leakage prevention

**High-Performance Storage:**
- Parquet columnar + DuckDB query, **10M rows loaded in seconds**
- Training reads local parquet directly, no database needed

### vs Self-Built Data

| Dimension | Self-Built (baostock/akshare) | QuantDB |
|------|------------------------|---------|
| Cleaning | Manual (adjustments/suspension) | Professionally cleaned |
| Features | Write 151 factors yourself | 315 AI factors built-in |
| Consistency | Multi-source inconsistent | Single authoritative source |
| Updates | Manual | Daily auto-sync |
| Speed | Days of preparation | **Out-of-box** |

**Core Value: Spend time on models, not data.**

---

## 🏗️ Architecture

### Overview

<div align="center">

**Layered Microservices · QuantDB Data Hub · GPU Training Cluster**

</div>

<table>
<tr>
<th align="center" width="33%">🎨 Presentation <br/><sub>Frontend</sub></th>
<th align="center" width="33%">🧠 Services <br/><sub>Microservices (FastAPI)</sub></th>
<th align="center" width="33%">⚙️ Infrastructure</th>
</tr>
<tr>
<td>

**Frontend (Electron + React + TS)**

Market · Strategy · Model Training  
Model Mgmt · Backtest · Simulation  
QuantBot · Research · RSS · TDX Push

</td>
<td>

**API `:8000`** — Auth / Strategy / Community  
**Engine `:8001`** — Qlib / **Train-Infer** / Alpha  
**Trade `:8002`** — Orders / Risk / Sim  
**Stream `:8003`** — Quotes / WebSocket

</td>
<td>

**QuantDB** — Professional Data Hub  
**Train Engine** — Qlib + Optuna  
**AutoDL GPU** — Remote Training  
**PostgreSQL + Redis** — Persistence  
**Celery** — Async Task Scheduling

</td>
</tr>
</table>

### Data Flow (Quant Research Loop)

```
QuantDB Data Source
   ↓
Feature Engineering (151+ / 315 AI factors)
   ↓
Feature Snapshot (Parquet columnar)
   ↓
13 Models Training (Optuna / Stacking / Remote GPU)
   ↓
Model Registration (Version · Monitoring · A/B · Gate)
   ↓
Multi-Market Inference (Cross-section rank · Signals · Fusion)
   ↓
Backtest → Strategy Deploy → Simulation → TDX Push
```

### Architecture Highlights

| Dimension | Design |
|------|------|
| **Microservice Isolation** | 4 services, independent scale & failure isolation |
| **Data Localization** | QuantDB parquet local, second-level reads, no DB |
| **Async Tasks** | Celery for sync/features/inference/backfill |
| **Remote GPU** | AutoDL training, auto push snapshot & return model |
| **Full Monitoring** | Training logs, production IC backfill, drift alert |

---

## 🧠 Model Training

**13 professional models** covering traditional ML to deep learning, visualized frontend config, out-of-box.

### 13 Training Models

| Category | Model | Strength |
|------|------|------|
| **Tree** | LightGBM | Fastest training, most stable IC, first baseline |
| | XGBoost | Heterogeneous ensemble, complements LGB |
| | CatBoost | Native categorical (industry) features |
| | RandomForest | Bagging baseline, validates Boosting value |
| **Linear** | Ridge | sanity check, signal linearity |
| **Deep Learning** | GRU | Best cost-performance, DL entry point |
| | LSTM | Long-term memory, large windows |
| | ALSTM | Attention-enhanced, event-driven |
| | Transformer | Self-attention, long-range dependency |
| | TabNet | Tabular-specific, built-in feature selection |
| | TCN | Temporal convolution, fast training |
| | NativeTFT | Lightweight TFT, GRU+attention |
| | MLP | Neural baseline, validates temporal value |

### Professional Training Capabilities

- **🎯 Multi-Horizon**: one training T+1/3/5/10, auto ICIR-weighted fusion
- **🔬 Optuna Auto-Tuning**: TPE sampling, Rank ICIR objective
- **📐 Cross-Sectional Preprocessing**: per-date Z-score + winsorize + median fill
- **🧪 WFA Stability**: Walk-Forward rolling validation
- **🔍 Factor Selection**: IC/ICIR screen + correlation prune + stability check
- **🧬 Stacking Ensemble**: time-series OOF + Ridge meta-learner
- **🛡️ Leakage Prevention**: strict time split, label anti-leak, ST/suspension filter

### Model Management (Professional)

- **Production Monitoring**: daily real Rank IC backfill, drift detection + signal decay alert
- **A/B Comparison**: two-model metrics + production IC + feature diff
- **Soft Gate**: test ICIR below threshold stays candidate, manual activation
- **Multi-Market**: CN/HK/US/CRYPTO/FUTURES independent model space

---

## 🖥️ Remote Training (AutoDL GPU)

**Local CPU too slow? One-click push to AutoDL GPU, model auto-returns.**

- **🚀 GPU Acceleration**: 10-50x faster for deep learning
- **📦 Auto Push**: feature snapshots + scripts auto rsync to remote
- **🔄 Bidirectional Sync**: config/code sync, model auto-return & register
- **📊 Node Management**: multi-node parallel, real-time monitoring

```
Local API → Push snapshot+config → AutoDL starts container
  → GPU training → model scp back → auto-register ready
```

---

## 🔮 Inference

Trained models auto-enter inference pipeline — **multi-market, batch, fusion**.

- **🌐 Multi-Market**: A-Share/HK/US/Crypto/Futures independent inference
- **📅 Batch**: single-day / range backfill / full batch, auto-scheduled
- **🧬 Fusion**: multi-model / multi-horizon dynamic weighted (production IC)
- **📡 Signal Generation**: score → cross-section rank → buy/sell signal → store
- **📊 Production Monitoring**: daily real IC, model effect at a glance
- **🛡️ Fallback**: auto-degrade on missing data, multi-level quote source

---

## ✨ Features

| Module | Description |
|------|------|
| **📈 Market Analysis** | Full-market quotes, sectors, multi-dimensional stock analysis |
| **🧠 Smart Strategy** | AI-assisted Qlib strategy, natural language |
| **🤖 AI-IDE** | Strategy code AI editor |
| **📊 Backtest Center** | Qlib backtest, multi-strategy compare, param optimize |
| **🟦 QuantBot** | Natural language quant assistant, intent-driven |
| **🎓 Model Training** | 13 models + Optuna + remote GPU |
| **🗂️ Model Management** | Lifecycle, production monitoring, A/B compare |
| **🔬 Research Platform** | Multi-agent A-Share research (TradingAgents) |
| **💰 Simulation Trading** | Full pipeline simulation, T+1/price-limit/risk |
| **📡 TDX Push** | One-click push picks to TDX (blocks+alerts+messages) |
| **📰 RSS Feed** | Financial news aggregation (Huntly + RSSHub) |
| **👤 Personal/Admin** | User & system management |

---

## 📰 RSS Feed

Built-in **Huntly + RSSHub** financial news aggregation:

- **📡 Multi-source**: dozens of financial RSS sources auto-fetch
- **🤖 Smart Recommendation**: portfolio/watchlist-related news push
- **🔔 Real-time**: scheduled refresh, never miss key news
- **🔗 News Proxy**: unified API, frontend direct consume

---

## 🧩 Skills & Agents

### Claude Code Skills (20+ packages)

- **Data**: `stock-market-analysis`, `quantdb-sdk`, `global-stock-data`, `a-stock-data`
- **Strategy**: `smart-strategy-stock-picking`, `backtest-center`, `strategy-*`
- **Training**: `simulation-trading`, `model-training`, `batch-inference-analysis`
- **Analysis**: `alphagbm-*` (earnings/valuation/sentiment/options), `financial-analysis`
- **Ops**: `quantmind-operations`, `deployment-patterns`

### QuantBot

Natural-language quant assistant, **intent → auto-execute**:
- Quotes, positions, backtest, train — one sentence
- QwenPaw integration, multi-turn
- Exchange real-time data

### RD-Agent Auto Factor Mining

Microsoft **RD-Agent** automated factor evolution:
- Multi-market factor sets (A-Share/HK/US/Crypto)
- Auto evolution: LLM factor generation → backtest → survival
- **AlphaAgent**: factor encoding expert system

### TradingAgents Multi-Agent Research

7 AI analysts + debate module:
- Multi-role analysis (technical/fundamental/sentiment)
- Debate improves conclusion reliability
- Auto structured research report

---

## 🛠️ Tech Stack

| Domain | Tech |
|------|------|
| **Quant Framework** | Qlib (Microsoft), Backtrader, custom engine |
| **ML** | LightGBM, XGBoost, CatBoost, scikit-learn, Optuna |
| **Deep Learning** | PyTorch, GRU/LSTM/Transformer/TabNet/TCN |
| **Data** | **QuantDB**, Parquet, DuckDB, pandas, pyarrow |
| **Factor Mining** | RD-Agent, AlphaAgent |
| **Backend** | Python 3.10, FastAPI, SQLAlchemy, Celery |
| **Database** | PostgreSQL, Redis (6-db isolation) |
| **Frontend** | Electron, React 18, TypeScript, Vite, Ant Design |
| **Visualization** | ECharts, Recharts |
| **AI Assistant** | QwenPaw, Claude Code Skills, LLM intent |
| **TDX Integration** | TDX push, rolling trade |
| **Deployment** | Docker, Compose, AutoDL GPU, Nginx |

---

## 🚀 Quick Start

### 💻 Environment (Multi-OS)

| OS | Note |
|------|------|
| **Ubuntu / Debian** | Recommended, best performance |
| **Windows + WSL2** | Docker Desktop + WSL2 backend |
| **macOS** | Docker Desktop directly |
| **Cloud Server** | Any Docker env, single machine |

**Core deps**: Docker + Docker Compose only (fully containerized, no Python/Node needed)

### 🧠 Memory Recommendations (Important)

| Use | Recommended | Note |
|------|---------|------|
| **Model Training** | **64GB+** | 10M-row features + deep learning |
| **Inference / Backtest** | **32GB+** | Full-market 5000+ stocks |

> ⚠️ **Insufficient memory causes training OOM/kill.** Training machine ≥64GB recommended.

### 🚀 One-Command Deploy (5 steps)

```bash
# 1. Clone
git clone https://github.com/qusong0627/QuantMind.git
cd QuantMind

# 2. Config env
cp .env.example .env
# Edit .env: DB_PASSWORD, SECRET_KEY, etc.

# 3. Start all services
docker-compose up -d

# 4. Sync QuantDB A-Share data (optional, base data built-in)
docker exec quantmind python backend/scripts/quantdb_daily_sync.py

# 5. Access
# Frontend: http://localhost:3000
# API:      http://localhost:8000
```

### 🔧 Troubleshooting

| Problem | Solution |
|------|---------|
| Port conflict | `WEB_PORT=8080 docker-compose up -d` |
| OOM | Close containers, reduce data window |
| WSL2 fail | `wsl --set-default-version 2`, update kernel |
| Incomplete data | Run quantdb_daily_sync.py |
| Training killed (Exit 137) | OOM — need 64GB+ or smaller data |

---

## 📦 Deployment

```bash
# Production
git clone https://github.com/qusong0627/QuantMind.git
# config .env → docker-compose up -d → register QuantDB & sync data → init DB → build index
```

---

## 🤝 Open Source Philosophy

**QuantMind's vision — Democratize quantitative trading, not just for institutions.**

Quantitative trading has been monopolized by institutions, blocked by two foundations: **data infrastructure** and **technical infrastructure**.

- **Data**: Professional quotes/financials/factors cost institutions millions — individuals must crawl, clean, and reinvent wheels
- **Tech**: Model training, backtest, inference, deployment need professional teams — individuals start from zero

**QuantMind solves both foundations with open source:**

| Foundation | Institution Way | QuantMind Open-Source |
|------|---------|------------------|
| **Data** | Millions for professional data | **QuantDB** — register & pull, out-of-box |
| **Features** | Team-developed 151+ factors | **315 AI factors** auto-generated |
| **Training** | Professional ML engineers | **13 AI models** + Optuna auto-tune |
| **Inference** | Institutional deployment team | Auto-register, one-click inference |

> **We believe quant should not be a rich man's game.** Turn complex data/features/training/inference into out-of-box capability, so every ordinary investor can arm themselves with AI — **Data ready, train directly, quant for everyone.**

**Data-Driven · Open Source · Quant Democratization · AI for Every Investor**

---

## 👥 Who It's For

- Individual quant researchers — validate Alpha strategies, factor mining
- Academic researchers — A-Share multi-factor, deep learning stock selection
- Stock enthusiasts — AI-assisted stock picking without infra build
- Small teams — strategy prototyping & secondary development

---

## 🔍 Keywords

Quantitative Trading · A-Share Quant · Multi-Factor Model · Factor Mining · Alpha Strategy · ML Stock Selection · Deep Learning Stock Selection · LightGBM · XGBoost · CatBoost · LSTM · Transformer · Qlib · Stock Prediction · Strategy Backtest · Model Training · AI Trading · QuantDB · Quantitative Data · Quant Platform · Open Source Quant

---

## QQ Group

<p align="center">
  <img src="docs/images/1097406397.png" alt="QuantMind QQ Group" width="260">
</p>

---

<p align="center">
  <strong>QuantMind</strong> — Making Quantitative Trading Simpler
</p>
<p align="center">
  <em>Data-Driven · AI-Powered · Multi-Market Quantitative Trading Platform</em>
</p>
