# A股风险评分卡设计 v1

> 状态：**设计冻结，待实现**
> 日期：2026-06-24
> 作者：QuantMind 量化组
> 范围：阶段 1 — 仅产出设计 + 数据探索结论；阶段 2/3/4 实现详见各自 PR/Issue

---

## 1. 目标与边界

### 1.1 要解决的问题

模型预测分数（`pred_score`）只回答「未来 N 天预期收益是多少」，**不回答**：

- 这只票流动性够不够（能否进退）
- 趋势是否已经走坏（即使预期收益为正也可能是反弹陷阱）
- 基本面是否在恶化（ROE 转负、PB < 0.8 净资产穿仓风险）
- 是不是 ST、停牌、次新、涨停封板（**根本不该买**的状态票）

业务诉求：**当 pred 不够顶尖（不是 top 5%）且风险又大时，把这种「鸡肋+危险」的票剔除或大幅降权**。等价于追求 Sharpe-adjusted return 而非 raw expected return。

### 1.2 边界

- **本方案只评估 A 股**（市场代码 SH/SZ/BJ）。HK/US 暂不支持
- **使用 `stock_daily_latest` 表已有字段**，不依赖外部新数据源
- **不重新训练任何模型**——评分卡是确定性规则系统
- **资金流维度暂时不实现**：`main_flow / flow_net_amount / inst_ownership / profit_growth` 字段当前 100% NULL，等数据补齐后追加为维度 6

### 1.3 不要做的事

- ❌ 不做组合优化（最小方差/最大 Sharpe）——那是方案 C，本卡片是方案 A
- ❌ 不动 `riskmodel_root`（Qlib Barra 路径，目前为空目录）
- ❌ 不做 ML-based risk model——评分卡是 sanity check 的基础，先建立这个基线

---

## 2. 数据字段与单位（**关键**）

通过 2026-06-22 全市场快照实际验证：

| 字段 | 单位 | 验证示例 | 备注 |
|------|------|----------|------|
| `close` | 元 | 茅台 294.94，平安银行 10.65 | 复权后名义价格 |
| `pct_change` | **百分数** | 中国平安 5.27 = +5.27% | **不要再 × 100** |
| `turnover_rate` | **百分数** | 平安银行 0.61 = 0.61% | 同上 |
| `vol_atr_14` | **绝对价位差** | 茅台 6.61（≈ 2.24% of close） | **使用前必须 / close** |
| `roe` | **小数** | 茅台 0.3126 = 31.26% | |
| `pb` / `pe_ttm` | 倍数 | PB=2.79 中位数 | |
| `amount` | 元 | 中位 1.2 亿/天 | |
| `float_mv` / `total_mv` | 元 | | |
| `ma5/10/20/60` | 元（绝对） | | **无 ma250** |
| `consecutive_limit_up_days` | 天 | | 用于"已连板涨停"判定 |
| `is_st` | 0/1 | | 1 = ST 标记 |
| `listed_days` | 天 | | 上市天数，<90 为次新 |
| `volume = 0` | bool | 06-22 有 224 票停牌 | 停牌判定 |
| `macd_hist` | 浮点（柱状图值） | 正/负即可，绝对值无意义 | |

**数据缺失字段（v1 不使用）**：
- `main_flow`（主力净流入）— 100% NULL
- `flow_net_amount` — 100% NULL
- `inst_ownership` — 100% NULL
- `profit_growth` — 100% NULL

---

## 3. 风险维度与评分公式

### 3.1 维度总览

| # | 维度 | 权重 | 关键字段 | 数据可用 |
|---|------|------|---------|----------|
| 1 | 流动性 | **30%** | `amount` 20d 均, `float_mv`, `turnover_rate` | ✅ |
| 2 | 波动率 | **25%** | `vol_atr_14 / close`, `pct_change` | ✅ |
| 3 | 趋势恶化 | **25%** | `close vs ma60`, 均线排列, `macd_hist` | ✅ |
| 4 | 基本面 | **12%** | `roe`, `pb`, `pe_ttm` | ✅ |
| 5 | 状态 | **8%** + 一票否决 | `is_st`, `listed_days`, `volume`, `consecutive_limit_up_days` | ✅ |
| — | ~~资金面~~ | ~~15%~~ | ~~`main_flow` 等~~ | ❌ 缺数据，v2 再加 |

权重之和 = 1.0。

### 3.2 一票否决（任一触发，`risk_score = 100`，立即剔除）

```python
veto = (
    is_st == 1                                      # ST 或退市预警
    or listed_days < 90                              # 次新股不超 90 天
    or volume == 0                                   # 当日停牌
    or (pct_change > 9.5 and turnover_rate < 1.0)    # 涨停封板，追不进
)
```

**经验依据**：A 股 ST 股从风险/合规两方面都不该常规买入；次新股 90 天内有解禁、机构博弈、估值修正等多重不确定，量化模型外的风险敞口；停牌不可交易；涨停封板挂单也成交不了。

### 3.3 维度 1：流动性风险（满分 100，权重 30%）

