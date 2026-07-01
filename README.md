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

## 企业级工程层:评测 + 闭环校准

引擎能跑只是起点。本项目还包含把个人脚本升级为**企业级 agent** 的工程层:评测、闭环校准、可靠性。代码公开,数据(golden 集、投递 outcome)各人自备。

### 评测 `eval/`(Step 1)
golden 集 + 跨模型 LLM-as-judge + 回归。每条 golden 跑 N 次报 mean±std,避免非确定性噪声误报;analyzer 与 judge 用不同模型族避免 self-preference。

```bash
python eval/run_eval.py --analyzer-model glm-5.2 --judge-model deepseek-chat --repeats 3
# 验证管线(不调 LLM):python eval/run_eval.py --golden eval/golden.example.jsonl --fake
```

产出 `eval/reports/<date>.md`:方向准确率 / judge 评分 / inter-rater / 异常 case。

### 闭环校准 `closedloop/` + `calibrate/`(Step 2)
- **`closedloop/`** 攒数据:给投递记录回填 outcome(回复/面试/拒/沉默),算转化漏斗。
- **`calibrate/`** 用数据校准评分:`load_feedback` join golden × 投递并打分 → `correlate` 算评分↔outcome 相关性 → `reviewer.md` 反思 agent 对偏差 case 归因。

```bash
# 1. 回填 outcome(时间推导沉默 + 手动正向)
python closedloop/backfill_outcomes.py --applied your-applied.json --out data/applied_enriched.json
# 2. 装配评分集(对 join 出的 JD 现跑 analyze_jd 打分)
python calibrate/load_feedback.py --analyzer-model glm-5.2
# 3. 校准分析
python calibrate/correlate.py --scored data/scored.jsonl
```

**诚实 gating**:`correlate` 在真实 HR 反馈 < 30 条时拒绝计算相关性,只输出"数据不足"报告 —— 不拿噪声数据假装校准通过。反思 agent `reviewer.md` 只在闭环分析按需触发,不进投递快路径(Anthropic workflow-vs-agent 判据:确定性 pipeline 不用反思,闭环归因才是反思的合理战场)。

### 轻量 trace `core/trace.py`(Step 3,Phase 2 补 token/cost)

引擎每次 LLM 调用自动落一行 jsonl 观测,便于复盘延迟毛刺与重试。单一写入点在 `LLMClient.complete_json`,analyze / greeting / judge 通过 `step` 字段区分。Phase 2 起 `LLMClient._call` 直接从 SDK 响应抓 `usage`,追加 token/cost(Phase 1 拿不到响应头时刻意 deferred 到此)。

```jsonl
{"ts":"2026-07-01T03:21:09Z","step":"analyze","model":"glm-5.2","latency_ms":2143.7,"input_hash":"a1b2...","output_summary":"{\"direction\":\"A\",...}","token_in":820,"token_out":340,"cost_usd":0.0007}
```

- `token_in/token_out` 来自 OpenAI/Anthropic SDK 的 usage(老端点不回 usage 时省略,退化为 Phase 1 的基础 6 字段);`cost_usd` 按 `core/pricing.py` 保守估值表算,**未知模型只记 token 不算 cost**(请按官方价目校准该表)。
- 不假装它 load-bearing:它是观测,不是判据。
- `input_hash` 存 prompt 的 sha256 前 16 位(不存原文 → 隐私 + 体积),`output_summary` 截前 200 字单行化。
- 默认写 `./trace/runs/<YYYY-MM-DD>.jsonl`(已 gitignore);`TRACE_DIR` 改目录,`TRACE_DISABLED=1` 关停。trace 写失败永远静默,不影响主流程。

### 独立服务:FastAPI + Docker(Phase 2)

引擎也包成了 HTTP 服务,核心能力(分析 / 话术 / 一体决策)经 API 暴露,带输入护栏与限流。库形态(`core/`)与服务形态(`api/`)共享同一引擎,无重复逻辑。

```bash
pip install ".[api]"                 # 装服务依赖(fastapi / uvicorn / httpx)
uvicorn api.app:app --port 8000      # 直接跑(需先设 LLM env + 准备 profile.md)
```

端点(请求体均为 `{title, company, jd}`):

| 方法 | 路径 | 返回 |
|---|---|---|
| POST | `/analyze` | 分析结果 + 投递等级(S/A/B/不建议) |
| POST | `/greeting` | 一句话开场白 |
| POST | `/decide` | 分析 + 等级 + 开场白(一体) |
| GET | `/health` | 可用性探针(不调 LLM) |
| GET | `/` | 最小前端(贴 JD → 渲染结果) |

