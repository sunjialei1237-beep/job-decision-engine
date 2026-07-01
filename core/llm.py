"""LLM 调用客户端。支持 OpenAI 和 Anthropic 两种协议。

OpenAI 协议:智谱 /api/paas/v4、DeepSeek、OpenAI 等。
Anthropic 协议:智谱 /api/anthropic(独立额度池,可与 paas/v4 余额不同)。
protocol 由 base_url 含 /anthropic 自动推断,或显式传入 / env PROTOCOL。
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

from openai import AuthenticationError, OpenAI, PermissionDeniedError

from .trace import log_llm_call


class LLMError(Exception):
    """LLM 调用或解析失败。"""


def _infer_protocol(base_url: str | None, protocol: str | None) -> str:
    if protocol:
        return protocol
    if base_url and "/anthropic" in base_url:
        return "anthropic"
    return "openai"


class LLMClient:
    """LLM 客户端(OpenAI / Anthropic 双协议)。

    配置优先级:显式参数 > 环境变量(BASE_URL / API_KEY / MODEL / PROTOCOL)> 默认。
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        protocol: str | None = None,
        retries: int = 3,
    ) -> None:
        self.model = model or os.environ.get("MODEL") or "gpt-4o-mini"
        base_url = base_url or os.environ.get("BASE_URL")
        api_key = api_key or os.environ.get("API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise LLMError("缺少 API key:请设置环境变量 API_KEY 或 OPENAI_API_KEY")
        self.protocol = _infer_protocol(base_url, protocol or os.environ.get("PROTOCOL"))
        self.retries = retries
        if self.protocol == "anthropic":
            from anthropic import Anthropic
            self._anthropic = Anthropic(base_url=base_url, api_key=api_key)
            self._openai = None
        else:
            self._openai = OpenAI(base_url=base_url, api_key=api_key)
            self._anthropic = None

    def _call(self, prompt: str, temperature: float) -> str:
        if self.protocol == "anthropic":
            resp = self._anthropic.messages.create(
                model=self.model,
                max_tokens=4096,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text if resp.content else ""
        resp = self._openai.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=temperature,
        )
        return resp.choices[0].message.content or ""

    def complete_json(
        self, prompt: str, *, temperature: float = 0.3, step: str = "llm"
    ) -> dict[str, Any]:
        """调用模型,返回解析后的 JSON dict。

        OpenAI 认证/权限错误立即失败;其余错误(含 Anthropic 协议错误、限流、超时、
        非法 JSON)重试 retries 次。

        step 为逻辑步骤名(analyze/greeting/judge...),写入 trace 用于区分调用来源。
        每次物理 _call 都记一条 trace(success/auth/error);_call 成功但 JSON 解析失败
        时,trace 已记为成功(API 调用本身没问题),随后按原语义重试。
        """
        last_err: Exception | None = None
        for _ in range(self.retries):
            t0 = time.perf_counter()
            try:
                content = self._call(prompt, temperature)
            except (AuthenticationError, PermissionDeniedError) as e:
                log_llm_call(
                    step=step, model=self.model,
                    latency_ms=(time.perf_counter() - t0) * 1000,
                    prompt=prompt, output=f"[auth] {type(e).__name__}",
                )
                raise LLMError(f"LLM 认证/权限失败(不重试): {e}") from e
            except Exception as e:  # noqa: BLE001 - Anthropic 错误/限流/超时,重试
                log_llm_call(
                    step=step, model=self.model,
                    latency_ms=(time.perf_counter() - t0) * 1000,
                    prompt=prompt, output=f"[error] {type(e).__name__}",
                )
                last_err = e
                continue
            # _call 成功:trace 只盯 LLM 调用本身,不含本地 JSON 解析耗时
            log_llm_call(
                step=step, model=self.model,
                latency_ms=(time.perf_counter() - t0) * 1000,
                prompt=prompt, output=content,
            )
            try:
                return _extract_json(content)
            except Exception as e:  # noqa: BLE001 - JSON 解析失败,重试
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
