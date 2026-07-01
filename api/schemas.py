"""HTTP 请求/响应 schema。

请求只含 JD 三元组(title/company/jd),**不含 profile**——profile 是服务侧配置
(见 config.py),由 Depends 注入,绝不来自请求方(防泄露他人画像 + PII 护栏)。

字段长度上限由 pydantic Field 约束 → 超限自动 422(基础护栏;内容级过滤见
guardrails.py)。
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from core.schemas import AnalysisResult

from .guardrails import sanitize_text


class JDRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, description="岗位标题")
    company: str = Field(..., min_length=1, max_length=200, description="公司名")
    jd: str = Field(..., min_length=1, max_length=20000, description="JD 正文")

    @field_validator("title", "company", "jd")
    @classmethod
    def _strip_control_chars(cls, v: str) -> str:
        """剥离控制字符(guardrails);sanitize 后为空 → 422。"""
        cleaned = sanitize_text(v)
        if not cleaned:
            raise ValueError("字段不能为空或仅含控制字符")
        return cleaned


class AnalyzeResponse(BaseModel):
    analysis: AnalysisResult
    level: str


class GreetingResponse(BaseModel):
    greeting: str


class DecideResponse(BaseModel):
    analysis: AnalysisResult
    level: str
    greeting: str


class HealthResponse(BaseModel):
    status: str


# --- 批处理(Phase 3)---
class BatchRequest(BaseModel):
    items: list[JDRequest] = Field(..., min_length=1, max_length=50, description="批量 JD(≤50 条)")


class BatchItemResult(BaseModel):
    """批处理单条结果:成功填 analysis/level,失败填 error(单条隔离不崩整批)。"""

    analysis: AnalysisResult | None = None
    level: str | None = None
    error: str | None = None


class BatchResponse(BaseModel):
    results: list[BatchItemResult]
