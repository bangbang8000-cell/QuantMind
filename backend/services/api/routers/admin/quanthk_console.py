"""管理员 - QuantHK 控制台（港股本地数据管理）。

GET  /api/v1/admin/data-platform/quanthk/catalog       数据集目录 + 本地落盘统计
GET  /api/v1/admin/data-platform/quanthk/preview       数据集预览（本地 parquet）
GET  /api/v1/admin/data-platform/quanthk/config        数据目录等运行时配置
POST /api/v1/admin/data-platform/quanthk/sync-datasets 按数据集触发同步（后台任务）
GET  /api/v1/admin/data-platform/quanthk/sync-jobs     同步任务列表
GET  /api/v1/admin/data-platform/quanthk/sync-jobs/{id} 单个任务进度
POST /api/v1/admin/data-platform/quanthk/sync-jobs/{id}/cancel 取消同步任务
"""

from backend.services.api.routers.admin.global_market_console import make_market_router

router = make_market_router(
    market="HK",
    env_var="QM_QUANTHK_DATA_DIR",
    default_dir="/data/quanthk",
    sync_entry="backend.scripts.quanthk_daily_sync",
)
