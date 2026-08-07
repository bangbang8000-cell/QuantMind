# 🏗️ Dexter 金融数据集成架构

## 系统架构图

```
┌────────────────────────────────────────────────────────────────────────┐
│                         Dexter AI Agent                                │
│                    (LangChain + TypeScript)                            │
└────────────────────────────────────────────────────────────────────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    │              │              │
                    ▼              ▼              ▼
        ┌───────────────┐ ┌───────────────┐ ┌───────────────┐
        │   AkShare     │ │    OpenBB     │ │ Cross-Market  │
        │   Tools       │ │    Tools      │ │    Tools      │
        │   (9 个)      │ │   (12 个)     │ │    (2 个)     │
        └───────────────┘ └───────────────┘ └───────────────┘
                │                  │              │   │
                │                  │              └───┼────────┐
                ▼                  ▼                  ▼        ▼
        ┌──────────────┐   ┌──────────────┐
        │  AkShare API │   │  OpenBB API  │
        │   Service    │   │   Service    │
        │              │   │              │
        │ FastAPI      │   │ FastAPI      │
        │ Port: 8000   │   │ Port: 8001   │
        └──────────────┘   └──────────────┘
                │                  │
                ▼                  ▼
        ┌──────────────┐   ┌──────────────┐
        │   AkShare    │   │    OpenBB    │
        │   Library    │   │   Platform   │
        │              │   │              │
        │ 中国市场数据  │   │  全球市场数据 │
        └──────────────┘   └──────────────┘
```

---

## 数据流向

### 场景 1: 查询中国 A股数据

```
User Query: "查询贵州茅台的股价"
    │
    ▼
Dexter Agent
    │
    ▼
get_a_stock_daily Tool (TypeScript)
    │
    ▼
HTTP GET → http://localhost:8000/stock/daily/600519
    │
    ▼
AkShare API Service (Python)
    │
    ▼
ak.stock_zh_a_hist(symbol="600519")
    │
    ▼
AkShare Library → 从新浪财经等源获取数据
    │
    ▼
返回 JSON 数据
    │
    ▼
格式化并返回给 Dexter
    │
    ▼
生成自然语言回答给用户
```

### 场景 2: 查询美股数据

```
User Query: "苹果公司股价如何？"
    │
    ▼
Dexter Agent
    │
    ▼
get_us_stock_historical Tool (TypeScript)
    │
    ▼
HTTP GET → http://localhost:8001/equity/quote/AAPL
    │
    ▼
OpenBB API Service (Python)
    │
    ▼
obb.equity.price.quote(symbol="AAPL")
    │
    ▼
OpenBB Platform → 从 Yahoo Finance 等源获取数据
    │
    ▼
返回 JSON 数据
    │
    ▼
格式化并返回给 Dexter
    │
    ▼
生成自然语言回答给用户
```

### 场景 3: 跨市场对比分析

```
User Query: "对比茅台和苹果的表现"
    │
    ▼
Dexter Agent
    │
    ▼
compare_cn_us_markets Tool (TypeScript)
    │
    ├─────────────────────────┬─────────────────────────┐
    │                         │                         │
    ▼                         ▼                         ▼
getCNStockDaily         getUSStockHistorical    计算相关性
(AkShare API)           (OpenBB API)            和涨跌幅
    │                         │                         │
    ▼                         ▼                         │
返回茅台数据             返回苹果数据                   │
    │                         │                         │
    └─────────────────────────┴─────────────────────────┘
                              │
                              ▼
                    生成对比分析报告
                              │
                              ▼
                    返回给 Dexter Agent
                              │
                              ▼
                    生成自然语言回答给用户
```

---

## 组件说明

### 1. Dexter AI Agent（决策层）

**技术栈**: TypeScript + LangChain

**职责**:
- 理解用户自然语言查询
- 选择合适的工具
- 组合多个工具完成复杂任务
- 生成自然语言回答

