"""api/ 端点的 TestClient 集成测试。

monkeypatch api.app 里的 analyze_jd / generate_greeting(从 core import 来的引用),
用 fake 返回值,不调真 LLM。跑法:python -m unittest tests.test_api
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import api.app as app_mod  # noqa: E402
from core.llm import LLMError  # noqa: E402
from core.schemas import AnalysisResult, Direction  # noqa: E402

client = TestClient(app_mod.app)


def _fake_analysis(score: int = 9) -> AnalysisResult:
    return AnalysisResult(
        direction=Direction.A,
        direction_reason="A级方向",
        ai_relevant="是,核心基于大模型",
        ai_score=5,
        tob="高,直接服务企业客户",
        role_type="解决方案",
        skill_migrate="4/5",
        recommend="强烈推荐",
        hidden_signal="技术型售前",
        capability_bar="可跨越",
        hr_reply_prob="高",
        score=score,
        conclusion="强烈建议投递",
    )


class TestAPI(unittest.TestCase):
    def setUp(self) -> None:
        # 限流计数在模块全局,每个测试前清零隔离
        app_mod._limiter.reset()

    # --- health / 前端 ---
    def test_health(self) -> None:
        r = client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"status": "ok"})

    def test_frontend_served(self) -> None:
        r = client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("<html", r.text.lower())

    # --- 正常路径(monkeypatch 引擎,不调 LLM)---
    @patch("api.app.analyze_jd", return_value=_fake_analysis(9))
    def test_analyze_ok(self, _mock) -> None:
        r = client.post("/analyze", json={"title": "AI 解决方案", "company": "某公司", "jd": "x" * 20})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["level"], "S")  # score 9 → S
        self.assertEqual(body["analysis"]["direction"], "A")
        self.assertNotIn("profile", body)  # PII:profile 永不入响应

    @patch("api.app.generate_greeting", return_value="你好,看到你们在招...")
    def test_greeting_ok(self, _mock) -> None:
        r = client.post("/greeting", json={"title": "t", "company": "c", "jd": "x" * 20})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["greeting"], "你好,看到你们在招...")

    @patch("api.app.generate_greeting", return_value="一句话话术")
    @patch("api.app.analyze_jd", return_value=_fake_analysis(6))
    def test_decide_ok(self, _a, _g) -> None:
        r = client.post("/decide", json={"title": "t", "company": "c", "jd": "x" * 20})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["level"], "A")  # score 6 → A
        self.assertEqual(body["greeting"], "一句话话术")
        self.assertEqual(body["analysis"]["score"], 6)

    # --- 错误路径 ---
    @patch("api.app.analyze_jd", side_effect=LLMError("boom"))
    def test_llm_error_502(self, _mock) -> None:
        r = client.post("/analyze", json={"title": "t", "company": "c", "jd": "x" * 20})
        self.assertEqual(r.status_code, 502)
        self.assertIn("LLM", r.json()["detail"])

    def test_missing_field_422(self) -> None:
        r = client.post("/analyze", json={"title": "t"})
        self.assertEqual(r.status_code, 422)

    def test_too_long_422(self) -> None:
        r = client.post("/analyze", json={"title": "t", "company": "c", "jd": "x" * 20001})
        self.assertEqual(r.status_code, 422)

    def test_control_chars_only_422(self) -> None:
        # 全控制字符 → sanitize 后空 → 422
        r = client.post("/analyze", json={"title": "\x00\x01\x02", "company": "c", "jd": "x" * 20})
        self.assertEqual(r.status_code, 422)

    # --- 限流 ---
    def test_ratelimit_triggers_429(self) -> None:
        app_mod._limiter.reset()
        n = app_mod._limiter.max_calls
        codes = [
            client.post("/analyze", json={"title": "", "company": "", "jd": ""}).status_code
            for _ in range(n + 5)
        ]
        self.assertEqual(codes[0], 422)   # 第一个正常处理(缺字段 422)
        self.assertIn(429, codes)         # 超限后出现 429
        self.assertEqual(codes[-1], 429)  # 最后一个必被限流


if __name__ == "__main__":
    unittest.main()
