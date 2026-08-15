---
name: rd-agent-factor-mining
description: "自动调用 RD-Agent 进行因子挖掘。在 QuantBot / Claude Code 中启动因子演化任务、查看演化进度、分析挖掘出的因子、对因子回测与导出时使用。触发词：挖因子、因子挖掘、因子演化、RD-Agent、alpha agent、演化因子、挖掘新因子、启动因子任务"
---

# RD-Agent 因子挖掘技能

自动调用 RD-Agent（Alpha Agent）因子演化管线，挖掘新的量化因子。

## 前置条件

需要配置 LLM API Key（`AI_IDE_LLM_API_KEY` 或 `OPENAI_API_KEY`），否则启动会返回 412。
```bash
# 检查是否已配置
docker exec quantmind env | grep -E "AI_IDE_LLM_API_KEY|OPENAI_API_KEY" | head
```

## 认证

```bash
BASE=http://127.0.0.1:8000
TOKEN=$(curl -s -X POST $BASE/api/v1/auth/login -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123","tenant_id":"default"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")
AUTH="Authorization: Bearer $TOKEN"
```

## 1. 查看支持的标的池

```bash
# 支持的股票池（universe）
curl -s -H "$AUTH" "$BASE/api/v1/alpha-agent/universes"
# 返回: csi300(沪深300)/csi500/csi1000/sse50/gem(创业板)/star(科创板)/csi800/all_a(全A)

# 支持的市场
curl -s -H "$AUTH" "$BASE/api/v1/alpha-agent/markets"

# 因子类别（挖掘方向参考）
curl -s -H "$AUTH" "$BASE/api/v1/alpha-agent/factor-categories"
# 返回类别: momentum(动量)/volatility(波动率)/liquidity(流动性)/fundamental(基本面)/style(风格)/industry(行业)/chip(筹码)/concept(概念)/microstructure(微观结构)
```

## 2. 启动因子演化（核心）

```bash
curl -s -X POST "$BASE/api/v1/alpha-agent/evolve" \
  -H "$AUTH" \
  --data-urlencode "market=a_share" \
  --data-urlencode "universe=csi300" \
  --data-urlencode "loop_n=3" \
  --data-urlencode "direction=动量反转类因子" \
  --data-urlencode "data_source=" \
  -w "\nHTTP %{http_code}\n"
```

**参数说明**：
| 参数 | 取值 | 说明 |
|---|---|---|
| `market` | `a_share` / `crypto` / `hong_kong` / `us_stock` | 市场 |
| `universe` | `csi300` / `csi500` / `csi1000` / `sse50` / `gem` / `star` / `csi800` / `all_a` | 股票池 |
| `loop_n` | 1~20（默认 3） | 演化轮数，越大越深入但耗时越长 |
| `direction` | 任意文本 | 挖掘方向/假设，如"动量反转"、"低波动"、"资金流异动" |
| `data_source` | `qlib_bin` / `parquet` / `pg` / 空 | 数据源（留空用默认） |

**返回**：`task_id` + 市场信息。之后用 task_id 轮询进度。

## 3. 查看演化任务进度

```bash
# 任务状态
curl -s -H "$AUTH" "$BASE/api/v1/alpha-agent/tasks/{task_id}"

# 实时日志
curl -s -H "$AUTH" "$BASE/api/v1/alpha-agent/tasks/{task_id}/log"

# 取消任务
curl -s -X POST -H "$AUTH" "$BASE/api/v1/alpha-agent/tasks/{task_id}/cancel"
```

**任务状态机**：`pending → running → backtesting → completed`（或 `failed`）

## 4. 查看挖掘出的因子

```bash
# 因子列表（全部）
curl -s -H "$AUTH" "$BASE/api/v1/alpha-agent/factors"

# 因子详情
curl -s -H "$AUTH" "$BASE/api/v1/alpha-agent/factors/{factor_id}"

# 因子解释（AI 解读因子逻辑）
curl -s -X POST -H "$AUTH" "$BASE/api/v1/alpha-agent/factors/{factor_id}/explain"

# 因子回测
curl -s -X POST -H "$AUTH" "$BASE/api/v1/alpha-agent/factors/{factor_id}/backtest" \
  --data-urlencode "start=2024-01-01" \
  --data-urlencode "end=2025-12-31"

# 因子导出（加入生产特征库）
curl -s -X POST -H "$AUTH" "$BASE/api/v1/alpha-agent/factors/{factor_id}/export"

# 全局统计
curl -s -H "$AUTH" "$BASE/api/v1/alpha-agent/stats"
# 返回: total/completed/pending/backtesting/failed + avg_ic/avg_sharpe/best_ic/best_sharpe

# 数据覆盖摘要（启动前确认）
curl -s -H "$AUTH" "$BASE/api/v1/alpha-agent/data-summary"
```

## 4.1 RD-Agent 轻量验证（`/rd-agent`）

RD-Agent 因子挖掘后，可用轻量端点快速验证因子 IC/夏普（不启动完整演化）：
```bash
# 因子列表（RD-Agent 已验证）
curl -s -H "$AUTH" "$BASE/api/v1/rd-agent/factors"
# 因子详情
curl -s -H "$AUTH" "$BASE/api/v1/rd-agent/factors/{factor_id}"
# 因子回测（轻量 IC/夏普）
curl -s -X POST -H "$AUTH" -H "$CT" "$BASE/api/v1/rd-agent/factors/{factor_id}/backtest" \
  -d '{"start":"2024-01-01","end":"2025-12-31"}'
# 全局统计
curl -s -H "$AUTH" "$BASE/api/v1/rd-agent/stats"
```

## 5. 实战流程

当用户要求"挖新因子"时按此流程：

1. **查池与类别**：`/universes` + `/factor-categories` 了解可选范围
2. **确认数据健康**：`/alpha-agent/data-summary` 看数据覆盖
3. **启动演化**：`/evolve` 选 universe + direction（如"低换手率高动量"）
4. **轮询进度**：`/tasks/{id}` 每 30s 查一次，completed 后停
5. **查看因子**：`/factors` 筛选 IC/Sharpe 高的
6. **解释 + 回测**：对高分因子 explain + backtest
7. **导出**：确认有效后 export 加入生产特征库

## 6. 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| 412 API Key 未配置 | 缺 LLM Key | 配 `AI_IDE_LLM_API_KEY` 后重启 |
| 400 Unknown market | market 参数错 | 用 `/markets` 查可用值 |
| 400 Unknown universe | universe 参数错 | 用 `/universes` 查可用值 |
| 任务一直 pending | 队列繁忙 | 查 `/tasks` 看并发任务 |
| 因子数为 0 | 无完成演化 | 先启动 evolve 并等 completed |
