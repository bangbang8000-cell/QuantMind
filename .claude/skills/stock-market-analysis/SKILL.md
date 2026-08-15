---
name: stock-market-analysis
description: "股票市场深度数据分析与导出 — 全市场信号扫描、行业轮动、个股全维度分析、数据挖掘、CSV/Excel 导出。在 QuantBot / Claude Code 中分析股票市场、挖掘机会、导出分析数据、生成选股/投研报告时使用。触发词：分析市场、数据分析、数据挖掘、全市场扫描、行业轮动、导出数据、导出CSV、生成报告、投研分析、深度分析、挖掘机会"
---

# 股票市场深度数据分析与导出

基于 QuantDB 全量数据（K线/财务/估值/技术/315维因子）的股票市场深度分析 + 数据导出技能。

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

### 1.1 每日选股信号
```bash
# 全市场扫描：11000+ 信号 → 精简候选
curl -s -H "$AUTH" "$BASE/api/v1/selection/daily"
# 返回: {status, meta:{trade_date, total_signals, strategy_config}, candidates, industry_signals}
# candidates 每项: {symbol, score, industry, trend, buy_reason, warnings}

# 指定策略
curl -s -H "$AUTH" "$BASE/api/v1/selection/daily?strategy=aggressive"
curl -s -H "$AUTH" "$BASE/api/v1/selection/daily?strategy=conservative"
curl -s -H "$AUTH" "$BASE/api/v1/selection/daily?strategy=balanced"
```

### 1.2 选股历史
```bash
curl -s -H "$AUTH" "$BASE/api/v1/selection/history"
```

## 2. 行业轮动与板块分析

选股响应的 `industry_signals` 字段包含各行业强度信号（行业 Top1 分数均值、强行业数等），用于判断：
- **入场信号**：`industry_avg_top1 >= 0.09` 且强行业数 >= 2 → 可入场
- **谨慎**：强行业数不足
- **空仓观望**：无强行业

## 3. 个股全维度分析

### 3.1 投研平台个股特征（371 字段全量）
```bash
# 单只股票全维度特征（估值/技术/动量/波动/流动性/资金流/风格/行业/筹码/概念/微观结构/情绪）
curl -s -H "$AUTH" "$BASE/api/v1/research/features/600519.SH"
# 批量
curl -s -X POST -H "$AUTH" -H "$CT" "$BASE/api/v1/research/batch-features" \
  -d '{"symbols":["600519.SH","000858.SZ"]}'
# 投影模式（只取指定字段，响应小）
curl -s -X POST -H "$AUTH" -H "$CT" "$BASE/api/v1/research/batch-features" \
  -d '{"symbols":["600519.SH"],"fields":["pe","roe","momRet5d","volStd20","mainFlow"]}'
```

### 3.2 个股风险评分卡
```bash
# 单只风险评分（流动性/波动/趋势/过热/基本面/状态 6 维度）
curl -s -H "$AUTH" "$BASE/api/v1/risk/score/600519.SH"
# 批量
curl -s -X POST -H "$AUTH" -H "$CT" "$BASE/api/v1/risk/scores" \
  -d '{"symbols":["600519.SH","000858.SZ"]}'
```

### 3.3 个股历史推理分数
```bash
curl -s -H "$AUTH" "$BASE/api/v1/models/inference/stock/600519.SH/history?days=180"
```

### 3.4 K 线数据（120 日）
```bash
curl -s -H "$AUTH" "$BASE/api/v1/research/kline/600519.SH?days=120"
# 多市场 K 线（A-HK-US，仅 daily 周期；A股 QuantDB 本地 parquet 优先）
curl -s -H "$AUTH" "$BASE/api/v1/market/kline?symbol=600519.SH&market=A&period=daily&days=30"
# 指数日线 + MA20（大盘均线过滤用）
curl -s -H "$AUTH" "$BASE/api/v1/market/index-kline?symbol=000001.SH&days=60"
# 多市场指数概览（QuantDB/QuantHK/QuantUS/QuantBC/QuantFutures）
curl -s -H "$AUTH" "$BASE/api/v1/market/overview"
```

