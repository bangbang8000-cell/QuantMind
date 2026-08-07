"""
Router 模块
负责 API 路由管理
"""

from typing import Dict, List, Callable, Any
from dataclasses import dataclass


@dataclass
class Route:
    """路由定义"""
    path: str
    method: str
    handler: Callable
    description: str = ""


class Router:
    """
    API 路由器
    
    管理和注册所有 API 端点
    """
    
    def __init__(self, prefix: str = ""):
        self.prefix = prefix
        self.routes: List[Route] = []
        self._handlers: Dict[str, Callable] = {}
    
    def add_route(
        self,
        path: str,
        handler: Callable,
        method: str = "GET",
        description: str = ""
    ):
        """添加路由"""
        full_path = f"{self.prefix}{path}"
        route = Route(
            path=full_path,
            method=method,
            handler=handler,
            description=description
        )
        self.routes.append(route)
        self._handlers[full_path] = handler
    
    def get(self, path: str, description: str = ""):
        """添加 GET 路由装饰器"""
        def decorator(func: Callable) -> Callable:
            self.add_route(path, func, "GET", description)
            return func
        return decorator
    
    def post(self, path: str, description: str = ""):
        """添加 POST 路由装饰器"""
        def decorator(func: Callable) -> Callable:
            self.add_route(path, func, "POST", description)
            return func
        return decorator
    
    def list_routes(self) -> List[Dict[str, Any]]:
        """列出所有路由"""
        return [
            {
                "path": r.path,
                "method": r.method,
                "description": r.description
            }
            for r in self.routes
        ]


# 全局路由器实例
router = Router()
