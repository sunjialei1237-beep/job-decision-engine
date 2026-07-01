"""模型 token 价目(USD / 1K tokens)与 cost 估算。

目的:给 trace 补 cost_usd(Phase 1 trace 刻意不含 token/cost,Phase 2 补上)。
机制是重点 —— token 从 SDK 响应直接抓(准确),cost 按价目表估算。

⚠️ 价目是**保守估算,非权威**:LLM 定价随厂商/时段变动,这里只给量级。
未知模型返回 None(trace 仍记 token,只是不算 cost)。使用者应按自己所用模型的
官方价目校准本表,或在 trace 后处理时覆盖 cost。

价格口径:USD per 1,000 tokens,in = prompt/input,out = completion/output。
"""
from __future__ import annotations

from typing import Mapping

# 价目表(USD / 1K tokens)。键支持「模型族前缀」回退,如 "glm-5.2" → "glm"。
# 数字为保守量级估值,请按官方价目校准。
_PRICING: Mapping[str, tuple[float, float]] = {
    # (in_per_1k, out_per_1k)
    "glm": (0.0005, 0.0015),       # 智谱 GLM 系列保守估值
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4o": (0.0025, 0.01),
    "deepseek": (0.00014, 0.00028),  # deepseek-chat 量级
}


def _family(model: str) -> str:
    """gpt-4o-mini→gpt-4o-mini(精确优先);glm-5.2→glm(族回退)。"""
    return model.lower().split("-")[0]


def estimate_cost_usd(model: str, token_in: int, token_out: int) -> float | None:
    """按价目表估算单次调用 USD cost。未知模型返回 None(不算,只记 token)。"""
    if token_in < 0 or token_out < 0:
        return None
    key = model.lower()
    rate = _PRICING.get(key) or _PRICING.get(_family(model))
    if rate is None:
        return None
    in_per_1k, out_per_1k = rate
    return token_in / 1000 * in_per_1k + token_out / 1000 * out_per_1k
