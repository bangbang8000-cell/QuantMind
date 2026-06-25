# QuantMind 系统审计与优化路线图 — 2026 Q3

> 创建日期：2026-06-25
> 审计基线：分支 `fix/rd-agent-quantbot-fixes` HEAD = `e37ddbe`
> 状态：**审计完成，待执行**

## 一、为什么有这份文档

经过两个 subagent 的彻底体检（Qlib 集成 + 数据质量），发现这套系统：
- **「基于 Qlib 的基座」是部分事实**：Qlib 实际含量 30-40%，主要用其 backtest 引擎和 D.features，但训练管道完全自研，标准 workflow（DatasetH / SignalRecord / qrun）主线不用
- **数据层有 4 个严重 bug**会污染训练，13 个其他级别问题
- **风险评分卡 v2 设计正确但底层数据脏**，所以"基本面"维度（10% 权重）目前是摆设

本文档为下次（不论是同一个 session 续作、还是新 session 接手）提供完整 context 和分阶段计划。

---

## 二、严重问题清单（按必须修复程度排序）

### 🔴 S 级（阻断性，不修则训练不可信）

| # | 问题 | 证据 | 影响 |
|---|------|------|------|
| **S-1** | 2016-2025 vs 2026 是两套不兼容的数据 | SH600519 2025-12-31 close=11948 / 600519.SH 2026-01-05 close=339（ratio 0.028）| 跨年特征全部失真 |
| **S-2** | `volume_ratio_5/_20` 单位漂移 100× | 2016-2025 均值 0.01（被错误 clip）/ 2026 均值 1.02 | 量价类模型/评分卡跨年直接失效 |
| **S-3** | 2026-06-22~24 数据严重不完整 | 06-22 茅台 volume=58k（应 ~3M）；06-23/24 只抓深市 | 风险评分对最近 3 天误判 |
| **S-3b** | **PG 2026-06-23~06-25 close 是非复权交易价（adj_factor=1）**，跟 5.6~6.22 的后复权价（adj_factor≈0.237）不连续 | 茅台 06-22 close=294 / 06-23 close=1222 | 最近 3 天所有特征/评分全错；新发现于 plan C 清洗后 |
| **S-4** | 4 个指数被混入个股表 | 000300.SH / 000852.SH / 000905.SH / 000906.SH / 399300.SZ；后者 return_5d=1039 | 横截面排序污染 |
| **S-5** | **2026 段 `prefix`/`suffix` 两个 symbol 格式同存** 且 5.6 起 prefix 行被错算（1011/5155 票 close 与 suffix 完全不同）| 万科 5.6 prefix close=8.31 / suffix close=4.01；平安银行 prefix 3.86 / suffix 11.0 | 训练数据 51% 重复 + 20% 错值 |

### 🟧 H 级（高，影响显著）

| # | 问题 | 影响 |
|---|------|------|
| **H-1** | 2016-2025 全表 14 个基本面字段 100% NULL（pe/pb/roe/total_mv/listed_days/concept_*/listing_market）| 评分卡基本面维度（10%权重）历史回测中是摆设；模型也学不到价值信号 |
| **H-2** | adj_factor 在 2016-2025 全部硬写为 1，但 close 已经被复权过 | close / adj_factor 推不出原始价 |
| **H-3** | 2026 parquet 内部 prefix + suffix 双格式同存，31.4 万对重复 key（51%）| groupby 重复加权污染；**最近几次训练用了这个 parquet** — ✅ 2026-06-25 已修（plan C）|
| **H-4** | parquet schema 2025→2026 漂移（新增 3 列 placeholder，删除 56 列；trade_date 类型变化）| 训练数据集合不一致 |

### 🟨 M 级（中）

| # | 问题 |
|---|------|
| M-1 | `pct_change` 是百分数 vs `return_*` 是小数，**差 100×**（喂模型时一视同仁就完蛋）|
| M-2 | `pct_change` 极端值未清洗（指数 100527%；BJ 股复权切换边界 14000-26000%）|
| M-3 | `vol_atr_14` 是绝对价位（茅台 7188 vs 仙股 0.05），横截面不可比 |
| M-4 | `vol_smile_20 / vol_term_structure / vol_of_vol / fund_pe_percentile / fund_pb_percentile` 是 placeholder 全 0 |

### ✅ 确认没问题的部分（重要：避免下次重复检查）

- 未来函数泄露：**没找到**（rv / rskew / qsp 等当日特征跟 ret_1d 相关性 |ρ| < 0.02）
- 时间对齐：无周末、无重复 PK（PG 段）、月度均匀、年交易日 242-244
- 同源一致性：PG vs parquet 同年同票数值末位完全一致
- listed_days：2026 段 茅台 9065 / 平安银行 12864 都准确

