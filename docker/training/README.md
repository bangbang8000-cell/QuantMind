# docker/training

用途：训练容器内的模型训练入口脚本与运行时辅助文件。

## 说明
- 统一运行镜像为 `quantmind-ml-runtime:latest`。
- `train.py` 会在用户提交特征的基础上自动补齐 6 个基础特征：`mom_ret_1d`、`mom_ret_5d`、`mom_ret_20d`、`liq_volume`、`liq_amount`、`fun_turnover_1`。
- `metadata.json` 现在会同时记录三层口径：
  - `requested_feature_count/requested_features`：前端提交的特征
  - `auto_appended_feature_count/auto_appended_features`：训练脚本自动补齐的基础特征
  - `feature_count/features/feature_columns`：最终实际入模特征
- 训练结束后默认生成 `shap_summary.csv`，使用 LightGBM 原生 `pred_contrib=True` 计算 SHAP 汇总贡献度；默认读取验证集、采样 30000 行，并在 `metadata.json.shap` 中记录状态、样本数、耗时和错误信息。SHAP 失败不会阻断训练完成。
- 前端训练页会据此展示“提交特征数 / 自动补充特征 / 实际入模特征数”，便于排查维度不一致问题。

## 多核 / 多线程控制

树模型与因子筛选默认用满机器所有 CPU 核心，可通过环境变量限制：

| 环境变量 | 默认 | 说明 |
|----------|------|------|
| `TRAIN_IC_WORKERS` | min(CPU 核数, 特征数, 交易日数) | 因子筛选（日频 Rank IC 计算）的并行进程数；设 `0` 或 `1` 退化为串行 |
| `TRAIN_NTHREADS` | `-1`（全部核心） | 各树模型框架（LightGBM/XGBoost/CatBoost/RandomForest）的线程数 |

- 因子筛选原为单核嵌套循环（2026 单年快照实测 79 秒，全量多年训练集估约 15-20 分钟），现改为多进程并行
  （`parallel_utils.py`，fork 共享内存零拷贝），**数值与串行版逐日 spearmanr 完全一致**。
- 并行按**交易日分块**（而非按特征分块）：父进程一次性 `groupby('trade_date')` 后，
  把日期区间切成 N 段分发给各 worker，每行数据只被一个 worker 读取——内存带宽真正分摊，
  20 核实测 7.9×（按特征分块时每个 worker 都要扫全表，16 worker 反而慢于 8 worker）。
- LightGBM 原生 API 的线程参数名是 `num_threads`（`n_jobs` 是 sklearn 层别名，
  直接传给 `lgb.train()` 会被忽略导致多核不生效），`train.py` 已修正并透传 `TRAIN_NTHREADS`。
- 多模型/OOF/DeepLearning 同时训练时内存叠加易 OOM，内存紧张时可
  设置 `TRAIN_NTHREADS=4` 限制单个模型线程数。
- 编排器（本地 Docker / 远端 AutoDL）会自动挂载/同步 `parallel_utils.py` 与 `train.py` 同目录。
