# 客户解决方案库数据模型 v2.2

## 推荐目录

```text
<客户库根目录>/
  00-入口池/
    01-待处理/
    02-待匹配/
    03-待确认/
    04-已入档/
    05-低价值归档/
  01-客户档案/
  02-客户事件流/
  03-业务模块/
    insurance/
    consulting/
    partnership/
    content/
    other/
  04-方案与分析/
  05-团队协同/
    01-待分配/
    02-处理中/
    03-待复核/
    04-已完成/
    05-协同摘要/
    06-脱敏案例/
  06-服务跟进/
  07-客户分层/
  08-复盘案例/
  09-产品与机会/
    products/
    matching/
  10-客户洞察/
  90-索引与看板/
  99-模板与规则/
```

## 设计原则

- 主档案保持轻量，保存当前稳定摘要。
- 客户事件流保存历史过程，如聊天、录音转写、面谈、补资料、方案沟通。
- 业务模块保存业务线专属资料，如保险、咨询、合作。
- 入口池先接住信息，再评分、匹配、路由。
- 索引与看板负责规模化查询，不要靠人工翻目录。

## 客户编号

使用不可识别真实身份的编号：

```text
CUST-0001
CUST-0002
ORG-0001
ANON-0001
```

命名建议：

```text
CUST-0001-杭州三口之家.md
ORG-0001-某教育机构.md
ANON-0001-体检异常投保案例.md
```

不要在文件名中写完整姓名、手机号、身份证、完整保单号。

## 主档案 YAML

```yaml
---
type: customer_profile
customer_id: CUST-0001
display_name: 杭州三口之家
aliases:
  - 张先生
customer_type:
  - insurance_client
business_line:
  - insurance
status: active
stage: lead
priority: B
source: 朋友转介绍
owner: self
age_range: 31-40
income_range: 20-50万
occupation: 教师
city: 杭州
family_structure: 已婚有孩
privacy_level: P2
info_completeness: L1
confidence: medium
created: 2026-07-11
updated: 2026-07-11
next_action: 补充已有保单
next_followup_date:
tags:
  - 家庭保障
  - 待补充
needs:
  - 家庭保障
risks:
  - 健康核保不确定
opportunities:
  - 保单整理
concerns:
  - 预算压力
product_fit: []
analysis_status: needs_review
solution_status: not_ready
---
```

## 画像字段

可结构化的画像字段，用于「主要客户画像」聚合、产品↔群体交叉分析，以及 `filter` 结构化筛选（如 `--age 45 --family 已婚有孩`）。有明确表述才填写，容忍缺省（缺省客户不计入该维度统计）。

| 字段 | 含义 | 示例 | 说明 |
|---|---|---|---|
| `age_range` | 年龄区间 | `31-40` | 用区间不用精确值，兼顾隐私与统计稳定。capture 遇到「35岁」自动归桶 |
| `income_range` | 收入区间 | `20-50万` | 同上；「月收入1.5万」会折算年化后归桶 |
| `occupation` | 职业 | `教师` | 主要职业，取首个匹配 |
| `city` | 城市 | `杭州` | 主工作/生活城市 |
| `family_structure` | 家庭结构 | `已婚有孩` | 从家庭线索保守归纳：单身/已婚无孩/已婚有孩/有孩 |

规约：

- 画像字段是「可聚合事实」，与 `tags`/`needs` 这类语义判断分开。
- 历史档案没有这些字段不用补全也能继续使用；`segment` 会标注覆盖率提示数据缺口。
- 用户描述里没提到的维度不推断（尤其家庭结构），宁缺毋滥。
- `capture` 会把画像字段写入 frontmatter 和正文「基础事实」，后续片段可直接在此基础上补充。

## 生命周期字段

`status` 表示客户是否仍需管理：

| status | 含义 |
|---|---|
| `active` | 活跃，需要跟进或服务 |
| `dormant` | 沉睡，暂不主动推进 |
| `archived` | 归档，不再作为当前客户处理 |

`stage` 表示当前业务阶段：

| stage | 含义 |
|---|---|
| `lead` | 线索 |
| `contacted` | 已接触 |
| `qualified` | 有效客户 |
| `analysis` | 分析中 |
| `solution` | 方案中 |
| `servicing` | 服务中 |
| `review` | 复盘/复核中 |

规则：

- 活跃客户：`status: active` 且通常应有 `next_action`。
- 沉睡客户：`status: dormant`，可无近期跟进日期，但应说明沉睡原因。
- 归档客户：`status: archived`，不进入日常跟进看板。

切换状态用 `set-status --customer-id <ID> --status active/dormant/archived [--reason <原因>]`（预览先行、`--apply` 才落盘），改动写进档案「变更记录」，`filter --status archived` 可单独查看归档客户。

## 合并字段

两份档案经人工确认为同一人后，用 `merge --keep <保留ID> --absorb <并入ID>` 合并（预览先行、`--apply` 才落盘）：

| 字段 | 规则 |
|---|---|
| `merged_from`（keep 新增） | 记录并入的档案 ID，可多个，如 `[CUST-0006, CUST-0009]` |
| `merged_into`（absorb 新增） | 记录被并入的保留档案 ID；absorb 同时转为 `status: archived` |

合并行为：aliases/tags/needs/risks/opportunities/concerns/customer_type/business_line 取并集；keep 缺省的画像/来源等标量用 absorb 补；信息完整度与优先级取较高者；`02-客户事件流/<absorb>/` 文件迁入 `<keep>/`；absorb 全文追加进 keep（不丢内容）。已合并的 absorb 再次合并会被拒绝。

## 客户类型

`customer_type` 可多选：

