"""一次性脚本：生成 baseline 训练配置（56 个特征 × 2016-2023 训练）。

把 catalog 里 default_selected=true 的列作为特征，跑一次完整 baseline 训练，
拿真实的 feature_importance 来验证因子选择是否合理。
"""
import json
import os
import yaml

CATALOG = '/app/config/features/model_training_feature_catalog_v1.json'
OUT_DIR = '/data/training_jobs/train_baseline_56_v1'

with open(CATALOG) as f:
    cat = json.load(f)
defaults = [feat['key'] for c in cat['categories'] for feat in c['features']
            if feat.get('default_selected')]
print(f"default features: {len(defaults)}")

config = {
    'run_id': 'train_baseline_56_v1',
    'job_name': 'baseline_default56_full',
    'data': {
        'train_start': '2016-01-04',
        'train_end': '2023-06-30',
        'features': defaults,
        'source_mode': 'LOCAL',
        'local_dir': '/tmp/feature_snapshots',
    },
    'model': {
        'type': 'lightgbm',
        'num_boost_round': 2000,
        'early_stopping_rounds': 100,
        'val_ratio': None,
        'params': {
            'objective': 'regression',
            'metric': 'l2',
            'learning_rate': 0.02,
            'num_leaves': 31,
            'max_depth': -1,
            'min_data_in_leaf': 300,
            'feature_fraction': 0.7,
            'bagging_fraction': 0.8,
            'lambda_l1': 0.5,
            'lambda_l2': 1.0,
        },
    },
    'label': {
        'target_horizon_days': 10,
        'target_mode': 'return',
        'label_formula': 'label = future_return(T, T+10)',
        'effective_trade_date': '2024-12-01',
        'training_window': '2016-01-04 → 2023-06-30 | 2023-07-01 → 2023-12-31 | 2024-01-01 → 2024-12-31',
    },
    'context': {
        'initial_capital': 1000000.0,
        'benchmark': 'SH000300',
        'commission_rate': 0.00025,
        'slippage': 0.0005,
        'deal_price': 'open',
        'market': 'CN',
    },
    'explain': {
        'enable_shap': True,
        'shap_sample_rows': 30000,
        'shap_split': 'valid',
    },
    'output': {
        'result_path': '/workspace/result.json',
        'required_artifacts': [
            'model.lgb', 'pred.pkl', 'pred.parquet',
            'metadata.json', 'config.yaml', 'result.json', 'shap_summary.csv'
        ],
    },
    'callback': {
        'url': 'http://quantmind-api:8000/api/v1/models/training-runs/train_baseline_56_v1/complete',
        'secret': 'changeme-internal-secret',
    },
    'cache': {'dir': '/tmp'},
    'split': {
        'train': ['2016-01-04', '2023-06-30'],
        'valid': ['2023-07-01', '2023-12-31'],
        'test':  ['2024-01-01', '2024-12-31'],
    },
}

os.makedirs(OUT_DIR, exist_ok=True)
with open(os.path.join(OUT_DIR, 'config.yaml'), 'w') as f:
    yaml.safe_dump(config, f, allow_unicode=True, default_flow_style=False)
print(f"config saved to {OUT_DIR}/config.yaml")