### 3.5 全方位深度分析框架（7 层金字塔）

用户要求"全方位分析一只股票"时，按 **REFERENCES/quantdb-full-analysis-design.md** 的 7 层框架执行，**每层必须有具体数值、不做泛泛之谈**：

| 层 | 数据 | 核心问题 |
|---|---|---|
| L0 市场环境 | `/selection/daily` market_state + 上证 MA20 | 牛熊 + 建议仓位（个股再强也受大盘拖累） |
| L1 估值 | features 的 valuation + 历史分位 + ind_relative_pe | 绝对/行业/历史三维对照（只看当前值没意义） |
| L2 财务 | income/balance/cashflow parquet + holder_num | 三表联动防纸面利润；股东户数趋势 |
| L3 技术 | technical 37 列 + K 线 | 趋势/动能/量价分层递进，不堆指标 |
| L4 资金筹码 | l2 flow_*/chip_* + margin_trading | 主力/散户/超大单多口径交叉 + 融资融券 |
| L5 行业概念 | l1 ind_*/concept_* + index_weights | 共振/逆势/掉队三分类；拥挤度警戒 |
| L6 模型信号 | `/models` 列表 + history 按 `model_id` 逐个拉 | **多模型共识度 + 各自趋势**（不只看默认模型） |
| L7 新闻舆情 | `/news/articles`（tickers+industries 双通道） | 催化剂/风险；事件要找后续数据印证 |

**三条铁律**：
1. **跨层印证**：任何结论至少两层数据支撑（见设计文档的印证矩阵，如"获利盘↑+大单流出+股价涨 = 派发结构"）
2. **模型背离最值钱**：基本面好但模型持续 SELL、资金流出 → "好公司 ≠ 好买点"这类结论必须写
3. **新闻禁止编造**：无新闻标 `[数据缺失]` 并提醒加 RSS 源

复杂度分级：快速体检（L0+L1+L3+L6 默认模型）/ 标准分析（全 7 层）/ 深度尽调（+全模型逐拉+三表+历史分位）。

## 4. 全市场候选池分析（投研）

### 4.1 候选池概览
```bash
# 某次推理批次的候选池（含各股行业/概念/指数/分数）
curl -s -H "$AUTH" "$BASE/api/v1/research/overview?limit=100"
```

### 4.2 全池特征（universe）
```bash
# 指定 run 的全池数据（筛选/排序需要全池）
curl -s -H "$AUTH" "$BASE/api/v1/research/universe?run_id=run_20260805_xxx&limit=2000"
```

## 5. 市场分析平台（页面版端点）

市场分析页面的后端端点（`/api/v1/market-analysis/*`）：

```bash
# 指数快照（上证/深证/创业板/沪深300/科创50）
curl -s -H "$AUTH" "$BASE/api/v1/market-analysis/indices/overview"

# 个股资金流向排行
curl -s -H "$AUTH" "$BASE/api/v1/market-analysis/money-flow/stocks?limit=20"

# 多周期资金净流入排行（period=1d/3d/5d/10d/20d, dimension=sector/stock, category=shenwan/concept）
curl -s -H "$AUTH" "$BASE/api/v1/market-analysis/money-flow/period?period=5d&dimension=sector&category=shenwan&limit=25"

# 主力/散户资金流桑基图
curl -s -H "$AUTH" "$BASE/api/v1/market-analysis/money-flow/sankey"

# 标签双向查询（板块→个股 / 个股→标签）
curl -s -H "$AUTH" "$BASE/api/v1/market-analysis/tags/by-tag?tag=半导体"
curl -s -H "$AUTH" "$BASE/api/v1/market-analysis/tags/by-stock?symbol=600519.SH"

# 申万行业热力图
curl -s -H "$AUTH" "$BASE/api/v1/market-analysis/heatmap?trade_date=2026-08-14"
```

> 注：部分端点当前为静态/Mock 数据（前端部分组件用本地数据渲染）；资金流真实聚合在 `qm_sector_daily_metrics`。

## 6. 量化数据挖掘（基于 QuantDB 因子）

