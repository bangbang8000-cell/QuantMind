import os

import yaml


class Config:
    def __init__(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            self.raw = yaml.safe_load(f) or {}

    def _resolve(self, value):
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            name = value[2:-1]
            return os.environ.get(name, "")
        return value

    def get(self, dotted: str, default=None):
        cur = self.raw
        for part in dotted.split("."):
            if not isinstance(cur, dict):
                return default
            cur = cur.get(part)
            if cur is None:
                return default
        return self._resolve(cur)

    def token(self) -> str:
        tok = self.get("auth.token", "")
        if not tok:
            raise ValueError("auth.token 未配置(通过 BRIDGE_AUTH_TOKEN 环境变量注入)")
        return tok
