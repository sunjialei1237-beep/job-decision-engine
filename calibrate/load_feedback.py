"""闭环反馈数据装配(设计文档 Step 2 · load_feedback)。

join golden.jsonl(JD 正文 + apply 标签)∩ applied_enriched.json(outcome)
on url → 对每条现跑 analyze_jd 打分 → 输出 scored.jsonl。

为什么 score 现跑而非读 eval 缓存:calibrate 自包含,score 永远对应当前引擎
版本,改 prompt 后 correlate 立刻反映。集小(=golden 规模,目前 29),成本可控。

用法:
  # 验证管线(fake 打分,不调 LLM)
  python calibrate/load_feedback.py --fake
  # 真打分
  python calibrate/load_feedback.py --analyzer-model glm-5.2
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_EVAL = _REPO / "eval"
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_EVAL))

from core import analyze_jd  # noqa: E402
from core.llm import LLMClient, LLMError  # noqa: E402
from run_eval import FakeAnalyzerClient, load_profile  # noqa: E402  复用 eval 的 fake 与 profile 加载


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    # Windows 中文 locale 默认 GBK,print 中文/重定向时强制 UTF-8(同 run_eval.py)
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(description="闭环反馈数据装配:join golden×applied + 打分")
    ap.add_argument("--golden", default="eval/golden.jsonl")
    ap.add_argument("--applied", default="data/applied_enriched.json")
    ap.add_argument("--profile", default="profile.md")
    ap.add_argument("--out", default="data/scored.jsonl")
    ap.add_argument("--analyzer-model", default=None)
    ap.add_argument("--fake", action="store_true", help="fake 打分,不调 LLM(验证管线)")
    args = ap.parse_args()

    golden_path = Path(args.golden).resolve() if Path(args.golden).is_absolute() else (_REPO / args.golden).resolve()
    applied_path = Path(args.applied).expanduser().resolve()
    profile_text = load_profile((_REPO / args.profile).resolve())

    items = _load_jsonl(golden_path)
    applied = {r["url"]: r for r in _load_json(applied_path)}

    if args.fake:
        cli, model = FakeAnalyzerClient(), "fake"
    else:
        cli = LLMClient(model=args.analyzer_model)
        model = cli.model

    print(f"装配 {len(items)} 条 golden × applied,on url;打分 model={model}")
    scored, n_hit, n_miss, n_fail = [], 0, 0, 0
    for it in items:
        rec = applied.get(it["url"])
        if rec is None:
            n_miss += 1
            continue
        n_hit += 1
        try:
            a = analyze_jd(title=it["title"], company=it["company"], jd=it["jd"], profile=profile_text, client=cli)
        except Exception as e:  # noqa: BLE001 - 批量装配:单条打分失败不中断
            n_fail += 1
            print(f"  ⚠ 打分失败 {it['company']}·{it['title']}: {str(e)[:120]}")
            continue
        scored.append({
            "url": it["url"], "title": it["title"], "company": it["company"], "jd": it["jd"],
            "applied": bool(it.get("applied")),
            "outcome": rec.get("outcome"),
            "direction": a.direction.value, "score": a.score,
            "recommend": a.recommend, "conclusion": a.conclusion,
        })

    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for s in scored:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    print(f"\n输出 {len(scored)} 条 → {out_path}")
    print(f"  join 命中 {n_hit} / 未命中 {n_miss} / 打分失败 {n_fail}")
    print(f"  outcome 分布: {dict(Counter((s['outcome'] or 'pending') for s in scored))}")


if __name__ == "__main__":
    main()
