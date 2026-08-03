# 时光回放 v2 实施规划

> 目标：把回放从「单日推演」升级为「选模型 → 推理 → 选策略 → 自动/手动步进 → 逐笔盈亏 → 回测级统计报告」的完整闭环。
>
> 状态：规划定稿，按 R1→R5 顺序推进。

## 一、设计决策（已确认）

| 决策项 | 选定方案 |
|---|---|
| 手动模式粒度 | 逐笔勾选 + 可改数量，服务端复校验 |
| 自动推进 | 前端循环调 `step`，4 档速度（慢2s/中1s/快0.3s/极速0），可暂停 |
| 报告深度 | 净值曲线+核心指标（基线）＋ 逐笔流水 ＋ 个股归因 ＋ 回撤/滚动指标；**不做基准对比** |
| 盈亏口径 | 移动加权平均成本（与券商对账口径一致），不做 FIFO 批次表 |

## 二、复用清单（不重造）

| 能力 | 复用对象 |
|---|---|
| 模型列表 | `GET /models/system-models`、`GET /models`；前端 `modelTrainingService.listSystemModels()/listUserModels()` |
| 模型元数据 | `metadata.json`：framework / feature_columns / train_start-end / metrics(train_ic,val_ic,test_ic,rank_icir) / target_horizon_days |
| 策略模板 | `strategy_templates/` 10 个模板 + `get_all_templates()` / `get_template_by_id()`；模板自带 `params[]`(name/default/min/max) → 前端自动渲染 |
| 指标算法 | `backtest_service.py`：`_max_drawdown()`、`_annualized_sharpe()`、`_newey_west_t_stat()` |
| 前端面板 | `components/backtestCenter/`：BasicRiskPanel / TradeStatsPanel / PerformancePanel / PositionPanel |

## 三、必修 bug（调研发现，共 9 个）

### 会让统计数字算错（R1 修）

| # | 位置 | 问题 | 后果 |
|---|---|---|---|
| 1 | `day_runner.py:551,574` | `cum_pnl` 基准是首日收盘而非 `initial_cash`，首日 `day_pnl` 恒 0 | 首日手续费+涨跌不计入 → 总收益系统性偏高 |
| 2 | `simulation_manager.py:97-101` | 持仓 `volume<=0.0001` 时整个 dict 被删，`cost` 永久丢失 | 清仓那笔 `realized_pnl` 算不出来 |
| 3 | `router.py:382-402` | `run_day` 返回 `error` 非空时仍推进游标、仍返回 200 | 静默跳过一天，曲线断档无提示 |
| 9 | `router.py:301,322,405` | `GET/{id}`、`step`、`DELETE` 不校验 tenant/user 归属 | 任意用户可操作他人会话 |

### 让回放失真（R2 修）

| # | 位置 | 问题 | 后果 |
|---|---|---|---|
| 4 | `rebalance_calculator.py:129-173` | `SignalScore` 无 `side` 属性 → 走「无方向」保守分支 | 跌停持仓不生成卖单，涨停也不买 |
| 5 | `rebalance_calculator.py:289` | 买单遍历 `set(target_symbols)` | 现金耗尽时拒单对象任意 → 不可复现 |
| 6 | `rebalance_calculator.py:205-237` | `max_position_pct` 与 `topk` 无交互 | topk=5+等权 → 每只0.2砍到0.15 → 25%永久空仓 |
| 7 | `rebalance_calculator.py:30` | `min_score` 定义了但全代码从不读取 | 死配置，前端做了也没用 |
| 8 | `day_runner.py:102`、`ashare_matcher.py:19-23` | `MatchConfig(price_mode="open")` 硬编码，滑点/费率是模块常量 | 撮合参数无法按 session 配置 |

## 四、五个阶段

### R1 — 口径修正 + 盈亏归因地基

**DDL**
- `replay_trades` 增：`avg_cost_before FLOAT NULL`、`realized_pnl FLOAT NULL`、`holding_days INT NULL`
- `replay_equity_snapshots` 增：`realized_pnl_cum FLOAT DEFAULT 0`、`unrealized_pnl FLOAT DEFAULT 0`
- 全部 nullable / 带默认值，老会话不破

**代码**
- 修 bug 1：`_write_snapshot()` 首日以 `initial_cash` 为基准
- 修 bug 2：`_persist_fill()` 在卖出撮合**前**抓 `cost` 落 `avg_cost_before`；`realized_pnl = (price - avg_cost) * qty - total_fee`
- 修 bug 3：`error` 非空 → 不推进游标，返回明确错误
- 修 bug 9：三个端点加归属校验
- 持仓补 `first_buy_date` → 算 `holding_days`

