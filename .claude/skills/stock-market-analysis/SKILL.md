---
name: stock-market-analysis
description: "股票市场深度数据分析与导出 — 全市场信号扫描、行业轮动、个股研报级深度分析（基本面/估值/技术/资金筹码/情绪/风险六维）、数据挖掘、CSV/Excel 导出。在 QuantBot / Claude Code 中分析股票市场、挖掘机会、导出分析数据、生成选股/投研报告时使用。触发词：分析市场、数据分析、数据挖掘、全市场扫描、行业轮动、导出数据、导出CSV、生成报告、投研分析、深度分析、挖掘机会、个股研报、个股分析"
---

# 股票市场深度数据分析与导出

基于 QuantDB 全量数据（K线/财务/估值/技术/315维因子/融资融券/股东户数）的股票市场深度分析 + 数据导出技能。

> **⚠️ 数据计算零容忍（本技能最高优先级）**
> 所有涉及金额、成交量、比率的计算**必须先查 [[quantdb-fields]] 技能核对单位与口径**，
> 并在报告中注明换算步骤。单位/口径错 = 结论全部作废。核心陷阱：
>
> | 陷阱 | 正确口径 |
> |---|---|
> | 个股 volume=**股**、amount=**万元** | 指数 volume=**手**、amount=万元 |
> | `close*volume/amount ≈ 1e4`（个股自检公式） | 指数 ≈ 2e4 |
> | technical_indicators 的 close=**后复权** | valuation/market_sentiment=**不复权** |
> | valuation `dividend_rate` 是**百分数**（0.148=0.148%），**20260814 起才切换** | 之前是小数口径，跨日分析必须 ×10 归一 |
> | l1 `vol_std_*` 是**小数**（0.0406） | technical_indicators `vol_std_*` 是 **%**（4.06），差 100 倍 |
> | `/research/features` API 已换算：市值→亿元、flow*→百万元 | parquet 原值：市值=元、flow=元（差 1e8/1e6） |
> | l2_factors 分区**停滞 20260227** | 用前先查最新日期，近期 l2 型字段大量 NaN 是正常的 |
> | min1/min5 停更 20260724、hsgt_north 停更 202408 | 别当实时数据用 |
> | 财务 parquet 单位=**元** | instrument_detail `J_*`=万元、`Zsz/Ltsz`=亿元 |
> | 股息：dividend_factors `interest`=**每10股派息** | 算每股股息要 /10 |

## 认证

```bash
BASE=http://127.0.0.1:8000
TOKEN=$(curl -s -X POST $BASE/api/v1/auth/login -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123","tenant_id":"default"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")
AUTH="Authorization: Bearer $TOKEN"
CT="Content-Type: application/json"
```

## 1. 全市场信号扫描（选股）

```bash
# 全市场扫描：11000+ 信号 → 精简候选
curl -s -H "$AUTH" "$BASE/api/v1/selection/daily"
# 返回: {meta:{trade_date, total_signals, strategy_config}, market_state:{state,should_enter,position_advice}, candidates, industry_signals}
# candidates 每项: {symbol, name, score, industry, trend, buy_reason, warnings}

# 指定策略 / 指定日期 / 忽略 MA20 空仓保护
curl -s -H "$AUTH" "$BASE/api/v1/selection/daily?strategy=aggressive"
curl -s -H "$AUTH" "$BASE/api/v1/selection/daily?date=2026-08-14&ignore_ma20=true"

# 选股历史 / 做空候选（负分分析）
curl -s -H "$AUTH" "$BASE/api/v1/selection/history"
curl -s -H "$AUTH" "$BASE/api/v1/selection/negative"
```

## 2. 行业轮动与板块分析

选股响应的 `industry_signals` 字段包含各行业强度信号（行业 Top1 分数均值、强行业数等）：

| 信号 | 阈值 | 含义 |
|---|---|---|
| `industry_avg_top1` | ≥ 0.09 | 行业整体强度达标 |
| `strong_industry_count` | ≥ 2 | 强行业（Top1≥0.10）数量足够 → 可入场 |
| 谨慎 | 强行业数不足 | 降低仓位预期 |
| 空仓观望 | 无强行业 | 不参与 |

