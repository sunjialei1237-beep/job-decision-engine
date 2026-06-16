# 工作原理

## 两个引擎 + 一层编排

本仓库的核心是两个**无状态**的 agent（`tools: []`，不读文件、不带记忆），由上层 skill 把数据「喂」进它们的 prompt：

| 组件 | 文件 | 职责 |
|---|---|---|
| 决策引擎 | `agents/job-analyzer.md` | 把 JD 看穿：AI/ToB 相关度、技能匹配、隐藏信号、能力门槛、HR 回复概率，输出 0-10 加权评分 |
| 话术引擎 | `agents/greeting-generator.md` | 自推断岗位性质与匹配度，按等级生成一句高回复率开场白 |
| 单条编排 | `commands/job-analyze.md` | 一条 JD → 并行跑两个引擎 → 投递分级 → 写追踪库 |
| 批量编排 | `commands/job-filter.md` | 一批 candidates → 并行评分 → 取 top 40 → 并行话术 → 写投递清单 |

关键设计：**画像不写死在 agent 里**。每个 agent 模板里有一个 `{{candidate_profile}}` 注入点；上层 skill 先读 `profile.md`，再把内容填进去。这样换人用只改一个 `profile.md`，引擎本体不动。

## 值得拿走的编排模式

这些是 `job-filter` 里反复验证过的工程套路，迁到别的批量 LLM 任务也通用：

### 1. 两段式：规则预筛（零 token）+ LLM 深度评分

先用便宜的规则（关键词、学历、经验、地点）粗筛砍掉大量明显不合适的，只把幸存者喂给 LLM。成本 = 幸存者数 ×（1 评分 + ≤1 话术），而不是全量 × 2。

> 规则预筛脚本不在本仓库（属于你的数据源侧）。它产出的 `candidates.json` 就是 LLM 阶段的输入，schema 见 `data-schema.md`。

### 2. 并行 fan-out + 同消息派发

评分和话术都是**在同一条消息里**用 Agent 工具并行启动 N 个子 agent，全部 `run_in_background: true`。墙钟时间 ≈ 最慢的一个，不是 N 个之和。

### 3. 模型分级路由（省钱）

话术不需要强推理，所以按投递等级分配模型：
- S/A 级 → `sonnet`（值得好好写）
- B 级 → `haiku`（边缘岗位，便宜够用）
- 未深评 / ≤3 分 → 不生成

### 4. 结构化输出 + 正则提分

要求子 agent 把评分行严格写成 `评分：X/10`，主 agent 用正则 `评分：\s*(\d+)\s*/\s*10` 提取整数。比让模型返回 JSON 再解析更鲁棒（模型偶尔会多说两句，正则照样抓得到）。

### 5. 兜底：子 agent 失败就内联

如果子 agent 返回里提不出分数（只输出开场白、没调工具、模型不支持工具调用），**主 agent 立刻停止派发**，改用自己在上下文里内联完成剩余评分/话术。不重试、不死等——保证流程一定走完。

### 6. top-N 上限控成本

`analyze_top` 参数（默认 40）只对 `rule_score` 最高的前 N 个深度评分，其余在清单末尾标「未深评（规则分 X）」。要更细就调大，要更省就调小。

## 数据流

```
你的数据源（爬虫/RSS/手动整理）
        │  产出 candidates.json（schema 见 data-schema.md）
        ▼
   /job-filter  ──读 profile.md──▶ 注入画像
        │
        ├─ 按 rule_score 取 top N
        ├─ 并行 fan-out: job-analyzer × N  ──▶ 评分（正则提取）
        ├─ 排序 + S/A/B/C 分级 + 取 top 40
        ├─ 并行 fan-out: greeting-generator × (S/A/B)  ──▶ 话术（模型分级）
        └─ 写 output/reports/<today>/投递清单.{md,csv}
                                            │
                                            ▼
                              人工照清单【手动】投递（不自动投递）
```
