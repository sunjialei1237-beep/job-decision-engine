"""评分↔outcome 校准分析(设计文档 Step 2 · correlate)。

gating(诚实):"真实 HR 反馈"(replied/interview/rejected)< 30 条 → 阻塞,
只输出"数据不足"报告,不算相关性。no_reply 是时间推导的软信号(沉默=未回复),
不计入回复率分母 —— 沉默往往是 open-rate 问题(HR 没点开),与岗位质量无关。

数据足够时算:score↔outcome Pearson 相关 + 评分分箱 vs 正向回应率表。
另产出 mismatch case(|score-outcome_score|>3)供 reviewer.md 归因。

用法:
  python calibrate/correlate.py --scored data/scored.jsonl
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]

# outcome → 校准分(reviewer mismatch 触发用)。
# 设计原则:no_reply 不该和"被明确拒绝"等价 —— 沉默往往是 HR 没点开(open-rate
# 问题),与岗位质量无关,故给最低分且不进"回复率"分母。
OUTCOME_SCORE = {"interview": 10, "replied": 7, "rejected": 3, "no_reply": 1}
POSITIVE = {"replied", "interview"}                  # 正向回应(回复率分子)
HR_FEEDBACK = {"replied", "interview", "rejected"}   # 真实 HR 反馈(gating 分母)
GATE = 30  # 设计文档:outcome < 30 条诚实输出"数据不足"


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _bucket(score: int) -> str:
    if score <= 3:
        return "0-3(低)"
    if score <= 6:
        return "4-6(中)"
    return "7-10(高)"


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(description="评分↔outcome 校准分析")
    ap.add_argument("--scored", default="data/scored.jsonl")
    ap.add_argument("--report", default=None)
    args = ap.parse_args()

    rows = _load_jsonl(Path(args.scored).expanduser().resolve())
    n = len(rows)
    by_outcome = Counter((r["outcome"] or "pending") for r in rows)
    n_hr = sum(by_outcome.get(k, 0) for k in HR_FEEDBACK)
    gated = n_hr < GATE

    # mismatch case(reviewer 触发条件:|score - outcome_score|>3)
    mismatches = []
    for r in rows:
        os_ = OUTCOME_SCORE.get(r["outcome"])
        if os_ is None:
            continue
        delta = abs(r["score"] - os_)
        if delta > 3:
            mismatches.append({
                "company": r["company"], "title": r["title"], "score": r["score"],
                "outcome": r["outcome"], "recommend": r.get("recommend", ""),
                "delta": delta,
            })
    mismatches.sort(key=lambda x: -x["delta"])

    # 评分分箱 vs 正向回应率
    buckets: dict[str, dict[str, int]] = {}
    for r in rows:
        b = _bucket(r["score"])
        d = buckets.setdefault(b, {"n": 0, "positive": 0})
        d["n"] += 1
        if r["outcome"] in POSITIVE:
            d["positive"] += 1

    # ---- 报告 ----
    lines = [
        f"# 校准报告 · {datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
        f"- scored: `{args.scored}` ({n} 条 join 命中)",
        f"- 真实 HR 反馈(replied/interview/rejected): {n_hr} 条  (gating 阈值 {GATE})",
        f"- outcome 分布: {dict(by_outcome)}\n",
    ]

    if gated:
        lines += [
            "## ⚠ 数据不足 — 校准阻塞\n",
            f"真实 HR 反馈仅 {n_hr} 条(< {GATE}),score↔回复相关性**不可信,不计算**。",
            f"no_reply {by_outcome.get('no_reply', 0)} 条是时间推导的软信号(沉默=未回复),"
            "不计入回复率分母 —— 沉默往往是 open-rate 问题(HR 没点开),与岗位质量无关。\n",
            f"**需要**:持续回填真实 outcome(手动标 replied/interview/rejected),"
            f"累计 ≥ {GATE} 条后本脚本自动开始计算相关性。\n",
        ]
    else:
        xs, ys = [], []
        for r in rows:
            os_ = OUTCOME_SCORE.get(r["outcome"])
            if os_ is not None:
                xs.append(r["score"])
                ys.append(os_)
        corr = _pearson(xs, ys)
        lines += [
            "## score↔outcome 相关性\n",
            f"- Pearson r = {corr:.3f}" if corr is not None else "- 样本不足,无法算 Pearson",
            f"- 正向回复率(回复+面试): {sum(by_outcome.get(k,0) for k in POSITIVE)}/{n}\n",
        ]

    # 分箱表(gating 时也展示,标注"仅供参考"——infra 该有的结构都在)
    tag = "(数据不足,仅供参考)" if gated else ""
    lines += [
        f"## 评分分箱 vs 正向回应率{tag}\n",
        "| 评分箱 | 样本 | 正向回复 | 回复率 |",
        "|---|---|---|---|",
    ]
    for b in ["0-3(低)", "4-6(中)", "7-10(高)"]:
        d = buckets.get(b, {"n": 0, "positive": 0})
        rate = f"{d['positive']/d['n']:.1%}" if d["n"] else "—"
        lines.append(f"| {b} | {d['n']} | {d['positive']} | {rate} |")

    lines += [f"\n## mismatch case(|score-outcome_score|>3,reviewer 归因用,共 {len(mismatches)} 条)\n"]
    if mismatches:
        for m in mismatches[:15]:
            lines.append(f"- {m['company']}·{m['title']}: score={m['score']} outcome={m['outcome']} Δ={m['delta']} ({m['recommend']})")
    else:
        lines.append("(无)")

    report_path = Path(args.report) if args.report else (_REPO / "calibrate" / "reports" / f"{datetime.now().strftime('%Y-%m-%d')}.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"报告: {report_path}")
    print(f"  n={n} 真实HR反馈={n_hr} {'[GATED 数据不足]' if gated else '[OK]'} mismatch={len(mismatches)}")


if __name__ == "__main__":
    main()