板块热度交叉验证（页面版端点，`/api/v1/market-analysis/*`）：
```bash
curl -s -H "$AUTH" "$BASE/api/v1/market-analysis/money-flow/period?period=5d&dimension=sector&category=shenwan&limit=25"
curl -s -H "$AUTH" "$BASE/api/v1/market-analysis/heatmap?trade_date=2026-08-14"
curl -s -H "$AUTH" "$BASE/api/v1/market-analysis/tags/by-tag?tag=半导体"
```

## 3. 个股研报级深度分析（核心流程）

用户要求"分析/深度分析"某股票时，按 **REFERENCES/quantdb-full-analysis-design.md** 的 6 层框架执行。
**每层必须有具体数值、必须展示计算公式**，不做泛泛之谈。输出格式见第 7 节研报模板。

### 3.1 数据采集（先全量拉取，再按需深挖）

```bash
# ① 全维度特征（估值/技术/动量/波动/流动性/资金流/风格/行业/筹码/概念/微观结构/情绪，371 字段）
#    注意：API 已换算单位（市值→亿元、flow*→百万元、totalMv→亿元），引用时注明
curl -s -H "$AUTH" "$BASE/api/v1/research/features/600519.SH"

# ② K线（120 日，不复权价 + adj_factor）
curl -s -H "$AUTH" "$BASE/api/v1/research/kline/600519.SH?days=120"
# 多市场 K 线（A-HK-US，daily；A股 QuantDB 本地 parquet 优先）
curl -s -H "$AUTH" "$BASE/api/v1/market/kline?symbol=600519.SH&market=A&period=daily&days=120"

# ③ 模型信号（按 model_id 逐个拉，多模型共识；详见 3.7）
curl -s -H "$AUTH" "$BASE/api/v1/models"                    # 用户模型列表（items[]，含 id/metadata/is_default）
curl -s -H "$AUTH" "$BASE/api/v1/models/inference/stock/600519.SH/history?days=180"
curl -s -H "$AUTH" "$BASE/api/v1/models/inference/stock/600519.SH/history?days=180&model_id=xxx"

# ④ 风险评分卡（6 维度 + veto 项）
curl -s -H "$AUTH" "$BASE/api/v1/risk/score/600519.SH"

# ⑤ 大盘环境（L0，先于一切）
curl -s -H "$AUTH" "$BASE/api/v1/selection/daily"           # market_state 牛熊+仓位建议
curl -s -H "$AUTH" "$BASE/api/v1/market/index-kline?symbol=000001.SH&days=60"
curl -s -H "$AUTH" "$BASE/api/v1/market/overview"           # 多市场指数概览
```

### 3.2 财务基本面（三表联动 + 每股指标，parquet 直读）

财务数据在 parquet（单位=**元**，季频），`/research/features` 拿不到，
**必须 docker exec 直读**：

```bash
docker exec quantmind python3 - <<'EOF'
import pandas as pd
base = "/data/quantdb/3_financial_data"
code = "600519.SH"
inc  = pd.read_parquet(f"{base}/income/{code}.parquet")        # 利润表（元）
bal  = pd.read_parquet(f"{base}/balance/{code}.parquet")       # 资产负债表（元）
cf   = pd.read_parquet(f"{base}/cashflow/{code}.parquet")      # 现金流量表（元）
ps   = pd.read_parquet(f"{base}/pershare_index/{code}.parquet")# 每股指标（ROE 直接可用）
dv   = pd.read_parquet(f"{base}/dividend_factors/{code}.parquet")
hn   = pd.read_parquet(f"{base}/holder_num/{code}.parquet")
# 最新 8 期趋势（每期 m_timetag=YYYYMMDD）
for df in (inc, bal, cf, ps):
    print(df.tail(8)[["m_timetag"] + [c for c in df.columns if c in (
        "revenue","net_profit_incl_min_int_inc","net_cash_flows_oper_act","s_fa_eps_basic",
        "s_fa_bps","s_fa_ocfps","equity_roe","net_roe","sales_gross_profit",
        "inc_net_profit_rate","inventory_turnover","goodwill","tot_assets","tot_liab",
        "account_receivable","inventories","tot_shrhldr_eqy_excl_min_int")]])
print(hn.tail(4)[["endDate","shareholder"]])   # 股东户数（户）
print(dv.tail(4)[["time","interest"]])         # interest=每10股派息（元），每股股息=interest/10
EOF
```

