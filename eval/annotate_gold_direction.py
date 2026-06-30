"""给 golden 集初标 gold_direction(A/B/OFF),输出 Markdown 表格供人工确认。

规则基于候选人方向权重:
- A: AI ToB 销售/解决方案/售前/商业化/AI 产品/Agent 产品
- B: AI 技术相关实习(AIGC 应用/Agent 工程师/算法/开发)
- OFF: 运营/市场/纯 C 端/非 AI

标注后需人工复核,确认无误再写回 golden.jsonl。
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def _tokens(title: str, jd: str) -> set[str]:
    text = f"{title} {jd[:300]}".lower()
    return set(re.findall(r"[a-z]+|\d+[a-z]*|[一-龥]{2,}", text))


_A_TECH = {"ai", "agent", "aigc", "大模型", "人工智能", "智能体"}
_A_ROLE = {"产品", "售前", "解决方案", "销售", "商业化", "bd", "客户经理", "管培生"}
_B_ROLE = {"工程师", "开发", "算法", "研发", "程序员"}
_OFF_ROLE = {"运营", "市场", "品牌", "公关", "人力", "行政", "财务", "客服"}


def suggest_direction(title: str, jd: str, applied: bool) -> str:  # noqa: ARG001
    lower_title = title.lower()
    ai_signals = {"ai", "agent", "aigc", "大模型", "人工智能", "智能体", "saas", "云计算"}
    has_ai_signal = any(s in lower_title for s in ai_signals) or "ai " in lower_title

    # 纯电销硬挡
    telesales_signals = {"电话", "外呼", "cold", "电销", "邀约", "无需外出"}
    if any(s in title for s in telesales_signals) and "解决方案" not in title and "售前" not in title:
        if any(s in title for s in {"销售", "管培生"}):
            return "OFF"

    # B: 明确技术岗(工程师/开发/算法),但产品工程师/售前/解决方案优先走 A
    if (
        any(s in title for s in {"工程师", "开发", "算法", "研发"})
        and "产品工程师" not in title
        and "售前" not in title
        and "解决方案" not in title
    ):
        return "B"

    # A: AI 产品 / AI 售前 / AI 解决方案 / AI 销售
    if "产品" in title and has_ai_signal:
        return "A"
    if ("售前" in title or "解决方案" in title) and has_ai_signal:
        return "A"
    if any(s in title for s in {"销售", "管培生", "商业化", "bd"}) and has_ai_signal:
        return "A"

    # OFF: 运营/市场/非 AI 销售/非 AI 解决方案
    if any(s in title for s in {"运营", "市场", "品牌", "公关", "人力", "行政", "财务", "客服"}):
        return "OFF"
    if any(s in title for s in {"销售", "管培生", "商业化"}) and not has_ai_signal:
        return "OFF"
    if ("售前" in title or "解决方案" in title) and not has_ai_signal:
        return "OFF"

    # 兜底
    if has_ai_signal:
        return "A"
    if any(s in title for s in {"工程师", "开发", "算法"}):
        return "B"
    return "OFF"


def main() -> None:
    golden_path = Path(__file__).resolve().parent / "golden.jsonl"
    rows = []
    for line in golden_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        d = suggest_direction(item["title"], item["jd"], item.get("applied", False))
        rows.append((item["company"], item["title"], item["applied"], d))

    print("| # | 公司 | 岗位 | 已投递 | 初标 gold_direction |")
    print("|---|------|------|--------|---------------------|")
    for i, (company, title, applied, d) in enumerate(rows, 1):
        print(f"| {i} | {company} | {title} | {'是' if applied else '否'} | **{d}** |")


if __name__ == "__main__":
    main()
