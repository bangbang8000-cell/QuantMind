# QuantDB 全量数据 · 单股全方位分析框架设计

> 设计目标：给定任意 A 股，把 QuantDB 能提供的**全部**证据维度组织成一份可复现、可证伪的深度分析。
> 原则：**每一层都有数据端点 + 具体字段 + 明确的分析问题**，拒绝"用大而全的数据做泛泛之谈"。

## 数据 → 问题映射（7 层金字塔）

| 层 | 数据来源（端点/parquet） | 回答的核心问题 |
|---|---|---|
| L0 市场环境 | `/selection/daily` market_state、`index_daily` 大盘 MA20 | 现在是牛还是熊？仓位该多少？ |
| L1 估值 | `valuation`（pe_ttm/pb/ps/dividend_rate）、`instrument_detail`（行业/ST/市值） | 贵不贵？相对行业、相对自身历史处在什么位置？ |
| L2 财务 | `income`/`balance`/`cashflow`/`pershare_index`/`holder_num` | 赚钱吗？真金白银还是纸面利润？资产负债表健康吗？ |
| L3 技术 | `technical_indicators`（37 列全量）+ `daily_forward` K 线 | 趋势、动能、支撑压力、量价是否配合？ |
| L4 资金筹码 | `l2_factors` flow_*/chip_*、`margin_trading` 融资融券 | 谁在买谁在卖？主力还是散户？筹码松动还是集中？ |
| L5 行业概念 | `l1_factors` ind_*/concept_*、`sector_concept`、`index_weights` | 所处行业强不强？概念热不热？轮动到了没有？ |
| L6 模型信号 | `/models/inference/stock/{symbol}/history`（可按 model_id 分模型） | 模型怎么看？多模型是否一致？趋势是改善还是恶化？ |
| L7 新闻舆情 | `/news/articles`（tickers+industries+sentiment+event_tags） | 消息面是催化剂还是风险？与量价/模型信号互相印证？ |

## 分析深度规范（每层的具体做法）

### L0 市场环境（先于一切）
- `/selection/daily` 的 `market_state`：牛/熊 + 建议仓位（熊市空仓正常，报告必须说明）
- `index_daily` 上证综指（000001.SH）收盘 vs MA20：`MA20 之上 + 仓位>0` 才支持做多；**个股再强也受大盘拖累**
- `meta.total_signals`、强行业数 → 市场宽度

### L1 估值（三维对照，缺一不可）
1. **绝对水平**：pe_ttm / pb / ps_ttm 当前值，负 PE 或无盈利 → 用 PB/PS
2. **行业相对**：`ind_relative_pe`（l1 因子，<1 = 相对行业折价）
3. **历史分位**：拉 valuation 近 3-5 年序列，算当前 PE 的历史百分位（**估值贵不贵只看当前值没有意义**）
- 输出一句话：`PE 23.1x = 近 5 年 18% 分位，行业相对 0.72 → 估值不构成风险`

### L2 财务（三表联动，防"纸面利润"）
- **利润质量**：income `net_profit` vs cashflow `net_cash_flows_oper_act`（连续 2 期经营现金流 < 净利润 → 红牌）
- **资产负债表**：balance 应收+存货增速 vs 营收增速（应收暴增 = 压货）；商誉/净资产 > 30% → 减值风险
- **股东行为**：`holder_num` 股东户数趋势（户数降 = 筹码集中，升 = 派发）
- **ROE 拆解**：净利率 × 周转 × 杠杆，哪个驱动
- 财务数据是季频：看最近 4-8 个季度趋势，不是单期

### L3 技术（分层递进，不堆指标）
- **趋势层**：MA5/10/20/60 排列（多头/空头/粘合），价格在均线系统的位置
- **动能层**：MACD（dif/dea/hist 方向+柱状收敛还是放大）、RSI 6/14（超买超卖+背离）、KDJ
- **波动层**：`vol_atr_14`、`vol_std_60`、`beta_20`（beta 高 = 大盘放大镜，L0 结论要加重）
- **量价层**：`vol_to_ma5/20`、`volume_trend_3d`（放量上涨 vs 缩量反弹）
- 输出：趋势方向 + 动能状态 + 关键价位（支撑/压力，来自 K 线近期高低点）

### L4 资金筹码（多口径交叉，防单一口径误导）
- **分单口径**：`flow_super_net`（超大单）/`flow_large_net`（大单）/`flow_small_net`（散户）——三口径同向才可信
- **全口径**：`flow_net` + `flow_net_ratio`（净流入占成交比）
- **持续性**：`flow_consistency`、5 日/20 日累计净流入方向
- **筹码**：`chip_profit_ratio_20/60`（获利盘比例）、`chip_concentration_20`（集中度）、`chip_peak_distance`（离成本峰距离）、`chip_cost_90_width`（成本区间宽度）、`chip_profit_delta_5`（5 日获利盘变化——散户接盘还是主力吸筹）
- **融资融券**：margin_trading `finance_net` 融资净买入趋势（杠杆资金态度）
- 经典背离：**股价涨 + 大单净流出 + 获利盘快速上升 = 散户接盘主力派发**（本次 300750 报告就是靠这个看穿的）

### L5 行业概念（个股强 ≠ 行业强）
- `ind_strength_20/60`（行业动量强度）、`ind_rotation_speed_20`（轮动速度）、`ind_crowding_20`（拥挤度——太热要警惕）
- `ind_breadth_up_20`（行业上涨家数占比，宽度）、`ind_netflow_rank_20`（行业资金流排名）
- 概念：`concept_hot_score`（热度）、`concept_momentum_top3`（动量）、`concept_leader_score`（龙头分）、`concept_crowding_max`（拥挤）
- 结论要区分：**行业强 + 个股强**（共振，最理想）/ 行业弱 + 个股强（逆势，持续性存疑）/ 行业强 + 个股弱（掉队）
- `index_weights`：该股在沪深300/中证500 的权重变化（被动资金流入流出）

