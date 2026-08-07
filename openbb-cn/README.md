# OPENBB-CN

面向中国个人投资者的开源金融数据平台 | 基于 OpenBB 架构扩展

[![GitHub stars](https://img.shields.io/github/stars/LSY1105/OPENBB-CN)](https://github.com/LSY1105/OPENBB-CN/stargazers)
[![License](https://img.shields.io/badge/License-GPL--3.0-blue)](LICENSE)

## 项目目标

OPENBB-CN 是一个专注于中国 A 股、港股、期货等市场的开源金融数据平台，目标是为个人投资者提供：

- 📊 **统一数据接口**：整合多个免费数据源
- 📈 **技术分析工具**：K线图、技术指标、形态识别
- 📝 **基本面分析**：财务报表、估值分析、业绩预测
- 🤖 **AI 智能助手**：接入国产大模型
- 🐍 **Python SDK**：一键安装，简洁 API
- 🌐 **REST API**：支持任意前端调用

## 支持的数据源

| 数据源 | 数据类型 | 费用 | 状态 |
|--------|----------|------|------|
| **akshare** | A股、期货、基金、宏观 | 免费 | ✅ 已完成 |
| **easyquotation** | 实时行情（通达信/新浪） | 免费 | ✅ 已完成 |
| **tushare** | A股、港股通、财务数据 | 部分免费 | ✅ 已完成 |
| **eastmoney** | 行情、新闻、资金流向 | 免费 | ✅ 已完成 |
| **东方财富** | 实时行情、资讯 | 免费 | ✅ 已完成 |

## AI 模型支持

| 模型 | 提供商 | 特点 |
|------|--------|------|
| **MiniMax** | MiniMax | 响应快、支持 Function Calling |
| **GLM** | 智谱 AI | 中文理解强 |
| **Qwen** | 阿里云 | 代码能力强 |
| **DeepSeek** | 深度求索 | 推理能力强 |

## 快速开始

### 1. 安装

```bash
pip install akshare easyquotation pandas numpy
# 或
pip install -e ".[providers]"
```

### 2. Python SDK 使用

```python
from openbb_core import OpenBB

obb = OpenBB()

# 获取股票历史数据
data = obb.stocks.historical("000001.SZ", provider="akshare")

# 获取实时行情
quote = obb.stocks.quote("600000", provider="eastmoney")

# 搜索股票
results = obb.stocks.search("茅台", provider="akshare")

# 技术分析
ma = obb.technical.ma("000001.SZ", period=20, provider="akshare")
macd = obb.technical.macd("000001.SZ", provider="akshare")

# AI 助手
obb.ai.set_provider("minimaxi", api_key="your-api-key")
result = obb.ai.chat("帮我分析贵州茅台的财务状况")
```

### 3. REST API 服务

```bash
# 启动 API 服务
cd OPENBB-CN
python -m uvicorn openbb_core.api:app --host 0.0.0.0 --port 8000

# 访问文档
# http://localhost:8000/docs
```

#### API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | API 信息 |
| `/health` | GET | 健康检查 |
| `/api/v1/stocks/historical` | GET | 历史行情 |
| `/api/v1/stocks/quote` | GET | 实时行情 |
| `/api/v1/stocks/search` | GET | 股票搜索 |
| `/api/v1/stocks/market-overview` | GET | 市场概览 |
| `/api/v1/technical/ma` | GET | 移动平均线 |
| `/api/v1/technical/macd` | GET | MACD 指标 |
| `/api/v1/technical/kdj` | GET | KDJ 指标 |
| `/api/v1/technical/rsi` | GET | RSI 指标 |
| `/api/v1/fundamental/valuation` | GET | 估值指标 |
| `/api/v1/ai/chat` | POST | AI 对话 |
| `/api/v1/ai/analyze` | POST | AI 股票分析 |

### 4. Docker 部署

```bash
cd OPENBB-CN/docker

# 构建镜像
docker build -t openbb-cn .

# 运行容器
docker run -p 8000:8000 openbb-cn

# 或使用 docker-compose
docker-compose up -d
```

## 项目结构

```
OPENBB-CN/
├── openbb_core/                  # 核心模块
│   ├── __init__.py               # 包入口
│   ├── core.py                   # OpenBB 主类
│   ├── api.py                    # FastAPI REST API
│   ├── router/                   # 路由模块
│   ├── providers/               # 数据源 Providers
│   │   ├── base.py              # Provider 基类
│   │   ├── akshare_provider.py   # AkShare 实现
│   │   ├── easyquotation_provider.py # EasyQuotation 实现
│   │   ├── tushare_provider.py  # Tushare 实现
│   │   └── eastmoney_provider.py # 东方财富实现
│   └── extensions/              # 功能扩展
│       ├── stocks.py           # 股票数据接口
│       ├── technical.py        # 技术分析 (MA/MACD/KDJ/RSI/BOLL)
│       ├── fundamental.py      # 基本面分析
│       └── ai.py              # AI 助手 (MiniMax/GLM/Qwen/DeepSeek)
├── tests/                      # 测试文件
├── docker/                     # Docker 配置
├── pyproject.toml             # 项目配置
└── README.md
```

## 环境变量

```bash
# Tushare Token (可选)
export TUSHARE_TOKEN="your-tushare-token"

# AI 模型 API Keys (至少需要一个)
export MINIMAX_API_KEY="your-minimax-api-key"
export ZHIPUAI_API_KEY="your-zhipuai-api-key"
export DASHSCOPE_API_KEY="your-dashscope-api-key"
export DEEPSEEK_API_KEY="your-deepseek-api-key"
```

## 本地开发

```bash
# 克隆项目
git clone https://github.com/LSY1105/OPENBB-CN.git
cd OPENBB-CN

# 安装依赖
pip install -e ".[dev,providers,ai]"

# 运行测试
pytest tests/ -v

# 启动开发服务器
python -m uvicorn openbb_core.api:app --reload
```

## 功能路线图

- [x] 核心框架搭建
- [x] AkShare Provider
- [x] EasyQuotation Provider
- [x] Tushare Provider
- [x] EastMoney Provider
- [x] 技术分析模块
- [x] 基本面分析模块
- [x] AI 助手模块
- [x] REST API
- [ ] Web UI 界面
- [ ] 回测框架
- [ ] 策略管理
- [ ] 因子库
- [ ] 量化策略生成

## 贡献指南

欢迎提交 Pull Request！请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

本项目基于 GPL-3.0 许可证开源。

## 致谢

- 基于 [OpenBB](https://github.com/OpenBB-finance/OpenBB) 架构
- 数据源来自 [akshare](https://github.com/akshare-org/akshare)、[tushare](http://tushare.org/)、[easyquotation](https://github.com/利益关系/easyquotation) 等开源项目
