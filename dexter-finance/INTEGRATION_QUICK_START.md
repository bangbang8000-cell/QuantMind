# 🚀 OpenBB + AkShare 集成快速入门

## 立即开始

### 1️⃣ 启动 AkShare 服务（如果还没启动）

```bash
cd /tmp/dexter/python-service
./start.sh
```

- 端口：`8000`
- 文档：http://localhost:8000/docs

---

### 2️⃣ 启动 OpenBB 服务

```bash
cd /tmp/dexter/openbb-service
./start.sh
```

- 端口：`8001`
- 文档：http://localhost:8001/docs

---

### 3️⃣ 测试服务

#### 测试 AkShare
```bash
cd /tmp/dexter/python-service
python3 test_api.py
```

#### 测试 OpenBB
```bash
cd /tmp/dexter/openbb-service
python3 test_service.py
```

---

### 4️⃣ 在 Dexter 中使用

#### 导入所有工具
```typescript
// src/index.ts 或 src/agent.ts

// AkShare 工具（中国市场）
import { akshareTools } from './tools/finance/cn-market';

// OpenBB 工具（全球市场）
import { openbbTools } from './tools/finance/openbb';

// 跨市场分析工具
import { crossMarketTools } from './tools/finance/cross-market';

// 组合所有工具
const financialTools = [
  ...akshareTools,      // 9 个中国市场工具
  ...openbbTools,       // 12 个全球市场工具
  ...crossMarketTools,  // 2 个跨市场分析工具
];

// 添加到 Dexter 代理
const agent = new Agent({
  tools: financialTools,
  // ... 其他配置
});
```

---

## 📖 常用示例

### 示例 1: 对比中美科技股

```typescript
// AI 代理会自动调用这些工具

// 用户问题：
"对比贵州茅台和苹果公司最近30天的表现"

// Dexter 会自动：
// 1. 调用 compare_cn_us_markets 工具
// 2. 内部调用 AkShare 获取茅台数据
// 3. 内部调用 OpenBB 获取苹果数据
// 4. 计算相关性和涨跌幅
// 5. 生成分析报告
```

### 示例 2: 研究美股

```typescript
// 用户问题：
"分析特斯拉最近三个月的走势"

// Dexter 自动调用：
get_us_stock_historical({
  symbol: "TSLA",
  startDate: "2025-11-24",
  endDate: "2026-02-24",
  interval: "1d"
})
```

### 示例 3: 查看比特币

```typescript
// 用户问题：
"比特币现在多少钱？"

// Dexter 自动调用：
get_crypto_quote({ symbol: "BTC" })
```

### 示例 4: 宏观经济

```typescript
// 用户问题：
"美国和中国的 CPI 对比"

// Dexter 自动调用：
// 1. get_cpi({ country: "united_states" })  # OpenBB
// 2. get_macro_cpi()                         # AkShare
```

---

## 🔧 环境变量配置

创建 `.env` 文件：

```bash
# AkShare 服务
AKSHARE_API_URL=http://localhost:8000

# OpenBB 服务
OPENBB_API_URL=http://localhost:8001
```

---

## 🌐 API 端点速查

### AkShare (端口 8000)
```
GET  /stock/realtime/{symbol}          # A股实时行情
GET  /stock/daily/{symbol}             # A股日线数据
GET  /stock/info/{symbol}              # 股票基本信息
GET  /fund/realtime/{symbol}           # 基金实时净值
GET  /macro/cpi                        # 中国 CPI
GET  /macro/gdp                        # 中国 GDP
GET  /macro/pmi                        # 中国 PMI
```

### OpenBB (端口 8001)
```
GET  /equity/historical/{symbol}       # 美股历史数据
GET  /equity/quote/{symbol}            # 美股实时报价
GET  /equity/profile/{symbol}          # 公司信息
GET  /equity/search?query=...          # 股票搜索
GET  /macro/gdp?country=...            # 全球 GDP
GET  /macro/cpi?country=...            # 全球 CPI
GET  /crypto/historical/{symbol}       # 加密货币历史
GET  /crypto/quote/{symbol}            # 加密货币报价
GET  /options/chains/{symbol}          # 期权链
```

---

## ✅ 验证清单

- [ ] AkShare 服务运行在 8000 端口
- [ ] OpenBB 服务运行在 8001 端口
- [ ] AkShare 测试全部通过
- [ ] OpenBB 测试全部通过
- [ ] Dexter 可以导入工具
- [ ] `.env` 文件配置正确

---

## 🆘 常见问题

### Q: 服务启动失败？
```bash
# 检查端口是否被占用
lsof -i :8000
lsof -i :8001

# 终止占用进程
kill -9 <PID>
```

### Q: 依赖安装失败？
```bash
# 使用国内镜像
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### Q: OpenBB 数据获取失败？
- 检查网络连接（OpenBB 需要访问国外数据源）
- 某些数据可能需要 API Key（查看 OpenBB 文档）

### Q: AkShare 数据格式不对？
- 确保使用正确的股票代码格式（如 `600519` 而不是 `SH600519`）
- 日期格式为 `YYYYMMDD`（如 `20260101`）

---

## 📚 更多资源

- [AkShare 官方文档](https://akshare.akfamily.xyz/)
- [OpenBB 官方文档](https://docs.openbb.co/)
- [LangChain 工具文档](https://js.langchain.com/docs/modules/agents/tools/)

---

**准备就绪！开始使用 Dexter 分析全球金融市场吧！🎉**