---

## 三、Qlib 集成实情

### 真在用
- `qlib.backtest`（包了 `safe_backtest` + `CnExchange` A 股专用 Exchange）
- `D.features` / `D.instruments`（strategy_lab、backtest、sync_investment_data）
- `qlib.contrib.strategy.signal_strategy`（`TopkDropoutStrategy` / `WeightStrategyBase`）

### 借用但非标准
- `qlib.contrib.model.pytorch_*_ts`：只当 PyTorch 模型壳，data 自己造

### 完全不用（dead code 或 0% 使用率）
- `DataHandlerLP / DatasetH / TSDatasetH / RecordTemp / SignalRecord`
- `qrun / R.start / task_train`（只在 rd-agent / alphaagent 子项目）
- `Alpha158Ext`（定义了，0 个 import）
- `backend/shared/backtest_engine/integration/qlib_adapter.py`

### 数据流向真相
```
GitHub release (qlib_bin.tar.gz)
  → db/qlib_data/ (Qlib bin)
  → sync_investment_data.py 用 D.features 读 OHLCV
  → PostgreSQL stock_daily_latest
  → daily_data_sync.py 用 baostock/akshare/eltdx 补
  → db/feature_snapshots/*.parquet ← 训练读这个，不经过 Qlib
  → docker/training/train.py → pred.pkl
  → Qlib backtest 用 pred.pkl 当信号 + Qlib bin 取价
```

**关键结论**：训练管道完全不经过 Qlib 数据层，Qlib 只在回测下游用，能力发挥了 1/3。

---

## 四、四阶段优化计划

### 🥇 Phase 1：修严重数据 bug（本周，2-3 天）

**目标**：让训练数据可信。不修就别再训练，否则模型建在脏数据上。

**Phase 1 进度（2026-06-25 更新）**

✅ **方案 C 已执行（`scripts/data_repair/cleanup_v3_plan_c.py`）**

- 用户决策：4.30 之前 parquet 数据**保留不动**（老标度，per-symbol 错缩放但内部连续），只清 5.6 之后段
- PG `stock_daily_latest`：
  - 删 5 个指数 ×2 格式 = 561 行（S-4）
  - 删 5.6 起所有 prefix 行（178,954 行）
  - 把 5.6 起 suffix 重命名为 prefix（193,484 行）
- Parquet `model_features_2026.parquet`：
  - 删 113 指数行
  - 删 5.6 起 130,086 prefix 行
  - 重命名 182,160 suffix → prefix
  - 保留 4.30 及之前 prefix 405,745 行不动
  - 备份在 `.before_cleanup_v3`

✅ **结果**：
- 2026 段 symbol 全部 prefix 一致，0 指数残留
- 5.6 起用新数据源（真复权价），4.30 前保留老标度
- 量级断层依然存在（设计如此 — 不影响训练，相对模式有效）

⚠️ **未解决（待 Phase 1 后续处理）**：

- **PG 2026-06-23~06-25 三天数据是第三种体系**：close=原始交易价（茅台 1222），adj_factor=1。
  跟 5.6~6.22 的新标度（茅台 ~294，adj_factor=0.237）不连续。
  根因：`daily_data_sync` 最近 3 天用了不同数据源（疑非复权接口）。
  影响：风险评分对最近 3 天数据完全误判。
  修法：要么重新跑 5.6 之后那套源补齐 6.23-25，要么把这 3 天标记 incomplete 排除。
- 2016-2025 段的 adj_factor 仍硬写 1（H-2）、volume_ratio 单位漂移（S-2）、跨年价格量级断裂（S-1）仍在。
  Plan C 没动 2016-2025 段。

剩余任务（按优先级，未完成）:

