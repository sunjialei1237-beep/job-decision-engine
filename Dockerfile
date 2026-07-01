# Phase 2 独立服务镜像。
# 不内置 API_KEY / profile —— 运行时 env 注入 / 挂载(见 docker-compose.yml)。
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PIP_NO_CACHE_DIR=1

# 先装依赖(改 core/pyproject 才重建;改 api 只走下方 COPY,层缓存友好)
COPY pyproject.toml README.md ./
COPY core/ ./core/
RUN pip install ".[api]"

# api 源码(改动频繁,放依赖安装之后)
COPY api/ ./api/

EXPOSE 8000

CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
