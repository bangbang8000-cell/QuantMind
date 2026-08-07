"""
OpenBB 客户端封装
提供统一的错误处理和数据格式化
"""
from typing import Any, Dict, Optional
import pandas as pd
from openbb import obb


class OpenBBClient:
    """OpenBB API 客户端封装"""

    def __init__(self):
        """初始化 OpenBB 客户端"""
        # OpenBB 会自动处理配置
        pass

    @staticmethod
    def format_response(data: Any, meta: Optional[Dict] = None) -> Dict:
        """
        格式化响应数据为统一格式

        Args:
            data: 数据（DataFrame 或其他格式）
            meta: 元数据信息

        Returns:
            标准化的响应字典
        """
        if isinstance(data, pd.DataFrame):
            return {
                "status": "success",
                "service": "openbb",
                "data": data.to_dict(orient="records"),
                "meta": {
                    **(meta or {}),
                    "rows": len(data),
                }
            }
        else:
            return {
                "status": "success",
                "service": "openbb",
                "data": data,
                "meta": meta or {}
            }

    @staticmethod
    def format_error(error: Exception, context: Optional[Dict] = None) -> Dict:
        """
        格式化错误响应

        Args:
            error: 异常对象
            context: 上下文信息

        Returns:
            错误响应字典
        """
        return {
            "status": "error",
            "service": "openbb",
            "message": str(error),
            "error_type": type(error).__name__,
            "context": context or {}
        }


# 全局客户端实例
openbb_client = OpenBBClient()
