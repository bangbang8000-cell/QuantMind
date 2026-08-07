# 🚀 Dexter 金融数据集成项目

> 为 Dexter AI 代理提供中国和全球金融市场数据能力

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-blue.svg)](https://www.typescriptlang.org/)
[![LangChain](https://img.shields.io/badge/LangChain-latest-orange.svg)](https://www.langchain.com/)

---

## 📋 项目概述

本项目为 **Dexter AI 金融研究代理** 集成了两个强大的数据源：

- **AkShare**: 中国金融市场数据专家（A股、港股、基金、宏观数据）
- **OpenBB**: 全球金融市场数据平台（美股、加密货币、期权、全球宏观）

通过 FastAPI 服务和 LangChain 工具层，Dexter 可以：
- 📊 查询中美股票市场数据
- 💹 分析加密货币价格走势
- 📈 对比全球宏观经济指标
- 🔍 研究期权市场
- 🌐 进行跨市场相关性分析

---

## 🎯 核心功能

### ✅ 已实现

1. **AkShare 集成** (9 个工具)
   - A股实时行情和历史数据
   - 基金净值查询
   - 中国宏观经济数据（GDP、CPI、PMI）

2. **OpenBB 集成** (12 个工具)
   - 美股历史价格和实时报价
   - 公司基本信息
   - 全球宏观经济数据
   - 加密货币数据
   - 期权链数据

3. **跨市场分析** (2 个工具)
   - 中美股市对比分析
   - 相关性计算
   - 投资建议生成

---

## 📁 项目结构

```
dexter/
├── README.md                          # 本文件
├── ARCHITECTURE.md                    # 架构设计文档
├── OPENBB_INTEGRATION_SUMMARY.md      # OpenBB 集成总结
├── INTEGRATION_QUICK_START.md         # 快速入门指南
│
├── python-service/                    # AkShare API 服务
│   ├── app/
│   │   ├── main.py                    # FastAPI 主应用
│   │   └── routes/                    # API 路由
│   ├── requirements.txt               # Python 依赖
│   ├── start.sh                       # 启动脚本
│   └── test_api.py                    # 测试脚本
│
├── openbb-service/                    # OpenBB API 服务
│   ├── app/
│   │   ├── main.py                    # FastAPI 主应用
│   │   ├── routes/
│   │   │   ├── equity.py              # 美股路由
│   │   │   ├── macro.py               # 宏观数据路由
│   │   │   ├── crypto.py              # 加密货币路由
│   │   │   └── options.py             # 期权路由
│   │   └── utils/
│   │       └── openbb_client.py       # OpenBB 客户端封装
│   ├── requirements.txt               # Python 依赖
│   ├── start.sh                       # 启动脚本
│   └── test_service.py                # 测试脚本
│
└── src/
    └── tools/
        └── finance/
            ├── cn-market/             # AkShare 工具（9个）
            │   ├── akshare-api.ts     # API 客户端
            │   └── tools.ts           # LangChain 工具
            ├── openbb/                # OpenBB 工具（12个）
            │   ├── openbb-api.ts      # API 客户端
            │   └── tools.ts           # LangChain 工具
            └── cross-market/          # 跨市场分析（2个）
                └── analysis.ts        # 分析工具
```

---

## 🚀 快速开始

### 前置要求

- Python 3.10+
- Node.js 16+ (用于 TypeScript 工具)
- Git

### 1️⃣ 启动 AkShare 服务

```bash
cd python-service
./start.sh
```

服务运行在: `http://localhost:8000`
API 文档: `http://localhost:8000/docs`

### 2️⃣ 启动 OpenBB 服务

```bash
cd openbb-service
./start.sh
```

服务运行在: `http://localhost:8001`
API 文档: `http://localhost:8001/docs`

### 3️⃣ 测试服务

```bash
# 测试 AkShare
cd python-service
python3 test_api.py

# 测试 OpenBB
cd openbb-service
python3 test_service.py
```

### 4️⃣ 在 Dexter 中使用

```typescript
// 导入工具
import { akshareTools } from './tools/finance/cn-market';
import { openbbTools } from './tools/finance/openbb';
import { crossMarketTools } from './tools/finance/cross-market';

// 组合所有工具
const allFinanceTools = [
  ...akshareTools,      // 9 个中国市场工具
  ...openbbTools,       // 12 个全球市场工具
  ...crossMarketTools,  // 2 个跨市场分析工具
];

// 添加到 Dexter 代理
const agent = createAgent({
  tools: allFinanceTools,
  // ... 其他配置
});
```

---

## 💡 使用示例

### 示例 1: 查询 A股数据

```bash
# 用户输入
"查询贵州茅台最近30天的股价走势"

# Dexter 自动调用
get_a_stock_daily({
  symbol: "600519",
  startDate: "20260125",
  endDate: "20260224"
})

# 返回格式化的价格数据和分析
```

### 示例 2: 查询美股数据

```bash
# 用户输入
"特斯拉现在股价多少？"

# Dexter 自动调用
get_us_stock_quote({ symbol: "TSLA" })

# 返回实时报价和涨跌幅
```

### 示例 3: 跨市场对比

```bash
# 用户输入
"对比宁德时代和特斯拉的表现"

# Dexter 自动调用
compare_cn_us_markets({
  cnSymbol: "300750",  // 宁德时代
  usSymbol: "TSLA",    // 特斯拉
  days: 30
})

# 返回相关性分析、涨跌幅对比、投资建议
```

### 示例 4: 加密货币

```bash
# 用户输入
"比特币最近一周走势如何？"

# Dexter 自动调用
get_crypto_historical({
  symbol: "BTC",
  startDate: "2026-02-17",
  endDate: "2026-02-24"
})
```

---

## 📊 数据覆盖

### AkShare（中国市场）

| 类别       | 覆盖范围                           |
|------------|------------------------------------|
| **股票**   | 上海、深圳、北京证券交易所所有股票 |
| **基金**   | 公募基金、ETF、货币基金            |
| **宏观**   | GDP、CPI、PMI、M2、利率            |
| **行业**   | 行业指数、板块数据                 |

### OpenBB（全球市场）

| 类别       | 覆盖范围                           |
|------------|------------------------------------|
| **股票**   | 纽交所、纳斯达克、欧洲、亚洲市场   |
| **加密**   | BTC、ETH、主流加密货币             |
| **期权**   | 美股期权链、隐含波动率             |
| **宏观**   | 美国、欧盟、日本、中国等全球数据   |

---

## 🔧 配置

### 环境变量

创建 `.env` 文件：

```bash
# AkShare 服务地址
AKSHARE_API_URL=http://localhost:8000

# OpenBB 服务地址
OPENBB_API_URL=http://localhost:8001

# OpenBB API Key（某些数据源需要）
# OPENBB_API_KEY=your_api_key_here
```

### 端口配置

| 服务             | 默认端口 | 配置文件              |
|------------------|----------|-----------------------|
| AkShare Service  | 8000     | `start.sh`            |
| OpenBB Service   | 8001     | `start.sh`            |

---

## 📚 文档

- [架构设计](./ARCHITECTURE.md) - 系统架构和数据流
- [OpenBB 集成总结](./OPENBB_INTEGRATION_SUMMARY.md) - OpenBB 详细说明
- [快速入门](./INTEGRATION_QUICK_START.md) - 一步步指南

### API 文档

启动服务后访问：
- AkShare API: http://localhost:8000/docs
- OpenBB API: http://localhost:8001/docs

---

## 🧪 测试

### 单元测试

```bash
# AkShare 服务测试
cd python-service
python3 test_api.py

# OpenBB 服务测试
cd openbb-service
python3 test_service.py
```

### 手动测试

```bash
# 测试 AkShare 端点
curl "http://localhost:8000/stock/daily/600519?start_date=20260101&end_date=20260224"

# 测试 OpenBB 端点
curl "http://localhost:8001/equity/quote/AAPL"
```

---

## 🔒 安全

- ✅ CORS 配置允许跨域访问
- ✅ 输入验证防止注入攻击
- ✅ 错误处理避免信息泄露
- ⏳ 建议生产环境添加 API 限流
- ⏳ 建议使用 HTTPS 加密传输

---

## 🚢 部署

### 开发环境

当前配置适用于本地开发：
- 服务运行在 localhost
- 使用 `--reload` 模式自动重启

### 生产环境

部署到腾讯云服务器（可选）：

```bash
# 1. 使用 systemd 管理服务
sudo systemctl start akshare-service
sudo systemctl start openbb-service

# 2. 配置 Nginx 反向代理
# 见 TENCENT_CLOUD_DEPLOYMENT.md

# 3. 配置防火墙
sudo ufw allow 8000/tcp
sudo ufw allow 8001/tcp
```

---

## 📈 性能优化

### 缓存

```python
# 添加 Redis 缓存（可选）
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend

@app.on_event("startup")
async def startup():
    redis = aioredis.from_url("redis://localhost")
    FastAPICache.init(RedisBackend(redis))
```

### 负载均衡

```bash
# 启动多个服务实例
uvicorn app.main:app --port 8000 --workers 4
uvicorn app.main:app --port 8001 --workers 4
```

---

## 🤝 贡献

欢迎贡献代码、报告问题或提出建议！

### 添加新工具

1. 在对应的 `tools.ts` 文件中添加工具定义
2. 在 FastAPI 服务中添加对应端点
3. 更新测试脚本
4. 更新文档

---

## 📝 版本历史

### v1.0.0 (2026-02-24)

**完成**:
- ✅ AkShare API 服务（9个端点）
- ✅ OpenBB API 服务（12个端点）
- ✅ TypeScript LangChain 工具（23个）
- ✅ 跨市场分析功能
- ✅ 完整文档和测试

**测试状态**:
- AkShare: 87.5% 通过 (7/8)
- OpenBB: 待测试
- 跨市场工具: 待测试

---

## 🙏 致谢

- [AkShare](https://github.com/akfamily/akshare) - 中国金融数据获取工具
- [OpenBB](https://github.com/OpenBB-finance/OpenBB) - 开源金融数据平台
- [FastAPI](https://fastapi.tiangolo.com/) - 现代 Python Web 框架
- [LangChain](https://www.langchain.com/) - AI 应用开发框架

---

## 📄 许可证

本项目基于 MIT 许可证开源。

---

## 📞 联系方式

有问题或建议？欢迎联系！

---

**现在开始使用 Dexter 分析全球金融市场吧！** 🚀📊💰
