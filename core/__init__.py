"""JD 决策引擎核心:analyze_jd / generate_greeting / derive_level。

纯函数引擎:profile 作为参数传入(无文件 IO),LLM client 可注入。
schema 对齐 boss-scraper/workflow/job_daily_analyze.js 的生产版本。
"""
from .analyze import derive_level, analyze_jd, generate_greeting
from .llm import LLMClient, LLMError
from .rules import is_pure_telesales, level_from_score
from .schemas import AnalysisResult, Direction, GreetingResult

__all__ = [
    "analyze_jd",
    "generate_greeting",
    "derive_level",
    "AnalysisResult",
    "GreetingResult",
    "Direction",
    "LLMClient",
    "LLMError",
    "is_pure_telesales",
    "level_from_score",
]
