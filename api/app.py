"""FastAPI 服务:把 core 引擎包成 HTTP API。

端点:
- POST /analyze   JD → 结构化分析 + 投递等级
- POST /greeting  JD → 一句话开场白
- POST /decide    JD → 分析 + 等级 + 开场白(一体)
- GET  /health    可用性探针(不调 LLM)
- GET  /          最小前端(Step 8 挂载)

LLMError(认证/重试耗尽)→ 502 Bad Gateway。输入超长/缺字段由 pydantic → 422。
限流 / 控制字符过滤见 guardrails.py、ratelimit.py(Step 7 挂中间件)。

启动:uvicorn api.app:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from core import analyze_jd, derive_level, generate_greeting
from core.llm import LLMError

from .auth import is_auth_enabled, is_authorized, needs_auth
from .config import get_profile
from .metrics import metrics
from .ratelimit import RateLimiter, rate_limit_per_minute
from .schemas import (
    AnalyzeResponse,
    BatchItemResult,
    BatchRequest,
    BatchResponse,
    DecideResponse,
    GreetingResponse,
    HealthResponse,
    JDRequest,
)

app = FastAPI(title="岗位决策引擎", version="0.1.0")

# 单实例内存限流(按 IP);多实例需换共享后端。health/前端豁免。
_limiter = RateLimiter(rate_limit_per_minute())

# 批处理并发度:限制同时打向 LLM provider 的请求数,避免压垮上游 / 触发限流。
_BATCH_MAX_WORKERS = 4


@app.middleware("http")
async def _auth_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    # 认证(最内层):限流先挡洪水,认证再验单次身份。
    # 未配 ENGINE_API_KEYS = 开发模式,认证关闭(生产必须配)。
    if is_auth_enabled() and needs_auth(request.url.path):
        if not is_authorized(request.headers.get("x-api-key", "")):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "未授权:API key 缺失或无效"},
            )
    return await call_next(request)


@app.middleware("http")
async def _rate_limit_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    # 限流(中层):探针 / 抓取 / 前端不限流(否则 prometheus 高频抓取会自堵)。
    if request.url.path in ("/health", "/", "/metrics"):
        return await call_next(request)
    ip = request.client.host if request.client else "unknown"
    if not _limiter.allow(ip):
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "请求过于频繁,请稍后再试"},
        )
    return await call_next(request)


@app.middleware("http")
async def _metrics_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    # 最外层(最后注册 → Starlette add_middleware 用 insert(0),后注册者在外):
    # 记录全部请求,含被限流/认证挡掉的 —— 生产要监控 429/401 率。
    t0 = time.monotonic()
    response = await call_next(request)
    metrics.record(request.url.path, response.status_code, time.monotonic() - t0)
    return response


def _llm_502(e: LLMError) -> HTTPException:
    """LLM 失败统一转 502;detail 截断,避免回显过长的模型原始输出(schema
    校验失败的 last_data 可能很完整)。"""
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"LLM 调用失败: {str(e)[:200]}",
    )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/metrics")
def get_metrics() -> Response:
    """Prometheus 文本格式(认证豁免,便于 scraper 抓取)。"""
    return Response(content=metrics.to_prometheus(), media_type="text/plain; version=0.0.4")


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: JDRequest, profile: str = Depends(get_profile)) -> AnalyzeResponse:
    try:
        result = analyze_jd(title=req.title, company=req.company, jd=req.jd, profile=profile)
    except LLMError as e:
        raise _llm_502(e) from e
    return AnalyzeResponse(analysis=result, level=derive_level(result))


@app.post("/greeting", response_model=GreetingResponse)
def greeting(req: JDRequest, profile: str = Depends(get_profile)) -> GreetingResponse:
    try:
        text = generate_greeting(title=req.title, company=req.company, jd=req.jd, profile=profile)
    except LLMError as e:
        raise _llm_502(e) from e
    return GreetingResponse(greeting=text)


@app.post("/decide", response_model=DecideResponse)
def decide(req: JDRequest, profile: str = Depends(get_profile)) -> DecideResponse:
    try:
        result = analyze_jd(title=req.title, company=req.company, jd=req.jd, profile=profile)
        text = generate_greeting(title=req.title, company=req.company, jd=req.jd, profile=profile)
    except LLMError as e:
        raise _llm_502(e) from e
    return DecideResponse(analysis=result, level=derive_level(result), greeting=text)


@app.post("/analyze-batch", response_model=BatchResponse)
def analyze_batch(req: BatchRequest, profile: str = Depends(get_profile)) -> BatchResponse:
    """批量分析:并发(ThreadPool,max_workers=4)调 analyze_jd,单条失败隔离。

    单条 LLM/解析失败 → 该条 error,其余照常;整批始终 200(尽力而为语义)。
    """
    def _one(item: JDRequest) -> BatchItemResult:
        try:
            r = analyze_jd(title=item.title, company=item.company, jd=item.jd, profile=profile)
            return BatchItemResult(analysis=r, level=derive_level(r))
        except Exception as e:  # noqa: BLE001 - 批处理:单条失败隔离,记 error 不崩整批
            return BatchItemResult(error=str(e)[:200])

    with ThreadPoolExecutor(max_workers=_BATCH_MAX_WORKERS) as ex:
        results = list(ex.map(_one, req.items))
    return BatchResponse(results=results)


# 最小前端:静态挂载到根路径。放最后,避免吞掉 /analyze 等显式路由。
_STATIC_DIR = Path(__file__).resolve().parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")
