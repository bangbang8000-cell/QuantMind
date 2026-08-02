"""时光回放模块。

组件：
- account.py    — ReplayAccountManager（Redis key 隔离）
- day_runner.py — ReplayDayRunner（单日推演引擎）
- signal_generator.py — ReplaySignalGenerator + ReplaySignalLoader
- router.py     — FastAPI 端点
"""
