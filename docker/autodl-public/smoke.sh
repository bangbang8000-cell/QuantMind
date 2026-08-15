#!/bin/bash
# QuantMind 公共镜像自测：验证 /root/QuantMind 仓库代码可执行
# 1) 训练预处理纯函数（cross_sectional_preprocess 全链路，真实 API）
# 2) LightGBM 训练/预测往返
# 3) torch + CUDA 可用性检测（无 GPU 时自动跳过 CUDA 断言）
set -euo pipefail

echo "=== [1/3] 训练预处理（preprocessing.py 真实代码） ==="
python3 - <<'PY'
import sys
sys.path.insert(0, "/root/QuantMind/docker/training")
import numpy as np
import pandas as pd
from preprocessing import binarize_labels, winsorize, cross_sectional_median_fill, cross_sectional_zscore, cross_sectional_preprocess

# binarize_labels：正收益→1，其余→0，NaN 透传
y = np.array([0.02, -0.01, 0.0, 0.05, -0.03])
out = binarize_labels(y)
assert out.dtype == np.float32
assert out.tolist() == [1.0, 0.0, 0.0, 1.0, 0.0]

# winsorize：极端值被钳到分位边界（n<10 不缩尾是设计行为，需足够样本）
rng_w = np.random.RandomState(0)
x = np.concatenate([rng_w.randn(18), [-100.0, 100.0]])
w = winsorize(x, quantiles=(0.1, 0.9))
assert abs(w.max()) < 5.0, w

# 全链路截面预处理：真实 API 按 trade_date 分组；fill 消除 NaN，
# zscore 对 NaN 透传（下游 dropna）
rng = np.random.RandomState(42)
df = pd.DataFrame(rng.randn(100, 6), columns=[f"f{i}" for i in range(6)])
df["trade_date"] = np.repeat(["2026-08-01", "2026-08-02"], 50)
df.iloc[5, 2] = np.nan  # 注入缺失值
feats = [f"f{i}" for i in range(6)]
filled = cross_sectional_median_fill(df, feats)
assert not filled.isna().any().any(), "中位数填充应消除 NaN"
z = cross_sectional_zscore(df, feats, winsor=True)
assert z.shape == (100, 7)
assert z[feats].dtypes.apply(lambda d: np.issubdtype(d, np.number)).all()
out = cross_sectional_preprocess(df, feats, enabled=True, winsor=True)
assert out.shape == (100, 7)
assert np.isclose(out.loc[0, "f0"], z.loc[0, "f0"])
print("preprocessing OK: binarize/winsorize/median_fill/zscore/preprocess")
PY

echo "=== [2/3] LightGBM 训练/预测往返 ==="
python3 - <<'PY'
import sys
sys.path.insert(0, "/root/QuantMind/docker/training")
import lightgbm as lgb
import numpy as np
import pandas as pd
from preprocessing import cross_sectional_preprocess

rng = np.random.RandomState(7)
df = pd.DataFrame(rng.randn(500, 8), columns=[f"f{i}" for i in range(8)])
df["trade_date"] = np.repeat(["2026-08-01"], 500)
feats = [f"f{i}" for i in range(8)]
X = cross_sectional_preprocess(df, feats, enabled=True)[feats]
y = rng.randn(500)

model = lgb.LGBMRegressor(n_estimators=50, num_leaves=15, n_jobs=2, verbosity=-1)
model.fit(X, y)
pred = model.predict(X.head(10))
assert pred.shape == (10,)
print(f"LightGBM OK: 50 轮训练完成，预测样例前3 = {np.round(pred[:3], 4)}")
PY

echo "=== [3/3] torch + CUDA ==="
python3 - <<'PY'
import torch
print(f"torch {torch.__version__}")
if torch.cuda.is_available():
    x = torch.randn(3, 3).cuda()
    y = (x @ x).sum()
    print(f"CUDA OK: {torch.cuda.get_device_name(0)}，矩阵运算结果 {y.item():.4f}")
else:
    x = torch.randn(3, 3)
    y = (x @ x).sum()
    print(f"CUDA 不可用（CPU-only 运行，结果 {y.item():.4f}）——GPU 实例请用 --gpus all 启动")
PY

echo ""
echo "SMOKE TEST PASSED：仓库代码可在镜像内正常执行"
