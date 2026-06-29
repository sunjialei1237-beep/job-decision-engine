"""LLM-as-judge:用独立模型族评 analyzer 的判断质量。

rubric 见 judge_prompt.md。judge 应与 analyzer 用不同模型族,避免 self-preference。
复用 core.llm.LLMClient(client 可注入,评测时传 judge_model)。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from core.llm import LLMClient, LLMError
from core.schemas import AnalysisResult, Direction


@lru_cache(maxsize=1)
def _judge_prompt() -> str:
    """lazy 读 rubric,避免 import 时 IO + 可被测试替换。"""
    return (Path(__file__).parent / "judge_prompt.md").read_text(encoding="utf-8")


class JudgeResult(BaseModel):
    """judge 对一份 analyzer 报告的评判结果。"""

    direction: Direction = Field(..., description="judge 独立判的 direction")
    direction_agree: bool = Field(..., description="是否同意 analyzer 的 direction")
    score_plausibility: int = Field(..., ge=1, le=5, description="analyzer score 合理性 1-5")
    hidden_signal_plausibility: int = Field(..., ge=1, le=5, description="hidden_signal 看穿本质程度 1-5")
    rationale_plausible: bool = Field(..., description="analyzer 推理是否可信(非空话)")
    overall: int = Field(..., ge=1, le=5, description="综合质量 1-5")
    comment: str = Field(..., description="一句话点评")


def build_judge_prompt(
    analysis: AnalysisResult, title: str, company: str, jd: str, profile: str
) -> str:
    return (
        f"{_judge_prompt()}\n\n"
        f"=== 候选人画像 ===\n{profile}\n\n"
        f"=== 待评岗位 ===\n公司:{company}\n岗位:{title}\nJD原文:\n{jd}\n\n"
        f"=== analyzer 输出(待评判)===\n{analysis.model_dump_json(indent=2)}\n\n"
        "输出 JSON,字段:direction(A/B/OFF)、direction_agree(bool)、"
        "score_plausibility(1-5)、hidden_signal_plausibility(1-5)、"
        "rationale_plausible(bool)、overall(1-5)、comment。只输出 JSON。"
    )


def judge_analysis(
    analysis: AnalysisResult,
    title: str,
    company: str,
    jd: str,
    profile: str,
    *,
    client: LLMClient | None = None,
    temperature: float = 0.0,
) -> JudgeResult:
    """用 judge 模型评一份 analyzer 报告。temperature 默认 0(评测要确定性)。"""
    cli = client or LLMClient()
    prompt = build_judge_prompt(analysis, title, company, jd, profile)
    data = cli.complete_json(prompt, temperature=temperature)
    try:
        return JudgeResult.model_validate(data)
    except ValidationError as e:
        raise LLMError(f"模型输出不符合 JudgeResult schema: {e}\n原始数据: {data}") from e
