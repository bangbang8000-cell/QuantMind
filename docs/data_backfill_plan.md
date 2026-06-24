# PG 历史数据回填方案

> 状态：**已执行（2026-06-24）**
> 范围：`stock_daily_latest` 表回填 2016-01 ~ 2025-12 历史数据

---

## 1. 问题背景

### 1.1 现象
- 投研平台 K 线只能看 60 天 ≈ 全 2026 年
- 风险评分卡只能对最新日打分
- 模型训练用 parquet 文件能跑 11 年（2016-2026）

### 1.2 真相

数据资产分布：

| 资产 | 时间范围 | 用途 | 状态 |
|------|----------|------|------|
| `stock_daily_latest` (PG) | 2026-01 ~ 2026-06 | K 线 / 风险评分 / 投研页 | ❌ 只有 2026 |
| `/app/db/feature_snapshots/model_features_{YYYY}.parquet` | 2016 ~ 2026 (13 GB) | 模型训练 | ✅ 完整 |
| Qlib bin (`/app/db/qlib/qlib_cn/`) | — | 回测 | ❌ 完全空 |

数据有，只是没有打通到 PG。

---

## 2. 决策

**方案 B：核心列回填 PG**（不是全部 194 列）。

| 候选方案 | 否决理由 |
|---------|---------|
| A. parquet 194 列全部塞 PG | PG 体积 30 GB，备份重，列频繁更新会重写 |
| **B. 36 直接映射 + 4 派生列** | ✅ 5 GB，前端零改动，K 线和评分立即可用 |
| C. 双源查询（PG + parquet 路由） | 双源同步债务高 |
| D. 转 Qlib bin | 训练好，但投研页要重写 |

**回填范围**：2016-01 ~ 2025-12（10 年，约 1000 万行）

---

## 3. Schema 映射（parquet → PG）

### 直接映射（36 列）
| parquet | PG | 说明 |
|---------|-----|------|
| symbol / trade_date | symbol / trade_date | 主键 |
| open / high / low / close / volume | 同名 | OHLCV |
| factor | adj_factor | 复权因子 |
| mom_ret_{1,3,5,10,20,60}d | return_{1,3,5,10,20,60}d | 收益序列 |
| mom_ma_gap_{5,10,20} | ma_gap_{5,10,20} | 均线偏离 |
| mom_macd_hist / mom_rsi_14 / mom_rsi_6 / kdj_k | macd_hist / rsi_14 / rsi_6 / kdj_k | 技术指标 |
| vol_atr_14 / vol_std_{5,20,60} | 同名 | 波动率 |
| style_bp / style_ep_ttm / style_ln_mv_total / style_beta_20 | bp / ep_ttm / ln_mv_total / beta_20 | 风格因子 |
| liq_volume_ratio_{5,20} | volume_ratio_{5,20} | 量比 |
| liq_volume_ma_5 / liq_amount_ma_5 | volume_ma_5 / amount_ma_5 | 量能均线 |
| liq_turnover_os | turnover_rate | 换手率 |
| flow_net_amount / flow_pressure_index | flow_net_amount / main_flow | 资金流 |

### 派生 5 列
| PG 列 | 派生公式 | 说明 |
|-------|----------|------|
| amount | parquet.liq_amount | 直接拷贝 |
| ma5 / ma10 / ma20 / ma60 | `close / (1 + mom_ma_gap_n)` | 因为 mom_ma_gap_n = (close-ma_n)/ma_n |
| pct_change | `mom_ret_1d * 100` | parquet 是小数，PG 是百分数 |

### NULL 列（无法回填）
- 基本面状态类：`is_st`、`listed_days`、`industry`、`stock_name`、`pe_ttm`、`pb`、`roe`、`profit_growth`、`inst_ownership`
- 指数标签：`idx_hs300`、`idx_zz1000`、`idx_chinext`、`idx_margin`、`idx_all`
- 概念标签：所有 `concept_*` 列
- 不可派生指标：`consecutive_limit_up_days`、`amount_ma_5`

这些列在**当前 PG 数据里也基本是 NULL**，不影响 K 线和评分卡（评分卡按字段缺失安全降级）。