| 任务 | 工作量 | 优先级 | 状态 |
|------|--------|--------|------|
| 1.1 统一 2016-2025 vs 2026 的 symbol 格式（全 prefix 或全 suffix，选 prefix） | 1 hr | S-1 | ❌ 2026 已统一，2016-2025 段未动 |
| 1.2 重新计算 2016-2025 段的 `adj_factor`（用 parquet `factor` 字段，而不是硬写 1） | 2 hr | S-1 / H-2 | ❌ 未做 |
| 1.3 移除 PG 和 parquet 里的指数行（000300.SH 等 5 个） | 30 min | S-4 | ✅ **完成** |
| 1.4 重新计算 2016-2025 段 `volume_ratio_5/_20`（去除 clip，改用 `/` 而非 `-1`）| 1 hr | S-2 | ❌ 未做 |
| 1.5 dedup 2026 parquet 内部重复 key | 30 min | H-3 | ✅ **完成（保留 suffix → 重命名为 prefix）** |
| 1.6 修 6.23~24 沪市缺失 + **修 6.23~25 第三套标度问题** | 2-3 hr | S-3 | ❌ 新发现，待处理 |
| 1.7 单位规范化：把 `return_*` ×100 改成百分数与 `pct_change` 一致 | 2 hr | M-1 | ❌ 未做 |
| 1.8 跑数据质量验证脚本，确认所有 S/H 问题消除 | 1 hr | — | ❌ 未做 |

**产出**：
- `scripts/data_repair/unify_data_v3.py` 一次性修复脚本
- `docs/data_quality_report_post_fix.md` 修复后的质量报告
- 新的 git tag `data-v3.0`

**风险**：
- 修 adj_factor 后历史 close 量级会变 → **必须同步 invalidate 所有训练好的模型 pred.pkl**
- 改单位后所有模型要 retrain

### 🥈 Phase 2：补基本面数据（下周，3-5 天）

**目标**：让评分卡 v2 的"基本面"维度真正生效，模型学到价值信号。

| 任务 | 工作量 | 数据源 |
|------|--------|--------|
| 2.1 用 baostock 历史 query 回填 `pe_ttm / pb / roe / total_mv / float_mv` 2016-2025 | 2 天 | baostock (`query_history_k_data_plus` 含 PE/PB) |
| 2.2 补 `listed_days` 历史值（从上市日期推算） | 1 hr | baostock (`query_stock_basic`) |
| 2.3 补 `listing_market`（上交所/深交所/北交所/创业板/科创板） | 30 min | symbol 规则 + baostock |
| 2.4 补 `industry`（中信/申万行业分类）| 1 天 | akshare (`stock_board_industry_cons_em`) |
| 2.5 补 `idx_hs300 / idx_zz1000 / idx_chinext` 指数成分历史 | 1 天 | akshare 指数成分股月度快照 |
| 2.6 补北向资金流入历史（**新维度，超高 ROI**） | 1 天 | akshare (`stock_hsgt_hist_em`) |
| 2.7 补概念板块标签 | 跳过（噪音多） | — |

**产出**：
- `scripts/data_ingestion/backfill_fundamentals.py`
- 风险评分卡 v2 的"基本面"维度真正激活

**风险**：
- baostock 限流：约 200 req/min，5500 票 × 10 年 × 250 天 ≈ 1300 万次查询，可能要分片 1-2 天
- akshare 部分接口在历史数据上不完整，需要核对

### 🥉 Phase 3：评分卡接入信号链 + 回测 PK（再下周，2-3 天）

**目标**：知道评分卡到底有没有实际价值。

| 任务 | 工作量 |
|------|--------|
| 3.1 实现 `apply_risk_gate()` 函数（参考 `docs/risk_scorecard_phase4_plan.md`） | 4 hr |
| 3.2 修改 `fusion_rules.json`：`layer3_risk_gate.enabled=true`，policy=continuous_discount, alpha=0.01 | 30 min |
| 3.3 跑回测 PK：baseline (LGB top 50) vs treatment (LGB × risk_discount top 50) | 4-6 hr 机器时间 |
| 3.4 出验证报告：Sharpe / Calmar / 最大回撤 / 换手率对比 | 2 hr |
| 3.5 网格搜索 alpha ∈ {0.005, 0.008, 0.01, 0.012, 0.015} 找最优 | 8 hr 机器时间 |

**产出**：
- `docs/risk_scorecard_backtest_report.md` 含完整对比表 + 净值曲线
- 灰度上线 / 关闭功能的决策证据

**关闭条件**（Phase 3 视为完成）：
- Sharpe ≥ baseline + 0.1 **或** 最大回撤改善 ≥ 10%
- 否则**回滚**到只展示不打折

### 🏅 Phase 4：让 Qlib 真正发挥作用（更长远，2-3 周）

**目标**：把 Qlib 标准 workflow 真正接进来，让训练管道也走 Qlib。

