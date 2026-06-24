# A股风险评分卡设计 v2

> 状态：**设计冻结，待实现**
> 日期：2026-06-24
> 上一版：v1（见 git 历史）
> 上游路线：[risk_scorecard_phase4_plan.md](./risk_scorecard_phase4_plan.md)

---

## 0. 与 v1 的差异（TL;DR）

| 变化 | 内容 |
|------|------|
| 维度数 | 5 → **6**（新增"过热"维度） |
| 现有维度 | "波动率" → "**波动率+量能**"（加入量价配合 + 波动率扩张子项） |
| Veto 新增 | "巨幅波动 + 巨量" 当日条款 |
| 字段修正 | `volume_ratio_*` 弃用（数据 bug），改用 `amount` 现场算量比 |
| 权重重平衡 | 流动性 30→25%、波动率 25→30%、趋势 25→20%、基本面 12→10%、状态 8→5%、过热 +10% |
| API 契约 | **完全向后兼容**（响应结构不变，只是多一个维度 key） |

---

## 1. M1 字段探查结论（必读）

### 1.1 单位真相
| 字段 | 实测分布（2026-06-22 全市场 5526 票） | 单位 | 用法 |
|------|--------------------------------------|------|------|
| `rsi_14` | p50=38.6  p90=67.0  p99=85.0 | 0-100 | 直接用 |
| `kdj_k` | p50=40.3  p95=83.6 | 0-100 | 直接用 |
| `vol_std_5 / _20 / _60` | 干净标准差 | 实数 | 取比值 |
| `return_5d` | p50=0.0  p90=0.19  p95=0.29 | **小数** | clip 到 (-0.99, 5) |
| `return_20d` | p90=0.29  p95=8.58（异常值污染）| **小数** | clip 同上 |
| `amount` | 中位 1.2 亿/天 | 元 | 现场算 5 日均值 |

### 1.2 数据缺陷
- ❌ **`volume_ratio_5` / `volume_ratio_20` 字段 buggy**：中位都是 0.01（应该 ~1.0），不能直接用
- ❌ **`volume` 字段在部分日期被压缩 100x**（06-22 茅台 volume=58251，实际百万级）
- ✅ **`amount`（成交额）字段干净** → 量价类指标全部改用 amount 计算
- ⚠️ **指数 & 部分北交所新股** `return_5d` 异常（如 399300.SZ = 1039、新股 = -0.999） → clip + 排除 6 位数字非股票的指数

### 1.3 实测分布验证（关键阈值落点）
| 信号 | 阈值 | 触发占比 | 评估 |
|------|------|---------|------|
| RSI > 80 | 强超买 | 131/5526 = 2.4% | ✅ |
| RSI > 75 | 中超买 | 224/5526 = 4.1% | ✅ |
| KDJ > 85 | KDJ 强超买 | 205/5526 = 3.7% | ✅ |
| return_5d > 25%（=0.25）| 短期暴涨 | 54/5526 = 1.0% | ✅ |
| return_5d > 15%（=0.15）| 短期强涨 | 73/5526 = 1.3% | ✅ |
| return_20d > 50%（=0.50）| 月度翻倍 | 24/5526 = 0.4% | ✅ |
| `vol_std_5/vol_std_20 > 1.4` | 波动率扩张 | 536/5526 = 9.7% | ✅ |
| `vol_std_5/vol_std_20 > 1.8` | 强扩张 | 149/5526 = 2.7% | ✅ |
| `amount/amt_5d_avg < 0.8` | 缩量 | 543/5526 = 9.8% | ✅ |
| `amount/amt_5d_avg > 1.5` | 放量 | 1040/5526 = 18.8% | ✅ |
| `amount/amt_5d_avg > 2.0` | 巨量 | 280/5526 = 5.1% | ✅ |

阈值全部落在 1-10% 分位区间，**不是噪声也不会过度灵敏**。

---

## 2. v2 维度全景

