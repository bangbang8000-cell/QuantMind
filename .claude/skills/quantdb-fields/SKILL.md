---
name: quantdb-fields
description: "QuantDB 字段单位速查手册 — 全部数据集实测验证的单位、口径与陷阱（个股 volume=股/amount=万元、指数 volume=手、technical % vs l1 小数、dividend_rate 百分数、PG 前缀 symbol）。用 QuantDB 数据做分析/回测/报告、判断成交量/成交额/股息率/换手率单位、排查数据口径不一致时使用。触发词：字段单位、成交量单位、成交额单位、股还是手、万元、股息率、数据口径"
---

# quantdb-fields — QuantDB 字段单位速查手册

> 用 QuantDB 数据做任何分析/回测/报告前**必读**。所有单位均为
> **2026-08 直接读本地 parquet 实测验证**（不是照抄文档）。
> 单位搞错的后果：成交额差 1 万倍、股息率差 100 倍、换手率差 100 倍——
> 分析结论全部作废。

## 一、通用规则（先记这个）

| 规则 | 说明 |
|---|---|
| **个股成交量 = 股** | A 股 1 手 = 100 股，但 QuantDB 个股 kline 的 `volume` 单位就是**股**，不是手 |
| **个股成交额 = 万元** | `amount = 5828.37` 表示 5828.37 **万元**（约 5828 万），不是元 |
| **指数成交量 = 手** | `index_daily.volume` 单位是**手**（1 手 = 100 股），与个股相反！ |
| **市值 = 元** | valuation 的 `total_mv/float_mv` 单位是**元**（工业富联 float_mv ≈ 1.31 万亿） |
| **比例字段 ≈ 小数或 %** | 没有统一约定，按数据集查下表；% 的字段值 = 百分数（4.06 即 4.06%） |
| **symbol 格式按数据源分** | parquet 用**后缀** `601138.SH`；PG 的 `stock_daily_latest` 用**前缀** `SH601138` |
| **验证公式** | 个股 `close*volume/amount ≈ 1e4`（股+万元）；指数 ≈ 2e4（手+万元） |

## 二、1_kline_data 日线（daily_forward / daily_backward / daily_unadjusted）

| 字段 | 单位 | 实测依据 |
|---|---|---|
| `volume` | **股** | 601138 20260814 volume=4704920 股，amount=5828.37 万元，close*volume/amount≈1e4 |
| `amount` | **万元** | 同上（close 66.19 × 470 万股 ≈ 3.1 亿 ≈ 31163 万元，与 amount 同量级吻合） |
| `open/high/low/close` | 元（forward=前复权，backward=**后复权**，unadjusted=不复权） | |
| 单位切换传闻 | **不存在**。20260721 前后 amount 均为万元、volume 均为股。曾有记忆说 20260721 切换到"手/元"，实测已无此切换，按股/万元统一处理 | |

**min1/min5**：同单位（volume=股、amount=万元），但数据**停滞在 2026-07-24**，用前先查最新日期。

## 三、1_kline_data/index_daily 指数日线（⚠️ 与个股相反）

| 字段 | 单位 | 实测依据 |
|---|---|---|
| `volume` | **手**（×100=股） | 上证 000001.SH 20260814 volume=499525600 手 = 499.5 亿股（合理）；close*volume/amount=19808≈2e4 |
| `amount` | **万元** | 99037192 万元 = 9903.7 亿元 ≈ 上证单日成交额 ✓ |
| `close` | 点位 | 3927.18 |

> 反推：指数平均股价 = close×100/(close×volume/amount) = close×100/19808 ≈ 19.8 元/股，符合 A 股平均股价，故 volume 必为手。

## 四、5_technical_derived 技术衍生

### valuation（估值）
| 字段 | 单位 | 注意 |
|---|---|---|
| `close` | 元，**不复权** | 601138 close=66.19（与 technical_indicators 的后复权 close=70.05 不同） |
| `total_mv / float_mv` | **元** | float_mv=1313480468277.96 ≈ 1.31 万亿 ✓ |
| `total_capital / circulating_capital` | 股 | 19844092284 股 ≈ 198.4 亿股 |
| `net_profit_ttm / revenue_ttm / equity / annual_net_profit` | 元 | |
| `pe_ttm / pe_static / pb / ps_ttm` | 倍 | |
| `dividend_rate` | **%（百分数值）** | 0.148 = **0.148%**！公式 = 近一年每10股派息/10/close×100。601138: 0.98/10/66.19×100=0.1481 ✓；600519: 51.98/10/1341.99×100=0.3873 ✓。**把它当小数会差 100 倍** |
| `dividend_rate` 口径切换 | **20260814 起** | 此前为小数口径（每10股派息/不复权close，如 0.98/65.60=0.01494）；20260814 起切换为百分数口径（×100）。同字段历史不连续，跨 20260814 分析需 ×10 归一 |