**Docker 一键起**(`docker-compose.yml` 挂载 profile 只读、env 注入 API_KEY/MODEL):

```bash
cp profile.example.md profile.md     # 填画像
export BASE_URL=... API_KEY=... MODEL=glm-5.2
docker compose up --build            # 访问 http://localhost:8000
```

**安全护栏**(企业级边界,诚实声明:不声称根治):
- 输入上限(JD ≤ 20000 字 / 标题公司 ≤ 200)→ 超限 422
- 控制字符卫生(剥离 NUL/DEL 等,保留 `\t \n \r`)
- IP 限流(滑动窗口,`RATE_LIMIT_PER_MINUTE` 默认 20)→ 429
- **PII**:profile 是服务侧配置(env / 挂载),永不进请求 / 响应
- **injection**:profile 不入请求 + 输出 schema 强校验 + 响应不回显原文;输入过滤只做基础卫生 —— LLM prompt injection 是开放问题,无法靠输入过滤根治

LLM 调用失败 → 502;长度 / 缺字段 / 全控制字符 → 422。

**关于 Langfuse**:可观测的核心价值(token / cost)已由 trace 落地,默认不引入 Langfuse(自部署需 pg + web + worker,对个人项目过重)。它是**可选扩展**:在 `LLMClient._call` 外包一层 `langfuse.observe()`、配 `LANGFUSE_*` env 即接通 —— 本仓不内置该依赖,留作按需集成。

**CI**:`.github/workflows/ci.yml` 在 push / PR 时跑 `unittest discover tests` + `--fake` 评测管线(无需 LLM key)。

### 生产化:认证 + 批处理 + metrics(Phase 3)

Phase 2 的服务「能跑」,Phase 3 让它「能上生产」(设计文档未显式定义 Phase 3,本仓自主补齐为企业级 agent 上线最不可省的三件套):

**API key 认证**:env `ENGINE_API_KEYS=k1,k2,...`(逗号分隔)开启。开启后受保护端点(`/analyze` `/greeting` `/decide` `/analyze-batch`)须带 `X-API-Key` header,否则 401。未配 env = 开发模式放行(本地 / 测试用;**生产必须配**)。`/health` `/metrics` `/` 豁免(探针 / 抓取 / 前端)。

**批量分析** `POST /analyze-batch`(企业级规模场景):

```json
{"items": [{"title": "...", "company": "...", "jd": "..."}]}   <!-- ≤ 50 条 -->
```

并发(ThreadPool,max_workers=4)分析,**单条失败隔离**(该条填 `error`,其余照常,整批始终 200 —— 尽力而为语义):

```json
{"results": [{"analysis": {...}, "level": "S"}, {"error": "..."}]}
```

**Prometheus metrics** `GET /metrics`(认证豁免,便于 scraper 抓取):输出 `engine_requests_total{path,status}` + `engine_request_latency_seconds_{sum,count}`。LLM token/cost 维度已由 `core/trace` 落盘,这里不重复;接 Langfuse 见 Phase 2 说明。

中间件顺序(请求穿越):**metrics(最外,记录全部含 401/429)→ 限流 → 认证 → 路由**。Starlette `add_middleware` 用 `insert(0)`,后注册者在外层 —— 代码里 metrics 最后注册才落在最外,这是刻意安排(否则被限流/认证挡掉的请求进不了 metrics)。

## 目录结构

```
job-decision-engine/
├── core/                   # 引擎真核:analyze_jd / generate_greeting + trace + pricing(Step 0/3)
├── api/                    # 服务:FastAPI app + 认证 + 护栏 + 限流 + 批处理 + metrics + 前端
├── commands/  agents/      # Claude Code 形态的编排与 prompt(画像注入点)
├── eval/                   # 评测:golden + 跨模型 judge + 回归(Step 1)
├── closedloop/             # 闭环数据:outcome 回填 + 转化漏斗(Step 2)
├── calibrate/              # 闭环校准:load_feedback + correlate + reviewer(Step 2)
├── tests/                  # 单测:rules / trace / pricing / api / guardrails(unittest)
├── trace/runs/             # LLM 调用 jsonl(本地,gitignore)
├── docs/                   # how-it-works / candidate-profile / data-schema / architecture
├── examples/               # candidates.sample.json / jd-sample.md / output-sample.md
├── Dockerfile  docker-compose.yml  .github/workflows/   # 部署 + CI(Phase 2)
├── profile.example.md      # 候选人画像模板(复制为 profile.md 自填)
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
