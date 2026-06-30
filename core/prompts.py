"""LLM prompt 构造。

逻辑搬自 boss-scraper/workflow/job_daily_analyze.js 的 analysisPrompt / greetingPrompt
(line 50-73),direction 适配为 enum 输出(design doc reviewer 建议),尾部要求纯 JSON。
"""
from __future__ import annotations


def build_analysis_prompt(title: str, company: str, jd: str, profile: str) -> str:
    return (
        f"公司:{company}\n岗位:{title}\nJD原文:\n{jd}\n\n{profile}\n\n"
        "你是「AI ToB 求职岗位洞察与决策引擎」:看穿岗位本质 + 判断值不值得投,不是总结JD。\n"
        "【最优先】先判 direction:这个岗在候选人方向里是 A级方向 / B级技术 / 方向偏离。\n"
        "输出 JSON 对象,必须包含下列全部 13 个字段,缺任何一个都算失败。字段如下:\n"
        '- direction:枚举值三选一,"A"(A级方向=ToB销售/解决方案/售前/商业化/AI产品/Agent产品)、'
        '"B"(B级技术=AI技术)、"OFF"(方向偏离=运营/市场/纯C端/非AI)。只输出字母。\n'
        "- direction_reason:direction 的一句理由\n"
        "- ai_relevant:是否AI相关(是/否+理由,禁复述JD)\n"
        "- ai_score:AI相关度(1-5整数)\n"
        "- tob:【必填,常被遗漏】ToB相关(高/中/低+理由,高=直接服务企业客户)\n"
        "- role_type:岗位类型\n"
        "- skill_migrate:技能迁移度(X/5)。【关键规则】销售/解决方案/售前/商业化/产品岗→评候选人AI背景对该岗的"
        "【迁移价值】(懂AI产品才能做AI售前/销售、懂技术才能给客户讲方案、留资转化经验能迁移到ToB客户经营),"
        "【绝不】评RAG/Agent/Python能否在该岗直接用上;技术岗→评技能直接匹配度。点名候选人具体项目模块。\n"
        "- recommend:是否推荐(强烈推荐/推荐/勉强/不推荐+一句原因)\n"
        "- hidden_signal:隐藏信号(看穿JD字面背后真实在招什么人,是否实为电销/陪标/打杂/外包/加班重,不复述标题)\n"
        "- capability_bar:能力门槛(低/可跨越/偏高/过高+理由)\n"
        "- hr_reply_prob:HR回复概率(高/中/低+原因)\n"
        "- score:优先级评分(0-10整数,权重 方向匹配30%/AI相关20%/ToB20%/技能迁移15%/与候选人阶段匹配15%。"
        "A级方向岗方向分满、B级技术岗方向分低,必须有区分度别集中中间值)\n"
        "- conclusion:结论(强烈建议投递/建议投递/可以尝试/性价比低/不建议)\n"
        "【自检】输出前检查 direction/ai_relevant/ai_score/tob/role_type/skill_migrate/recommend/hidden_signal/"
        "capability_bar/hr_reply_prob/score/conclusion 13 个字段全部存在,尤其不能漏 tob。\n"
        "输出严格遵循此 JSON 结构(全部 13 字段必填,缺任一尤其 tob 都算失败):\n"
        '{"direction":"A|B|OFF","direction_reason":"一句理由","ai_relevant":"是/否+理由","ai_score":1-5整数,"tob":"高/中/低+理由","role_type":"类型","skill_migrate":"X/5+理由","recommend":"强烈推荐/推荐/勉强/不推荐+原因","hidden_signal":"看穿本质","capability_bar":"低/可跨越/偏高/过高+理由","hr_reply_prob":"高/中/低+原因","score":0-10整数,"conclusion":"强烈建议投递/建议投递/可以尝试/性价比低/不建议"}\n'
        "【硬规则·纯电销】销售岗若实为纯电销(电话量驱动/cold-call/外呼/无售前/方案/产品讲解成分)→ "
        "conclusion=不建议、recommend=不推荐、score≤3,不进清单;需懂产品讲方案的售前/解决方案/技术销售岗不受此限。\n"
        "约束:禁止复述JD原文、每个判断必须有推断逻辑、禁空话、评分必须有区分度。\n"
        "只输出 JSON 对象,不要 markdown 代码块、不要任何额外文字。"
    )


def build_greeting_prompt(title: str, company: str, jd: str, profile: str) -> str:
    return (
        f"公司:{company}\n岗位:{title}\nJD原文:\n{jd}\n\n{profile}\n\n"
        "你是「高回复率BOSS直聘私聊生成器」。先内部推断(不输出):"
        "job_nature(偏销售/产品/技术/运营)、match_level(强/一般/弱),"
        "并从候选人画像里选一个最相关的项目模块绑定。\n"
        "强匹配→50-80字深度绑定项目模块像同行交流;一般匹配→40-70字;弱匹配→30-50字只选一个点。\n"
        "硬约束:禁词(热爱/激情/渴望/非常期待/荣幸/贵公司/希望能够/高度契合/非常匹配)、"
        "不以「你好/您好」开头、匹配点必须具体禁废话、像真人发的消息不像简历群发、无emoji、不用被动句。\n"
        '输出 JSON 对象 {"greeting": "..."},只含最终一句话话术,不加引号不加前缀,不要额外文字。'
    )