**示例工作流**:
```typescript
用户: "对比贵州茅台和苹果最近30天的表现"

Agent 决策:
1. 识别意图: 跨市场对比
2. 选择工具: compare_cn_us_markets
3. 提取参数:
   - cnSymbol: "600519"
   - usSymbol: "AAPL"
   - days: 30
4. 执行工具
5. 解释结果
6. 生成回答
```

---

### 2. LangChain Tools（工具层）

**技术栈**: TypeScript + Zod

**文件结构**:
```
src/tools/finance/
├── cn-market/          # AkShare 工具
│   ├── akshare-api.ts  # API 客户端
│   ├── tools.ts        # 9 个 LangChain 工具
│   └── index.ts
├── openbb/             # OpenBB 工具
│   ├── openbb-api.ts   # API 客户端
│   ├── tools.ts        # 12 个 LangChain 工具
│   └── index.ts
└── cross-market/       # 跨市场工具
    ├── analysis.ts     # 2 个分析工具
    └── index.ts
```

**工具定义示例**:
```typescript
export const getUSStockHistoricalTool = new DynamicStructuredTool({
  name: 'get_us_stock_historical',
  description: '获取美股历史价格数据...',
  schema: z.object({
    symbol: z.string().describe('美股代码'),
    startDate: z.string().optional(),
    endDate: z.string().optional(),
  }),
  func: async (input) => {
    const result = await getEquityHistorical(input.symbol, {
      startDate: input.startDate,
      endDate: input.endDate,
    });
    return formatToolResult(result.data);
  },
});
```

---

### 3. API Services（服务层）

#### AkShare API Service

**技术栈**: Python + FastAPI

**端口**: 8000

**核心文件**:
```python
# app/main.py
from fastapi import FastAPI
import akshare as ak

app = FastAPI(title="AkShare API Service")

@app.get("/stock/daily/{symbol}")
async def get_stock_daily(symbol: str, start_date: str, end_date: str):
    df = ak.stock_zh_a_hist(symbol=symbol,
                             start_date=start_date,
                             end_date=end_date)
    return {"status": "success", "data": df.to_dict(orient="records")}
```

**9 个端点**:
1. `/stock/realtime/{symbol}` - A股实时
2. `/stock/daily/{symbol}` - A股日线
3. `/stock/info/{symbol}` - 股票信息
4. `/stock/financials/{symbol}` - 财务数据
5. `/fund/realtime/{symbol}` - 基金净值
6. `/fund/daily/{symbol}` - 基金日线
7. `/macro/cpi` - CPI
8. `/macro/gdp` - GDP
9. `/macro/pmi` - PMI

#### OpenBB API Service

**技术栈**: Python + FastAPI

**端口**: 8001

**核心文件**:
```python
# app/main.py
from fastapi import FastAPI
from openbb import obb

app = FastAPI(title="OpenBB API Service")

@app.get("/equity/historical/{symbol}")
async def get_equity_historical(symbol: str, start_date: str, end_date: str):
    result = obb.equity.price.historical(symbol=symbol,
                                          start_date=start_date,
                                          end_date=end_date)
    return {"status": "success", "data": result.to_dict()}
```

**12 个端点**:

**美股 (4)**:
1. `/equity/historical/{symbol}` - 历史数据
2. `/equity/quote/{symbol}` - 实时报价
3. `/equity/profile/{symbol}` - 公司信息
4. `/equity/search` - 股票搜索

**宏观 (4)**:
5. `/macro/gdp` - GDP
6. `/macro/cpi` - CPI
7. `/macro/unemployment` - 失业率
8. `/macro/interest-rate` - 利率

**加密货币 (2)**:
9. `/crypto/historical/{symbol}` - 历史数据
10. `/crypto/quote/{symbol}` - 实时报价

**期权 (2)**:
11. `/options/chains/{symbol}` - 期权链
12. `/options/expirations/{symbol}` - 到期日

---

### 4. Data Libraries（数据层）

#### AkShare

**类型**: Python 库