| 任务 | 工作量 | 价值 |
|------|--------|------|
| 4.1 用 `DatasetH + DataHandlerLP` 替换自造训练数据管道 | 5-7 天 | ⭐⭐⭐ |
| 4.2 启用 `SignalRecord + PortAnaRecord` 标准化产物 | 2 天 | ⭐⭐⭐ |
| 4.3 接入 rd-agent（已在 repo 内）做自动因子挖掘 | 1 周（学习成本）| ⭐⭐⭐⭐ |
| 4.4 删除 Alpha158Ext / qlib_adapter 等 dead code | 30 min | ⭐ |
| 4.5 把生成 Qlib bin 列入 daily_data_sync 流程（让训练和回测共用一份数据）| 2 天 | ⭐⭐⭐⭐ |

**何时启动**：Phase 1-3 完成且回测 PK 验证评分卡有效之后。如果评分卡无效，Phase 4 优先级上升。

---

## 五、相关文档地图

| 文档 | 用途 |
|------|------|
| `docs/risk_scorecard_design.md` | 风险评分卡 v1 设计（5 维度） |
| `docs/risk_scorecard_design_v2.md` | v2 设计（6 维度 + 量价配合 + 过热） |
| `docs/risk_scorecard_v2_validation_report.md` | v2 正交性/单调性验证报告 |
| `docs/risk_scorecard_phase4_plan.md` | 接入 fusion pipeline 的方案（即本路线图的 Phase 3）|
| `docs/data_backfill_plan.md` | 2016-2025 PG 历史回填方案（已完成）|
| `scripts/data_backfill/backfill_pg_from_parquet.py` | 回填脚本（已跑过一遍）|
| `scripts/risk_scoring/validate_v2.py` | 评分卡正交性/单调性测试脚本 |
| `backend/tests/test_risk_scoring.py` | 53 单测 |

## 六、当前未 push 的 commit（5 个，待推私人仓库）

```
e37ddbe  feat(data):     PG 历史回填 2016-2025
dfb4c0c  feat(training): catalog truth source + 模型分类修复
e0db905  feat(risk):     风险评分卡 v2 全栈
b934d7d  fix(research):  K 线 symbol 格式匹配
d01af8e  ops(training):  训练容器资源保护
```

待用户给 PAT 加 `Administration: write` 权限后，执行：
```bash
gh repo create quantmind-private-v2 --private --description "..."
git remote add quantmind-private-v2 https://github.com/guge199205-byte/quantmind-private-v2.git
git push quantmind-private-v2 --all
git push quantmind-private-v2 --tags
```

## 七、决策原则与陷阱

### 已确认的原则
1. **单调性测试用 `future_vol` 比 `future_dd` 更可靠**：DD 是事件型方差大
2. **`volume_ratio_*` 字段已弃用**：用 `amount_ratio_5d` 现场算（评分卡 v2 已落地）
3. **风险评分必须支持历史 trade_date 参数**：否则用今天评估当年决策，幸存者偏差
4. **训练容器需要资源保护机制**：之前一次实际 OOM 把容器击杀（ExitCode 137）
5. **catalog `default_selected` 是 truth source**：前端不再硬编码 PRESET 列表

### 已知陷阱
- `vol_atr_14` 是绝对价位差，**用前必须 / close**
- `turnover_rate`、`pct_change` 是百分数（已 ×100），**不要再 ×100**
- `roe` 是小数（0.31 = 31%），跟 pct_change 单位不同
- parquet 里 symbol 是 suffix（600519.SH），PG 是 prefix（SH600519）—— 都用 `_norm_symbol_sql` 归一化
- asyncpg `result.rowcount` 在 executemany 上可能返回 -1，不能用它计数 insert
- asyncpg 不支持 `:param::date` 写法，要用 `cast(:param as date)`

## 八、参考：审计当天的实际 SQL 证据片段

```text
-- S-1 跨年标度断裂
SH600519 2025-12-31 close=11948.30 / 600519.SH 2026-01-05 close=338.80  ratio=0.0284

-- S-2 volume_ratio 单位漂移
2025: mean=0.0101 max=0.05    (被错误 clip 到 0.05)
2026: mean=1.02   max=5       (正常的当日/5日均比值)

-- S-3 数据不完整
2026-06-22 茅台 volume=58251   (正常 3M+)
2026-06-23 行数=1656 (深 1651 / 沪 5 / 北 0)
2026-06-24 行数=1644 (深 1640 / 沪 4 / 北 0)

-- S-4 指数混入
000906.SH ln_mv_total=38.84    (隐含市值 71 万亿，是指数)
399300.SZ pct_change=100527    return_5d=1039.87

-- H-1 基本面 100% NULL
pe_ttm / pb / roe / total_mv / concept_* / listed_days / listing_market:
  0 filled / 10.1M rows  (2016-2025 全部)

-- H-3 parquet 2026 内部重复
314,467 dup keys / 611,002 unique  (51% 重复)
```