### L6 模型信号（多模型，不只看一个）
- **默认模型**：`/models/default` 拿 default model，`history?days=180` 拉默认模型序列
- **全部模型**：`/models` 拿模型列表（含 ensemble 融合模型），**用 `model_id` 参数逐个拉 `history`**——不同模型是独立视角（不同训练期/周期 T3/T10/T15/融合），比较：
  1. **共识度**：多模型同方向 = 高置信；分歧 = 报告单独说明
  2. **趋势**：每个模型序列自身是上升/回落/横盘（分数绝对值小不代表无意义，看**变化方向**）
  3. **极值**：分数处于该模型历史序列的什么位置（z-score/分位）
- `signal_side`（BUY/HOLD/SELL）是模型当时的操作信号，与 fusion_score 并列引用
- **模型与量价/资金背离时**：这是最值钱的信号（如基本面好但模型 4 个月 SELL = 边际改善未被确认）
- 排名 `score_rank` 是该股在当天批次内的截面排名（越小越靠前）

### L7 新闻舆情（催化剂 vs 印证）
- `tickers={code}` 个股新闻 + `industries={行业}` 行业新闻（个股没新闻不代表行业没新闻）
- `sentiment=bullish|bearish|neutral` 分类统计 + `strong_only=true` 强信号（|score|>=0.5）
- `event_tags` 事件标签（并购/财报/解禁/政策）——事件型新闻要找**后续数据印证**（公告增持 → 查资金流是否真流入）
- 排序：`sort=sentiment_bullish` / `sentiment_bearish` 快速定位最强多空新闻
- **无新闻处理**：明确标注 `[数据缺失]` 并提醒加 RSS 源；**禁止编造新闻**
- 新闻的价值排序：**政策 > 公司重大事件 > 行业动态 > 分析师观点 > 市场情绪文**

## 跨层印证矩阵（设计的灵魂：不孤立看任何一层）

| 组合 | 印证逻辑 | 典型结论 |
|---|---|---|
| L6 模型↑ + L4 大单流入 + L3 突破 | 三重共振 | 高置信做多信号 |
| L2 财务好 + L6 模型持续 SELL + L4 流出 | 好公司≠好买点 | 等待确认，不追 |
| L1 估值低 + L5 行业弱 | 价值陷阱风险 | 低有低的理由 |
| L3 放量长阴 + L4 大单流出 + L7 有利空新闻 | 事件驱动下跌 | 看承接力 |
| L4 获利盘↑ + 大单流出 + 股价涨 | 派发结构 | 警惕 |
| L5 概念拥挤 + L3 RSI 超买 | 情绪顶点风险 | 减仓区 |

## 报告结论结构（推荐）

1. **一句话结论**：评级 + 核心逻辑（好公司/好价格/好时机三问）
2. **多空证据表**：按 L1-L7 逐层列多方/空方证据（每条带数值）
3. **模型共识度**：多模型方向分布 + 趋势 + 与结论是否一致
4. **关键观察**：跨层印证矩阵中命中的组合
5. **风险清单**：风险评分卡（`/risk/score`）+ veto 项 + 上述各层风险点
6. **行动建议**：分持仓状态（已持仓/未持仓）+ 触发条件（价位/信号阈值）

## 落地端点速查

```bash
# L0: 市场状态（market_state 含牛熊+仓位建议）
curl -s -H "$AUTH" "$BASE/api/v1/selection/daily"
# L0: 大盘 MA20（000001.SH 上证综指）
curl -s -H "$AUTH" "$BASE/api/v1/market/index-kline?symbol=000001.SH&days=60"
# L1-L5: 371 维特征一次拿全（valuation/technical/l1/l2 聚合）
curl -s -H "$AUTH" "$BASE/api/v1/research/features/600519.SH"
# L1 补充: 估值历史分位（parquet 直读）
docker exec quantmind python -c "
import pandas as pd
df = pd.read_parquet('/data/quantdb/5_technical_derived/valuation/dt=20260815/data.parquet')  # 或按分区目录
"
# L2 补充: 财务季报（income/balance/cashflow per-symbol flat）
#   /data/quantdb/3_financial_data/income/600519.SH.parquet
# L4 补充: 融资融券
#   /data/quantdb/2_base_sector/margin_trading/（Hive 分区）
# L6: 模型信号（默认模型 / 指定模型）
curl -s -H "$AUTH" "$BASE/api/v1/models/default"
curl -s -H "$AUTH" "$BASE/api/v1/models"                      # 全部模型含 ensemble
curl -s -H "$AUTH" "$BASE/api/v1/models/inference/stock/600519.SH/history?days=180&model_id=xxx"
# L7: 新闻（个股+行业双通道）
curl -s -H "$AUTH" "$BASE/api/v1/news/articles?tickers=600519&industries=白酒&limit=30&strong_only=true"
curl -s -H "$AUTH" "$BASE/api/v1/news/articles?tickers=600519&sort=sentiment_bullish&limit=10"
```

## 复杂度分级（智能体按需选择深度）

| 级别 | 用时 | 适用场景 |
|---|---|---|
| 快速体检 | 1-2 min | 用户只问"怎么样"：L0+L1+L3+L6 默认模型 |
| 标准分析 | 3-5 min | 日常投研：全部 7 层，L6 拉默认+融合 |
| 深度尽调 | 10+ min | 用户明确要"全方位"：全部 7 层 + L6 全模型逐拉 + 财务三表 + 历史分位 |
