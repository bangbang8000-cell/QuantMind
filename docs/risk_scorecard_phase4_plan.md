# 阶段 4：风险评分卡接入信号链 — 落地建议

> 状态：**待执行**（阶段 1-3 已完成）
> 上游设计：[risk_scorecard_design.md](./risk_scorecard_design.md)
> 日期：2026-06-24

---

## 1. 当前已完成（v1）

- ✅ `docs/risk_scorecard_design.md` — 5 维度 + veto + 阈值定稿
- ✅ 后端 service：`backend/services/api/risk_scoring/`（34 单测全过）
- ✅ HTTP API：`GET /api/v1/risk/score/{symbol}` + `POST /api/v1/risk/scores`
- ✅ 前端卡片：投研平台股票详情页插入"风险评分卡 v1"，5 维度水平条 + 否决提示 + 高风险警示

**用户当前能看到的**：在投研平台点开任一支股票，详情页会显示评分 0-100、风险等级（极低/低/中/高/极高）、各维度明细以及触发的提示。

---

## 2. 阶段 4 要做的事

把评分卡从"展示工具"升级为"决策工具" —— **让评分实际影响选股结果**，并通过回测验证收益/风险比。

### 2.1 接入 fusion pipeline（半天）

#### 改动位置
- `backend/services/engine/config/fusion_rules.json` 的 `layer3_risk_gate`
- 推理 pipeline 生成 `fused_pred.pkl` 的入口（参见 `backend/services/engine/README.md:233`）

#### 配置扩展
```json
{
  "layer3_risk_gate": {
    "enabled": true,
    "policy": "continuous_discount",     // continuous_discount | threshold_gate | weight_penalty
    "weights": {
      "liquidity": 0.30, "volatility": 0.25, "trend": 0.25,
      "fundamental": 0.12, "status": 0.08
    },
    "veto": {
      "is_st": true,
      "min_listed_days": 90,
      "halt_on_zero_volume": true,
      "limit_up_locked": true
    },
    "discount": {
      "alpha": 0.01            // final = pred * max(0, 1 - alpha*risk)
    },
    "threshold": {              // 仅 policy=threshold_gate 时生效
      "veto_score": 80,
      "warning_score": 60,
      "warning_top_percentile": 0.05
    }
  }
}
```

#### Pipeline 集成代码骨架
```python
# backend/services/engine/inference/fusion_pipeline.py (示例)
from backend.services.api.risk_scoring import compute_risk_scores_batch

async def apply_risk_gate(pred_df, rules):
    if not rules.get("enabled"):
        return pred_df

    symbols = pred_df.index.get_level_values("symbol").unique().tolist()
    scores = await compute_risk_scores_batch(symbols)

    risk_arr = pred_df.index.get_level_values("symbol").map(
        lambda s: scores.get(s, {}).get("risk_score", 0)
    ).values

    policy = rules.get("policy", "continuous_discount")
    if policy == "continuous_discount":
        alpha = rules.get("discount", {}).get("alpha", 0.01)
        pred_df["pred"] = pred_df["pred"] * np.maximum(0, 1 - alpha * risk_arr)
    elif policy == "threshold_gate":
        # 见设计文档 §4.2
        ...
    elif policy == "weight_penalty":
        # 选股不变，权重配置时再用
        pred_df["risk_score"] = risk_arr
    return pred_df
```

#### 兼容性
- `enabled: false`（当前默认）→ 完全跳过，行为不变
- 第一次上线建议在测试环境 `policy: continuous_discount, alpha: 0.005`（弱折扣）观察一周后再调大

---

### 2.2 回测 PK（1-2 天）

#### 实验设计

| 维度 | Baseline | Treatment |
|------|----------|-----------|
| 模型 | LightGBM (当前已训) | 同 |
| 选股 | pred top 50 | (pred × risk_discount) top 50 |
| 周期 | 2024-01-01 ~ 2026-06-01 | 同 |
| 调仓频率 | 周频 | 同 |
| 基准 | SH000300 | 同 |
| 初始资金 | 100 万 | 同 |
| 手续费 / 滑点 | 0.00025 / 0.0005 | 同 |

