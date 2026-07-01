"""输入护栏:控制字符过滤。

⚠️ 不声称「防 prompt injection」——LLM prompt injection 是开放问题,无法靠输入
过滤根治。本模块只做基础输入卫生:剥离 C0 控制字符(NUL/BEL/BS/DEL 等),它们
在正常 JD 里不出现,但可被恶意构造(如用 NUL 截断后端字符串处理)。保留 \t \n \r
(正常文本)。

真正的 injection 纵深防御靠三条(不在本模块):
1. profile 不入请求 —— 请求方无法注入你的画像;
2. 输出强制 schema 校验 —— 模型即便被注入也得吐合法 JSON;
3. 响应不回显未过滤的输入原文。
"""
from __future__ import annotations

import re

# C0 控制字符 + DEL,保留 \t(\x09)\n(\x0a)\r(\x0d)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_text(s: str) -> str:
    """剥离控制字符。长度上限交由 pydantic Field 校验。"""
    if not s:
        return s
    return _CONTROL_CHARS.sub("", s)