| 类型 | 说明 |
|---|---|
| `insurance_client` | 保险、保单整理、理赔、核保相关客户 |
| `consulting_client` | 咨询服务客户 |
| `knowledge_service_client` | 知识库、AI 工具、内容服务客户 |
| `partnership_client` | 合作方、渠道、机构 |
| `content_audience` | 内容读者、社群用户、潜在受众 |
| `other_client` | 其他客户 |

`business_line` 可多选：

| 业务线 | 说明 |
|---|---|
| `insurance` | 保险咨询、保障规划、理赔协助 |
| `consulting` | 咨询、顾问、方案服务 |
| `knowledge_service` | 知识库搭建、AI 工作流 |
| `partnership` | 合作、转介绍、渠道 |
| `content` | 内容运营、选题、社群 |
| `other` | 其他 |

## 信息完整度

| 等级 | 达成条件 |
|---|---|
| `L0` | 仅有线索、称呼或一句话背景 |
| `L1` | 有来源、初步需求、可跟进方式中的至少两项 |
| `L2` | 有家庭/职业/预算/业务背景中的至少一类 |
| `L3` | 有关键业务资料：如保单、健康、项目需求、合作目标 |
| `L4` | 可形成阶段性分析和优先级判断 |
| `L5` | 可形成完整方案，并有跟进/复盘闭环 |

## 字段状态

对不完整信息使用状态标记：

```yaml
family_status:
  value: 已婚
  status: known
children:
  value:
  status: pending
budget:
  value: 中等
  status: assumed
  basis: 客户提到“保费不能压力太大”
```

状态值：

- `known`
- `unknown`
- `pending`
- `assumed`
- `conflict`
- `not_applicable`

## 主档案正文结构

```markdown
# 客户档案：CUST-0001

## 一句话画像

## 基础事实

## 客户类型与业务线

## 当前需求

## 关键顾虑

## 已知资料

## 待补充资料

## 阶段性判断

## 下一步动作

## 重要记录索引

## 变更记录
```

## 事件流

每次沟通或资料变化都应进入事件流：

```text
02-客户事件流/CUST-0001/2026-07-11-微信初次沟通.md
02-客户事件流/CUST-0001/2026-07-15-录音转写摘录.md
02-客户事件流/CUST-0001/2026-07-20-保单补充.md
```

事件记录只记录当次发生了什么；主档案只吸收稳定摘要。

## 业务模块

保险客户资料放在：

```text
03-业务模块/insurance/CUST-0001-保险资料.md
```

建议结构：

```markdown
# 保险资料

## 已有保单

## 家庭责任

## 健康情况

## 核保关注点

## 保障缺口

## 理赔/保全/续保记录
```

咨询客户资料放在：

```text
03-业务模块/consulting/CUST-0001-咨询需求.md
```

建议结构：

```markdown
# 咨询需求

## 背景

## 目标

## 约束

## 当前卡点

## 可交付成果

## 决策人/影响人
```

## 索引文件

建议维护：

```text
90-索引与看板/客户总索引.md
90-索引与看板/customer-index.json
90-索引与看板/待跟进清单.md
90-索引与看板/信息缺口清单.md
90-索引与看板/客户分层索引.md
90-索引与看板/数据质量报告.md
90-索引与看板/本周经营看板.md
90-索引与看板/产品机会看板.md
90-索引与看板/客户洞察索引.md
90-索引与看板/客户群体分析.md
90-索引与看板/入口评分汇总.md
```

客户总索引字段：

```markdown
| customer_id | 显示名 | 类型 | 业务线 | 阶段 | 完整度 | 优先级 | 下步动作 | 更新日期 | 路径 |
```

## 客户洞察卡

客户洞察卡放在：

```text
10-客户洞察/CUST-0001/
```

推荐结构：

```yaml
---
type: customer_insight
customer_id: CUST-0001
insight_type: 需求洞察
confidence: medium
status: pending_review
related_products: []
created: 2026-07-11
---
```

洞察卡用于承接分析结论，不替代原始事件记录。事件记录回答“发生了什么”，洞察卡回答“这意味着什么”。

## 产品/服务画像

产品或服务画像放在：

```text
09-产品与机会/products/
```

推荐结构：

```yaml
---
type: product_profile
product_id: PROD-001
product_name: 某产品或服务
business_line: insurance
status: active
suitable_for: []
not_suitable_for: []
matching_signals: []
risk_signals: []
required_information: []
age_fit: []
income_fit: []
occupation_fit: []
city_fit: []
family_fit: []
created: 2026-07-11
updated: 2026-07-11
---
```

产品画像用于反向筛选客户，例如”某产品有哪些潜在客户”。

## 产品适配画像字段

可选的「适配画像」约束，声明这个产品适配哪类画像，让 `product-match` 把「客户群体 → 产品」反推接进筛选：

| 字段 | 含义 | 示例 |
|---|---|---|
| `age_fit` | 适配年龄区间 | `[41-50, 51-60]` |
| `income_fit` | 适配收入区间 | `[50万以上]` |
| `occupation_fit` | 适配职业 | `[企业主, 高管]` |
| `city_fit` | 适配城市 | `[上海, 杭州]` |
| `family_fit` | 适配家庭结构 | `[已婚无孩, 已婚有孩]` |

规约：

- 与客户侧画像字段取值对齐（年龄/收入用同一套区间）。
- 空 = 不约束，该维度不参与评分。
- 匹配为**软信号**：客户画像命中适配列表 +8、偏离 -8、客户缺省该维度不奖不罚；偏离 ≥2 项时匹配分封顶 74（不硬排除）。
- 明确不适合请用 `not_suitable_for` 硬信号，不要依赖画像偏离。
- 可先用 `segment` 的「保险类型 × 客户画像」典型画像反推合适人群，再据此填写。
