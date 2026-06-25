#!/usr/bin/env python3
"""
重建完整历史数据的 core parquet (2016-2026)
从 yearly parquet 文件中提取 78 个核心因子
"""

import os
import sys
from pathlib import Path
import pandas as pd
import pyarrow.parquet as pq

# 路径配置
if os.path.exists("/app"):
    DATA_DIR = Path("/app/db/feature_snapshots")
else:
    DATA_DIR = Path("/workspace/quantmind/db/feature_snapshots")

# 核心因子列表 (78个)
CORE_FACTORS = [
    # 基础行情 (6)
    'close', 'open', 'high', 'low', 'volume', 'amount',
    # 动量 (11)
    'mom_ret_1d', 'mom_ret_5d', 'mom_ret_20d', 'mom_ret_60d',
    'mom_ma_gap_5', 'mom_ma_gap_20',
    'mom_macd_hist', 'mom_rsi_14', 'kdj_k',
    'mom_breakout_20d', 'mom_sharpe_20',
    # 波动率 (9)
    'vol_std_20', 'vol_atr_14',
    'vol_parkinson_20', 'vol_downside_20', 'vol_upside_20',
    'vol_realized_rv', 'vol_realized_rrv',
    'vol_jump_zadj',
    # 成交量 (6)
    'liq_volume', 'liq_amount', 'liq_turnover_os',
    'liq_volume_ratio_5', 'liq_mfi_14', 'liq_amihud_20',
    # 资金流 (7)
    'flow_net_amount', 'flow_net_amount_ratio', 'flow_large_net_amount',
    'flow_vpin', 'flow_vpin_ma_5', 'flow_vpin_ma_20',
    'flow_pressure_index',
    # 风格因子 (7)
    'style_ln_mv_total', 'style_ln_mv_float', 'style_beta_20',
    'style_beta_60', 'style_idio_vol_20',
    'style_bp', 'style_ep_ttm',
    # 行业因子 (4)
    'ind_ret_1d', 'ind_ret_20d', 'ind_strength_20',
    'ind_momentum_rank_20',
    # 技术形态 (8)
    'kline_kmid', 'kline_klen', 'kline_kup2', 'kline_klow2',
    'kline_ksft2', 'prel_vwap0', 'tech_bollinger_position', 'tech_cci_20',
    # Alpha因子 (7)
    'alpha_decay_ret_10', 'alpha_corr_cv_20', 'alpha_tsrank_ret_20',
    'alpha_high_20d_ratio',
    'alpha_close_open_gap', 'fund_pe_percentile', 'fund_pb_percentile',
    # 趋势质量 (3)
    'trend_r2_20', 'trend_slope_20', 'pv_corr_20',
    # 基础列
    'symbol', 'trade_date', 'industry', 'is_st', 'listing_market',
]


def main():
    import pyarrow as pa
    import pyarrow.parquet as pq

    print("=" * 70)
    print("重建完整历史 Core Parquet (2016-2026) - 分块处理模式")
    print("=" * 70)

    # 查找所有 yearly parquet 文件
    yearly_files = sorted(DATA_DIR.glob("model_features_20*.parquet"))
    yearly_files = [f for f in yearly_files if "core" not in f.name and "hk" not in f.name and "us" not in f.name and "crypto" not in f.name]

    if not yearly_files:
        print(f"❌ 未找到 yearly parquet 文件: {DATA_DIR}")
        sys.exit(1)

    print(f"\n找到 {len(yearly_files)} 个 yearly parquet 文件:")
    total_size = 0
    for f in yearly_files:
        size_mb = f.stat().st_size / (1024 * 1024)
        total_size += size_mb
        print(f"  {f.name}: {size_mb:.1f} MB")
    print(f"  总计: {total_size:.1f} MB")

    output_path = DATA_DIR / "model_features_core.parquet"
    writer = None
    total_rows = 0

    # 分块处理每个 yearly 文件
    for f in yearly_files:
        print(f"\n处理 {f.name}...")
        try:
            # 读取 schema 以确定可用列
            pf = pq.ParquetFile(f)
            available_cols = [c for c in CORE_FACTORS if c in pf.schema_arrow.names]
            missing_cols = [c for c in CORE_FACTORS if c not in pf.schema_arrow.names]

            if missing_cols and total_rows == 0:
                print(f"  ⚠️ 缺失列 (前5个): {missing_cols[:5]}")

            # 分块读取（每次 10 万行）
            for batch in pf.iter_batches(batch_size=100000, columns=available_cols):
                df = batch.to_pandas()

                # 数值列转为 float32 以节省内存
                for col in df.columns:
                    if col not in ['symbol', 'trade_date', 'industry', 'listing_market']:
                        if pd.api.types.is_numeric_dtype(df[col]):
                            df[col] = df[col].astype('float32')

                # 转换为 PyArrow Table
                table = pa.Table.from_pandas(df, preserve_index=False)

                # 初始化 writer（使用第一个 batch 的 schema）
                if writer is None:
                    writer = pq.ParquetWriter(output_path, table.schema, compression='snappy')

                writer.write_table(table)
                total_rows += len(df)

                if total_rows % 500000 == 0:
                    print(f"  已处理 {total_rows:,} 行...")

        except Exception as e:
            print(f"  ❌ 处理失败: {e}")
            import traceback
            traceback.print_exc()
            continue

    # 关闭 writer
    if writer:
        writer.close()
        print(f"\n✅ 写入完成!")
    else:
        print("❌ 没有成功写入任何数据")
        sys.exit(1)

    # 验证输出文件
    if output_path.exists():
        size_mb = output_path.stat().st_size / (1024 * 1024)
        pf_out = pq.ParquetFile(output_path)
        print(f"\n📊 输出文件统计:")
        print(f"  文件: {output_path}")
        print(f"  大小: {size_mb:.1f} MB")
        print(f"  行数: {total_rows:,}")
        print(f"  列数: {len(pf_out.schema_arrow.names)}")
        print(f"  列名: {pf_out.schema_arrow.names[:10]}...")
    else:
        print(f"❌ 输出文件不存在: {output_path}")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("✅ 完成! Core parquet 已重建")
    print("=" * 70)


if __name__ == "__main__":
    main()
