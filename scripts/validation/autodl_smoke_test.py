#!/usr/bin/env python3
"""QuantMind 环境自检脚本（AutoDL 公共镜像审核用）。

验证 Git 仓库代码（docker/training/preprocessing.py 真实训练预处理链路）
可在本镜像的 Python 环境中正常执行，并以退出码 0 表示通过。

运行：python3 /root/QuantMind/scripts/validation/autodl_smoke_test.py
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "docker" / "training"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from preprocessing import (  # noqa: E402
    binarize_labels,
    cross_sectional_median_fill,
    cross_sectional_preprocess,
    winsorize,
)

print(f"Python {sys.version.split()[0]} | numpy {np.__version__} | pandas {pd.__version__}")

# [1] 仓库真实代码：标签二值化 + 缩尾
y = np.array([0.02, -0.01, 0.0, 0.05, -0.03])
assert binarize_labels(y).tolist() == [1.0, 0.0, 0.0, 1.0, 0.0]
rng = np.random.RandomState(0)
x = np.concatenate([rng.randn(18), [-100.0, 100.0]])
assert abs(winsorize(x, quantiles=(0.1, 0.9)).max()) < 5.0
print("[1/3] preprocessing.binarize_labels / winsorize OK")

# [2] 仓库真实代码：截面预处理全链路（中位数填充 + Z-score）
df = pd.DataFrame(np.random.RandomState(42).randn(100, 6), columns=[f"f{i}" for i in range(6)])
df["trade_date"] = np.repeat(["2026-08-01", "2026-08-02"], 50)
df.iloc[5, 2] = np.nan
feats = [f"f{i}" for i in range(6)]
filled = cross_sectional_median_fill(df, feats)
assert not filled.isna().any().any()
out = cross_sectional_preprocess(df, feats, enabled=True, winsor=True)
assert out.shape == (100, 7)
print("[2/3] preprocessing.cross_sectional_preprocess OK")

# [3] LightGBM 训练/预测往返（真实模型训练依赖）
try:
    import lightgbm as lgb  # noqa: E402
except ImportError:
    print("[3/3] LightGBM 未安装（训练容器内可用），跳过训练往返")
    lgb = None

if lgb is not None:
    X = out[feats]
    model = lgb.LGBMRegressor(n_estimators=30, num_leaves=15, n_jobs=2, verbosity=-1)
    model.fit(X, np.random.RandomState(7).randn(100))
    pred = model.predict(X.head(10))
    assert pred.shape == (10,)
    print(f"[3/3] LightGBM 30 轮训练/预测 OK（样例前3 = {np.round(pred[:3], 4)}）")

try:
    import torch  # noqa: E402

    cuda = torch.cuda.is_available()
    print(f"torch {torch.__version__} | CUDA {'可用: ' + torch.cuda.get_device_name(0) if cuda else '不可用（CPU 模式）'}")
except Exception:
    print("torch 未安装（可选依赖）")

print("\nENVIRONMENT CHECK PASSED —— 仓库代码可在本镜像内正常执行")
