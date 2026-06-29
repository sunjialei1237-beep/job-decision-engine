"""JD 决策引擎入口:analyze_jd / generate_greeting / derive_level。

纯函数风格:profile 作为参数传入(= profile.md 文件内容),引擎不读文件,
无状态、可换人、可测。LLM client 可注入,默认从 env 构造。
"""
from __future__ import annotations

from typing import Literal

from pydantic import ValidationError

from .llm import LLMClient, LLMError
from .prompts import build_analysis_prompt, build_greeting_prompt
from .rules import is_pure_telesales, level_from_score
from .schemas import AnalysisResult, GreetingResult

Level = Literal["S", "A", "B", "不建议"]


def analyze_jd(
    title: str,
    company: str,
    jd: str,
    profile: str,
    *,
    client: LLMClient | None = None,
    temperature: float = 0.2,
) -> AnalysisResult:
    """分析一条 JD,返回结构化决策结果。"""
    cli = client or LLMClient()
    prompt = build_analysis_prompt(title, company, jd, profile)
    data = cli.complete_json(prompt, temperature=temperature)
    try:
        return AnalysisResult.model_validate(data)
    except ValidationError as e:
        raise LLMError(
            f"模型输出不符合 AnalysisResult schema: {e}\n原始数据: {data}"
        ) from e


def generate_greeting(
    title: str,
    company: str,
    jd: str,
    profile: str,
    *,
    client: LLMClient | None = None,
    temperature: float = 0.7,
) -> str:
    """基于 JD + 画像生成一句话私聊开场白。"""
    cli = client or LLMClient()
    prompt = build_greeting_prompt(title, company, jd, profile)
    data = cli.complete_json(prompt, temperature=temperature)
    try:
        return GreetingResult.model_validate(data).greeting
    except ValidationError as e:
        raise LLMError(
            f"模型输出不符合 GreetingResult schema: {e}\n原始数据: {data}"
        ) from e


def derive_level(analysis: AnalysisResult) -> Level:
    """从 AnalysisResult 推导投递等级(S/A/B/不建议),含纯电销兜底。

    纯确定性逻辑,不依赖 LLM。搬自 workflow line 89-96。
    """
    telesales = is_pure_telesales(analysis.role_type, analysis.hidden_signal)
    return level_from_score(analysis.score, telesales=telesales)
