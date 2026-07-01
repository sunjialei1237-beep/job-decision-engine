"""API key 认证(生产门禁)。

env ENGINE_API_KEYS(逗号分隔)配置允许的 key 集合:
- **未配置** → 开发模式,认证关闭(本地 / 测试用;**生产部署必须配**)。
- **已配置** → 受保护端点须带 `X-API-Key: <集合内某个 key>`,否则 401。

豁免路径(探针 / 监控 / 前端 / 文档):/health /metrics / /docs /redoc
/openapi.json /docs/oauth2-redirect。这些公开便于 prometheus 抓取与前端打开。
"""
from __future__ import annotations

import os

_EXEMPT = {
    "/health",
    "/metrics",
    "/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/docs/oauth2-redirect",
}


def load_api_keys() -> set[str]:
    """解析 env ENGINE_API_KEYS 为 key 集合(空 env → 空集 → 认证关闭)。"""
    raw = os.environ.get("ENGINE_API_KEYS", "")
    return {k.strip() for k in raw.split(",") if k.strip()}


def is_auth_enabled() -> bool:
    return bool(load_api_keys())


def needs_auth(path: str) -> bool:
    return path not in _EXEMPT


def is_authorized(provided_key: str) -> bool:
    """提供的 key 是否在白名单内。认证未开启时调用方应先判 is_auth_enabled。"""
    return provided_key in load_api_keys()
