"""HTTP 层 metrics(Prometheus 文本格式,无 prometheus_client 依赖)。

聚焦生产监控最小集:请求计数(by path/status)+ 延迟累计(by path,可算均值)。
LLM token/cost 维度**已由 core/trace 落盘**,这里不重复实时累加 —— 保持 core
不被观测逻辑侵入(trace 是单一观测写入点)。需要 token/cost 实时面板时,从
trace/runs/*.jsonl 离线聚合,或接 Langfuse(见 README)。

线程安全:Lock 保护(counter 写入来自线程池批处理 + ASGI worker)。
"""
from __future__ import annotations

import threading


class MetricsCollector:
    """请求计数 + 延迟累计,线程安全。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: dict[tuple[str, int], int] = {}      # (path, status) -> count
        self._latency_sum: dict[str, float] = {}             # path -> 累计秒
        self._latency_count: dict[str, int] = {}             # path -> 次数

    def record(self, path: str, status: int, latency_sec: float) -> None:
        with self._lock:
            self._requests[(path, status)] = self._requests.get((path, status), 0) + 1
            self._latency_sum[path] = self._latency_sum.get(path, 0.0) + latency_sec
            self._latency_count[path] = self._latency_count.get(path, 0) + 1

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()
            self._latency_sum.clear()
            self._latency_count.clear()

    def to_prometheus(self) -> str:
        with self._lock:
            reqs = dict(self._requests)
            l_sum = dict(self._latency_sum)
            l_cnt = dict(self._latency_count)
        lines: list[str] = [
            "# HELP engine_requests_total HTTP requests by path and status",
            "# TYPE engine_requests_total counter",
        ]
        for (path, status), n in sorted(reqs.items()):
            lines.append(f'engine_requests_total{{path="{path}",status="{status}"}} {n}')
        lines += [
            "# HELP engine_request_latency_seconds_sum Cumulative request latency by path",
            "# TYPE engine_request_latency_seconds_sum counter",
        ]
        for path, s in sorted(l_sum.items()):
            lines.append(f'engine_request_latency_seconds_sum{{path="{path}"}} {s:.6f}')
        lines += [
            "# HELP engine_request_latency_seconds_count Request count by path",
            "# TYPE engine_request_latency_seconds_count counter",
        ]
        for path, n in sorted(l_cnt.items()):
            lines.append(f'engine_request_latency_seconds_count{{path="{path}"}} {n}')
        return "\n".join(lines) + "\n"


# 模块级单例;app.py 中间件与 /metrics 端点共用。
metrics = MetricsCollector()
