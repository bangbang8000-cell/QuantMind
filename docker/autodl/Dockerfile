# QuantMind AutoDL 远程训练镜像
#
# 用途：作为 AutoDL GPU 训练节点的运行镜像。主节点通过 SSH 在此镜像上
#       docker run 启动训练容器（python /app/train.py --config config.yaml）。
#
# 说明：
#   - 直接基于 quantmind-oss（已含 CUDA + qlib + lightgbm/xgboost/catboost/torch）
#     精简，仅去除不必要的服务代码，保留训练脚本与特征生成脚本。
#   - 不设置 ENTRYPOINT —— 训练命令由主节点 SSH docker run 时指定。
#
# 构建：
#   docker build -f docker/autodl/Dockerfile -t quantmind-autodl:latest .

FROM quantmind-oss:latest

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

# 训练脚本（与本地 LocalDockerOrchestrator 挂载的是同一份）
COPY docker/training/train.py /app/train.py

# 特征生成脚本（供主节点推送 QuantDB 后远端算特征）
COPY backend/scripts/generate_feature_snapshots.py /app/scripts/generate_feature_snapshots.py
COPY backend/scripts/update_feature_parquet.py /app/scripts/update_feature_parquet.py

# 训练工作目录（主节点 rsync 特征快照/config 到此，产物也在此）
RUN mkdir -p /workspace

# 无 ENTRYPOINT/CMD —— 由主节点指定训练命令