**指标公式（全部写死在报告里，禁止心算）**：
- 单季营收增速 = 本期营收 / 去年同期营收 − 1（找去年同期行：`m_timetag - 10000`）
- 毛利率 = `sales_gross_profit`（%）；净利率 = `inc_net_profit_rate`（%）
- 经营现金流/净利润（利润质量）：`cf.net_cash_flows_oper_act / inc.net_profit_incl_min_int_inc`，连续 2 期 < 1 → 红牌
- 应收+存货增速 vs 营收增速（压货检测）；商誉/净资产 > 30% → 减值风险
- ROE = `equity_roe`（%）；股息率 = `interest/10/close(不复权)×100`，与 valuation.dividend_rate 互验
- 股东户数环比 = (本期−上期)/上期：户数↓筹码集中，↑派发

### 3.3 估值（三维对照 + 历史分位，parquet 直读）

```bash
docker exec quantmind python3 - <<'EOF'
import pandas as pd, glob
# 拉近 5 年 valuation 序列算历史分位（Hive 分区 dt=YYYYMMDD/data.parquet）
files = sorted(glob.glob("/data/quantdb/5_technical_derived/valuation/dt=*/data.parquet"))[-1260:]
rows = []
for f in files:
    df = pd.read_parquet(f, columns=["symbol","time","pe_ttm","pb","ps_ttm","dividend_rate","total_mv","float_mv"])
    r = df[df.symbol == "600519.SH"]
    if len(r): rows.append(r.iloc[0])
v = pd.DataFrame(rows).sort_values("time").dropna(subset=["pe_ttm"])
cur = v.iloc[-1]
print("当前 PE %.2f 处于近5年 %.0f%% 分位（%d 个交易日）" % (cur.pe_ttm, (v.pe_ttm <= cur.pe_ttm).mean()*100, len(v)))
print("PB %.2f 分位 %.0f%%，股息率 %.3f%%" % (cur.pb, (v.pb <= cur.pb).mean()*100, cur.dividend_rate))
print("总市值 %.0f 亿元 / 流通市值 %.0f 亿元" % (cur.total_mv/1e8, cur.float_mv/1e8))
EOF
```

- **注意**：valuation.dividend_rate 20260814 起才是百分数口径，此前为小数——历史分位计算必须先按日期统一口径（×10 归一）
- 负 PE / 无盈利 → 用 PB/PS；行业相对：l1 `ind_relative_pe`（<1 = 相对行业折价，从 /research/features 的 industry 类取）
- 一句话结论模板：`PE 23.1x = 近 5 年 18% 分位，行业相对 0.72 → 估值不构成风险`

### 3.4 技术分析（分层递进 + 关键价位）

- **趋势层**：MA5/10/20/60 排列（多头/空头/粘合），收盘价在均线系统的位置
- **动能层**：MACD（dif/dea/hist 方向 + 柱状收敛/放大）、RSI 6/14（超买超卖 + 背离）、KDJ
- **波动层**：`vol_atr_14`（元）、`vol_std_60`（%，technical 口径）、`beta_20`（高 beta = 大盘放大镜，L0 结论加重）
- **量价层**：`vol_to_ma5/20`（量比）、`volume_trend_3d`（放量上涨 vs 缩量反弹）
- 支撑/压力：K 线近 20/60 日高低点（**注意 /research/kline 是不复权价**，与后复权指标对比时要先换算）

