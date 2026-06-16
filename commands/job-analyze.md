---
name: job-analyze
description: 求职自动化分析 - 发送岗位链接或JD，Agent Teams 并行分析并生成话术
---

接收到用户提供的岗位信息后，主会话作为调度中心，严格按以下流程执行。全程静默，不解释中间步骤。

## Step 0 — 载入候选人画像

用 Read 读取仓库根目录的 `profile.md`（不存在则停止，提示：「请先复制 `profile.example.md` 为 `profile.md` 并填写你的画像，见 `docs/candidate-profile.md`」）。
将内容暂存为 `CANDIDATE_PROFILE`，后续注入给两个子 agent。

## Step 1 — 信息提取（主会话）

从用户输入中提取三个变量：

- **招聘平台链接**：本项目不内置爬虫。若你已自行接入目标平台的数据抓取适配器（输入输出契约见 `docs/data-schema.md`），按你的实现抓取 job_title / company / job_description。
  **没有适配器也没关系**——最省事的方式是让用户直接粘贴 JD 纯文本。
- **其他网页链接**：执行 `curl -s "https://r.jina.ai/<链接>"`，提取 job_title、company、job_description（超800字则取前600+后200字）
- **纯文本JD**：直接解析提取，company未提及填"未知公司"

失败处理：链接无法访问 → 回复"❌ 链接解析失败，请直接粘贴 JD 文本"；job_description 少于50字 → 回复"⚠️ JD 内容不完整，请提供完整职位描述"

## Step 2 — 并行启动两个 Agent（核心）

**在同一轮中同时启动以下两个 agent，均使用 run_in_background: true**。两个 agent 完全独立，互不依赖。

每个 agent 的 prompt 必须：
1. 把 Step 0 读到的 `CANDIDATE_PROFILE` 填入 agent 模板里的 `{{candidate_profile}}` 位置；
2. 直接嵌入 job_title / company / job_description，不要让子 agent 读任何文件。

### Agent 1: job-analyzer
传入完整 JD 文本 + 候选人画像。

### Agent 2: greeting-generator
传入完整 JD 文本 + 候选人画像。

等待两个 agent 均完成后再继续。

## Step 3 — 投递决策（主会话）

从 job-analyzer 返回中提取 priority_score（数字），按以下规则决定 delivery_level：

| 分数 | 等级 |
|------|------|
| ≥8 | S |
| 6-7 | A |
| 4-5 | B |
| ≤3 | C |

C 级：丢弃 greeting-generator 的话术，最终话术显示"该岗位匹配度较低，建议优先投递 S/A 级岗位"。

## Step 4 — 写入追踪文档

输出路径默认 `output/岗位追踪库.md`（可按用户偏好改）。先 Read 目标文件获取现有内容，将新条目追加后 Write；文件不存在则创建。

```
---
## 🏢 {{company}} · {{job_title}}

| 维度 | 结果 |
|------|------|
| 优先级评分 | {{priority_score}}/10 |
| 投递等级 | {{delivery_level}}级 |
| 是否推荐 | {{recommendation}} |
| AI相关度 | {{ai_score}}/5 |
| ToB相关度 | {{tob_level}} |
| 技能匹配 | {{skill_match}}/5 |
| HR回复概率 | {{reply_probability}} |

**核心要求**
1. {{core_req_1}}
2. {{core_req_2}}
3. {{core_req_3}}

**关键洞察**
- 隐藏信号：{{hidden_signal}}
- 能力门槛：{{ability_threshold}}

**为什么匹配**
{{match_reason}}

**📋 招聘平台打招呼话术**
> {{greeting_text}}
```

## Step 5 — 输出结果

```
✅ {{company}} · {{job_title}}

📊 优先级：{{priority_score}}/10 ｜ 投递等级：{{delivery_level}}级 ｜ {{recommendation}}
🔍 隐藏信号：{{hidden_signal}}
📬 HR回复概率：{{reply_probability}}

💬 建议话术：
{{greeting_text}}
```
