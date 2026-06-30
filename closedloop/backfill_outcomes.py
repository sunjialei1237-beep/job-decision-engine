"""闭环 outcome 回填:给 applied.json 的空 outcome 字段填值。

默认安全:写到 --out(富化副本),原始 applied.json 不动。
--in-place 才回写原文件(先备份 .bak)。

outcome 优先级:
  1. 已有非空 outcome(手动/历史):跳过,幂等
  2. --manual(jsonl,用户手记的正向结果):replied/interview/rejected
  3. 时间推导:投递超过 --threshold 天(默认 7)且无 manual → no_reply
  4. 未到阈值:留 null(pending,投递太近,不算转化)

用法:
  python closedloop/backfill_outcomes.py \
      --applied ~/boss-scraper/data/applied.json \
      --manual closedloop/manual_outcomes.jsonl \
      --out data/applied_enriched.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]


def _load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _load_jsonl(p: Path | None) -> list[dict]:
    if not p or not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    # Windows 中文 locale 默认 GBK,print 中文/重定向时强制 UTF-8(同 run_eval.py)
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(description="闭环 outcome 回填")
    ap.add_argument("--applied", required=True, help="applied.json 路径")
    ap.add_argument("--manual", default="closedloop/manual_outcomes.jsonl", help="手记正向结果 jsonl(job_id→outcome)")
    ap.add_argument("--out", default=str(_REPO / "data" / "applied_enriched.json"), help="富化副本输出路径")
    ap.add_argument("--threshold", type=int, default=7, help="沉默多少天判 no_reply(默认 7)")
    ap.add_argument("--today", default=dt.date.today().isoformat(), help="基准日期(默认今天)")
    ap.add_argument("--in-place", action="store_true", help="回写原 applied.json(先备份 .bak)")
    args = ap.parse_args()

    applied_path = Path(args.applied).expanduser().resolve()
    rows = _load_json(applied_path)
    today = dt.date.fromisoformat(args.today)
    manual = {m["job_id"]: m for m in _load_jsonl((Path(args.manual)).expanduser().resolve())}

    n_manual = n_noreply = n_pending = n_kept = 0
    for r in rows:
        jid = r.get("job_id")
        cur = r.get("outcome")
        if cur not in (None, "", "null"):           # 1. 已有 → 幂等跳过
            n_kept += 1
            continue
        if jid in manual:                            # 2. manual 正向
            m = manual[jid]
            r["outcome"] = m["outcome"]
            r["outcome_date"] = m.get("outcome_date") or args.today
            n_manual += 1
            continue
        d = r.get("date")                            # 3/4. 时间推导
        try:
            age = (today - dt.date.fromisoformat(d)).days
        except (TypeError, ValueError):
            age = 0
        if age >= args.threshold:
            r["outcome"] = "no_reply"
            r["outcome_date"] = args.today
            n_noreply += 1
        else:
            n_pending += 1                            # 投递太近,留 null

    out_path = applied_path if args.in_place else Path(args.out).expanduser().resolve()
    if args.in_place:
        bak = applied_path.with_suffix(applied_path.suffix + ".bak")
        shutil.copy2(applied_path, bak)
        print(f"已备份原文件 → {bak}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"输入 {len(rows)} 条 → {out_path}")
    print(f"  manual 正向: {n_manual}")
    print(f"  no_reply(>={args.threshold}d 沉默): {n_noreply}")
    print(f"  pending(未到阈值,留 null): {n_pending}")
    print(f"  已有 outcome(跳过): {n_kept}")


if __name__ == "__main__":
    main()
