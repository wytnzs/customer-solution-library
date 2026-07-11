---
name: customer-solution-library
description: 客户解决方案库管理 Skill v3。用于建立、维护、查询、分析和协同处理客户信息库，支持 Markdown 客户档案、结构化索引、统一信息入口、信号价值评分、保险客户与其他客户分类管理、录音转写/聊天记录/口述记录摘录、客户身份匹配与防误并档、分批补全、客户洞察卡、客户深度分析、信息缺口识别、产品/服务反向匹配客户、潜在客户筛选、客户分层、经营看板、跟进复盘、团队协同、分享脱敏、数据质量检查和标准化输出。触发场景包括：录入客户、查询客户、整理客户信息、判断一段客户信息是否值得入档、从聊天记录提取客户情况、把录音文字整理进客户档案、生成客户画像、生成客户分析 brief、生成专属解决方案、筛选某产品潜在客户、根据需求筛客户、找高价值客户、生成本周经营看板、更新客户档案、客户分层、客户跟进、客户复盘、团队协同处理客户、设计客户管理系统。
---

# 客户解决方案库 v3

## 核心定位

把客户库当成“客户长期服务大脑”，不是普通通讯录或销售 CRM。目标是围绕客户持续沉淀事实、判断、方案、沟通、跟进、复盘和团队协作。

v3 的关键升级是：客户库不能只停留在录入和归档，必须进一步支持客户洞察、产品/服务反向筛选、专属方案和经营看板。录入是底座，分析和行动才是价值。

## 启动检查

处理客户库任务前先判断用户意图：

| 用户意图 | 动作 |
|---|---|
| 初始化客户库 | 使用 `scripts/customer_library.py init --base <路径>` 创建目录骨架 |
| 判断信息是否值得入库 | 读取 `references/intake-routing.md`，按 100 分制评分并给出路由 |
| 从录音转写/聊天记录摘录客户信息 | 读取 `references/conversation-ingestion.md`，先摘录，再身份匹配 |
| 查询客户 | 先查索引/文件名/YAML，再按用户指定格式输出 |
| 生成客户分析/方案 | 读取 `references/customer-insights.md`，读取客户档案、事件流、业务模块，区分事实/推断/待确认 |
| 识别信息缺口 | 使用 `scripts/customer_library.py gaps --base <路径> --customer-id <ID>`，再人工补充判断 |
| 筛选某产品潜在客户 | 读取 `references/product-matching.md`，使用产品画像和 `product-match` 命令 |
| 生成经营看板 | 使用 `scripts/customer_library.py dashboard --base <路径>` |
| 分批补全客户信息 | 追加事件记录，更新主档案摘要，不覆盖历史 |
| 团队协同/分享 | 读取 `references/team-collaboration.md`，按权限与分享类型输出 |
| 数据质量检查 | 读取 `references/data-quality-audit.md`，扫描缺口、重复、过期、隐私风险 |

## 系统分层

采用“Markdown 长期档案 + 结构化索引 + Skill 操作系统”的模式：

```text
Markdown：保存客户事实、沟通记录、方案、复盘
索引/JSON/表格：负责快速查询、筛选、分层、跟进、统计
Skill：负责入口判断、信息摘录、身份匹配、输出和质检
洞察层：负责需求、风险、机会、顾虑、信息缺口和下一步动作
经营层：负责产品匹配、客户筛选、跟进看板和复盘
```

规模化规则：

- 100-500 客户：Markdown + 搜索基本可用。
- 1000-5000 客户：必须维护客户总索引、待跟进索引、待匹配池。
- 10000+ 客户：Markdown 作为长期档案层，查询必须优先走结构化索引。

## 库与知识库的关系

采用“方法论合并，真实数据隔离”的原则：

- 客户管理 Skill、模板、字段规范：放在当前知识库。
- 真实客户资料：放私有客户库，不要推送公开仓库。
- 脱敏案例：可进入知识库，用 `ANON-` 编号，不保留可识别个人信息。
- 可公开方法论：沉淀为知识卡片、团队手册或培训材料。

## 统一信息入口

所有客户相关信息先进入入口池，不要一开始就强行匹配客户。

入口池推荐结构：

```text
00-入口池/
  01-待处理/
  02-待匹配/
  03-待确认/
  04-已入档/
  05-低价值归档/
```

入口处理顺序：

```text
接收信息
→ 生成 intake_id
→ 判断来源和敏感级别
→ 按信号评分制评估价值
→ 提取身份锚点
→ 路由到：立即入档 / 待匹配 / 待确认 / 低价值归档 / 丢弃
```

价值判断必须使用 `references/intake-routing.md` 的 100 分制，不要只凭直觉。

## 多类型客户处理

客户类型用数组，不互斥：

```yaml
customer_type:
  - insurance_client
  - consulting_client
business_line:
  - insurance
  - knowledge_service
```

规则：

1. 一个客户可以同时是保险客户、咨询客户、合作客户、内容受众。
2. 主档案只保存跨类型通用事实。
3. 类型专属信息放入对应业务模块。
4. 输出时按任务选择视角：保险分析、咨询分析、合作推进、综合画像。
5. 不要把某一业务线的判断强行套到所有客户。

详细字段见 `references/data-model.md`。

## 对话入库机制

录音转写、微信聊天、面谈纪要、用户口述聊天经过，都可以作为客户信息补充来源。

三段式处理：

