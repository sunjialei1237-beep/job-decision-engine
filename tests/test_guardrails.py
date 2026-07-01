"""guardrails.py / ratelimit.py 单测(stdlib unittest)。

跑法:python -m unittest tests.test_guardrails
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.guardrails import sanitize_text  # noqa: E402
from api.ratelimit import RateLimiter  # noqa: E402


class TestSanitize(unittest.TestCase):
    def test_strips_control_chars(self) -> None:
        self.assertEqual(sanitize_text("a\x00b\x07c"), "abc")
        self.assertEqual(sanitize_text("\x01\x02\x7f"), "")
        self.assertEqual(sanitize_text("净文本"), "净文本")

    def test_keeps_normal_whitespace(self) -> None:
        # \t \n \r 是正常文本字符,保留
        self.assertEqual(sanitize_text("a\tb\nc\rd"), "a\tb\nc\rd")

    def test_empty(self) -> None:
        self.assertEqual(sanitize_text(""), "")


class TestRateLimiter(unittest.TestCase):
    def test_allows_up_to_limit(self) -> None:
        r = RateLimiter(3)
        self.assertTrue(r.allow("ip1"))
        self.assertTrue(r.allow("ip1"))
        self.assertTrue(r.allow("ip1"))
        self.assertFalse(r.allow("ip1"))  # 第 4 次超限

    def test_per_ip_isolation(self) -> None:
        r = RateLimiter(2)
        r.allow("ip1")
        r.allow("ip1")
        self.assertFalse(r.allow("ip1"))
        self.assertTrue(r.allow("ip2"))  # 不同 IP 独立计数

    def test_window_evicts_old_hits(self) -> None:
        r = RateLimiter(2, window_sec=60)
        r.allow("x")
        r.allow("x")
        self.assertFalse(r.allow("x"))
        # 把历史打点推到窗口外(远古时间戳),过期清理后应重新放行
        r._hits["x"] = [0.0, 0.0]
        self.assertTrue(r.allow("x"))

    def test_reset(self) -> None:
        r = RateLimiter(1)
        r.allow("x")
        self.assertFalse(r.allow("x"))
        r.reset()
        self.assertTrue(r.allow("x"))


if __name__ == "__main__":
    unittest.main()
