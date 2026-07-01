"""core/pricing.py 单测(stdlib unittest)。

跑法:python -m unittest tests.test_pricing
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.pricing import estimate_cost_usd  # noqa: E402


class TestEstimateCost(unittest.TestCase):
    def test_known_exact_model(self) -> None:
        # gpt-4o-mini: 0.00015/1k in, 0.0006/1k out(价目表精确键)
        cost = estimate_cost_usd("gpt-4o-mini", 1000, 500)
        self.assertAlmostEqual(cost, 0.00015 + 0.0003, places=8)

    def test_family_fallback(self) -> None:
        # glm-5.2 无精确键 → 回退到 glm 族
        cost = estimate_cost_usd("glm-5.2", 1000, 1000)
        self.assertIsNotNone(cost)
        self.assertGreater(cost, 0)

    def test_case_insensitive(self) -> None:
        self.assertEqual(
            estimate_cost_usd("GPT-4O-MINI", 100, 0),
            estimate_cost_usd("gpt-4o-mini", 100, 0),
        )

    def test_unknown_model_returns_none(self) -> None:
        self.assertIsNone(estimate_cost_usd("made-up-model-xyz", 1000, 1000))

    def test_zero_tokens(self) -> None:
        self.assertEqual(estimate_cost_usd("gpt-4o-mini", 0, 0), 0.0)

    def test_negative_returns_none(self) -> None:
        self.assertIsNone(estimate_cost_usd("gpt-4o-mini", -1, 10))
        self.assertIsNone(estimate_cost_usd("gpt-4o-mini", 10, -1))


if __name__ == "__main__":
    unittest.main()
