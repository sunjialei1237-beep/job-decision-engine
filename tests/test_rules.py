"""rules.py / derive_level 的确定性单测(stdlib unittest,无需额外依赖)。

跑法(仓库根目录):python -m unittest tests.test_rules
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.analyze import derive_level  # noqa: E402
from core.rules import is_pure_telesales, level_from_score  # noqa: E402
from core.schemas import AnalysisResult, Direction  # noqa: E402


def _make(role_type: str = "产品", hidden_signal: str = "x", score: int = 5) -> AnalysisResult:
    return AnalysisResult(
        direction=Direction.A,
        direction_reason="x",
        ai_relevant="yes",
        ai_score=4,
        tob="高",
        role_type=role_type,
        skill_migrate="3/5",
        recommend="推荐",
        hidden_signal=hidden_signal,
        capability_bar="低",
        hr_reply_prob="中",
        score=score,
        conclusion="建议投递",
    )


class TestLevelFromScore(unittest.TestCase):
    def test_thresholds(self) -> None:
        self.assertEqual(level_from_score(9), "S")
        self.assertEqual(level_from_score(8), "S")
        self.assertEqual(level_from_score(7), "A")
        self.assertEqual(level_from_score(6), "A")
        self.assertEqual(level_from_score(5), "B")
        self.assertEqual(level_from_score(4), "B")
        self.assertEqual(level_from_score(3), "不建议")

    def test_telesales_forces_not_recommend(self) -> None:
        self.assertEqual(level_from_score(9, telesales=True), "不建议")


class TestIsPureTelesales(unittest.TestCase):
    def test_sales_plus_telesales_signal(self) -> None:
        self.assertTrue(is_pure_telesales("销售", "实为电话外呼电销"))
        self.assertTrue(is_pure_telesales("电话销售", "cold-call 驱动"))

    def test_not_telesales(self) -> None:
        self.assertFalse(is_pure_telesales("解决方案", "售前 POC"))
        self.assertFalse(is_pure_telesales("销售", "方案讲解"))  # 销售但无电销信号
        self.assertFalse(is_pure_telesales("", "电销"))


class TestDeriveLevel(unittest.TestCase):
    def test_pure_telesales_overrides_high_score(self) -> None:
        a = _make(role_type="销售", hidden_signal="电话量驱动外呼", score=7)
        self.assertEqual(derive_level(a), "不建议")

    def test_normal_high_score(self) -> None:
        a = _make(role_type="解决方案", hidden_signal="售前", score=8)
        self.assertEqual(derive_level(a), "S")


if __name__ == "__main__":
    unittest.main()