1. 原始记录层：保存来源、时间、参与人、转写质量。
2. 摘录层：提取事实、需求、顾虑、承诺、待办、疑点。
3. 入档层：完成身份匹配后，才更新客户主档案、业务模块或方案。

完整规则见 `references/conversation-ingestion.md`。

## 同名客户防误并档

同名客户不能自动合并。至少需要满足两个身份锚点，才可以建议并入已有客户：

- `customer_id`
- 脱敏联系方式
- 来源人/来源渠道
- 城市/公司/职业
- 家庭结构
- 业务线和关键需求
- 历史事件
- 用户明确指定

只有姓名相同：不得并档。进入候选确认或待匹配。

## 输出格式选择

| 场景 | 默认输出 |
|---|---|
| 查客户 | 客户速览 |
| 分析客户 | 客户分析 brief |
| 给方案 | 专属解决方案草稿 |
| 下一步怎么跟进 | 跟进建议 |
| 整理成发客户的话 | 客户可读版话术 |
| 从聊天记录摘录 | 对话摘录报告 + 入档建议 |
| 判断信息有没有价值 | 信号评分表 + 路由建议 |
| 做深度分析 | 客户深度分析 + 洞察卡 + 信息缺口 |
| 某产品找客户 | 产品潜在客户清单 |
| 本周经营安排 | 本周经营看板 |
| 团队协同 | 协同任务卡/脱敏摘要/复核清单 |

输出模板见 `references/output-formats.md`。

## 分批更新机制

字段状态：

| 标记 | 含义 |
|---|---|
| `known` | 已确认 |
| `unknown` | 未知 |
| `pending` | 待客户补充 |
| `assumed` | 暂时推断，必须标注依据 |
| `conflict` | 信息冲突，需核实 |
| `not_applicable` | 不适用 |

完整度等级：

| 等级 | 含义 |
|---|---|
| `L0` | 只有线索或称呼 |
| `L1` | 有基础联系方式/来源/初步需求 |
| `L2` | 有家庭、职业、预算或业务背景之一 |
| `L3` | 有关键业务资料，如保单、健康、项目需求 |
| `L4` | 能形成阶段性分析 |
| `L5` | 能形成完整方案并进入持续服务 |

更新原则：

1. 新信息先写事件记录。
2. 主档案只更新稳定摘要。
3. 不确定信息不得写成事实。
4. 关键变更追加变更记录。
5. 每次更新刷新 `updated`、`info_completeness`、`next_action`。

## 洞察与经营能力

客户信息入库后，优先判断是否需要进一步生成洞察：

```text
客户信息事件
→ 客户洞察卡
→ 信息缺口
→ 客户深度分析
→ 产品/服务匹配
→ 跟进动作或专属方案
```

规则：

1. 客户洞察卡回答“这意味着什么”，不要替代原始记录。
2. 深度分析必须区分事实、推断、待确认。
3. 信息缺口要服务于“能否形成方案/行动”，不是无限补资料。
4. 产品匹配必须说明匹配原因、风险点、缺口和建议动作。
5. 高匹配不等于直接推荐；涉及保险、健康、理赔、法律、财务承诺时必须人工复核。

详细规则见：

- `references/customer-insights.md`
- `references/product-matching.md`

## 隐私与合规边界

硬规则：

1. 不在公开仓库保存真实姓名、手机号、身份证号、银行卡号、完整保单号、病历原件。
2. 文件名使用客户编号和别名。
3. 需要 AI 分析时先脱敏。
4. 涉及保险、健康、法律、财务结论时，用“建议核实/可能/初步判断”，不要承诺承保、赔付或收益。
5. 给客户看的内容要和内部判断分开。

## 可复用资源

- `references/intake-routing.md`：统一信息入口、信号价值评分、路由规则。
- `references/data-model.md`：目录结构、字段规范、客户类型设计。
- `references/workflows.md`：录入、更新、查询、分析、方案、复盘工作流。
- `references/customer-insights.md`：客户洞察卡、深度分析、信息缺口识别。
- `references/product-matching.md`：产品/服务画像、潜在客户筛选、产品机会清单。
- `references/conversation-ingestion.md`：录音转写、聊天记录、口述记录的摘录与入档规则。
- `references/team-collaboration.md`：团队协同、分享、复核、权限边界。
- `references/data-quality-audit.md`：数据质量检查、重复客户、过期跟进、隐私风险。
- `references/output-formats.md`：客户速览、分析 brief、方案、跟进、客户可读话术模板。
- `scripts/customer_library.py`：初始化目录、刷新索引、关键词查询、入口评分、数据质量检查。

常用命令：

```powershell
python .claude/skills/customer-solution-library/scripts/customer_library.py init --base <客户库路径>
python .claude/skills/customer-solution-library/scripts/customer_library.py index --base <客户库路径>
python .claude/skills/customer-solution-library/scripts/customer_library.py audit --base <客户库路径>
python .claude/skills/customer-solution-library/scripts/customer_library.py score-intake --text "<客户信息片段>"
python .claude/skills/customer-solution-library/scripts/customer_library.py analyze-customer --base <客户库路径> --customer-id CUST-0001
python .claude/skills/customer-solution-library/scripts/customer_library.py gaps --base <客户库路径> --customer-id CUST-0001
python .claude/skills/customer-solution-library/scripts/customer_library.py product-match --base <客户库路径> --product-id PROD-001
python .claude/skills/customer-solution-library/scripts/customer_library.py dashboard --base <客户库路径>
```