### 3.5 资金与筹码（多口径交叉 + 融资融券）

- **分单口径**（l2，API 已换算为百万元）：`flowSuperNet`（超大单）/`flowLargeNet`（大单）/`flowMediumNet`/`flowSmallNet`——三口径同向才可信；parquet 原值是元（差 1e6）
- **全口径**：`flowNetAmount` + `flowNetRatio`（净流入占成交比）
- **筹码**（l1）：`chipProfitRatio20/60`（获利盘%）、`chipConcentration20`、`chipPeakDistance`、`chipProfitDelta5`（5日获利盘变化——散户接盘还是主力吸筹）
- **⚠️ l2 分区停滞 20260227**：flow/chip/micro 型字段近期大量 NaN。若 l2 全 NaN，明确标注「l2 数据缺失（厂商停更），资金结论降级为不可验证」而不是跳过或编造
- **融资融券**（parquet，单位：finance_*=**万元**、slo_volume=**股**）：

```bash
docker exec quantmind python3 - <<'EOF'
import pandas as pd, glob
files = sorted(glob.glob("/data/quantdb/2_base_sector/margin_trading/dt=*/data.parquet"))[-30:]
rows = []
for f in files:
    df = pd.read_parquet(f, columns=["symbol","time","finance_balance","finance_buy","finance_repay","finance_net","slo_volume","slo_net"])
    r = df[df.symbol == "600519.SH"]
    if len(r): rows.append(r.iloc[0])
m = pd.DataFrame(rows).sort_values("time")
cur = m.iloc[-1]
print("融资余额 %.1f 亿元（近30日 %+.1f%%）" % (cur.finance_balance/1e4, (cur.finance_balance/m.iloc[0].finance_balance-1)*100))
print("近30日融资净买入累计 %.1f 万元，融券净卖出 %.0f 股" % (m.finance_net.tail(20).sum(), m.slo_net.tail(20).sum()))
EOF
```
- 经典背离：**股价涨 + 大单净流出 + 获利盘快速上升 = 散户接盘主力派发**

### 3.6 行业与概念（个股强 ≠ 行业强）

- 行业：`indStrength20/60`、`indRotationSpeed20`、`indCrowding20`（拥挤度——太热警惕）、`indBreadthUp20`、`indNetflowRank20`、`indRelativePe`
- 概念：`conceptHotScore`、`conceptMomentumTop3`、`conceptLeaderScore`、`conceptCrowdingMax`
- 结论三分类：**行业强+个股强**（共振，最理想）/ **行业弱+个股强**（逆势，持续性存疑）/ **行业强+个股弱**（掉队）

### 3.7 模型信号（多模型共识，不只看一个）

- `/api/v1/models` 拉**用户模型列表**（`items[]`，字段 `id` + `is_default`）；`/api/v1/inference/models`（engine 直连）拉系统模型（字段 `model_id`）
- 按 `model_id` 逐个拉 `history`——不同模型是独立视角（不同训练期/周期 T3/T10/T15/融合）
- 三个观察：① 共识度（多模型同方向=高置信，分歧=单独说明）② 趋势（分数序列上升/回落，看**变化方向**不看绝对值）③ 极值（分数在该模型历史序列的分位）
- `signal_side`（BUY/HOLD/SELL）+ `score_rank`（当天批次内截面排名，越小越靠前）并列引用
- **模型与量价/资金背离是最值钱的信号**（基本面好但模型持续 SELL = 边际改善未被确认 → "好公司 ≠ 好买点"）

### 3.8 新闻舆情（催化剂 vs 印证）

```bash
curl -s -H "$AUTH" "$BASE/api/v1/news/articles?tickers=600519&limit=30"
curl -s -H "$AUTH" "$BASE/api/v1/news/articles?tickers=600519&industries=白酒&strong_only=true"
curl -s -H "$AUTH" "$BASE/api/v1/news/articles?tickers=600519&sort=sentiment_bullish&limit=10"
```
- 个股 + 行业双通道；`sentiment=bullish|bearish|neutral` 分类统计；`event_tags` 事件标签（并购/财报/解禁/政策）
- 事件型新闻要找**后续数据印证**（公告增持 → 查资金流是否真流入）
- 无新闻：明确标 `[数据缺失]`；**禁止编造新闻**。价值排序：政策 > 公司重大事件 > 行业动态 > 分析师观点 > 市场情绪文

