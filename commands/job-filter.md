---
name: job-filter
description: 批量筛选投递清单 - 从 candidates.json 并行 LLM 评分+话术，输出 top 40 投递清单
---

批量版 `/job-analyze`：从 `candidates.json`（你自己的数据源产出的幸存者，schema 见 `docs/data-schema.md`）
并行 LLM 评分 → 排序 → 取 top 40 → 并行生成打招呼话术 → 写投递清单。全程静默执行中间步骤，不解释工具调用。

## Step 0 — 载入画像 + 定位 candidates.json + 成本参数

1. 用 Read 读 `profile.md`（不存在则停止，提示用户先按 `profile.example.md` 填写）。内容暂存为 `CANDIDATE_PROFILE`。
2. **`<batch_date>`（抓取/预筛日）**：用户参数 `$ARGUMENTS` 里的日期（如 `2026-06-14`）；无则取 `data/jobs/` 下最新日期目录。**只用于定位输入 candidates.json**。
3. **`<today>`（生成/投递日）**：当前日期。**用于归档输出清单**。⚠️ 必须与 batch_date 分开：`reports/` 按「你哪天生成清单去投递」归档，避免今天的投递动作混进昨天的抓取批次。
4. `analyze_top`：`$ARGUMENTS` 里的数字（如 `/job-filter 2026-06-14 50`），无则默认 **40**。只对 rule_score 最高的前 N 个深度评分，其余标「未深评」。
5. **输入路径**：`data/jobs/<batch_date>/candidates.json`（可按你的数据源布局调整，schema 见 `docs/data-schema.md`）。用 Read 读入。
   - 不存在 → 回复「❌ 找不到 candidates.json，请先用你自己的数据源/预筛脚本产出（schema 见 docs/data-schema.md）」。
6. 打印成本提示：「将深度评分 min({N}, {analyze_top}) 个 → 预估 min({N},{analyze_top}) + min({analyze_top},40) 次 agent 调用」。再附一行：「输入 batch=<batch_date> ｜ 输出归档 reports/<today>/」。

## Step 1 — 并行评分（job-analyzer，仅 top N 控成本）

按 candidates 里的 `rule_score` **降序排**，取前 `analyze_top`（Step 0 定，默认 40）个**深度评分**；其余跳过，待 Step 4 清单末尾以「未深评（规则分 X）」列出。

**主 agent 必须先把 candidates.json 读入上下文**（用 Read 工具完整读取）。然后**在同一条消息里**用 Agent 工具并行启动 `job-analyzer` agent，全部 `run_in_background: true`，并**显式传 `model: "sonnet"`**。

每个 agent 的 prompt 必须**直接嵌入该岗位完整信息**，并把 `CANDIDATE_PROFILE` 填入 `{{candidate_profile}}` 位置，不要让子 agent 读取任何文件：

```
公司：{company}
岗位：{job_title}
JD原文：
{job_description（取 full_jd；>800 字取前 600 + "..." + 后 200）}

候选人画像：{CANDIDATE_PROFILE}

请基于以上 JD 直接进行深度岗位分析。输出结构化中文分析，必须包含以下字段，且评分行严格写成 `评分：X/10`（X 为 0-10 整数）以便程序提取：
- 评分：X/10
- HR回复概率：高/中/低
- 技能匹配：X/5
- 核心要求：（1-3 条最关键的硬性要求）
- 隐藏信号：（JD 字面背后的真实信号：是否其实是销售/电销、加班强度、转正确定性、团队规模、是否打杂等）
- 匹配原因：（结合候选人画像，说清为什么匹配或不匹配）
- 风险提示：（如有）
```

- agent 返回结构化分析，含「评分：X/10」。
- 等待全部完成。

从每个返回里用正则 `评分：\s*(\d+)\s*/\s*10` 提取整数 priority_score。解析失败记 0 分并标注「评分解析失败」。

