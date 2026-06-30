"""评测主脚本:golden × analyze ×N × judge ×N → 指标(mean±std)→ 报告。

analyzer 与 judge 用不同模型族(跨模型 judge,避免 self-preference);同族会告警。

真实跑(需可用 provider):
    python eval/run_eval.py --analyzer-model glm-5.2 --judge-model deepseek-chat --repeats 3

验证流水线(不调 LLM,验证代码正确):
    python eval/run_eval.py --golden eval/golden.example.jsonl --fake
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parent.parent
_EVAL = Path(__file__).resolve().parent
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_EVAL))

from core import analyze_jd, derive_level  # noqa: E402
from core.llm import LLMClient  # noqa: E402
from core.schemas import AnalysisResult, Direction  # noqa: E402
from judge import JudgeResult, judge_analysis  # noqa: E402

_VALID_DIRECTIONS = {d.value for d in Direction}  # {"A","B","OFF"}
_REQUIRED_KEYS = ("url", "title", "company", "jd", "applied")


# ---------- golden / profile ----------

def load_golden(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise SystemExit(f"{path}:{i} 非合法 JSON: {e}")
        missing = [k for k in _REQUIRED_KEYS if k not in obj]
        if missing:
            raise SystemExit(f"{path}:{i} 缺字段: {missing}")
        gd = obj.get("gold_direction")
        if gd is not None and gd not in _VALID_DIRECTIONS:
            raise SystemExit(f"{path}:{i} gold_direction 非法({gd}),应为 A/B/OFF")
        items.append(obj)
    return items


def load_profile(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    example = path.parent / "profile.example.md"
    return example.read_text(encoding="utf-8")


# ---------- fake clients(--fake 验证用,不调 LLM)----------

class FakeAnalyzerClient:
    def complete_json(self, prompt: str, *, temperature: float = 0.3) -> dict[str, Any]:
        if any(k in prompt for k in ("销售", "解决方案", "售前", "商业化")):
            d, role, score = "A", "解决方案", 7
        elif any(k in prompt for k in ("运营", "市场")):
            d, role, score = "OFF", "运营", 3
        else:
            d, role, score = "B", "技术", 5
        return {
            "direction": d, "direction_reason": "fake", "ai_relevant": "是", "ai_score": 4,
            "tob": "高", "role_type": role, "skill_migrate": "3/5", "recommend": "推荐",
            "hidden_signal": "fake", "capability_bar": "可跨越", "hr_reply_prob": "中",
            "score": score, "conclusion": "建议投递",
        }


class FakeJudgeClient:
    def complete_json(self, prompt: str, *, temperature: float = 0.3) -> dict[str, Any]:
        return {
            "direction": "A", "direction_agree": True, "score_plausibility": 4,
            "hidden_signal_plausibility": 3, "rationale_plausible": True,
            "overall": 4, "comment": "fake ok",
        }


# ---------- 单条评测 ----------

@dataclass
class ItemResult:
    item: dict[str, Any]
    analyses: list[AnalysisResult | None] = field(default_factory=list)
    levels: list[str | None] = field(default_factory=list)
    judges: list[JudgeResult | None] = field(default_factory=list)
    analyzer_errors: list[str] = field(default_factory=list)
    judge_errors: list[str] = field(default_factory=list)


def run_item(item, analyzer_cli, judge_cli, profile, repeats) -> ItemResult:
    res = ItemResult(item=item)
    for _ in range(repeats):
        try:
            a = analyze_jd(title=item["title"], company=item["company"], jd=item["jd"], profile=profile, client=analyzer_cli)
        except Exception as e:  # noqa: BLE001 - 批量评测:单条失败不中断,记录原因
            a = None
            res.analyzer_errors.append(str(e)[:200])
        res.analyses.append(a)
        if a is None:
            res.levels.append(None)
            res.judges.append(None)
            continue
        res.levels.append(derive_level(a))
        try:
            j = judge_analysis(a, item["title"], item["company"], item["jd"], profile, client=judge_cli)
        except Exception as e:  # noqa: BLE001
            j = None
            res.judge_errors.append(str(e)[:200])
        res.judges.append(j)
    return res


# ---------- 指标 ----------

def _mean_std(xs: list[float]) -> tuple[float, float] | None:
    if not xs:
        return None
    m = statistics.mean(xs)
    s = statistics.stdev(xs) if len(xs) > 1 else 0.0
    return m, s


def _mode_ratio(vals: list[str | None]) -> float | None:
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    counts: dict[str, int] = {}
    for v in vals:
        counts[v] = counts.get(v, 0) + 1
    return max(counts.values()) / len(vals)


def compute_metrics(results: list[ItemResult], has_gold_direction: bool) -> dict[str, tuple[float, float]]:
    per_item: dict[str, list[float]] = {
        "apply_skip_consistency": [], "judge_agree": [], "direction_stability": [],
        "direction_accuracy": [], "judge_score_plausibility": [],
        "judge_hidden_signal": [], "judge_overall": [],
    }
    for r in results:
        applied = bool(r.item.get("applied"))
        consist = [1.0 if (lv in ("S", "A", "B")) == applied else 0.0 for lv in r.levels if lv]
        if consist:
            per_item["apply_skip_consistency"].append(statistics.mean(consist))
        agrees = [1.0 if j.direction_agree else 0.0 for j in r.judges if j]
        if agrees:
            per_item["judge_agree"].append(statistics.mean(agrees))
        ds = _mode_ratio([a.direction.value if a else None for a in r.analyses])
        if ds is not None:
            per_item["direction_stability"].append(ds)
        if has_gold_direction:
            gold = r.item.get("gold_direction")
            acc = [1.0 if (a and a.direction.value == gold) else 0.0 for a in r.analyses if a]
            if acc:
                per_item["direction_accuracy"].append(statistics.mean(acc))
        for key, attr in (("judge_score_plausibility", "score_plausibility"),
                          ("judge_hidden_signal", "hidden_signal_plausibility"),
                          ("judge_overall", "overall")):
            vals = [getattr(j, attr) for j in r.judges if j]
            if vals:
                per_item[key].append(statistics.mean(vals))
    summary: dict[str, tuple[float, float]] = {}
    for k, xs in per_item.items():
        ms = _mean_std(xs)
        if ms:
            summary[k] = ms
    return summary


# ---------- 报告 ----------

_NAMES = {
    "apply_skip_consistency": "apply/skip 一致性",
    "judge_agree": "judge 方向一致率(inter-rater)",
    "direction_stability": "方向稳定度(同条多次)",
    "direction_accuracy": "方向准确率(vs gold)",
    "judge_score_plausibility": "judge: score 合理性",
    "judge_hidden_signal": "judge: hidden_signal",
    "judge_overall": "judge: overall",
}


def _metric_row(key: str, summary: dict) -> str:
    label = _NAMES[key]
    if key in summary:
        m, s = summary[key]
        return f"| {label} | {m:.3f} | {s:.3f} |"
    return f"| {label} | N/A | — |"  # 数据全失败,显式标 N/A 而非消失


def write_report(path, results, summary, args, has_gold_direction, analyzer_model, judge_model) -> None:
    lines = [
        f"# 评测报告 · {datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
        f"- golden: `{args.golden}` ({len(results)} 条)",
        f"- repeats: {args.repeats}",
        f"- analyzer_model: {analyzer_model}",
        f"- judge_model: {judge_model}",
        f"- gold_direction 标注: {'有' if has_gold_direction else '无(方向准确率未算)'}\n",
        "## 指标(mean ± std,跨 golden 条目)\n",
        "| 指标 | mean | std |",
        "|---|---|---|",
    ]
    for k in _NAMES:
        if k == "direction_accuracy" and not has_gold_direction:
            continue
        lines.append(_metric_row(k, summary))
    total_calls = sum(len(r.analyses) for r in results)
    failed_a = sum(1 for r in results for a in r.analyses if a is None)
    failed_j = sum(1 for r in results for j in r.judges if j is None)
    lines += [
        "\n## 健壮性\n",
        f"- analyzer 调用: {total_calls}, 失败 {failed_a}",
        f"- judge 调用(成功 analysis 后): {total_calls - failed_a}, 失败 {failed_j}",
    ]
    if failed_a or failed_j:
        lines.append("\n## 失败原因样例\n")
        first_a = next((r.analyzer_errors[0] for r in results if r.analyzer_errors), None)
        first_j = next((r.judge_errors[0] for r in results if r.judge_errors), None)
        if first_a:
            lines.append(f"- analyzer 首条: {first_a}")
        if first_j:
            lines.append(f"- judge 首条: {first_j}")
    lines.append("\n## 异常 case(方向不稳 / judge overall≤2)\n")
    flagged = []
    for r in results:
        ds = _mode_ratio([a.direction.value if a else None for a in r.analyses])
        low = [j for j in r.judges if j and j.overall <= 2]
        if (ds is not None and ds < 1.0) or low:
            flagged.append((r, ds, len(low)))
    lines.append("(无)" if not flagged else "")
    for r, ds, nlow in flagged[:20]:
        lines.append(f"- {r.item.get('company', '?')} · {r.item.get('title', '?')}: 稳定度={ds:.2f}, low_judge={nlow}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(l for l in lines if l != "") + "\n", encoding="utf-8")


# ---------- main ----------

def main() -> None:
    # Windows 中文 locale 默认 GBK,print 重定向到文件时 emoji(⚠️)触发 UnicodeEncodeError。强制 UTF-8。
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="JD agent 评测")
    p.add_argument("--golden", default="eval/golden.jsonl")
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--analyzer-model", default=None)
    p.add_argument("--judge-model", default=None)
    p.add_argument("--profile", default="profile.md")
    p.add_argument("--report", default=None)
    p.add_argument("--fake", action="store_true", help="用 fake client 跑通流水线,不调 LLM")
    args = p.parse_args()

    golden_path = Path(args.golden).resolve() if Path(args.golden).is_absolute() else (Path.cwd() / args.golden).resolve()
    items = load_golden(golden_path)
    has_gold_direction = any("gold_direction" in it for it in items)
    profile = load_profile((_REPO / args.profile).resolve())

    if args.fake:
        analyzer_cli, judge_cli = FakeAnalyzerClient(), FakeJudgeClient()
        analyzer_model = args.analyzer_model or "fake"
        judge_model = args.judge_model or "fake"
    else:
        analyzer_cli = LLMClient(model=args.analyzer_model)
        judge_cli = LLMClient(model=args.judge_model)
        analyzer_model = analyzer_cli.model
        judge_model = judge_cli.model
        fam_a = analyzer_model.split("-")[0].lower()
        fam_j = judge_model.split("-")[0].lower()
        if fam_a == fam_j:
            print(f"⚠️ analyzer 与 judge 同模型族({fam_a}),self-preference 风险,结果仅供参考")

    print(f"评测 {len(items)} 条 × {args.repeats} repeats (analyzer={analyzer_model}, judge={judge_model}) ...")
    results = [run_item(it, analyzer_cli, judge_cli, profile, args.repeats) for it in items]
    summary = compute_metrics(results, has_gold_direction)

    report_path = Path(args.report) if args.report else (_REPO / "eval" / "reports" / f"{datetime.now().strftime('%Y-%m-%d')}.md")
    write_report(report_path, results, summary, args, has_gold_direction, analyzer_model, judge_model)
    print(f"报告: {report_path}")
    for k, (m, s) in summary.items():
        print(f"  {_NAMES.get(k, k)}: {m:.3f} ± {s:.3f}")


if __name__ == "__main__":
    main()
