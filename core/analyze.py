"""JD 决策引擎入口:analyze_jd / generate_greeting / derive_level。

纯函数风格:profile 作为参数传入(= profile.md 文件内容),引擎不读文件,
无状态、可换人、可测。LLM client 可注入,默认从 env 构造。
schema-feedback retry:模型漏 required 字段时,带缺失提示重试(修 6.9% 失败率)。
"""
from __future__ import annotations

from typing import Literal, TypeVar

from pydantic import BaseModel, ValidationError

from .llm import LLMClient, LLMError
from .prompts import build_analysis_prompt, build_greeting_prompt
from .rules import is_pure_telesales, level_from_score
from .schemas import AnalysisResult, GreetingResult

Level = Literal["S", "A", "B", "不建议"]

M = TypeVar("M", bound=BaseModel)


def _complete_validated(
    cli: LLMClient,
    base_prompt: str,
    model_cls: type[M],
    *,
    temperature: float,
    schema_retries: int = 1,
    step: str = "llm",
) -> M:
    """complete_json + schema 校验;漏 required 字段时带缺失提示重试。"""
    prompt = base_prompt
    last_err: Exception | None = None
    last_data: object = None
    for _ in range(schema_retries + 1):
        data = cli.complete_json(prompt, temperature=temperature, step=step)
        last_data = data
        try:
            return model_cls.model_validate(data)
        except ValidationError as e:
            last_err = e
            missing = [str(err["loc"][0]) for err in e.errors() if err.get("type") == "missing"]
            tail = f"(缺失字段: {missing})" if missing else ""
            prompt = f"{base_prompt}\n\n⚠ 上次 JSON 不符合 schema{tail},请补全后重新输出完整 JSON。"
    raise LLMError(
        f"{model_cls.__name__} schema 校验失败 {schema_retries + 1} 次: {last_err}\n最后数据: {last_data}"
    ) from last_err


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
    return _complete_validated(
        cli,
        build_analysis_prompt(title, company, jd, profile),
        AnalysisResult,
        temperature=temperature,
        schema_retries=2,
        step="analyze",
    )


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
    return _complete_validated(
        cli,
        build_greeting_prompt(title, company, jd, profile),
        GreetingResult,
        temperature=temperature,
        step="greeting",
    ).greeting


def derive_level(analysis: AnalysisResult) -> Level:
    """从 AnalysisResult 推导投递等级(S/A/B/不建议),含纯电销兜底。

    纯确定性逻辑,不依赖 LLM。搬自 workflow line 89-96。
    """
    telesales = is_pure_telesales(analysis.role_type, analysis.hidden_signal)
    return level_from_score(analysis.score, telesales=telesales)
