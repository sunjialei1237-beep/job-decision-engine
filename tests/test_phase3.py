"""Phase 3 测试:API key 认证 / 批处理 / metrics(stdlib unittest + TestClient)。

跑法:python -m unittest tests.test_phase3
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import api.app as app_mod  # noqa: E402
from api.metrics import metrics  # noqa: E402
from core.schemas import AnalysisResult, Direction  # noqa: E402

_GOOD = {"title": "AI 解决方案", "company": "某公司", "jd": "x" * 20}
_BAD = {"title": "", "company": "", "jd": ""}  # 缺字段 → 422(不调 LLM)


def _fake_analysis(score: int = 9) -> AnalysisResult:
    return AnalysisResult(
        direction=Direction.A, direction_reason="r", ai_relevant="y", ai_score=5,
        tob="高", role_type="解决方案", skill_migrate="4/5", recommend="强烈推荐",
        hidden_signal="x", capability_bar="低", hr_reply_prob="高",
        score=score, conclusion="建议",
    )


class TestAuth(unittest.TestCase):
    def setUp(self) -> None:
        self._old = os.environ.get("ENGINE_API_KEYS")
        app_mod._limiter.reset()
        metrics.reset()

    def tearDown(self) -> None:
        if self._old is None:
            os.environ.pop("ENGINE_API_KEYS", None)
        else:
            os.environ["ENGINE_API_KEYS"] = self._old

    def test_dev_mode_no_auth(self) -> None:
        """未配 ENGINE_API_KEYS → 开发模式,无 key 也放行。"""
        os.environ.pop("ENGINE_API_KEYS", None)
        with patch.object(app_mod, "analyze_jd", return_value=_fake_analysis()):
            r = TestClient(app_mod.app).post("/analyze", json=_GOOD)
        self.assertEqual(r.status_code, 200)

    def test_no_key_401(self) -> None:
        os.environ["ENGINE_API_KEYS"] = "k1,k2"
        r = TestClient(app_mod.app).post("/analyze", json=_GOOD)
        self.assertEqual(r.status_code, 401)

    def test_wrong_key_401(self) -> None:
        os.environ["ENGINE_API_KEYS"] = "k1"
        r = TestClient(app_mod.app).post("/analyze", json=_GOOD, headers={"X-API-Key": "wrong"})
        self.assertEqual(r.status_code, 401)

    def test_right_key_200(self) -> None:
        os.environ["ENGINE_API_KEYS"] = "k1,k2"
        with patch.object(app_mod, "analyze_jd", return_value=_fake_analysis()):
            r = TestClient(app_mod.app).post("/analyze", json=_GOOD, headers={"X-API-Key": "k2"})
        self.assertEqual(r.status_code, 200)

    def test_exempt_paths_no_key(self) -> None:
        """health / metrics / 前端 豁免认证。"""
        os.environ["ENGINE_API_KEYS"] = "k1"
        c = TestClient(app_mod.app)
        self.assertEqual(c.get("/health").status_code, 200)
        self.assertEqual(c.get("/metrics").status_code, 200)
        self.assertEqual(c.get("/").status_code, 200)


class TestBatch(unittest.TestCase):
    def setUp(self) -> None:
        os.environ.pop("ENGINE_API_KEYS", None)
        app_mod._limiter.reset()
        metrics.reset()

    def test_batch_ok(self) -> None:
        with patch.object(app_mod, "analyze_jd", return_value=_fake_analysis(9)):
            r = TestClient(app_mod.app).post(
                "/analyze-batch", json={"items": [_GOOD, _GOOD, _GOOD]}
            )
        self.assertEqual(r.status_code, 200)
        res = r.json()["results"]
        self.assertEqual(len(res), 3)
        self.assertTrue(all(x["level"] == "S" for x in res))

    def test_batch_single_failure_isolated(self) -> None:
        def fake(title, company, jd, profile, **kw):  # noqa: ANN001
            if title == "bad":
                raise RuntimeError("boom")
            return _fake_analysis()

        items = [
            {"title": "ok", "company": "c", "jd": "x" * 20},
            {"title": "bad", "company": "c", "jd": "x" * 20},
            {"title": "ok2", "company": "c", "jd": "x" * 20},
        ]
        with patch.object(app_mod, "analyze_jd", side_effect=fake):
            r = TestClient(app_mod.app).post("/analyze-batch", json={"items": items})
        res = r.json()["results"]
        self.assertEqual(r.status_code, 200)
        self.assertIsNotNone(res[0]["analysis"])
        self.assertIsNone(res[1]["analysis"])
        self.assertIsNotNone(res[1]["error"])
        self.assertIsNotNone(res[2]["analysis"])  # 单条失败不影响其余

    def test_batch_over_limit_422(self) -> None:
        r = TestClient(app_mod.app).post(
            "/analyze-batch", json={"items": [{"title": "t", "company": "c", "jd": "x"}] * 51}
        )
        self.assertEqual(r.status_code, 422)

    def test_batch_empty_422(self) -> None:
        r = TestClient(app_mod.app).post("/analyze-batch", json={"items": []})
        self.assertEqual(r.status_code, 422)


class TestMetrics(unittest.TestCase):
    def setUp(self) -> None:
        os.environ.pop("ENGINE_API_KEYS", None)
        app_mod._limiter.reset()
        metrics.reset()

    def test_metrics_format(self) -> None:
        r = TestClient(app_mod.app).get("/metrics")
        self.assertEqual(r.status_code, 200)
        self.assertIn("# TYPE engine_requests_total counter", r.text)
        self.assertIn("engine_request_latency_seconds_sum", r.text)

    def test_metrics_counts_requests(self) -> None:
        c = TestClient(app_mod.app)
        c.get("/health")
        c.get("/health")
        m = c.get("/metrics").text
        self.assertIn('path="/health",status="200"', m)

    def test_metrics_captures_422(self) -> None:
        c = TestClient(app_mod.app)
        c.post("/analyze", json=_BAD)  # 422
        m = c.get("/metrics").text
        self.assertIn('status="422"', m)


if __name__ == "__main__":
    unittest.main()
