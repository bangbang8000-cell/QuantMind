"""
TDX 桥配置管理路由

读取/更新通达信桥配置 (环境变量), 查询桥健康状态。
供前端"模拟交易设置 → 通达信桥"卡片使用。
"""
import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.services.trade.deps import AuthContext, get_auth_context
from backend.services.trade.trade_config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


class TdxConfigResponse(BaseModel):
    enabled: bool = Field(..., description="是否启用通达信推送")
    bridge_url: str = Field(..., description="桥地址")
    bridge_token_configured: bool = Field(..., description="token 是否已配置")
    real_trading_enabled: bool = Field(..., description="实盘是否启用")
    broker_type: str = Field(..., description="实盘 broker 类型")
    health: dict | None = Field(None, description="桥健康状态")


class TdxConfigUpdate(BaseModel):
    bridge_url: str | None = Field(None, description="桥地址")
    bridge_token: str | None = Field(None, description="桥 token")


@router.get("/tdx/config", response_model=TdxConfigResponse)
async def get_tdx_config(auth: AuthContext = Depends(get_auth_context)):
    """读取通达信桥配置状态 (不返回 token 明文)."""
    bridge_url = str(getattr(settings, "TDX_BRIDGE_URL", "") or "").strip()
    bridge_token = str(getattr(settings, "TDX_BRIDGE_TOKEN", "") or "").strip()
    enable_push = os.getenv("ENABLE_TDX_PUSH", "").strip().lower() == "true"
    enable_real = str(getattr(settings, "ENABLE_REAL_TRADING", "false")).lower() == "true"

    health = None
    if bridge_url and bridge_token:
        try:
            import httpx
            resp = httpx.get(f"{bridge_url}/api/v1/health", timeout=3)
            if resp.status_code == 200:
                health = resp.json()
            else:
                health = {"error": f"HTTP {resp.status_code}"}
        except Exception as e:
            health = {"error": str(e)}

    return TdxConfigResponse(
        enabled=enable_push,
        bridge_url=bridge_url,
        bridge_token_configured=bool(bridge_token),
        real_trading_enabled=enable_real,
        broker_type=str(getattr(settings, "REAL_BROKER_TYPE", "tdx")),
        health=health,
    )


@router.post("/tdx/config")
async def update_tdx_config(
    data: TdxConfigUpdate,
    auth: AuthContext = Depends(get_auth_context),
):
    """更新通达信桥配置 (运行时, 进程内生效)."""
    # 运行时覆盖 pydantic-settings (进程内生效)
    if data.bridge_url is not None:
        settings.TDX_BRIDGE_URL = str(data.bridge_url).strip()
        os.environ["TDX_BRIDGE_URL"] = str(data.bridge_url).strip()
    if data.bridge_token is not None:
        settings.TDX_BRIDGE_TOKEN = str(data.bridge_token).strip()
        os.environ["TDX_BRIDGE_TOKEN"] = str(data.bridge_token).strip()
    if data.bridge_url is not None or data.bridge_token is not None:
        from backend.services.trade.services.tdx_push_service import tdx_pusher
        tdx_pusher.bridge_url = str(getattr(settings, "TDX_BRIDGE_URL", "")).strip()
        tdx_pusher.bridge_token = str(getattr(settings, "TDX_BRIDGE_TOKEN", "")).strip()

    return {"success": True, "message": "通达信桥配置已更新"}
