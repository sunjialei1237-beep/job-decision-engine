"""引擎 smoke test:用 examples/jd-sample.md 跑通 analyze_jd + generate_greeting。

用法(在仓库根目录):
    python examples/run_engine.py

需要先设 LLM 环境变量(BASE_URL / API_KEY / MODEL),见 README「作为 Python 库调用」。
profile 优先读 profile.md(私人,gitignore);没有则用 profile.example.md(模板)。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# 让脚本不依赖 pip install 也能 import core
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from core import analyze_jd, derive_level, generate_greeting  # noqa: E402

_JD_SAMPLE = _REPO_ROOT / "examples" / "jd-sample.md"


def parse_jd_sample(text: str) -> tuple[str, str, str]:
    """从 jd-sample.md 提取 (company, title, jd)。"""
    company = "未知公司"
    title = "未知岗位"
    m = re.search(r"^公司[：:]\s*(.+)$", text, re.MULTILINE)
    if m:
        company = m.group(1).strip()
    m = re.search(r"^岗位[：:]\s*(.+)$", text, re.MULTILINE)
    if m:
        title = m.group(1).strip()
    # JD 正文:第一个 --- 之后的内容(兼容 CRLF)
    parts = re.split(r"\r?\n---\r?\n", text, maxsplit=1)
    jd = parts[1] if len(parts) > 1 else text
    return company, title, jd.strip()


def main() -> None:
    text = _JD_SAMPLE.read_text(encoding="utf-8")
    company, title, jd = parse_jd_sample(text)

    profile_path = _REPO_ROOT / "profile.md"
    if profile_path.exists():
        print(f"[profile] 用 {profile_path.name}")
    else:
        profile_path = _REPO_ROOT / "profile.example.md"
        print("[profile] 未找到 profile.md,用模板 profile.example.md(填 profile.md 后输出更准)")
    profile = profile_path.read_text(encoding="utf-8")

    print(f"\n=== 分析:{company} · {title} ===\n")
    result = analyze_jd(jd=jd, title=title, company=company, profile=profile)
    print(result.model_dump_json(indent=2))
    print(f"\n投递等级:{derive_level(result)}")

    print("\n=== 话术 ===\n")
    greeting = generate_greeting(title=title, company=company, jd=jd, profile=profile)
    print(greeting)


if __name__ == "__main__":
    main()