#### 关键观察指标
- 年化收益（预期：treatment 略低 -1~-3%）
- **Sharpe**（预期：treatment +0.1~+0.3 — 主要价值在这）
- **最大回撤**（预期：treatment 显著改善 -10~-20%）
- **Calmar**（年化/最大回撤，预期 treatment 更优）
- 换手率（预期：treatment 略降，因为高 veto 票被排除后稳定性更好）
- 极端日表现（前 5% 下跌日的相对超额）

#### 验证清单
1. **单调性**：高 risk_score 票的实际未来 5/10/20 日波动率单调高于低 risk 票
2. **veto 命中率**：veto 触发的票若被 baseline 选入，未来 20 日跌幅大于均值
3. **alpha 网格搜索**：`alpha ∈ {0.005, 0.008, 0.01, 0.012, 0.015}` 看哪个 Calmar 最优
4. **行业平衡**：treatment 不应出现某个行业被全行业打高分（评分应是个股层而非行业层）

#### 输出
`docs/risk_scorecard_backtest_report.md` 包含：
- 上述全部指标对比表
- 年化净值曲线（baseline vs treatment）
- 月度超额收益分布
- 关键失败案例（baseline 选入但 treatment 剔除的股票，看是否真的塌方）

---

### 2.3 长尾改进（可选，3-5 天）

#### A. 在候选池表格里展示 risk badge
现在 `risk_score` 只在点开详情时才显示。下一步可以：
- 在选股结果表加一个"风险"列（颜色徽章）
- 但**需要批量为页面上的 N 票（≤100）一次性调 `/risk/scores`** —— 已有批量 API，加 React Query 缓存即可

#### B. 历史风险演化看板
- 一支票最近 60 个交易日的 risk_score 时间序列
- 帮助判断"是不是稳定的高风险股 vs 突然变高"
- 实现：加一个 `GET /api/v1/risk/history/{symbol}?days=60` 端点

#### C. 行业相对风险
- 同行业内分位数：避免周期股全行业一起被打高分
- 加权时除以该行业的 risk 中位数

#### D. 资金面维度上线（数据补齐后）
- 等 `main_flow / flow_net_amount / inst_ownership / profit_growth` 数据补齐
- 加入维度 6（设计文档已预留）

---

## 3. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 评分过于保守，年化收益降太多 | 中 | 中 | alpha 从 0.005 起，观察 1 月再上调 |
| 评分跟模型 pred 相关性太高（信息冗余） | 中 | 高 | 回测时检查 corr(pred, risk)，若 \|r\| > 0.5 重审权重 |
| veto 触发占比过高 | 低 | 高 | 实测 06-22 仅 248 票（4.5%）被 veto，可控 |
| 算分逻辑回归到了 ML 模型（高分票表现差） | 低 | 高 | 阈值都基于经验+实测分位数，rules-based 比 ML 稳健 |

---

## 4. 执行顺序建议

1. **先回测 PK**（不动 pipeline）—— 在 notebook 里加载历史 pred + 历史 risk_score，离线乘出 final_score 跑回测，1-2 天
2. **若 Sharpe / Calmar 显著改善**，再上 pipeline 改造，灰度（`enabled: true, alpha: 0.005`）
3. **观察 1-2 月生产数据**，逐步上调 alpha 到 0.01

---

## 5. 关闭条件

阶段 4 视为完成的标志：
- ✅ 回测报告显示 Sharpe ≥ baseline + 0.1 **或** 最大回撤改善 ≥ 10%
- ✅ `fusion_rules.json` 配置可灰度开关
- ✅ 至少 1 月生产观察期，risk_discount 接入对实盘信号无显著负向影响

否则**回滚到 v1**（只展示，不影响选股）。