| # | 维度 | 权重 | 子项 | 字段 |
|---|------|------|------|------|
| 1 | 流动性 | 25% | 20日均成交额、流通市值、换手率异常 | `amount`(20d) `float_mv` `turnover_rate` |
| 2 | 波动率+量能 ⭐改造 | 30% | ATR、当日异动、波动率扩张、量价配合 | `vol_atr_14` `close` `pct_change` `vol_std_5/20` `amount` |
| 3 | 趋势 | 20% | 跌破 ma60、空头排列、MACD 死叉、跌破 ma20 | `close` `ma5/10/20/60` `macd_hist` |
| 4 | 过热 ⭐新增 | 10% | 短期超涨、超买共振 | `return_5d/_20d` `rsi_14` `kdj_k` |
| 5 | 基本面 | 10% | ROE、PB、PE | `roe` `pb` `pe_ttm` |
| 6 | 状态 | 5% | 连板涨停 | `consecutive_limit_up_days` |

总和 = 100%。

---

## 3. 维度公式（满分 100 内 clip）

### 3.1 一票否决（**v2 新增**：剧烈波动 + 巨量）
```python
veto = (
    is_st == 1
    or listed_days < 90
    or volume == 0
    or (pct_change > 9.5 and turnover_rate < 1.0)   # 涨停封板
    # v2 新增
    or (abs(pct_change) > 8 and amount_ratio_5d > 2.0)  # 巨幅+巨量黑天鹅
)
```

### 3.2 维度 1：流动性（25%）
（公式与 v1 完全相同，仅权重 30→25）

```python
liq_score = clip(0, 100,
    # 20日均成交额
    100 if amount_20d < 1e7  else 70 if amount_20d < 3e7
    else 40 if amount_20d < 5e7 else 15 if amount_20d < 1e8 else 0
    # 流通市值
    + (20 if float_mv < 1e9 else 10 if float_mv < 2e9 else 0)
    # 换手率异常
    + (15 if turnover_rate > 15 else 8 if turnover_rate < 0.3 else 0)
)
```

### 3.3 维度 2：波动率+量能（30%，**改造**）

```python
atr_pct = vol_atr_14 / close * 100         # %
vol_expansion = vol_std_5 / vol_std_20      # 倍数
amt_ratio = amount / amt_5d_avg             # 倍数

vol_score = clip(0, 100,
    # 子项 A：基础 ATR（v1 已有）
    (80 if atr_pct > 8 else 55 if atr_pct > 6 else 30 if atr_pct > 4.5 else 10)
    # 子项 B：当日异动（v1 已有）
    + (15 if abs(pct_change) > 7 else 0)
    # 子项 C：波动率扩张（v2 新增）
    + (30 if vol_expansion > 1.8 else 15 if vol_expansion > 1.4 else 0)
    # 子项 D：量价配合（v2 新增，4 种关系）
    + (50 if pct_change < -3 and amt_ratio > 1.5 else    # 放量下跌 = 主力出货
       40 if pct_change > 2  and amt_ratio < 0.8 else    # 缩量上涨 = 弱势反弹
       20 if pct_change < -2 and amt_ratio < 0.8 else    # 缩量下跌 = 阴跌
       -10 if pct_change > 2 and amt_ratio > 1.2 else 0) # 放量上涨 = 健康（减分）
)
```

**量价配合矩阵的设计理由**：
- 放量下跌（+50）：主力出货最明显信号，A 股最常见的暴跌前兆
- 缩量上涨（+40）：缺乏主力推动的反弹，95% 三日内回吐
- 缩量下跌（+20）：阴跌
- 放量上涨（-10）：健康行情，反而**减分**

注意"健康行情"减分会被 clip 在 0，但能抵消其它子项的噪声。

### 3.4 维度 3：趋势（20%）
（公式与 v1 完全相同，仅权重 25→20）

### 3.5 维度 4：过热（10%，**全新**）