## 4. 量化数据挖掘（基于 QuantDB 因子）

```bash
curl -s -H "$AUTH" "$BASE/api/v1/admin/data-platform/quantdb/catalog"
curl -s -H "$AUTH" "$BASE/api/v1/admin/data-platform/quantdb/preview?dataset=l1_factors&limit=5"
```

### 深度挖掘路径（因子组合分析）

| 分析主题 | 用到的 QuantDB 字段 |
|---|---|
| **动量挖掘** | `mom_ret_5d/20d/60d, mom_ma_gap_*, mom_rsi_*` |
| **波动率掘金** | `vol_std_*, vol_atr_14, vol_parkinson_*, vol_gk_20` |
| **流动性异常** | `liq_volume_ratio_5/20, liq_obv_20, liq_mfi_14` |
| **资金流异动** | `flow_net_*, flow_large_net, flow_money_flow_index`（⚠️ l2 停更 20260227） |
| **筹码集中** | `chip_profit_ratio_*, chip_concentration_20, chip_peak_distance` |
| **行业强度** | `ind_strength_20/60, ind_rotation_speed_20, ind_crowding_20` |
| **概念热度** | `concept_hot_score, concept_momentum_top3, concept_leader_score` |
| **微观结构** | `micro_vpin_*, micro_pin, micro_order_flow_toxicity, micro_kyle_lambda` |

## 5. 数据导出（CSV / Excel）

### 5.1 导出选股候选 CSV
```bash
curl -s -H "$AUTH" "$BASE/api/v1/selection/daily" -o /tmp/selection.json
python3 <<'EOF'
import json, csv
d = json.load(open('/tmp/selection.json'))
meta = d.get('meta', {}); ms = d.get('market_state', {})
cands = d.get('candidates', [])
with open('/tmp/selection.csv', 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['代码','名称','分数','行业','趋势','买入理由'])
    for c in cands:
        w.writerow([c.get('symbol'), c.get('name'), round(c.get('score',0),4), c.get('industry'), c.get('trend'), c.get('buy_reason')])
print(f'导出 {len(cands)} 只选股 → /tmp/selection.csv（交易日 {meta.get("trade_date")}，市场状态 {ms.get("state")}）')
EOF
```

### 5.2 导出个股全维度特征 CSV
```bash
curl -s -H "$AUTH" "$BASE/api/v1/research/features/600519.SH" -o /tmp/stock_features.json
python3 <<'EOF'
import json
d = json.load(open('/tmp/stock_features.json')).get('data', {})
rows = []
for cat, fields in d.items():
    if isinstance(fields, dict):
        for k, v in fields.items():
            rows.append([cat, k, v])
with open('/tmp/stock_features.csv', 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['类别','字段','值'])
    for r in rows: w.writerow(r)
print(f'导出 {len(rows)} 个字段 → /tmp/stock_features.csv（API 已换算：市值=亿元、flow=百万元）')
EOF
```

### 5.3 导出批量股票对比 CSV
```bash
curl -s -X POST -H "$AUTH" -H "$CT" "$BASE/api/v1/research/batch-features" \
  -d '{"symbols":["600519.SH","000858.SZ","601318.SH"],"fields":["pe","pb","roe","totalMv","momRet20d","volStd20","mainFlow"]}' \
  -o /tmp/batch_features.json
python3 <<'EOF'
import json, csv
d = json.load(open('/tmp/batch_features.json')).get('data', {}).get('items', [])
with open('/tmp/stock_compare.csv', 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    if d:
        w.writerow(['代码'] + list(d[0].get('values', {}).keys()))
        for it in d:
            w.writerow([it.get('symbol')] + list(it.get('values', {}).values()))
print(f'导出 {len(d)} 只股票对比 → /tmp/stock_compare.csv')
EOF
```

