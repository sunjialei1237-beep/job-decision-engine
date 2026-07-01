"""轻量 trace:每次 LLM 调用落一行 jsonl(design doc Step 3)。

记录 {ts, step, model, latency_ms, input_hash, output_summary}。
刻意不含 token/cost —— 脚本内拿不到响应头,留 Phase 2 Langfuse SDK 补。现在记
是因为 hook 一处即可,事后补成本高;但也不假装它 load-bearing(它不是判据,只是观测)。

设计要点:
- 单一写入点:由 core.llm.LLMClient.complete_json 在每次物理 _call 后调用,
  analyze / greeting / judge 三类逻辑步骤通过 step 标签区分。
- 失败静默:trace 永不影响主流程(写入异常吞掉)。
- 可关停:TRACE_DISABLED=1 完全不写;TRACE_DIR 覆盖输出目录(默认 ./trace/runs)。
- 输出已 .gitignore(trace/runs/),只在本机留存。

字段说明:
- ts            UTC ISO8601(秒精度)
- step          逻辑步骤名(analyze / greeting / judge / llm / 自定义)
- model         模型名(来自 LLMClient.model)
- latency_ms    单次 _call 墙钟延迟(含网络,不含本地 JSON 解析)
- input_hash    prompt 的 sha256 前 16 位(不存原文 → 隐私 + 体积;排查用 hash 对齐)
- output_summary 模型输出前 200 字(单行化);失败时为 [error]/[auth] + 异常类型
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _trace_dir() -> Path:
    """trace jsonl 输出目录(TRACE_DIR 覆盖,默认 ./trace/runs)。"""
    return Path(os.environ.get("TRACE_DIR", "trace/runs"))


def _disabled() -> bool:
    return os.environ.get("TRACE_DISABLED", "").lower() in ("1", "true", "yes")


def log_llm_call(
    *,
    step: str,
    model: str,
    latency_ms: float,
    prompt: str,
    output: str,
) -> None:
    """记录一次 LLM 调用。任何异常静默吞掉(trace 不应影响主流程)。"""
    if _disabled():
        return
    try:
        now = datetime.now(timezone.utc)
        entry = {
            "ts": now.isoformat(timespec="seconds"),
            "step": step,
            "model": model,
            "latency_ms": round(latency_ms, 1),
            "input_hash": hashlib.sha256(
                (prompt or "").encode("utf-8", "replace")
            ).hexdigest()[:16],
            "output_summary": (output or "").strip().replace("\n", " ")[:200],
        }
        line = json.dumps(entry, ensure_ascii=False)
        path = _trace_dir() / f"{now.strftime('%Y-%m-%d')}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        # trace 永不抛出:磁盘满 / 权限 / 编码等问题都不应打断业务
        return
