"""确定性决策规则:纯电销检测 + 投递等级阈值。

搬自 boss-scraper/workflow/job_daily_analyze.js 的分级后处理(line 89-96),
独立于 LLM,可单测。derive_level() 在 analyze.py 里组合本模块。
"""
from __future__ import annotations

import re

# role_type 含「销售」
SALES_PATTERN = re.compile(r"销售")
# hidden_signal 命中电销标记(workflow line 92)
TELESALES_PATTERN = re.compile(r"电销|cold.?call|电话销售|电话量|外呼", re.IGNORECASE)

# 投递等级阈值(workflow line 94)
LEVEL_S = 8
LEVEL_A = 6
LEVEL_B = 4

LEVEL_DELIVERABLE = ("S", "A", "B")
LEVEL_NOT_RECOMMEND = "不建议"


def is_pure_telesales(role_type: str, hidden_signal: str) -> bool:
    """销售岗 + hidden_signal 命中电销标记 → 判纯电销。"""
    if not role_type or not hidden_signal:
        return False
    return bool(
        SALES_PATTERN.search(role_type) and TELESALES_PATTERN.search(hidden_signal)
    )


def level_from_score(score: int, telesales: bool = False) -> str:
    """分数 → 投递等级。纯电销强制不建议。"""
    if telesales:
        return LEVEL_NOT_RECOMMEND
    if score >= LEVEL_S:
        return "S"
    if score >= LEVEL_A:
        return "A"
    if score >= LEVEL_B:
        return "B"
    return LEVEL_NOT_RECOMMEND
