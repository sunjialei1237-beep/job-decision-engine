# candidates.json —— 数据源适配器契约

`/job-filter` 不关心你的岗位数据从哪来（爬虫、RSS、手动整理都行），只要你能产出一个符合下面 schema 的 `candidates.json`。这就是你的数据源和本仓库之间的「插座」。

## Schema

`candidates.json` 是一个对象数组，每个元素描述一个幸存岗位：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `company` | string | ✅ | 公司名 |
| `job_title` | string | ✅ | 岗位名 |
| `full_jd` | string | ✅ | 完整 JD 文本（>800 字时 job-filter 会自动截断为前 600 + 后 200） |
| `url` | string | ✅ | 岗位详情链接，写进投递清单 |
| `rule_score` | number | ✅ | 规则预筛打出的粗分。job-filter 按它降序取 top N 决定哪些值得 LLM 深评。没有规则分就全填同一个值（=不排序，全量深评） |
| `applied` | bool | 推荐 | 是否已投过。`true → ✅已投`，清单里标出来避免重复 |
| `is_new` | bool | 推荐 | 相对上一轮是否新冒出来的。`true → 🆕新`，否则 `🔁旧` |

> `applied` / `is_new` 不是必填，但填了清单会更友好。规则分 `rule_score` 是省钱的关键——它让你只深评最有希望的那批。

## 示例（虚构数据）

```json
[
  {
    "company": "示例科技有限公司",
    "job_title": "AI 解决方案工程师（实习）",
    "full_jd": "【岗位职责】\n1. 对接企业客户，理解其业务场景...\n2. 基于 AI 平台设计落地方案...\n【任职要求】\n1. 熟悉大模型应用开发...\n2. 有 RAG / Agent 项目经验优先...",
    "url": "https://example-jobs.com/position/abc123",
    "rule_score": 85,
    "applied": false,
    "is_new": true
  },
  {
    "company": "另一家数据公司",
    "job_title": "AI 产品经理实习生",
    "full_jd": "...",
    "url": "https://example-jobs.com/position/def456",
    "rule_score": 72,
    "applied": false,
    "is_new": true
  }
]
```

## 你的数据源要做什么

1. **抓取**：用任何合规方式拿到岗位列表 + 详情 JD（本仓库不提供、不假设你的抓取方式——请遵守目标平台的使用条款）。
2. **规则预筛**：用一个轻量脚本按你的硬性条件（关键词、学历、经验、地点、回避项）打 `rule_score` 并剔除明显不合适的。这一步零 token 成本，是省钱的核心。
3. **产出** `candidates.json`，放到 `data/jobs/<batch_date>/candidates.json`（路径可在 `/job-filter` 里按需调整）。

预筛脚本写得越严，喂给 LLM 的幸存者越少、越准、越省。
