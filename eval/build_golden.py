"""构造评测 golden 集:join applied.json × _workflow_args.json on url。

⚠️ 参考实现:适配作者本地 boss-scraper 的数据格式。换数据源需改适配逻辑。
真实 golden.jsonl 含真实 JD(平台抓取),已 gitignore,不入开源仓库。

用法:
    python eval/build_golden.py \
        --applied ~/boss-scraper/data/applied.json \
        --workflow-args ~/boss-scraper/data/jobs/2026-06-17/_workflow_args.json \
        --out eval/golden.jsonl

输出 jsonl,每行 {url, title, company, jd, applied[, gold_direction]}。
applied: 用户实投(True)/ 跳过(False),来自 applied.json 的 status。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    p = argparse.ArgumentParser(description="构造评测 golden 集")
    p.add_argument("--applied", required=True, help="applied.json 路径(含 status/url)")
    p.add_argument("--workflow-args", required=True, help="_workflow_args.json 路径(含 JD 正文)")
    p.add_argument("--out", default="eval/golden.jsonl")
    args = p.parse_args()

    applied = load_json(Path(args.applied))
    wf = load_json(Path(args.workflow_args))

    # url → applied(bool):status == "applied" 为实投,其余(skipped 等)为跳过
    applied_map: dict[str, bool] = {}
    for a in applied:
        url = a.get("url")
        if url:
            applied_map[url] = (a.get("status", "").strip().lower() == "applied")

    # join: wf 条目 ∩ applied_map on url
    out = []
    skipped_empty_jd = 0
    for w in wf:
        url = w.get("url")
        if url not in applied_map:
            continue
        if not w.get("jd"):
            skipped_empty_jd += 1
            continue
        out.append({
            "url": url,
            "title": w.get("title", ""),
            "company": w.get("company", ""),
            "jd": w.get("jd", ""),
            "applied": applied_map[url],
        })

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for item in out:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    n_applied = sum(1 for x in out if x["applied"])
    n_skip = len(out) - n_applied
    print(f"golden: {len(out)} 条 ({n_applied} applied + {n_skip} skipped) -> {out_path}")
    if skipped_empty_jd:
        print(f"(跳过 {skipped_empty_jd} 条空 JD)")
    if len(out) < 20:
        print("⚠️ 不足 20 条起步线,考虑补 _workflow_args 落盘或补标注")


if __name__ == "__main__":
    main()
