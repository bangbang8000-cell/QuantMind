#!/usr/bin/env python3
"""
QuantMind Parquet 数据源推理脚本 (inference.py 模板)
=====================================================
适用于训练数据来自 feature_snapshots/*.parquet 的 LightGBM/XGBoost 模型。

平台注入环境变量：
    MODEL_DIR      模型目录绝对路径（含 metadata.json + model.lgb/model.xgb）
    TRADE_DATE     推理日期（同 --date 参数，互为备份）
    OUTPUT_FORMAT  固定值 json

调用方式（由 InferenceScriptRunner 自动调用）：
    python inference.py --date YYYY-MM-DD --output /path/to/out.json

输出格式（写入 --output 文件）：
    [{"symbol": "sh600519", "score": 0.82}, ...]

exit code：
    0  = 成功
    1  = 致命错误（模型/元数据损坏）
    2  = 该日期无可用数据（触发 alpha158 兜底）
"""
from __future__ import annotations
import argparse, json, logging, os, sys
from pathlib import Path
import pickle
import numpy as np
import pandas as pd

try:
    import lightgbm as lgb
except ImportError:
    lgb = None
try:
    import xgboost as xgb
except ImportError:
    xgb = None
try:
    from catboost import CatBoost
except ImportError:
    CatBoost = None
try:
    import torch
except ImportError:
    torch = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stderr)
logger = logging.getLogger("inference_parquet")

_DEFAULT_DATA_DIR = "/app/db/feature_snapshots"

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--date", "-d", type=str, default=os.getenv("TRADE_DATE", ""))
    p.add_argument("--output", "-o", type=str, required=True)
    p.add_argument("--model-dir", type=str, default=os.getenv("MODEL_DIR", str(Path(__file__).parent)))
    p.add_argument("--data-dir", type=str, default=os.getenv("MODEL_TRAINING_DATA_DIR", _DEFAULT_DATA_DIR))
    return p.parse_args()

def load_metadata(model_dir):
    meta_path = Path(model_dir) / "metadata.json"
    if not meta_path.exists():
        logger.error("metadata.json 不存在: %s", meta_path); sys.exit(1)
    return json.loads(meta_path.read_text(encoding="utf-8"))

def load_model(model_dir, meta):
    model_file = meta.get("model_file", "")
    model_path = Path(model_dir) / model_file if model_file else None
    if not model_path or not model_path.exists():
        for ext in ("*.xgb", "*.lgb", "*.cbm", "*.pkl", "*.pth", "*.pt", "*.txt", "*.bin"):
            candidates = list(Path(model_dir).glob(ext))
            if candidates:
                model_path = candidates[0]; break
        else:
            logger.error("未找到模型文件: %s", model_dir); sys.exit(1)
    suffix = model_path.suffix.lower()
    logger.info("加载模型: %s (格式=%s)", model_path.name, suffix)
    if suffix == ".xgb":
        if xgb is None: logger.error("XGBoost 未安装"); sys.exit(1)
        booster = xgb.Booster(); booster.load_model(str(model_path)); return ("xgb", booster)
    elif suffix == ".cbm":
        if CatBoost is None: logger.error("CatBoost 未安装"); sys.exit(1)
        m = CatBoost(); m.load_model(str(model_path), format="cbm"); return ("catboost", m)
    elif suffix == ".pkl":
        with open(model_path, "rb") as f: m = pickle.load(f)
        return ("sklearn", m)
    elif suffix in (".pth", ".pt"):
        if torch is None: logger.error("PyTorch 未安装"); sys.exit(1)
        model_class_name = meta.get("model_class_name")
        _QLIB_MAP = {"GRU":("qlib.contrib.model.pytorch_gru_ts","GRU"),"LSTM":("qlib.contrib.model.pytorch_lstm_ts","LSTM"),"ALSTM":("qlib.contrib.model.pytorch_alstm_ts","ALSTM"),"Transformer":("qlib.contrib.model.pytorch_transformer_ts","Transformer"),"TCN":("qlib.contrib.model.pytorch_tcn_ts","TCN"),"TabNet":("qlib.contrib.model.pytorch_tabnet","TabNet")}
        if model_class_name and model_class_name in _QLIB_MAP:
            import importlib
            mod_path, cls_name = _QLIB_MAP[model_class_name]
            mod = importlib.import_module(mod_path); ModelCls = getattr(mod, cls_name)
            mp = dict(meta.get("model_params", {})); mp["GPU"] = -1
            model_obj = ModelCls(**mp)
            sd = torch.load(str(model_path), map_location="cpu", weights_only=True)
            inner = getattr(model_obj, "model", None)
            if inner is None:
                for a in ("gru_model","lstm_model","alstm_model","transformer_model","tcn_model","tabnet_model"):
                    inner = getattr(model_obj, a, None)
                    if inner is not None: break
            if inner is not None and sd is not None: inner.load_state_dict(sd); inner.eval()
            model_obj.fitted = True; return ("torch_qlib", model_obj)
        m = torch.load(str(model_path), map_location="cpu", weights_only=False)
        if hasattr(m, "eval"): m.eval()
        return ("torch", m)
    else:
        if lgb is None: logger.error("LightGBM 未安装"); sys.exit(1)
        return ("lgb", lgb.Booster(model_file=str(model_path)))