### technical_indicators（技术指标）
| 字段 | 单位 | 陷阱 |
|---|---|---|
| `close` | **后复权** | 601138=70.05，与不复权 66.19 不同；凡基于 close 算的指标都是后复权口径 |
| `volume_ma_3/5` | 股 | |
| `amount_ma_5` | 万元 | |
| `pct_change` | **%** | 1.4717 = 1.47% |
| `return_1d / return_20d` | 缺失（NaN） | 别用，改用 pct_change |
| `vol_std_20` | **%** | 4.0578 = 4.06%（l1 里同名字段是小数 0.0406，差 100 倍！） |
| `vol_atr_14` | **元** | 3.58 元（l1 同名字段也是元，一致） |
| `macd_hist / rsi_14 / kdj_*` | 原始指标值 | 与 l1 一致 |

### market_sentiment（市场情绪）
| 字段 | 单位 |
|---|---|
| `close` | 不复权 |
| `turnover_rate` 等比率 | 小数（0.02 = 2%） |
| `momentum_*` | %（百分数值） |

## 五、6_ml_datasets 因子

### features_daily（技术+估值合并表）
| 字段 | 单位 | 注意 |
|---|---|---|
| `dividend_rate` | **小数口径（无 ×100）** | 与 valuation 不同！公式 = 每10股派息/不复权close（0.98/66.19=0.0148），**从未切换口径**。valuation 20260814 起是它的 10 倍。特征快照 generate_feature_snapshots.py 已 ×10 归一到百分数口径 |
| `total_mv / float_mv / pe / pb 等` | 与 valuation 完全一致 | 实测 601138 全部 ✓ |

### l1_factors（一级因子，decimal 为主）
| 字段 | 单位 |
|---|---|
| 收益率类 `mom_ret_*` | 小数（0.0147 = 1.47%） |
| `vol_std_*` | **小数**（0.0406 = 4.06%；与 technical_indicators 的 % 版本差 100 倍） |
| `vol_atr_14` | **元**（3.55 元） |
| `fun_total_mv` | **ln(市值元)** —— 用时要 exp() |
| 分位数/percentile 字段 | 0~1 小数 |
| `liq_* / fun_turnover / fun_mv` | 部分日期为 None，注意补缺 |

### l2_factors（二级因子，flow 金额注意）
| 字段 | 单位 | 实测依据 |
|---|---|---|
| `flow_net_amount / flow_super_net / flow_large_net / flow_medium_net / flow_small_net` | **元** | 600519 flow_net_amount=-274109797.7 元 = -2.74 亿；flow_net_amount/(amount×1e4)=flow_net_ratio ✓ |
| `flow_*_ratio` | 小数 | |
| `vol_turnover_total` | **股** | 与 kline volume 完全相等 ✓ |
| 分区 | **停滞在 dt=20260227** | 用前先查最新分区日期 |

## 六、PG 表 stock_daily_latest（API 服务数据源）

| 列 | 单位 / 格式 | 实测依据 |
|---|---|---|
| `symbol` | **前缀格式** `SH601138`（不是 601138.SH） | suffix 查询 0 行，prefix 查询 1072 万行 |
| `volume` | 股 | 601138 max_volume=633217088 股 |
| `amount` | **万元** | 601138 amount=5828.37，max_amount=3306339（万元） |
| `float_mv / total_mv` | 元 | float_mv=7095151630 元 |
| `turnover_rate / flow_net_amount / main_flow` | **NULL**（未灌） | 风险评分里"缺少换手率"由此而来 |
| `volume_ratio_5` | 倍（0.934） | |

**flow 灌入口径**（update_sdl_complete_pipeline.py）：`main_flow = flow_large_net_amount/1e6`（**百万元**），`flow_net_amount = flow_net_amount/1e6`（**百万元**）——与 l2 parquet 的元不同，读 PG 时注意。

## 七、research API 换算表（/research/features 等接口返回）

API 层 `_UNIT_SCALES` 把部分字段缩放后输出：