**数据源**:
- 新浪财经
- 东方财富
- 同花顺
- 雪球
- 中国统计局

**覆盖**:
- A股、港股
- 基金、债券
- 期货、期权
- 宏观经济（中国）

#### OpenBB Platform

**类型**: Python 平台

**数据源**:
- Yahoo Finance
- Alpha Vantage
- FRED (美联储经济数据)
- Binance (加密货币)
- 等 100+ 数据源

**覆盖**:
- 美股、欧股、全球市场
- 加密货币
- 期权
- 宏观经济（全球）

---

## 数据对比

| 特性           | AkShare               | OpenBB                |
|----------------|-----------------------|-----------------------|
| **地理覆盖**   | 🇨🇳 中国为主          | 🌍 全球               |
| **股票市场**   | A股、港股             | 美股、欧股等          |
| **宏观数据**   | 中国                  | 全球主要国家          |
| **加密货币**   | ❌                    | ✅                    |
| **期权数据**   | ❌                    | ✅                    |
| **基金数据**   | ✅                    | 部分                  |
| **更新频率**   | 实时                  | 实时                  |
| **数据源**     | 免费                  | 免费 + 付费           |
| **API 密钥**   | 不需要                | 部分需要              |

---

## 技术栈总结

```
┌─────────────────────────────────────────────────────┐
│  前端/代理层                                         │
│  • TypeScript                                       │
│  • LangChain                                        │
│  • Zod (schema validation)                         │
└─────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│  API 服务层                                         │
│  • Python 3.10+                                     │
│  • FastAPI                                          │
│  • Uvicorn (ASGI server)                           │
│  • CORS middleware                                 │
└─────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│  数据层                                             │
│  • AkShare (Python library)                        │
│  • OpenBB Platform (Python)                        │
│  • Pandas (data processing)                        │
└─────────────────────────────────────────────────────┘
```

---

## 部署架构

### 开发环境（当前）

```
本地机器
├── Dexter Agent (开发中)
├── AkShare Service (localhost:8000)
└── OpenBB Service (localhost:8001)
```

### 生产环境（可选）

```
┌─────────────────────────────────────────────────┐
│  腾讯云服务器 (43.162.121.13)                   │
│                                                 │
│  ┌───────────────────────────────────────────┐ │
│  │  Nginx (反向代理)                          │ │
│  │  Port: 80/443                             │ │
│  └───────────────────────────────────────────┘ │
│              │                                  │
│    ┌─────────┴─────────┐                       │
│    ▼                   ▼                        │
│  ┌──────────┐      ┌──────────┐                │
│  │ AkShare  │      │ OpenBB   │                │
│  │ Service  │      │ Service  │                │
│  │ :8000    │      │ :8001    │                │
│  └──────────┘      └──────────┘                │
│                                                 │
│  systemd services (后台运行)                    │
└─────────────────────────────────────────────────┘
```

---

## 性能优化

### 缓存策略

```python
# 可选：添加 Redis 缓存
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend

@app.on_event("startup")
async def startup():
    redis = aioredis.from_url("redis://localhost")
    FastAPICache.init(RedisBackend(redis), prefix="dexter-cache")
```

### 负载均衡

```nginx
# Nginx 配置
upstream akshare_backend {
    server localhost:8000;
    server localhost:8002;  # 多实例
}

upstream openbb_backend {
    server localhost:8001;
    server localhost:8003;  # 多实例
}
```

---

## 安全考虑

1. **API 限流**
   - 每个 IP 限制请求频率
   - 防止滥用

2. **数据验证**
   - 输入参数验证
   - 防止注入攻击

3. **HTTPS**
   - 生产环境使用 SSL/TLS
   - 保护数据传输

4. **认证授权**（可选）
   - API Key 验证
   - JWT Token

---

## 监控和日志

```python
# 添加请求日志
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Request: {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"Response: {response.status_code}")
    return response
```

---

**架构设计完成！** 🎉

这是一个可扩展、模块化、生产就绪的金融数据分析系统架构。