```python
liq_score = clip(0, 100,
    # 部分 A：20 日平均成交额（最重要）
    100  if amount_20d < 1e7  else      #  < 1000 万：极度危险
    70   if amount_20d < 3e7  else      #  < 3000 万：高风险
    40   if amount_20d < 5e7  else      #  < 5000 万：中等
    15   if amount_20d < 1e8  else      #  < 1 亿：偏紧
    0                                   #  ≥ 1 亿：充足
  + 
    # 部分 B：流通市值（次要）
    20   if float_mv < 1e9  else        #  < 10 亿：超小盘
    10   if float_mv < 2e9  else        #  < 20 亿：小盘
    0
  + 
    # 部分 C：换手率异常
    15   if turnover_rate > 15 else     # > 15%：投机泡沫
    8    if turnover_rate < 0.3 else    # < 0.3%：流动性停滞
    0
)
```

**阈值依据**（2026-06-22 全市场实测）：
- 成交额中位 1.2 亿，5% 分位 2000 万 → 1000 万阈值能精准识别"几乎没人交易"的票
- 流通市值 20 亿是 A 股小盘股传统门槛
- 换手率中位 2.61%，p99 = 20.7% → 15% 是公认的过度活跃线
- 0.3% 以下的换手率几乎等同于停滞

### 3.4 维度 2：波动率风险（满分 100，权重 25%）

```python
atr_pct = vol_atr_14 / close * 100   # 转百分比

vol_score = clip(0, 100,
    # 部分 A：基础波动率（最重要）
    80   if atr_pct > 8    else         # > 8%：极端波动
    55   if atr_pct > 6    else         # > 6%：高波动
    30   if atr_pct > 4.5  else         # > 4.5%：偏高
    10                                  # ≤ 4.5%：正常
  + 
    # 部分 B：当日异动加成
    15   if abs(pct_change) > 7 else 0  # 当日 ±7% 以上视为异动
)
```

**阈值依据**：
- ATR%/close 中位 4.98%, p75 = 6.28%, p95 = 8.80%
- 6% 是 A 股个股波动率"过山车"区间
- 4.5% 卡在中位线略上，给市场正常状态打个 30 分基础分（合理保守）

### 3.5 维度 3：趋势恶化（满分 100，权重 25%）

```python
trend_score = clip(0, 100,
    40   if close < ma60       else 0   # 跌破 60 日线（系统级走坏）
  + 30   if (ma5 < ma10 < ma20 < ma60) else 0   # 完美空头排列
  + 20   if macd_hist < 0       else 0   # MACD 红柱转绿
  + 10   if close < ma20       else 0   # 跌破中期均线（辅助确认）
)
```

**经验**：
- A 股 60 日均线是中期多空分界，2026-06-22 实测 5526 票里 **3835 票（69%）跌破 ma60** → 当前整体偏弱，60 日线判定确实有区分力
- 均线空头排列（5<10<20<60）2026-06-22 共 2008 票（36%），是最纯净的下跌结构
- MACD 红柱 2433 票（44%），辅助参考

### 3.6 维度 4：基本面风险（满分 100，权重 12%）

```python
fund_score = clip(0, 100,
    # ROE（盈利能力）
    50   if roe < -0.05  else           # ROE < -5%：严重亏损
    30   if roe < 0      else           # ROE < 0：亏损
    15   if roe < 0.03   else           # ROE < 3%：低盈利
    0
  + 
    # PB（净资产估值）
    20   if pb < 0.8    else            # PB < 0.8：警惕净资产穿仓
    10   if pb < 1.0    else            # PB < 1.0：折价
    0
  + 
    # PE（估值合理性）
    20   if pe_ttm < 0  else            # PE < 0：亏损
    15   if pe_ttm > 200 else           # PE > 200：估值泡沫
    0
)
```

**经验**：
- ROE 2026-06-22 实测 5526 票中 **1144 票为负**（21%）—— A 股盈利能力分化很严重
- PB < 0.8 共 258 票（4.7%）—— 这些票多数是周期股或基本面恶化标的
- ROE 单调性已验证（高风险档平均 ROE -19.6%，极低风险档 +11.4%）

### 3.7 维度 5：状态风险（满分 100，权重 8%）

> 注：状态维度的一票否决已经在 §3.2 实现；这里 8% 权重只评估**非否决的**状态信号。

```python
status_score = clip(0, 100,
    60   if consecutive_limit_up_days >= 3 else   # 连板 3+：追高极险
    30   if consecutive_limit_up_days >= 2 else   # 连板 2：注意
    0
)
```

### 3.8 最终评分

```python
if veto:
    risk_score = 100  # 一票否决
else:
    risk_score = (
        0.30 * liq_score   +
        0.25 * vol_score   +
        0.25 * trend_score +
        0.12 * fund_score  +
        0.08 * status_score
    )
# risk_score 取值 [0, 100]
```

---

## 4. 评分聚合后的使用方式（与 `pred_score` 融合）

提供 3 种策略，**默认采用「连续折扣」**：

### 4.1 策略 A：连续折扣（默认）
```python
risk_discount = max(0, 1 - 0.01 * risk_score)
final_score = pred_score * risk_discount
# 解读：risk=0 → 不变；risk=50 → 半价；risk=100 → 归零
```