**验收**
- `sum(realized_pnl) + unrealized_pnl == cum_pnl`（误差 < 0.01）
- `cum_pnl` 末值 == `total_asset - initial_cash`
- 清仓交易的 `realized_pnl` 非空

### R2 — 模型/策略接线（含 bug 4-8）

**后端**
- 新增 `GET /replay/strategy-templates` — 薄封装 `get_all_templates()`，做 Qlib 口径 → replay 6 key 参数映射
- 修 bug 4：replay 侧显式传 side（持仓票=SELL 候选，信号票=BUY 候选）
- 修 bug 5：买单按 score 降序遍历
- 修 bug 6：权重砍削后重新归一
- 修 bug 7：`min_score` 真正生效
- 修 bug 8：`price_mode`/滑点/费率纳入 `strategy_params`
- `SessionResponse` 补 `strategy_params` 字段（现在不返回）
- `model_id` 创建时校验存在性（现在要等后台 FAILED 才暴露）

**前端**
- `CreateSessionForm` 改分步：① 选模型（含 IC 指标展示）→ ② 选策略模板（params[] 自动渲染可调参）→ ③ 区间/资金/止损 → ④ 自动或手动

**验收**：两个不同模型 × 两套策略参数 → `replay_signals` 分数不同、调仓结果不同

### R3 — 手动模式

**后端**
- `day_runner` 拆 `propose_day()`（算提案不落单）/ `execute_day(confirmed)`
- 新增 `POST /sessions/{id}/propose` — 返回提案数组，写 `pending_orders`，状态 `awaiting_confirm`
- `POST /step` 扩展：`confirmed: [{symbol,side,quantity}] | null`、`skip: bool`
  - `auto_trade=true` → 原行为
  - `auto_trade=false` 无 confirmed → 返回提案等确认
  - 带 confirmed → 按清单执行，**服务端重新校验**资金/整手/涨跌停/可卖量
- 新增状态 `awaiting_confirm`

**前端**：提案表（勾选框+数量可编辑+全选/全不选）、确认执行、跳过今日

**验收**：改数量/取消单笔生效；超资金被服务端拒绝

### R4 — 统计报告

**后端** `replay/analytics.py`（预计 350-400 行，纯计算无副作用）
- import 复用 `_max_drawdown` / `_annualized_sharpe`
- 核心指标：总收益、年化、夏普、索提诺、最大回撤、卡玛、波动率、胜率、盈亏比、换手率、交易笔数
- 净值曲线：日期/总资产/日收益/回撤（水下图）
- 逐笔流水：join `replay_trades` 含 `realized_pnl`
- 个股归因：按 symbol 聚合总盈亏/胜负/持有天数/贡献度排名
- 滚动指标：20日滚动夏普/波动率、月度收益热力图
- 三端点：`GET /sessions/{id}/report`、`/trades`（分页+排序）、`/attribution`

**前端** `ReplayReportPage`：指标卡片 + 净值/回撤双轴图 + 月度热力图 + 流水表 + 归因表（优先复用 backtestCenter 组件）

**验收**：与现有回测同区间同参数对比，夏普/回撤量级一致；`sum(个股盈亏) == 总已实现盈亏`

### R5 — 自动推进

- 前端 `useAutoAdvance` hook：4 档速度循环调 `step`，可暂停/继续
- 单日报错立即停止并高亮
- 进度条 + 逐日结果滚动列表
- 走完自动跳报告页

**验收**：60 天区间不掉步；中途暂停/继续游标不错乱

## 五、工程约束

- **不碰实盘/模拟盘链路**：改动限定 `replay/` 目录 + `replay_*` 表；Redis 前缀仍 `replay:account:{session_id}`
- **DDL 增量**：`db_init.sql` 同步；新字段 nullable 或带默认值
- **测试**：每阶段配单测；R1/R4 算术必须有独立对账测试（不只测"跑通"）
- **文件大小**：`analytics.py` ≤400 行；`day_runner.py` 拆分后各 ≤400 行
- **共享组件谨慎改**：`rebalance_calculator.py` 与实盘共用 → bug 4-7 的修改必须保持实盘路径行为不变（用参数开关或不改默认值），并有回归测试
