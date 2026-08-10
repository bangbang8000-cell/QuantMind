# Market Analysis(大盘分析)

> 模块状态: **W08 领域骨架(开发中)**
> 归属服务: quantmind-api (8000), 行情来自 quantmind-stream (8003)

## 状态

| 项 | 说明 |
| --- | --- |
| 当前状态 | 板块/概念/指数映射、指标聚合、热力图、资金流、异动检测骨架已完成 |
| API 契约 | 已注册 `/api/v1/market-analysis/*` |
| 数据库 | qm_market_sectors、qm_sector_constituents、qm_sector_daily_metrics、qm_market_anomalies(平台公共参考数据, 跨租户共享) |
| 已知边界 | K 线/指标/热力图/异动须可由同一交易日数据重放; WebSocket 断线恢复不丢失事件 |

## 运行方式

```bash
source .venv/bin/activate   # 或 WSL: source ~/.venvs/quantmind-wsl/bin/activate
python -m uvicorn backend.services.api.main:app --port 8000
```

## 测试

```bash
python -m pytest TEST/test_market_analysis_d.py TEST/test_market_analysis_extended.py \
  TEST/test_market_analysis_integration.py TEST/test_market_realtime.py -q --no-cov
```

## 已知边界

- pct_change 为百分比点口径(涨停=10), 严禁比例值; 复权口径统一后复权价格÷复权因子。
- Prefix 代码巡检异常会阻断下游发布并告警。
- 为平台特征、模型推理、交易前检查提供统一 as-of 时间数据读取。
