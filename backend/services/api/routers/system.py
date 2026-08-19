from fastapi import APIRouter
from config.settings import settings
from backend.shared.version import get_version

router = APIRouter(prefix="/api/v1/system", tags=["System"])


@router.get("/version")
async def get_version_info():
    """当前运行代码版本（deploy/update.sh 每次更新后写入 version.txt）。"""
    return {
        "version": get_version(),
        "edition": settings.edition,
    }


@router.get("/capabilities")
async def get_capabilities():
    """获取当前版本的系统能力与开关"""
    return settings.capabilities