```bash
# 查看可用数据集与字段（见 quantdb-sdk 技能）
curl -s -H "$AUTH" "$BASE/api/v1/admin/data-platform/quantdb/catalog"
curl -s -H "$AUTH" "$BASE/api/v1/admin/data-platform/quantdb/preview?dataset=l1_factors&limit=5"
curl -s -H "$AUTH" "$BASE/api/v1/admin/data-platform/quantdb/preview?dataset=l2_factors&limit=5"
```

### 深度挖掘路径（因子组合分析）
| 分析主题 | 用到的 QuantDB 字段 |
|---|---|
| **动量挖掘** | `mom_ret_5d/20d/60d, mom_ma_gap_*, mom_rsi_*` |
| **波动率掘金** | `vol_std_*, vol_atr_14, vol_parkinson_*, vol_gk_20` |
| **流动性异常** | `liq_volume_ratio_5/20, liq_obv_20, liq_mfi_14` |
| **资金流异动** | `flow_net_*, flow_large_net, flow_money_flow_index` |
| **筹码集中** | `chip_profit_ratio_*, chip_concentration_20, chip_peak_distance` |
| **行业强度** | `ind_strength_20/60, ind_rotation_speed_20, ind_crowding_20` |
| **概念热度** | `concept_hot_score, concept_momentum_top3, concept_leader_score` |
| **微观结构** | `micro_vpin_*, micro_pin, micro_order_flow_toxicity, micro_kyle_lambda` |

## 6. 数据导出（CSV / Excel）

### 6.1 导出选股候选 CSV
```bash
# 取选股结果 → 转换 CSV
curl -s -H "$AUTH" "$BASE/api/v1/selection/daily" -o /tmp/selection.json
python3 <<'EOF'
import json, csv
d = json.load(open('/tmp/selection.json')).get('data', {})
cands = d.get('candidates', [])
with open('/tmp/selection.csv', 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['代码','名称','分数','行业','趋势','买入理由'])
    for c in cands:
        w.writerow([c.get('symbol'), c.get('name'), round(c.get('score',0),4), c.get('industry'), c.get('trend'), c.get('buy_reason')])
print(f'导出 {len(cands)} 只选股 → /tmp/selection.csv')
EOF
```

### 6.2 导出个股全维度特征 CSV
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
print(f'导出 {len(rows)} 个字段 → /tmp/stock_features.csv')
EOF
```

### 6.3 导出批量股票对比 CSV
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

### 6.4 导出风险评分卡 CSV
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

## 7. 综合投研报告流程（推荐）

当用户要求"深度分析"某股票/行业/全市场时：

1. **全市场扫描**：`/selection/daily` 看当前机会（11000+ 信号）
2. **行业判断**：从选股响应的 `industry_signals` 看板块强弱
3. **个股深挖**：`/research/features/{symbol}` 拿 371 字段全维度
4. **风险审查**：`/risk/score/{symbol}` 6 维度评分
5. **模型交叉验证**：`/models/inference/stock/{symbol}/history` 看推理分数趋势
6. **新闻印证**：`/news/articles?tickers=xxx` 看利好利空
7. **K线确认**：`/research/kline/{symbol}` 看走势
8. **导出报告**：按需导出 CSV（选股/特征对比/风险评分）

## 8. 相关技能联动

- **[[quantdb-sdk]]** — QuantDB 数据源（Key 配置、28 数据集、字段清单）
- **[[smart-strategy-stock-picking]]** — 条件选股（183 字段 DSL 筛选）
- **[[quantmind-operations]]** — 模型训练/推理/RSS 新闻
- **[[rd-agent-factor-mining]]** — 因子挖掘深化分析维度

## 9. 常见问题

| 现象 | 处理 |
|---|---|
| 选股 candidates 空 | 检查 `total_signals`，可能当天无满足阈值信号 |
| 个股特征空 | 确认 symbol 格式（600519.SH），用 `/research/batch-features` 批量试 |
| 导出乱码 | CSV 用 `utf-8-sig` 编码（已内置 BOM） |
| 需要更多字段 | 用 `/research/features` 全量（371 字段）而非投影 |