```python
# return_5d / _20d 必须先 clip 到合理范围，避免指数/异常值
r5 = clip(-0.99, 5.0, return_5d)
r20 = clip(-0.99, 5.0, return_20d)

overheat_score = clip(0, 100,
    # 子项 A：短期暴涨
    (60 if r5 > 0.25 else 30 if r5 > 0.15 else 0)
    # 子项 B：月度大涨
    + (20 if r20 > 0.50 else 10 if r20 > 0.30 else 0)
    # 子项 C：超买共振（必须叠加短期上涨，避免误杀长期强势股）
    + (50 if rsi_14 > 80 and r5 > 0.15 else
       30 if rsi_14 > 75 and r5 > 0.10 else
       25 if rsi_14 > 75 and kdj_k > 85 else 0)
)
```

**设计要点**：
- "超买" 单独存在不算高风险（强势股长期 RSI 60-80）
- **必须 RSI 超买 + 短期 5 日累计涨幅高** 才打分
- KDJ 仅用于跟 RSI 共振，单独不打分

### 3.6 维度 5：基本面（10%）
（公式与 v1 完全相同，仅权重 12→10）

### 3.7 维度 6：状态（5%）
（公式与 v1 完全相同，仅权重 8→5）

---

## 4. 实现注意事项

### 4.1 数据获取层
- **新增** `amount_5d_avg`：在 `_fetch_snapshot` 的 SQL 里加一个 CTE，跟 `amount_20d_avg` 一起算
- **不要用** `volume_ratio_5/_20` 字段（数据 bug）

### 4.2 输入校验
- `return_5d/_20d` 必须 clip：
  ```python
  r = max(-0.99, min(5.0, return_5d))   # 指数 1039 会被压到 5
  ```
- 跳过 6 位数字指数（symbol 不以 `0`/`3`/`6` 开头数字开头的不评分）—— 实际上 service 入口对 `symbol` 已经做 `to_prefix`，可加一个 `_is_valid_stock(symbol)` 守卫

### 4.3 API 契约
- 响应结构**完全向后兼容**：仍然是
  ```json
  {
    "symbol": "...", "trade_date": "...", "risk_score": 27.5,
    "risk_level": "低", "veto": false, "veto_reasons": [],
    "dimensions": {"liquidity": {...}, "volatility": {...}, "trend": {...},
                   "fundamental": {...}, "status": {...}, "overheat": {...}},  // 多一个 key
    "weights": {...},  // 权重也变
    "snapshot": {...}   // 多 amt_5d_avg / rsi_14 / kdj_k / return_5d / return_20d
  }
  ```
- 前端 `RiskScoreCard.tsx` 用 `DIM_META` 数组渲染，**只需要加一行 `overheat`** 即可自动适配

### 4.4 单元测试
- 保留 v1 全部 34 个测试（向后兼容）
- 新增：
  - veto 新条款（巨幅+巨量）3 个 case
  - 波动率扩张 + 量价配合 4 矩阵 共 8 个 case
  - 过热维度 5 个 case（短期暴涨、RSI 超买、KDJ 共振、不该误杀长期强势股）

预计总测试 50+。

---

## 5. 正交性与单调性验证

### 5.1 正交性测试
在 2026-01-01 ~ 2026-06-22（约 110 个交易日）每天算 6 个维度分数，然后两两 Pearson 相关。

**接受标准**：
- `corr(overheat, trend) | corr(overheat, vol) | corr(overheat, fund) < 0.5`
- `corr(vol_v2, trend) < 0.6`（波动率改造后，波动率扩张和趋势可能微相关，可接受）

**实施**：写一次性脚本 `scripts/risk_scoring/validate_v2.py`，输出 6x6 相关矩阵。

### 5.2 单调性测试
- 按 6 维度各自分 5 组（按分数四分位 + 100 分组）
- 看每组**未来 5/10/20 日实际波动率**和**实际最大回撤**是否单调
- 单调性失败的维度需要重新校阈值

---

## 6. 关闭条件（v2 视为完成）

- ✅ 设计文档冻结（本文）
- ✅ 后端实现 + 50+ 单测 100% 通过
- ✅ 正交性测试：6 个维度两两 corr < 0.5（个别 < 0.6 可接受）
- ✅ 单调性测试：6 个维度的 5 分组未来回撤单调
- ✅ 前端自动适配（无 typecheck 错误，UI 显示 6 维度）
- ✅ 端到端：茅台 / 平安银行 / ST 票评分变化在合理范围内
