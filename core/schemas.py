"""JD 分析结果的数据模型。

字段对齐生产 workflow (boss-scraper/workflow/job_daily_analyze.js 的 ANALYSIS_SCHEMA)。
direction 按 design doc reviewer 建议改成 enum (A/B/OFF) 并拆出 direction_reason,
便于 Step 1 评测时 judge 只判枚举值,不做 free-text 字符串匹配。
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Direction(str, Enum):
    """岗位在候选人方向里的归类。"""

    A = "A"      # A级方向:AI ToB 销售 / 解决方案 / 售前 / 商业化 / AI 产品 / Agent 产品
    B = "B"      # B级技术:AI 技术相关实习(AIGC 应用 / Agent 工程师 / 算法 / 开发)
    OFF = "OFF"  # 方向偏离:运营 / 市场 / 纯 C 端 / 非 AI


class AnalysisResult(BaseModel):
    """analyze_jd() 的结构化输出,12 维判断 + 优先级评分。"""

    direction: Direction = Field(
        ..., description="岗位方向归类:A=A级方向 / B=B级技术 / OFF=方向偏离"
    )
    direction_reason: str = Field(..., description="direction 的一句理由")
    ai_relevant: str = Field(..., description="是否 AI 相关(是/否 + 理由,禁复述 JD)")
    ai_score: int = Field(..., ge=1, le=5, description="AI 相关度 1-5 整数")
    tob: str = Field(..., description="ToB 相关(高/中/低 + 理由)")
    role_type: str = Field(
        ...,
        description="岗位类型:销售/解决方案/售前/产品/技术/运营/BD/商业化/其他",
    )
    skill_migrate: str = Field(
        ...,
        description=(
            "技能迁移度 X/5 + 理由。销售/解决方案/售前/商业化/产品岗评迁移价值,"
            "技术岗评直接匹配"
        ),
    )
    recommend: str = Field(..., description="强烈推荐/推荐/勉强/不推荐 + 一句原因")
    hidden_signal: str = Field(
        ..., description="看穿 JD 字面背后真实在招什么人,不复述"
    )
    capability_bar: str = Field(
        ..., description="能力门槛:低/可跨越/偏高/过高 + 理由"
    )
    hr_reply_prob: str = Field(..., description="HR 回复概率:高/中/低 + 原因")
    score: int = Field(
        ...,
        ge=0,
        le=10,
        description="优先级评分 0-10。权重:方向30/AI20/ToB20/迁移15/阶段匹配15",
    )
    conclusion: str = Field(
        ..., description="强烈建议投递/建议投递/可以尝试/性价比低/不建议"
    )


class GreetingResult(BaseModel):
    """generate_greeting() 的结构化输出。"""

    greeting: str = Field(..., description="一句话私聊开场白,不加引号不加前缀")