---

## 4. 实施步骤

### 4.1 前置：创建 2016-2023 月度分区
PostgreSQL 分区表不会自动建子分区。回填前必须建好：

```bash
# 2016-01 ~ 2023-12 共 96 个月分区
docker exec quantmind-db psql -U quantmind -d quantmind -f /tmp/create_partitions.sql
```

`create_partitions.sql` 是个 DO 块，自动跳过已存在的分区。

### 4.2 跑回填脚本
```bash
# 后台跑（避免阻塞 session）
docker exec -d quantmind sh -c \
  "python /app/scripts/data_backfill/backfill_pg_from_parquet.py \
   --start-year 2016 --end-year 2025 > /tmp/backfill.log 2>&1"

# 看进度
docker exec quantmind tail -f /tmp/backfill.log
```

参数：
- `--limit-symbols N`：调试时只跑前 N 票
- `--dry-run`：只读取，不写 PG

### 4.3 性能基准
- 写入速率：~3400 行/秒（PG asyncpg + 5000 行/批 + ON CONFLICT DO NOTHING）
- 单年 70-130 万行 → 3-7 分钟/年
- **全 10 年总耗时：约 50 分钟**
- 磁盘占用：约 5 GB（PG 数据 + 索引）

---

## 5. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 分区缺失导致写入失败 | 前置 DO 块按月批量建；脚本本身用 ON CONFLICT，可重跑 |
| 写入中断 | 用 INSERT ... ON CONFLICT DO NOTHING，下次重跑跳过已存在行 |
| PG 体积爆涨影响生产 | 控制在 ~5 GB；只回填核心列；备份策略需要更新 |
| asyncpg result.rowcount 不准 | 已知问题：仍能正确写入；脚本日志的 inserted 计数器以"事务成功提交的批次大小"为准 |
| 部分行 v 字段是 NaN | Python 层 `v != v` 检测后置 None |

---

## 6. 验证

回填后必须做的：

### 6.1 行数核验
```sql
SELECT EXTRACT(YEAR FROM trade_date) AS yr, COUNT(*) AS rows
FROM stock_daily_latest GROUP BY yr ORDER BY yr;
```
预期：2016-2025 每年 70-130 万行 + 2026 ~60 万行

### 6.2 K 线接口测试
```python
from backend.services.api.routers.research_service import get_stock_kline
import asyncio
asyncio.run(get_stock_kline('600519.SH', 250))   # 茅台一年
# 期望：拿到 250 条 K 线，跨越多个年份
```

### 6.3 历史风险评分测试
```python
from datetime import date
from backend.services.api.risk_scoring import compute_risk_score
import asyncio
asyncio.run(compute_risk_score('600519.SH', date(2020, 3, 16)))
# 期望：能拿到当时的评分（不是 no_data）
```

### 6.4 抽样数据质量
- close > 0 ✓
- volume > 0 ✓
- return_5d 在 (-1, 1) 范围内（极值除外）✓
- adj_factor > 0 ✓
- 不应有重复 (trade_date, symbol) 主键

---

## 7. 后续

### 7.1 日常增量
现有 `backend/scripts/daily_data_sync.py` 已经把新数据写到 `stock_daily_latest`。本次回填只是补足历史，**不影响每日增量**。

### 7.2 缺失字段补回
基本面字段（is_st、listed_days、industry、pe_ttm 等）目前 NULL，可以单独写一个补回脚本：从 baostock / akshare 拉历史快照覆盖。**优先级低**，因为 K 线和评分卡已经够用。

### 7.3 Qlib bin 生成
如果以后要回测，需要把 parquet 转 Qlib bin 格式。跟本次回填**互不依赖**，独立任务。

---

## 8. 相关文件

| 文件 | 作用 |
|------|------|
| `scripts/data_backfill/backfill_pg_from_parquet.py` | 主回填脚本 |
| `/tmp/create_partitions.sql`（一次性）| 建 2016-2023 月分区的 DO 块 |
| `config/features/model_training_feature_catalog_v1.json` | 特征 catalog（与本次回填无关，但是 parquet 列定义来源） |
