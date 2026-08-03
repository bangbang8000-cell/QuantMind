# R3 / R4 / R5 实施规划（细化）

> R1、R2 已完成并验收。本文档细化剩余三阶段的落地方案。
> 每条都锚定到已核实的代码位置，不做假设。

---

## R3 — 手动模式（逐笔勾选 + 改数量）

### 已确认的交互决策

| 决策项 | 选定方案 | 理由 |
|---|---|---|
| 止损卖出 | **纳入提案表但强制执行**，勾选框置灰、标「风控·强制执行」 | 止损是风控不该由用户关掉；但必须让用户看见它发生了。也避免"反复取消止损"让回放偏乐观 |
| 改数量边界 | **只能调小或取消，不能调大** | 保证不超出策略算出的风险敞口；超出报 `EXCEED_PROPOSED_QTY` |

### 现状锚点

| 事实 | 位置 |
|---|---|
| `pending_orders` JSONB 字段已存在，**代码零读取** | `models/replay.py:110` |
| `auto_trade` Boolean 已存在，`CreateSessionRequest` 描述写着「S1 仅支持自动交易」 | `router.py:57` |
| `approved_orders` 通路已存在，但 `_build_orders` 分支**完全不校验** | `day_runner.py:296-321` |
| `StepRequest.approved_orders` 描述「S1 暂不使用」 | `router.py:61-65` |
| `ReplayStatus` 无 `awaiting_confirm` 状态 | `models/replay.py:55-62` |
| `OrderOrigin.MANUAL` 已存在 | `models/replay.py:65-68` |

### 关键缺陷（必须在 R3 修）

`_build_orders` 的 manual 分支照抄用户输入：
- 不做整手取整 → 可下 137 股这种不合法数量
- 不校验标的是否在提案内 → 用户可凭空构造任意标的的委托
- 不校验方向合理性 → 可对无持仓标的下卖单
- 数量为 0 或负数也会进入撮合

### 实现

**1. 状态机扩展** `models/replay.py`
- `ReplayStatus` 新增 `AWAITING_CONFIRM = "awaiting_confirm"`
- 流转：`ready --propose--> awaiting_confirm --step(confirmed)--> ready|finished`
- `awaiting_confirm` 下再次 propose → 直接返回已存的 `pending_orders`（幂等，不重算）

**2. `day_runner` 拆分**
- 抽出 `propose_day(...) -> ProposalResult`：跑到「算出 orders」为止，**不撮合不落库**
  - 复用现有 `_run_stop_loss` 之前的全部步骤（unlock / load signals / load bars）
  - ⚠️ 止损扫描是否纳入提案：**纳入但标记 `origin=stop_loss` 且不可取消**
    （止损是风控，不该由用户勾掉；但要让用户看见）
  - 返回每笔提案：`symbol / side / quantity / est_price / reason / origin / cancellable`
    买入附 `est_amount`，卖出附 `avg_cost` / `est_pnl`（让用户带着盈亏信息决策）
- `execute_day(confirmed)`：按确认清单撮合
- `run_day` 保留为 `propose + execute` 的组合（auto 模式不变，向后兼容）

**3. 服务端复校验**（不信前端）`_validate_confirmed()`
按顺序校验，任一不过则该笔进 `rejected` 并给出原因码：
- `NOT_IN_PROPOSAL` — 标的不在 `pending_orders` 内
- `SIDE_MISMATCH` — 方向与提案不符
- `INVALID_QUANTITY` — ≤0 或非整手（按 `lot_size` 取整，卖出允许零头清仓）
- `EXCEED_PROPOSED_QTY` — 数量超过提案数量（允许调小，不允许调大）
- `INSUFFICIENT_AVAILABLE` — 卖出超可卖量
- `INSUFFICIENT_CASH` — 买入总额超可用现金（按 score 序累计校验）
- 止损笔若被用户剔除 → 强制加回

**4. API**
- `POST /sessions/{id}/propose` → `ProposalResponse`
  - `auto_trade=true` 时返回 400（自动模式无需提案）
  - 写 `pending_orders`，状态置 `awaiting_confirm`
- `POST /sessions/{id}/step` 扩展 `StepRequest`：
  - `confirmed: list[ConfirmedOrder] | None`
  - `skip: bool = False`
  - 路由逻辑：
    - `auto_trade=true` → 原行为（忽略 confirmed）
    - `auto_trade=false` + 状态 `ready` + 无 confirmed → 400「请先调用 /propose」
    - `auto_trade=false` + 状态 `awaiting_confirm` + 有 confirmed → 校验后执行
    - `skip=true` → 只 mark-to-market + 写快照 + 推进游标（不下单）
- 清空 `pending_orders`（执行或跳过后）

**5. 前端** `ReplayPage`
- 提案表：勾选框 / 数量可编辑（step=lot_size）/ 全选 / 全不选
- 卖出行显示 `avg_cost` 和 `est_pnl`（红绿着色）
- 止损行标记「风控·不可取消」且勾选框禁用
- 底部：`确认执行 N 笔`（显示预计动用资金）/ `跳过今日`
- 服务端拒绝时逐行显示原因

### 验收
- 改数量（调小）生效；调大被拒 `EXCEED_PROPOSED_QTY`
- 取消单笔生效；取消止损笔被强制加回
- 构造不在提案内的标的 → `NOT_IN_PROPOSAL`
- 非整手数量 → 自动取整或拒绝
- 买入超现金 → `INSUFFICIENT_CASH`
- `skip=true` 游标正常推进且当日无成交
- auto 模式行为与 R2 完全一致（回归）

