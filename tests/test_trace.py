"""trace.py + LLMClient.complete_json trace 接入的单测(stdlib unittest,无需联网/真实 key)。

跑法(仓库根目录):python -m unittest tests.test_trace
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import core.trace as trace_mod  # noqa: E402
from core.llm import LLMClient, LLMError  # noqa: E402


def _read_jsonl(dir_: Path) -> list[dict]:
    files = sorted(dir_.glob("*.jsonl"))
    rows = []
    for fp in files:
        for line in fp.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


class TestLogLlmCall(unittest.TestCase):
    """直接测 log_llm_call 的字段、截断、开关、容错。"""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        self._old_dir = os.environ.get("TRACE_DIR")
        self._old_dis = os.environ.get("TRACE_DISABLED")
        os.environ["TRACE_DIR"] = self._tmp
        os.environ.pop("TRACE_DISABLED", None)

    def tearDown(self) -> None:
        for k, v in (("TRACE_DIR", self._old_dir), ("TRACE_DISABLED", self._old_dis)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_writes_six_fields(self) -> None:
        trace_mod.log_llm_call(
            step="analyze", model="glm-5.2", latency_ms=123.456,
            prompt="你好", output='{"direction":"A"}',
        )
        rows = _read_jsonl(Path(self._tmp))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        # design doc Step 3 规定的 6 个字段,且不含 token/cost
        self.assertEqual(
            set(row.keys()), {"ts", "step", "model", "latency_ms", "input_hash", "output_summary"}
        )
        self.assertEqual(row["step"], "analyze")
        self.assertEqual(row["model"], "glm-5.2")
        self.assertEqual(row["output_summary"], '{"direction":"A"}')
        self.assertIsInstance(row["latency_ms"], float)
        self.assertIsInstance(row["input_hash"], str)
        self.assertEqual(len(row["input_hash"]), 16)
        self.assertIn("T", row["ts"])  # ISO8601

    def test_disabled_writes_nothing(self) -> None:
        os.environ["TRACE_DISABLED"] = "1"
        trace_mod.log_llm_call(
            step="x", model="m", latency_ms=1, prompt="p", output="o",
        )
        self.assertEqual(_read_jsonl(Path(self._tmp)), [])

    def test_output_truncated_and_single_line(self) -> None:
        long_out = "行\n带\n换\n行" * 100
        trace_mod.log_llm_call(
            step="greeting", model="m", latency_ms=1, prompt="p", output=long_out,
        )
        row = _read_jsonl(Path(self._tmp))[0]
        self.assertNotIn("\n", row["output_summary"])
        self.assertLessEqual(len(row["output_summary"]), 200)

    def test_input_hash_deterministic(self) -> None:
        trace_mod.log_llm_call(step="a", model="m", latency_ms=1, prompt="same", output="o1")
        trace_mod.log_llm_call(step="b", model="m", latency_ms=1, prompt="same", output="o2")
        trace_mod.log_llm_call(step="c", model="m", latency_ms=1, prompt="different", output="o3")
        rows = _read_jsonl(Path(self._tmp))
        self.assertEqual(rows[0]["input_hash"], rows[1]["input_hash"])
        self.assertNotEqual(rows[0]["input_hash"], rows[2]["input_hash"])

    def test_swallows_write_errors(self) -> None:
        # TRACE_DIR 指向一个已存在文件的「子路径」→ mkdir 必然失败 → 必须静默
        blocker = Path(self._tmp) / "blocker"
        blocker.write_text("x", encoding="utf-8")
        os.environ["TRACE_DIR"] = str(blocker / "sub")
        # 不应抛
        trace_mod.log_llm_call(step="a", model="m", latency_ms=1, prompt="p", output="o")


class TestCompleteJsonTrace(unittest.TestCase):
    """complete_json 在每次 _call 后落 trace,step 透传正确,失败也记。"""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        self._old_dir = os.environ.get("TRACE_DIR")
        os.environ["TRACE_DIR"] = self._tmp
        os.environ.pop("TRACE_DISABLED", None)
        # api_key 必填但不会真正联网(_call 被 mock);base_url 让协议推断为 openai
        self.cli = LLMClient(api_key="fake-key", base_url="http://localhost", retries=2)

    def tearDown(self) -> None:
        if self._old_dir is None:
            os.environ.pop("TRACE_DIR", None)
        else:
            os.environ["TRACE_DIR"] = self._old_dir

    def test_success_logs_step_and_output(self) -> None:
        with patch.object(self.cli, "_call", return_value=('{"k": 1}', None)):
            data = self.cli.complete_json("prompt-here", step="analyze")
        self.assertEqual(data, {"k": 1})
        rows = _read_jsonl(Path(self._tmp))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["step"], "analyze")
        self.assertEqual(rows[0]["model"], self.cli.model)
        self.assertEqual(rows[0]["output_summary"], '{"k": 1}')
        # usage=None(mock 拿不到响应头)时不写 token/cost 字段,保持旧 6 字段
        self.assertNotIn("token_in", rows[0])
        # mock 的 _call 瞬时返回,latency 可能 round 到 0.0;只校验非负
        self.assertGreaterEqual(rows[0]["latency_ms"], 0)

    def test_logs_token_and_cost_when_usage(self) -> None:
        # _call 返回 (content, usage):Phase 2 trace 在此追加 token/cost 字段
        with patch.object(
            self.cli, "_call",
            return_value=('{"k": 1}', {"token_in": 1000, "token_out": 500}),
        ):
            self.cli.complete_json("p", step="analyze")
        row = _read_jsonl(Path(self._tmp))[0]
        self.assertEqual(row["token_in"], 1000)
        self.assertEqual(row["token_out"], 500)
        # model 默认 gpt-4o-mini 有价目 → cost 估算落盘
        self.assertIn("cost_usd", row)
        self.assertGreater(row["cost_usd"], 0)

    def test_no_cost_for_unknown_model(self) -> None:
        cli = LLMClient(api_key="fake-key", base_url="http://localhost", model="totally-unknown-model")
        with patch.object(
            cli, "_call",
            return_value=('{"k": 1}', {"token_in": 100, "token_out": 50}),
        ):
            cli.complete_json("p")
        row = _read_jsonl(Path(self._tmp))[0]
        self.assertEqual(row["token_in"], 100)  # token 仍记
        self.assertNotIn("cost_usd", row)        # 未知模型不算 cost

    def test_error_logs_each_attempt_then_raises(self) -> None:
        def boom(_prompt, _temp):
            raise RuntimeError("net down")
        with patch.object(self.cli, "_call", side_effect=boom):
            with self.assertRaises(LLMError):
                self.cli.complete_json("p", step="greeting")
        rows = _read_jsonl(Path(self._tmp))
        self.assertEqual(len(rows), self.cli.retries)  # 每次重试都记一条
        self.assertTrue(all(r["output_summary"].startswith("[error]") for r in rows))
        self.assertTrue(all(r["step"] == "greeting" for r in rows))

    def test_default_step_is_llm(self) -> None:
        with patch.object(self.cli, "_call", return_value=('{"k": 1}', None)):
            self.cli.complete_json("p")
        rows = _read_jsonl(Path(self._tmp))
        self.assertEqual(rows[0]["step"], "llm")


if __name__ == "__main__":
    unittest.main()