### 5.4 导出风险评分卡 CSV
```bash
curl -s -X POST -H "$AUTH" -H "$CT" "$BASE/api/v1/risk/scores" \
  -d '{"symbols":["600519.SH","000858.SZ","601318.SH"]}' -o /tmp/risk_batch.json
python3 <<'EOF'
import json, csv
d = json.load(open('/tmp/risk_batch.json')).get('data', {}).get('items', {})
with open('/tmp/risk_scores.csv', 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['代码','风险分','等级','否决','否决原因','日期'])
    for sym, v in d.items():
        w.writerow([sym, v.get('risk_score'), v.get('risk_level'), v.get('veto'), ';'.join(v.get('veto_reasons') or []), v.get('trade_date')])
print(f'导出 {len(d)} 只风险评分 → /tmp/risk_scores.csv')
EOF
```

## 6. 全市场候选池分析（投研）

```bash
# 某次推理批次的候选池（含各股行业/概念/指数/分数）
curl -s -H "$AUTH" "$BASE/api/v1/research/overview?limit=100"
# 指定 run 的全池数据（筛选/排序需要全池）
curl -s -H "$AUTH" "$BASE/api/v1/research/universe?run_id=run_20260805_xxx&limit=2000"
```

## 7. 研报输出格式（券商研报级排版）

> 输出报告时**必须**采用以下结构。Markdown 表格承载所有数据，
> 每个表格列名带单位，每个计算指标在下方用小字注明公式与数据来源。

### 7.1 报告骨架

```markdown
# {股票名}（{代码}）深度分析报告

> **报告日期**：{YYYY-MM-DD}　**数据截至**：{最新交易日，注明各数据集实际日期}
> **分析框架**：市场环境 → 基本面 → 估值 → 技术 → 资金筹码 → 行业 → 模型 → 舆情
> **免责声明**：本报告由 AI 自动生成，仅供研究参考，不构成投资建议。

## 一、投资要点（3-5 条，每条 ≤ 1 行，多空都写）

## 二、核心结论

| 维度 | 评级 | 核心依据（带数值） |
|---|---|---|
| 市场环境 | 中性/偏多/偏空 | 上证 3927 vs MA20 3890，建议仓位 40% |
| 基本面 | 优秀/良好/一般/恶化 | 单季营收 +12.3%，现金流/净利润 1.15 |
| 估值 | 低估/合理/高估 | PE 23.1x = 近5年 18% 分位 |
| 技术面 | 多头/空头/震荡 | 收盘站上 MA20/60，MACD 金叉后柱状放大 |
| 资金面 | 流入/流出/分歧 | 近5日大单净流入 +2.1 亿元 |
| 综合评级 | 买入/增持/中性/减持 | 好公司 + 好价格 + 时机待确认 |

## 三、公司概况与业务透视
（名称、代码、申万行业、上市日期、总市值/流通市值、两融标的与否）

## 四、财务分析（最近 8 个报告期表格 + 趋势解读）
| 报告期 | 营收(亿元) | 单季同比% | 归母净利(亿元) | 毛利率% | 净利率% | ROE% | EPS(元) | 经营现金流(亿元) |
|---|---|---|---|---|---|---|---|---|
（每个 % 值注明：毛利=利润表 sales_gross_profit，同比=本期/去年同期−1，现金流/净利=利润质量）

## 五、估值分析
| 指标 | 当前值 | 近5年分位 | 行业相对 | 判断 |
|---|---|---|---|---|
| PE(TTM) | 23.1x | 18% | 0.72 | 低估 |
| PB | … | … | — | … |
| 股息率 | 0.39% | … | — | … |

## 六、技术分析
（趋势/动能/波动/量价分层 + 关键支撑压力位 + 各指标当前值与判断依据）

## 七、资金面与筹码
（超大单/大单/散户三口径 + 近5日/20日趋势 + 融资融券 + 获利盘 + 派发/吸筹判断）

## 八、行业与概念
（行业强度/拥挤度/资金流排名 + 共振/逆势/掉队分类 + 概念热度）

## 九、AI 模型信号
| 模型 | 周期 | 最新分数 | 180日趋势 | 信号 | 排名 |
|---|---|---|---|---|---|
（共识度 + 与量价背离说明）

## 十、多空证据对照
| 层 | 多方证据 | 空方证据 |
|---|---|---|
（每格带数值，无证据写「—」）

## 十一、风险提示（按严重度排序）
1. **{风险}**：{触发条件 + 影响 + 监测指标}

## 十二、操作建议
| 持仓状态 | 建议 | 触发条件 |
|---|---|---|
| 未持仓 | 等待回踩 62 元或模型转 BUY | 放量突破 68 元可追 |
| 已持仓 | 持有，止损 58 元 | 跌破 MA60 或大单连续 3 日流出减仓 |
```