**兜底**：如果子 agent 返回中**没有可提取的评分**（例如只输出开场白、没有调用工具、或模型不支持工具调用），则主 agent 立刻停止继续派发子 agent，改为在上下文中**内联完成剩余所有岗位的深度评分**，然后继续 Step 2。不要反复重试失败的子 agent。

## Step 2 — 排序 + 分级 + 取 top 40

- 按 priority_score 降序排。
- 取前 40（不足全取）。**40 = 单日投递上限**：清单出 ≤40 条，照单投完即今日止；明天预筛剔除已投 + 标 is_new，新一轮再出 ≤40。
- 推导 delivery_level：`≥8 → S`，`6-7 → A`，`4-5 → B`，`≤3 → 不建议`（不生成话术，清单里标注）。

## Step 3 — 并行话术（greeting-generator，按等级路由模型省成本）

对 top 40 中**等级 S/A/B 的**（即 >3 分），在**同一条消息里**并行启动 `greeting-generator` agent，全部 `run_in_background: true`。

每个 agent 的 prompt 必须**直接嵌入该岗位完整信息**并填入 `CANDIDATE_PROFILE`，不要让子 agent 读取任何文件：

```
公司：{company}
岗位：{job_title}
JD原文：
{job_description（同 Step 1 的截断规则）}

候选人画像：{CANDIDATE_PROFILE}

请直接基于以上信息生成一句招聘平台打招呼话术。
```

- **模型路由**：S/A 级显式传 `model: "sonnet"`；B 级显式传 `model: "haiku"`——话术不需强推理，B 级又是边缘岗，用便宜模型。未深评的不生成话术。
- agent 自推断匹配度并输出**一句话**话术。
- 等待全部完成。

**兜底**：如果子 agent 返回无效（如只输出开场白、未生成一句话话术），主 agent 改为在上下文中**内联生成剩余话术**；S/A 用 sonnet，B 用 haiku。

## Step 4 — 写投递清单

输出目录 `output/reports/<today>/`（先建目录；⚠️ 用**今天日期**，不是 batch_date）。写两文件。

**CSV 写入容错**：如果 `投递清单.csv` 被 Excel 等程序锁定导致 PermissionError，则回退写入 `投递清单_new.csv`，并在最终输出中告知用户文件名。

**状态标记**（从 candidates 字段推）：`applied=true → ✅已投`；`is_new=true → 🆕新`，否则 `🔁旧`。总览表和详情都标，让你一眼看出哪些是今天新冒出来的、哪些已发过。

**`投递清单.md`**：

```
# 投递清单 <today>

源 batch：`<batch_date>` 的 candidates.json ｜ 生成日：<today>
{N} 个幸存者 → top {M}（S:{s} / A:{a} / B:{b}）

## 排名总览

| # | 状态 | 等级 | 评分 | 公司 | 岗位 | 链接 |
|---|------|------|------|------|------|------|
| 1 | 🆕新 | S | 8/10 | 公司 | 岗位 | [详情](url) |
...

## 逐家详情（按排名）

### 1. [S] 🆕新 公司 · 岗位
- 评分：8/10 ｜ HR回复概率：中 ｜ 技能匹配：4/5
- 核心要求：1... / 2... / 3...
- 隐藏信号：...
- 匹配原因：...
- 链接：url

**📋 打招呼话术（直接复制）**
> {greeting}
```

**`投递清单.csv`**（utf-8-sig，Excel 友好）：列 = `排名,状态,等级,评分,公司,岗位,话术,链接,未投(填1)`。
末列「未投(填1)」生成时**全留空**，作为可选的手动投递记账列（没投的填 `1`、投了的留空），供你自己的记账工具消费；不需要可删。话术列含逗号 → 必须用 csv 模块写，禁止字符串拼接。

## Step 5 — 输出

```
✅ 投递清单已生成：{N} 幸存者 → top {M}（S:{s} A:{a} B:{b}）
📄 output/reports/<today>/投递清单.md  +  .csv（源 batch=<batch_date>）
📋 建议：从 S 级开始，照话术在目标招聘平台逐家【手动】发送（不自动投递，规避写操作风控）。
```
