"""LLM 调用客户端。

走 OpenAI 协议,env 驱动切换 provider(用户已有 LiteLLM 代理 / 智谱 OpenAI 兼容端点)。
retry(3),要求模型输出 JSON。client 可注入,为 Step 1 评测的跨模型族 judge 铺路。
"""
from __future__ import annotations

import json
import os
from typing import Any

from openai import (
    APIError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)


class LLMError(Exception):
    """LLM 调用或解析失败。"""


class LLMClient:
    """OpenAI 协议的 LLM 客户端。

    配置优先级:显式参数 > 环境变量 > 默认值。
    环境变量:``BASE_URL`` / ``API_KEY`` / ``MODEL``(见 README「作为 Python 库调用」)。
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        retries: int = 3,
    ) -> None:
        self.model = model or os.environ.get("MODEL") or "gpt-4o-mini"
        base_url = base_url or os.environ.get("BASE_URL")
        api_key = api_key or os.environ.get("API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise LLMError("缺少 API key:请设置环境变量 API_KEY 或 OPENAI_API_KEY")
        self.retries = retries
        self._client = OpenAI(base_url=base_url, api_key=api_key)

    def complete_json(self, prompt: str, *, temperature: float = 0.3) -> dict[str, Any]:
        """调用模型,返回解析后的 JSON dict。

        认证/权限错误立即失败(重试无意义);限流/超时/连接错误重试 retries 次。
        """
        retryable = (APITimeoutError, RateLimitError, APIError)
        last_err: Exception | None = None
        for _ in range(self.retries):
            try:
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=temperature,
                )
                content = resp.choices[0].message.content or ""
                return _extract_json(content)
            except (AuthenticationError, PermissionDeniedError) as e:
                # 终端错误:重试无意义,立即失败
                raise LLMError(f"LLM 认证/权限失败(不重试): {e}") from e
            except retryable as e:
                last_err = e  # 可重试:连接/超时/限流/5xx
            except Exception as e:  # noqa: BLE001 - 未知错误(含非法 JSON),记下重试
                last_err = e
        raise LLMError(f"LLM 调用 {self.retries} 次均失败: {last_err}") from last_err


def _extract_json(content: str) -> dict[str, Any]:
    """从模型输出里抠 JSON 对象(兼容被 markdown 代码块包裹的情况)。"""
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMError(f"模型输出非合法 JSON: {e}\n原始输出: {content!r}") from e
    if not isinstance(parsed, dict):
        raise LLMError(f"模型输出不是 JSON 对象: {content!r}")
    return parsed
