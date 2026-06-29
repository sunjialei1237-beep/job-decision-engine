# 岗位决策引擎 · Job Decision Engine

> 把 JD 喂进去 → 吐出结构化评分 + 隐藏信号洞察 + 可直接发送的打招呼话术。
> 一个平台无关的求职决策引擎，基于 Claude Code 的 Agent 编排。

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

## 这是什么

一套跑在 [Claude Code](https://claude.com/claude-code) 里的求职决策引擎。两个**无状态**的核心 agent，加两层编排 skill：

- **决策引擎** `job-analyzer`：看穿 JD 本质，判断值不值得投。
- **话术引擎** `greeting-generator`：生成高回复率的、像真人发的开场白。

它不总结 JD，它做**判断**。

## 解决什么问题

- 人眼看几十上百条 JD，效率低、容易漏掉关键信号；
- 看不出「挂羊头卖狗肉」——AI 产品经理实为文档整理、AI 销售实为电销、AI 解决方案实为陪标 PPT；
- 打招呼话术千篇一律，回复率低。

## 核心能力

1. **决策引擎**：AI 相关度 / ToB 相关度 / 技能匹配 / 隐藏信号 / 能力门槛 / HR 回复概率，输出 0-10 加权评分（权重：AI 35% · ToB 25% · 技能 25% · 阶段匹配 15%）。
2. **话术引擎**：自推断岗位性质与匹配度，按强/一般/弱匹配分档生成一句话开场白，内置禁用词表和字数约束。
3. **编排模式**：并行 fan-out + 模型分级路由（S/A→sonnet，B→haiku）+ 子 agent 失败兜底内联 + 正则提分。这套套路迁到别的批量 LLM 任务也通用，见 [docs/how-it-works.md](docs/how-it-works.md)。

## 不是什么（重要）

- **不含爬虫**。数据源各人自备。本仓库只定义 `candidates.json` 这个「插座」契约（[docs/data-schema.md](docs/data-schema.md)）——你怎么抓数据是你的事，请遵守目标平台的使用条款。
- **不自动投递**。投递清单照着人工手动发。写操作（自动投递 / 群发）风控高、对平台和其他用户都是干扰，本项目刻意不碰，把分析自动化、把投递留给人。

## 30 秒上手

前置：装好 Claude Code。

```bash
git clone https://github.com/sunjialei1237-beep/job-decision-engine job-decision-engine
cd job-decision-engine
cp profile.example.md profile.md      # 编辑 profile.md，填你的画像
```

把 `commands/*.md` 和 `agents/*.md` 放进你的 Claude Code skill / agent 目录（或直接在本目录开一个 Claude Code 会话，它能识别到这些 skill/agent）。填好画像后：

```
/job-analyze   <粘贴一条 JD，或 examples/jd-sample.md 的内容>
```

批量评分（先按 [docs/data-schema.md](docs/data-schema.md) 准备 `candidates.json`）：

```
/job-filter 2026-06-16 40      # 批次日期 + 深度评分数量
```

## 作为 Python 库调用(Step 0 引擎)

决策引擎也抽成了纯 Python 函数,可被评测脚本、闭环脚本、API 直接调用,无需 Claude Code。`core/` 是引擎真核;`agents/*.md` 保留为 Claude Code 形态的 prompt 对照。

```bash
pip install -e .          # 或 pip install -r requirements.txt
```

设 LLM 环境变量(走 OpenAI 协议;可指向 OpenAI / LiteLLM 代理 / 智谱兼容端点等):

```bash
export BASE_URL=https://open.bigmodel.cn/api/paas/v4   # 智谱 GLM 示例;连 OpenAI 官方则省略
export API_KEY=your-key
export MODEL=glm-5.2
# Windows PowerShell: $env:BASE_URL="..."; $env:API_KEY="..."; $env:MODEL="..."
```

```python
from core import analyze_jd, derive_level, generate_greeting

profile = open("profile.md", encoding="utf-8").read()
result = analyze_jd(jd="JD 正文", title="AI 解决方案工程师", company="某公司", profile=profile)

print(result.direction, result.score, result.conclusion)  # A/B/OFF · 0-10 · 结论
print(result.hidden_signal)                                # 隐藏信号
print(derive_level(result))                                # S/A/B/不建议
print(generate_greeting(title="AI 解决方案工程师", company="某公司", jd="JD 正文", profile=profile))
```

快速验证:`python examples/run_engine.py` 用 `examples/jd-sample.md` 跑通整条链路。需要 Python 3.10+。

## 目录结构

```
job-decision-engine/
├── commands/
│   ├── job-analyze.md      # 单条 JD 分析编排
│   └── job-filter.md       # 批量评分编排（top 40 投递清单）
├── agents/
│   ├── job-analyzer.md     # 决策引擎 prompt（画像注入点）
│   └── greeting-generator.md  # 话术引擎 prompt（画像注入点）
├── docs/
│   ├── how-it-works.md     # 架构与可复用的编排模式
│   ├── candidate-profile.md # 如何填 profile.md
│   ├── data-schema.md      # candidates.json 契约（数据源适配器）
│   └── architecture.md     # 完整日流水线编排模式参考
├── examples/
│   ├── candidates.sample.json
│   ├── jd-sample.md        # 虚构 JD，可直接 demo
│   └── output-sample.md    # 示例输出
├── profile.example.md      # 候选人画像模板（复制为 profile.md 自填）
├── LICENSE
└── README.md
```

## 关键设计：画像外置

画像不写死在 agent 里。每个 agent 模板里有一个 `{{candidate_profile}}` 注入点，上层 skill 先读 `profile.md` 再把内容填进去。换人用只改一个 `profile.md`，引擎本体不动。详见 [docs/candidate-profile.md](docs/candidate-profile.md)。

## 伦理与边界

- 本项目用于**个人求职决策辅助**。
- **不含爬虫、不自动投递、不规避平台规则**；使用前请了解并遵守你所用招聘平台的用户协议。
- 话术引擎的产出是「一句有效的、像真人发的开场白」，**不是群发模板**——请逐条人工发送，不要拿去批量群发。
- 抓取、自动投递等写操作在多数平台的服务条款里是被禁止的，由此产生的账号/法律风险与本仓库无关。

## License

MIT，见 [LICENSE](LICENSE)。
