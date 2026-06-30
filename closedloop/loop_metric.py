"""闭环转化漏斗:从富化后的 applied.json 算 投递→回复→面试 的转化率。

用法:
  python closedloop/loop_metric.py --enriched data/applied_enriched.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def main() -> None:
    # Windows 中文 locale 默认 GBK,强制 UTF-8(同 run_eval.py)
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(description="闭环转化漏斗")
    ap.add_argument("--enriched", default="data/applied_enriched.json")
    args = ap.parse_args()

    rows = json.loads(Path(args.enriched).read_text(encoding="utf-8"))
    n = len(rows)
    by = Counter((r.get("outcome") or "pending") for r in rows)

    replied = by.get("replied", 0)
    interview = by.get("interview", 0)
    rejected = by.get("rejected", 0)
    no_reply = by.get("no_reply", 0)
    pending = by.get("pending", 0)

    positive = replied + interview
    reply_rate = positive / n if n else 0.0
    interview_rate = interview / n if n else 0.0

    print(f"闭环漏斗(共 {n} 条投递)")
    print(f"  投递              : {n}")
    print(f"  有正向回应(回复+面试): {positive}   回复率 {reply_rate:.1%}")
    print(f"  ├─ 回复           : {replied}")
    print(f"  └─ 约面试         : {interview}   面试率 {interview_rate:.1%}")
    print()
    print("outcome 分布:")
    for k, v in by.most_common():
        pct = f"{v/n:.1%}" if n else ""
        print(f"  {k:12s}: {v}  {pct}")


if __name__ == "__main__":
    main()