_MARKET_PARQUET = {"HK": "model_features_hk.parquet", "US": "model_features_us.parquet", "CRYPTO": "model_features_crypto.parquet", "FUTURES": "model_features_futures.parquet"}

def load_date_data(trade_date, data_dir, meta):
    market = str((meta.get("context") or {}).get("market", "")).upper()
    if market in _MARKET_PARQUET:
        parquet_path = Path(data_dir) / _MARKET_PARQUET[market]
    else:
        year = int(trade_date[:4])
        parquet_path = Path(data_dir) / f"model_features_{year}.parquet"
    if not parquet_path.exists():
        logger.warning("parquet 文件不存在: %s", parquet_path); return None
    df = pd.read_parquet(parquet_path, engine="pyarrow")
    if "symbol" not in df.columns and "instrument" in df.columns:
        df = df.rename(columns={"instrument": "symbol"})
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
    day_df = df[df["trade_date"] == trade_date].copy()
    if len(day_df) == 0:
        logger.warning("日期 %s 无数据", trade_date); return None
    # 过滤不可交易（停牌、零成交、ST）
    if "close" in day_df.columns:
        day_df = day_df[pd.to_numeric(day_df["close"], errors="coerce") > 0]
    if "volume" in day_df.columns:
        day_df = day_df[pd.to_numeric(day_df["volume"], errors="coerce") > 0]
    if "is_st" in day_df.columns:
        day_df = day_df[pd.to_numeric(day_df["is_st"], errors="coerce") != 1]
    if len(day_df) == 0:
        logger.warning("日期 %s 过滤后无数据", trade_date); return None
    logger.info("找到 %d 条记录，日期=%s", len(day_df), trade_date)
    return day_df

def preprocess(df, meta):
    feature_cols = meta.get("feature_columns") or meta.get("features", [])
    fill_values  = meta.get("fill_values", {})
    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        logger.warning("缺少 %d 个特征列，填 0: %s", len(missing), missing[:8])
        for c in missing: df[c] = 0.0
    X_df = df[feature_cols].copy()
    for col, val in fill_values.items():
        if col in X_df.columns: X_df[col] = X_df[col].fillna(val)
    return X_df.fillna(0.0), df["symbol"].tolist()

def main():
    args = parse_args()
    trade_date = (args.date or "").strip()
    if not trade_date:
        logger.error("未指定推理日期"); sys.exit(1)
    model_dir, data_dir, out_path = Path(args.model_dir), Path(args.data_dir), Path(args.output)
    logger.info("=== parquet 推理脚本 === date=%s  model_dir=%s", trade_date, model_dir)
    meta  = load_metadata(model_dir)
    day_df = load_date_data(trade_date, data_dir, meta)
    if day_df is None:
        print(f"日期 {trade_date} 无数据，触发兜底", file=sys.stderr); sys.exit(2)
    model_type, model = load_model(model_dir, meta)
    X_df, symbols = preprocess(day_df, meta)
    if len(X_df) == 0:
        print(f"日期 {trade_date} 预处理后无有效行", file=sys.stderr); sys.exit(2)
    X_values = X_df.values.astype(np.float32)
    best_iter = meta.get("best_iteration")
    if model_type == "xgb":
        dmat = xgb.DMatrix(X_values, feature_names=list(X_df.columns))
        scores = model.predict(dmat, iteration_range=(0, best_iter) if best_iter else None)
    elif model_type == "catboost":
        scores = model.predict(X_values)
    elif model_type == "sklearn":
        scores = model.predict_proba(X_values)[:, 1] if hasattr(model, "predict_proba") else model.predict(X_values)
    elif model_type in ("torch_qlib", "torch"):
        inner = model
        if model_type == "torch_qlib":
            inner = getattr(model, "model", None)
            if inner is None:
                for a in ("gru_model","lstm_model","alstm_model","transformer_model","tcn_model","tabnet_model"):
                    inner = getattr(model, a, None)
                    if inner is not None: break
            if inner is None: logger.error("DL 内部模型未找到"); sys.exit(1)
        inner.eval()
        xt = torch.from_numpy(X_values)
        dev = getattr(model, "device", None) or getattr(inner, "device", None)
        if dev is not None: xt = xt.to(dev)
        with torch.no_grad(): pred = inner(xt).detach().cpu().numpy()
        scores = pred.flatten()
    else:
        scores = model.predict(X_values, num_iteration=best_iter)
    signals = sorted(
        [{"symbol": s, "score": float(v)} for s, v in zip(symbols, scores) if v == v],
        key=lambda x: x["score"], reverse=True
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(signals, ensure_ascii=False), encoding="utf-8")
    logger.info("已写入信号文件: %s  (%d 条)", out_path, len(signals))

if __name__ == "__main__":
    main()