---

## R4 — 统计报告

### 复用锚点（已核实签名）

| 函数 | 位置 | 入参语义 |
|---|---|---|
| `_max_drawdown(cumulative_returns)` | `backtest_service.py:43` | **累计收益率序列**（非净值），返回相对回撤 |
| `_annualized_sharpe(returns, sample_interval, holding_days)` | `backtest_service.py:89` | 逐日连续时传 `(1,1)` → lag=0 退化为标准夏普 |
| `_newey_west_t_stat(series, lag)` | `backtest_service.py:58` | Bartlett 核校正 |

数据源（R1 已备齐）：
- `replay_equity_snapshots`：逐日 `total_asset/day_pnl/cum_pnl/realized_pnl_cum/unrealized_pnl/positions`
- `replay_trades`：逐笔 `realized_pnl/avg_cost_before/holding_days/total_fee/origin`

### 新建 `replay/analytics.py`（纯计算，无副作用，目标 ≤400 行）

**核心指标**
- 总收益率 = `(final_total_asset - initial_cash) / initial_cash`
- 年化收益 = `(1+总收益)^(252/交易日数) - 1`
- 夏普 / 索提诺（下行标准差）
- 最大回撤（复用）+ 回撤区间起止日 + 修复天数
- 卡玛比 = 年化 / |最大回撤|
- 年化波动率 = `日收益std × sqrt(252)`
- 胜率 = 盈利卖出笔数 / 总卖出笔数
- 盈亏比 = 平均盈利 / |平均亏损|
- 期望 = 胜率×平均盈利 − (1−胜率)×|平均亏损|
- 换手率 = `Σ成交额 / (平均总资产 × 交易日数)` 年化
- 总手续费 / 费用拖累 = 总费用 / 初始资金
- 交易笔数 / 平均持有天数
- 止损触发次数与止损总亏损（回放特有，很有价值）

**净值曲线** — 逐日 `date / total_asset / nav(归一) / day_return / cum_return / drawdown / cash_ratio`

**逐笔流水** — `replay_trades` 全字段 + 排序分页，卖出附 `realized_pnl` / `return_pct`

**个股归因** — 按 symbol 聚合：`总已实现盈亏 / 买入笔数 / 卖出笔数 / 胜负 / 平均持有天数 / 总费用 / 贡献占比`，按盈亏排序

**滚动指标** — 20 日滚动夏普 / 滚动波动率 / 月度收益热力图（`{year-month: return}`）

### API
- `GET /sessions/{id}/report` → 指标 + 净值曲线 + 滚动指标
- `GET /sessions/{id}/trades?page=&size=&sort=&side=` → 分页流水
- `GET /sessions/{id}/attribution` → 个股归因

全部走 `_load_owned_session` 归属校验。

### 前端 `ReplayReportPage`
- 指标卡片区（分组：收益 / 风险 / 交易）
- 净值 + 回撤双轴图（ECharts，回撤用水下面积图）
- 月度收益热力图
- 逐笔流水表（可排序、可筛选 side/origin、可导出 CSV）
- 个股归因表（盈亏红绿条形）
- 优先复用 `components/backtestCenter/` 的 `BasicRiskPanel` / `TradeStatsPanel`

### 验收（算术必须独立对账，不只测跑通）
- `sum(个股归因盈亏) == sum(trades.realized_pnl)` 差 <0.01
- `净值曲线末值 == final_total_asset`
- `cum_return 末值 == 总收益率`
- 手工构造已知序列验证夏普/回撤（如等差净值、单峰回撤）
- 与现有回测引擎同区间对比，回撤/夏普量级一致

---

## R5 — 自动推进（前端循环）

### 实现
- `useAutoAdvance(sessionId, opts)` hook
  - 4 档速度：慢 2000ms / 中 1000ms / 快 300ms / 极速 0
  - `state`: `idle | running | paused | error | done`
  - 串行调 `stepSession`，**上一次返回后才发下一次**（不能并发，服务端有 409 防连点）
  - 收到非 2xx 或 `result.error` → 立即 `error` 并停
  - `next_date == null` → `done`
  - 卸载时 abort（`useRef` 标记 + 检查）
- 逐日结果滚动列表：日期 / 成交数 / 当日收益率 / 累计（新行高亮淡入）
- 进度条 `sessions_done / sessions_total`
- 走完自动跳报告页（带 `?tab=report`）
- 手动模式下自动推进按钮禁用（需逐日确认，语义冲突）

### 验收
- 60 交易日跑完不掉步（`sessions_done == sessions_total`）
- 中途暂停→继续，游标不错乱、不重复执行同一天
- 单日报错立即停止并高亮该日
- 切换 tab / 卸载组件后循环真正停止（不再发请求）

---

## 实施顺序与工程约束

**R3 → R4 → R5**（R5 依赖 R3 的 step 语义稳定，R4 独立但报告页要能被 R5 跳转）

- 改动限定 `replay/` 目录 + `replay_*` 表
- `analytics.py` 从 `backtest_service` **import 复用**指标函数，不重写算法
- 每阶段配单测；R3 校验矩阵、R4 算术对账必须独立测试
- 新状态 `awaiting_confirm` 需同步 `db_init.sql` 注释（枚举存 VARCHAR，无需 DDL 迁移）