### 7.2 排版铁律

1. **每个数字带单位**：亿元/百万元/万元/元、股/手、%、x（倍）——没有单位的数字禁止出现在报告里
2. **每个计算指标带公式**：`股息率 = 每10股派息 0.98 ÷ 10 ÷ 不复权收盘 66.19 × 100 = 0.148%`
3. **每个时间序列注明口径**：前复权/后复权/不复权、单季/累计/同比
4. **数据分层标注**：API 数据标 `[API]`、parquet 直读标 `[parquet]`、模型信号标 `[模型]`、新闻标 `[新闻]`；缺失标 `[数据缺失]`（注明缺的是哪个数据集）
5. **禁止编造**：拿不到的数据写缺失原因，绝不估一个数字
6. **评级统一**：综合评级只允许 买入/增持/中性/减持/卖出 五档，且必须由多维证据推导，禁止只凭单一指标

## 8. 复杂度分级（智能体按需选择深度）

| 级别 | 用时 | 内容 |
|---|---|---|
| 快速体检 | 1-2 min | L0 市场 + 估值 + 技术 + 默认模型 + 风险卡，输出核心结论表 |
| 标准分析 | 3-5 min | 全部 6 层 + 财务 4 期 + 估值分位 + 多模型 + 完整研报模板 |
| 深度尽调 | 10+ min | 标准分析 + 财务 8 期三表 + 5 年估值分位 + 全模型逐拉 + 融资融券 30 日 + 股东户数趋势 + 分红历史 + 多空证据对照 + 情景推演（目标价区间） |

## 9. 相关技能联动

- **[[quantdb-fields]]** — **必读**：全部数据集单位/口径速查（本技能计算正确性的前提）
- **[[quantdb-sdk]]** — QuantDB 数据源（Key 配置、28 数据集、字段清单）
- **[[smart-strategy-stock-picking]]** — 条件选股（183 字段 DSL 筛选）
- **[[quantmind-operations]]** — 模型训练/推理/RSS 新闻
- **[[rd-agent-factor-mining]]** — 因子挖掘深化分析维度

## 10. 常见问题

| 现象 | 处理 |
|---|---|
| 选股 candidates 空 | 检查 `total_signals` 与 `market_state`（MA20 空仓保护），或 `ignore_ma20=true` |
| 个股特征空 | 确认 symbol 格式（600519.SH），用 `/research/batch-features` 批量试 |
| 财务/融资融券数据拿不到 | 这些不在 API 里，必须 docker exec 直读 parquet（见 3.2/3.5） |
| l2 资金流字段全 NaN | l2 分区停更 20260227（厂商侧），明确标注数据缺失，勿编造 |
| 股息率两个值对不上 | valuation.dividend_rate 20260814 起切换百分数口径，跨日对比先 ×10 归一 |
| 市值/成交额数字离谱 | 单位错：API 市值=亿元、flow=百万元；parquet 市值=元；成交额永远是万元 |
| 导出乱码 | CSV 用 `utf-8-sig` 编码（已内置 BOM） |
