"""验证 load_forward_labels 能否为批次窗口产出前瞻标签（P4 前置检查）。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")

from backend.services.engine.inference.data_loader import load_forward_labels

MODEL_DIR = Path(
    "/app/models/users/default/00000001/mdl_train_20260803015340_1637df5e_0d322a31"
)
meta = json.loads((MODEL_DIR / "metadata.json").read_text(encoding="utf-8"))
horizon = int(meta.get("target_horizon_days") or 10)

data_dir = sys.argv[1] if len(sys.argv) > 1 else None
if not data_dir:
    inf = meta.get("inference") or {}
    data_dir = inf.get("data_dir") or meta.get("data_dir") or "/app/data/model_features"
print("data_dir =", data_dir)
print("horizon  =", horizon)

dates = [
    "2026-07-09", "2026-07-10", "2026-07-13", "2026-07-14", "2026-07-15",
    "2026-07-16", "2026-07-17", "2026-07-20", "2026-07-21", "2026-07-22",
]

labels = load_forward_labels(
    dates, horizon, data_dir=data_dir, meta=meta, signal_lag_days=1
)
print("labels rows:", len(labels))
if not labels.empty:
    print("date range:", labels["trade_date"].min(), "..", labels["trade_date"].max())
    sub = labels[labels["trade_date"].isin(dates)]
    print("in-window rows:", len(sub))
    print(sub.groupby("trade_date")["fwd_return"].agg(["count", "mean", "std"]))
