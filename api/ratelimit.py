"""极简内存限流(滑动窗口,按 IP),无外部依赖。

设计:每 IP 在 window_sec 秒内最多 max_calls 次请求,超限返回 False(端点转 429)。
内存存储 → 仅适合单实例部署。多实例需换 Redis/共享后端(本模块留作接口稳定,
替换内部实现即可)。

env RATE_LIMIT_PER_MINUTE(默认 20)控制窗口容量。health/前端不限流(在 app.py
中间件里豁免)。
"""
from __future__ import annotations

import os
import time
from collections import defaultdict

_DEFAULT_PER_MIN = 20


def rate_limit_per_minute() -> int:
    try:
        return max(1, int(os.environ.get("RATE_LIMIT_PER_MINUTE", _DEFAULT_PER_MIN)))
    except ValueError:
        return _DEFAULT_PER_MIN


class RateLimiter:
    """按 IP 的滑动窗口限流器(线程不安全;ASGI 单 worker 下请求串行进入端点足够)。"""

    def __init__(self, max_calls: int, window_sec: int = 60) -> None:
        self.max_calls = max_calls
        self.window_sec = window_sec
        self._hits: dict[str, list[float]] = defaultdict(list)

    def allow(self, ip: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_sec
        bucket = [t for t in self._hits[ip] if t > cutoff]
        if len(bucket) >= self.max_calls:
            self._hits[ip] = bucket  # 仍刷新窗口,便于下次同样判定
            return False
        bucket.append(now)
        self._hits[ip] = bucket
        return True

    def reset(self) -> None:
        """测试用:清空所有计数。"""
        self._hits.clear()
