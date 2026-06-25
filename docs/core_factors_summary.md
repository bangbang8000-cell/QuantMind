# 核心因子集 (Core Factors) - 精简版

## 概览

从原始 197 个因子中精选 **78 个核心因子**，去除冗余和低 IC 因子。

| 指标 | 原始版 | 精简版 | 优化 |
|------|--------|--------|------|
| 总列数 | 197 | 89 (11 base + 78 factors) | -55% |
| 文件大小 | ~1 GB | 381 MB | -62% |
| 因子数 | 186 | 78 | -58% |

## 因子分布 (78个)

| 类别 | 数量 | 代表因子 |
|------|------|----------|
| **动量** | 10 | mom_ret_60d (IC最高), mom_sharpe_20, mom_rsi_14 |
| **波动率** | 8 | vol_realized_rrv (IC高), vol_std_20, vol_parkinson_20 |
| **流动性** | 6 | liq_mfi_14, liq_amihud_20, liq_turnover_os |
| **资金流** | 7 | flow_large_net_amount (已修复), flow_vpin_ma_20 |
| **风格** | 7 | style_ln_mv_total (已修复), style_beta_20 |
| **基本面** | 8 | roe (IC最高), ep_ttm, pb |
| **行业** | 4 | ind_ret_20d (已修复), ind_strength_20 |
| **K线** | 6 | kline_kmid, kline_kup2, prel_vwap0 |
| **技术** | 5 | tech_bollinger_position, tech_cci_20, kdj_k |
| **Alpha** | 7 | fund_pb_percentile (IC最高!), alpha_high_20d_ratio |
| **趋势** | 3 | trend_r2_20, trend_slope_20, pv_corr_20 |
| **价格位置** | 3 | price_position_20, dist_to_high_20 |
| **指数/概念** | 4 | idx_hs300, concept_new_energy |

## 关键修复 (已应用)

1. ✅ **行业因子**: 从硬编码 0 → 真实计算 84 个行业
2. ✅ **流通市值**: 从 `total * 0.9` → 使用实际 float_mv
3. ✅ **总市值**: 从 `log(amount)` → 使用实际 total_mv
4. ✅ **大单资金流**: 从硬编码 0 → 使用 main_flow 或大单近似
5. ✅ **BP/EP**: 增加 fallback (1/pb, 1/pe_ttm)
6. ✅ **lookback 窗口**: 120天 → 180天 (解决长期因子 null)

## Top 10 高 IC 因子

| 因子 | IC | ICIR | 说明 |
|------|----|------|------|
| fund_pb_percentile | 0.093 | 1.27 | PB历史分位 (价值投资核心) |
| roe | 0.094 | 1.06 | ROE (质量因子之王) |
| ep_ttm | 0.097 | 0.59 | 盈利收益率 |
| mom_ret_60d | 0.073 | 0.61 | 60日动量 |
| mom_sharpe_60 | 0.072 | 0.58 | 风险调整动量 |
| alpha_high_20d_ratio | 0.074 | 0.57 | 创新高频率 |
| trend_r2_20 | 0.035 | 0.48 | 趋势质量 |
| ind_ret_20d | 0.055 | 0.47 | 行业收益 |
| vol_realized_rrv | 0.034 | 0.57 | 相对波动率 |
| style_bp | 0.040 | 0.45 | 账面市值比 |

## 文件位置

- **精简版**: `/app/db/feature_snapshots/model_features_core.parquet`
- **完整版**: `/app/db/feature_snapshots/model_features_2026.parquet`
- **因子目录**: `/app/db/feature_snapshots/core_factors.csv`

## 使用建议

### 模型训练
```python
# 使用精简版 (推荐)
df = pd.read_parquet('/app/db/feature_snapshots/model_features_core.parquet')

# 或使用完整版 (需要全部因子时)
df = pd.read_parquet('/app/db/feature_snapshots/model_features_2026.parquet')
```

### 日常更新
```bash
# 更新完整版
python backend/scripts/update_feature_parquet.py --since 2026-06-01

# 重新生成精简版
python backend/scripts/select_core_factors.py
```

## 被移除的因子 (119个)

### 冗余因子 (相关性 > 0.85)
- 短期动量: mom_ret_3d, mom_ret_10d (与 mom_ret_5d/20d 高度相关)
- 波动率: vol_std_5, vol_std_10 (与 vol_std_20 高度相关)
- 流动性: liq_volume_ma_5/10/60 (与 liq_volume_ma_20 高度相关)
- 均线偏离: mom_ma_gap_10/60/120 (与 mom_ma_gap_5/20 高度相关)

### 低 IC 因子 (IC < 0.01)
- 部分概念因子: concept_medical, concept_consumption, concept_state_owned
- 部分技术因子: tech_macd_cross, tech_ma_cross_5_20
- 部分风格因子: style_residual_ret_20

### 二进制因子 (信息量有限)
- concept_chip, concept_ai (0/1 值，单调性检验无效)
- idx_zz1000, idx_chinext (成分股标记)

## 下一步

1. ✅ 已创建精简版 parquet
2. ✅ 已修复 6 个关键 bug
3. ⏳ 建议: 使用精简版训练模型，对比完整版效果
4. ⏳ 建议: 每月重新评估因子 IC，动态调整核心因子集

---
**生成时间**: 2026-06-23  
**数据范围**: 2026-01-05 ~ 2026-06-23  
**股票数量**: 11,340
