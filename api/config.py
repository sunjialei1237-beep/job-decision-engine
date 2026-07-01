"""服务配置:候选人画像来源。

profile 是**服务侧配置**(非请求参数)——env CANDIDATE_PROFILE 覆盖 > profile.md
(私人,gitignore)> profile.example.md(模板)。换人用 = 换 env 或换挂载文件,
引擎本体无状态。画像永不出现在 HTTP 响应(PII 护栏,见 guardrails.py)。
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def get_profile() -> str:
    """启动期读一次 profile(env 覆盖 > profile.md > profile.example.md)。"""
    text = os.environ.get("CANDIDATE_PROFILE")
    if text:
        return text
    p = _REPO_ROOT / "profile.md"
    if not p.exists():
        p = _REPO_ROOT / "profile.example.md"
    return p.read_text(encoding="utf-8")