### 4.2 策略 B：阶梯门槛
```python
if risk_score > 80:                   final_score = 0
elif risk_score > 60:
    final_score = pred_score if pred_score >= top_5_percentile else 0
elif risk_score > 40:                 final_score = pred_score * 0.6
else:                                 final_score = pred_score
```

### 4.3 策略 C：仓位惩罚（组合层）
```python
# 选股仍取 top N，但配置权重时风险高仓位小
weight_i = base_weight_i * (1 - risk_score_i / 100) ** 2
weight = normalize(weight)
```

**策略选择**配置在 `fusion_rules.json` 的 `layer3_risk_gate.policy` 字段，默认 `"continuous_discount"`。

---

## 5. v1 评分卡分布验证（2026-06-22 全市场）

按上述公式跑 5526 票得到的分桶：

| 等级 | 数量 | 占比 | 平均价 | 平均 PB | 平均 ROE | 平均成交额 | 是否含 ST |
|------|------|------|--------|---------|----------|-----------|----------|
| 极低 (0-20) | 1446 | 26.2% | 21.5 元 | 5.64 | **+11.4%** | 19.7 亿 | 0 |
| 低 (20-40) | 2794 | 50.6% | 6.1 元 | 5.71 | +6.8% | 3.95 亿 | 0 |
| 中 (40-60) | 1000 | 18.1% | 2.6 元 | 4.88 | -4.8% | 26.8 亿 ⚠️ | 0 |
| 高 (60-80) | 38 | 0.7% | 0.8 元 | 4.23 | **-19.6%** | 2400 万 | 0 |
| 极高 (80+) | 248 | 4.5% | 3.0 元 | 29.15 | **-5828%** | 1.5 亿 | **225 全 ST** |

**单调性验证**：随风险等级升高 → 平均 ROE 单调下降、ST 比例只在极高档集中，符合预期。

**已知反常**：中风险档的"平均成交额 26.8 亿"被几支单日换手 >15% 的次新疯炒票拉高，**不影响个股判定**（中位数仍然低），但提醒后续观察。

---

## 6. 实现路线图（阶段 2/3/4）

### 阶段 2：后端服务（1 天）
- `backend/services/engine/risk_scoring/__init__.py`
- `backend/services/engine/risk_scoring/dimensions.py` — 5 个维度子分函数
- `backend/services/engine/risk_scoring/scorecard.py` — 聚合 + veto
- `backend/services/api/routers/risk_scoring.py` — `GET /api/v1/risk/score/{symbol}` + 批量
- Redis 缓存 TTL 60s（与 K 线一致）
- 单元测试（极端 case）

### 阶段 3：前端 UI 透出（1 天）
- `electron/src/services/researchService.ts`：加 `getRiskScore(symbol)`
- `electron/src/components/Research/RiskScoreCard.tsx`（新建）：5 维度水平条 + 总分徽章 + 触发提示文案
- `electron/src/pages/ResearchPlatformPage.tsx`：插入卡片到股票详情区

### 阶段 4：接入信号链 + 回测验证（1 天）
- `backend/services/engine/config/fusion_rules.json` — 扩展 `layer3_risk_gate` 配置：
  ```json
  {
    "enabled": true,
    "policy": "continuous_discount",
    "weights": {"liq": 0.30, "vol": 0.25, "trend": 0.25, "fund": 0.12, "status": 0.08},
    "veto": {"is_st": true, "min_listed_days": 90, "halted": true, "limit_up_locked": true}
  }
  ```
- 推理 pipeline 把 risk_discount 接进 `fused_pred.pkl` 生成处
- 回测 PK：Baseline (LGB top 50) vs Treatment (LGB×risk_discount top 50)，区间 2024-01-01 至 2026-06-01
- 看：年化收益、Sharpe、最大回撤、Calmar、换手率
- 产出 `docs/risk_scorecard_backtest_report.md`

---

## 7. 关键决策汇总

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 评分范围 | 0-100 整数 | 直观、易解释、UI 友好 |
| 维度数 | 5（v1）+ 资金面预留 | 简单、可验证、阈值有市场依据 |
| 一票否决 | ST/次新/停牌/封板 | 这 4 类不该出现在量化选股结果里 |
| 默认融合策略 | 连续折扣 (`pred × (1 - 0.01·risk)`) | 柔和、不丢候选、回测可观察边际 |
| 阈值来源 | 2026-06-22 实测分位数 + A 股经验 | 不拍脑袋，有数据依据 |
| 资金面维度 | 暂不实现 | 当前字段全 NULL，等数据补齐 |

---

## 8. 后续 v2 候选改进

1. **资金面维度上线**——等 `main_flow / flow_net_amount` 数据补齐
2. **行业相对风险**——同行业内分位数，避免周期股全行业一起被打高分
3. **历史风险演化**——把过去 5/20 日风险均值作为额外维度
4. **拥挤交易指标**——同 pred top 5% 内换手率/北向资金占比
5. **机器学习 risk model**——以历史最大回撤为 label 训练 LGB（要谨慎处理生存偏差）