| 输出字段 | 缩放 | 输出单位 | 例（600519 探针） |
|---|---|---|---|
| `totalMv / floatMv` | ×1e-8 | 亿元 | 16775.97 亿 ✓ |
| `mainFlow / flowNetAmount / flowLargeNet / flowMediumNet / flowSmallNet` | ×1e-6 | 百万元 | flow_net_amount=-274.11（百万） |
| **`flowSuperNet`** | **无缩放** | **元（bug！）** | flow_super_net=-6840376 元，与同类别其他字段差 1e6 |
| `turnoverRate` | — | % 小数 | 0.00239 |

> ⚠️ **fundFlow 类别内单位不一致**：flowSuperNet 是元，其余 flow* 是百万元。skill 分析时要统一换算后再比。

## 八、3_financial_data 财务数据

| 数据集 | 字段 | 单位 |
|---|---|---|
| `balance / income / cashflow` | 各科目 | 元 |
| `capital` | 股本 | 股 |
| `holder_num` | 股东户数 | 户 |
| `dividend_factors` | `interest` | **每10股派息（元）**——600519 每10股派 51.98 元，601138 派 0.98 元。算每股股息要 /10 |
| `dividend_factors` | `stockBonus / stockGift / allotNum` | 每10股送/转/配股数 |
| `dividend_factors` | `dr` | 除权因子（复权用） |

## 九、2_base_sector

| 数据集 | 字段 | 单位 | 注意 |
|---|---|---|---|
| `instrument_detail` | `Symbol` | 后缀 601138.SH | HqDate 停滞 **20260720**，市值/估值滞后 |
| | `J_zgb / FreeLtgb` | **万股**（1984409.25 万股 = 198.4 亿股） | 与 valuation 的 circulating_capital(股) 差 1e4 |
| | `J_yysy / J_jly / J_zzc` 等 J_* | **万元**（25107808 万 = 251 亿） | 与 financials 的元差 1e4 |
| | `Zsz / Ltsz` | **亿元**（11211.91 亿 ✓） | |
| | `J_mgsy` | 元（2.14 元/股） | |
| | `fHSL` | 不明（0.56，非换手率%，与自算 0.74% 不符），**别当换手率用** | |
| | `TotalBVol` | 不明（43555，量级像手，但远小于全天量） | L2 快照字段，非全天 |
| | `DYRatio` | 不可靠（600519=4.15 vs 真实 0.39%），**别当股息率**，用 valuation.dividend_rate | |
| | `Yield` | 不明（6078.44），勿用 | |
| `index_weights` | `Weight` | **%** | 文件名 `000300.SH.parquet` 不是 `000300.parquet` |
| `trading_calendar` | `TradingDate` | YYYYMMDD int | |

## 十、其他数据集

| 数据集 | 字段 | 单位 | 状态 |
|---|---|---|---|
| `margin_trading` | `finance_*` | 万元 | |
| | `slo_volume / slo_net` | 股 | |
| `hsgt_north` | `holding_quantity` 股 / `holding_value` 元 / 比率 % | | **停滞 2024-08**（北向改季度披露后） |

## 十一、已知数据缺口（2026-08 实测）

1. **min1/min5** 分钟线停更（最新 2026-07-24）
2. **l2_factors** 分区停更（dt 止于 20260227）
3. **hsgt_north** 北向明细停更（2024-08，改季度披露所致）
4. **instrument_detail** HqDate 滞后（20260720）
5. **dt=20260729~20260802** 个股日线有同步缺口（非交易日+同步中断）
5b. **valuation dt=20260813** 只有 101 行（同步缺口，dividend_rate 全 NaN），features_daily 同日 5543 行正常
6. **technical_indicators.return_1d/return_20d** 全 NaN
7. **stock_daily_latest** 的 turnover_rate/flow_net_amount/main_flow 常为 NULL

## 十二、分析前检查清单

- [ ] 确认数据源是 parquet 还是 PG/API（单位体系不同）
- [ ] symbol 格式匹配数据源（parquet 后缀 / PG 前缀）
- [ ] 成交量：个股=股，指数=手
- [ ] 成交额：万元（API 输出已缩放为亿/百万）
- [ ] 波动率：technical_indicators 是 %，l1 是小数（差 100 倍）
- [ ] 股息率：valuation.dividend_rate 是 % 百分数值（0.148=0.148%），不是小数
- [ ] close 口径：technical_indicators 是后复权，valuation 是不复权
- [ ] 市值：parquet 是元，instrument_detail 是亿元/万股，API 是亿元
- [ ] 财务：financials 是元，instrument_detail J_* 是万元
- [ ] 用前查数据最新日期（分钟线、l2、hsgt 都可能已停更）
