"""Phase 2 独立服务:FastAPI 包装 core 引擎为 HTTP API。

启动:uvicorn api.app:app --reload
测试:tests/test_api.py(TestClient,monkeypatch 引擎函数,不调真 LLM)
"""
