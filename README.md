# Customer Solution Library

客户解决方案库是一套面向 Claude Code / Codex / Agent 的客户信息管理与客户经营 Skill。

它不是传统 CRM，也不是简单通讯录。它的目标是把聊天记录、录音转写、面谈纪要、保单资料、客户口述、团队反馈等零散信息，沉淀为可分析、可筛选、可跟进、可复盘的长期客户资产。

当前版本：**v3.1**（15 个命令，110 项回归测试全部通过）。

核心链路：

```text
客户信息
→ 入口判断
→ 身份匹配
→ 档案沉淀
→ 客户洞察
→ 信息缺口
→ 产品/服务匹配
→ 专属方案
→ 跟进复盘
```

## 它能做什么

- 录入客户信息，支持不完整信息分批补全
- 一段客户描述直接抓取入档：自动判断新老客户，无记录建档、有记录生成更新建议，模糊时提示待确认而不是静默新建
- 从聊天记录、录音转写、口述记录中摘录客户情况
- 防止同名客户误并档，确认同一人后合并档案
- 建立客户主档案和客户事件流
- 生成客户深度分析、客户洞察卡、信息缺口清单
- 客户群体分析：按类型/阶段/完整度聚合，输出主要客户画像与「保险类型 × 客户画像」经营侧重反推
- 按画像/生命周期/保险类型结构化筛选客户（年龄、收入、职业、城市、家庭结构、缺省字段）
- 根据某个产品/服务反向筛选潜在客户
- 档案生命周期管理：成交后归档、长期不回复转沉睡、重新联系唤醒
- 生成本周经营看板和数据质量报告
- 入口池批量评分（100 分制判断一条信息值不值得入库）
- 支持团队协同、脱敏分享、客户复盘
- 与个人知识库协同使用：知识库保存方法论，私有客户库保存真实客户资料

## 推荐安装方式：项目级安装

推荐把本 Skill 安装到当前 Claude Code / Codex 项目的 `.claude/skills` 目录中，而不是默认全局安装。

这样当前项目中的 AI 更容易稳定识别和使用本 Skill，尤其适合“知识库项目 + 客户管理库”联动场景。

### Windows：安装到当前项目

先进入你的项目目录，例如你的知识库项目：

```powershell
cd "<你的知识库项目路径>"
```

一条指令安装：

```powershell
New-Item -ItemType Directory -Force ".claude\skills" | Out-Null; git clone https://github.com/wytnzs/customer-solution-library.git ".claude\skills\customer-solution-library"
```

如果已经安装过，更新：

```powershell
git -C ".claude\skills\customer-solution-library" pull
```

如果这个目录不是独立 git 仓库，建议先备份旧目录，再重新 clone：

```powershell
Rename-Item ".claude\skills\customer-solution-library" "customer-solution-library.backup"
git clone https://github.com/wytnzs/customer-solution-library.git ".claude\skills\customer-solution-library"
```

### macOS / Linux：安装到当前项目

```bash
mkdir -p .claude/skills && git clone https://github.com/wytnzs/customer-solution-library.git .claude/skills/customer-solution-library
```

如果已经安装过，更新：

```bash
git -C .claude/skills/customer-solution-library pull
```

## 可选：全局安装

只有当你希望所有 Codex 任务都默认可用时，才建议全局安装。

如果你主要在某个知识库或客户库项目里使用，不建议只做全局安装；否则 AI 可能无法稳定把 Skill 与当前项目内容结合起来。

Windows：

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.codex\skills" | Out-Null; git clone https://github.com/wytnzs/customer-solution-library.git "$env:USERPROFILE\.codex\skills\customer-solution-library"
```

macOS / Linux：

```bash
mkdir -p ~/.codex/skills && git clone https://github.com/wytnzs/customer-solution-library.git ~/.codex/skills/customer-solution-library
```

## 与知识库如何配合

推荐三层结构：

```text
知识库项目
  保存方法论、模板、产品知识、话术、脱敏案例

customer-solution-library Skill
  保存客户管理规则、脚本、字段规范、分析流程

私有客户库
  保存真实客户档案、事件流、方案、跟进记录、产品机会清单
```

关键原则：

- 知识库保存方法论，不保存真实客户资料。
- 私有客户库保存真实客户资料：真实姓名、真实联系方式、真实情况。
- 客户编号（`customer_id`）只是系统内部键，用于合并和引用；档案与目录用真实姓名命名。
- Skill 安装在知识库项目的 `.claude/skills/customer-solution-library` 中。
- AI 生成客户方案时，可以参考知识库中的产品知识和话术。
- 可复用经验进入知识库前必须脱敏。

推荐启动语：

```text
使用项目内 .claude/skills/customer-solution-library。

当前项目是我的知识库，用于保存方法论、模板、产品知识和脱敏案例。
真实客户库路径是：<你的私有客户库路径>。

处理客户信息时：
1. 真实客户资料只写入私有客户库；
2. 可复用方法论、脱敏案例、复盘内容才写入知识库；
3. 生成方案时可以参考知识库中的产品知识和话术；
4. 输出中请区分事实、推断、知识库参考和待确认信息。
5. 涉及健康、保险、理赔、法律、财务承诺时必须保守表达并提示人工复核。
```

## 第一次使用

初始化私有客户库：

```text
使用项目内 .claude/skills/customer-solution-library。
请询问我希望把私有客户库存放在哪里，然后在我确认的路径初始化客户库。
```

或手动运行：

```powershell
python .claude\skills\customer-solution-library\scripts\customer_library.py init --base "<你的私有客户库路径>"
```

也可以先设置环境变量，后续命令就不用每次传 `--base`：

Windows PowerShell：

```powershell
$env:CUSTOMER_LIBRARY_BASE="<你的私有客户库路径>"
```

macOS / Linux：

```bash
export CUSTOMER_LIBRARY_BASE="<你的私有客户库路径>"
```

初始化后会生成：

```text
00-入口池/
01-客户档案/
02-客户事件流/
03-业务模块/
04-方案与分析/
05-团队协同/
06-服务跟进/
07-客户分层/
08-复盘案例/
09-产品与机会/
10-客户洞察/
90-索引与看板/
99-模板与规则/
```

## 常用指令

录入客户信息：

```text
使用项目内 .claude/skills/customer-solution-library。
客户库路径是 <你的私有客户库路径>。

请处理这条客户信息：
……
```

分析客户：

```text
请分析 CUST-0001，输出客户深度分析、信息缺口和下一步跟进建议。
```

根据产品筛选潜在客户：

```text
我准备推广 PROD-001，请筛选潜在客户，并说明匹配原因、风险点、缺口和建议动作。
```

生成经营看板：

```text
请生成本周经营看板，列出优先跟进、缺下一步动作、信息不足但活跃、可进入方案复核的客户。
```

客户群体分析：

```text
请做客户群体分析，看我的客户主要集中在什么年龄段和城市，各群体的典型画像是什么。
```

档案清理：

```text
请把已成交的 CUST-0001 归档；另外 CUST-0002 和 CUST-0006 是同一个客户，请合并。
```

## 常用脚本

全部命令都是 `customer_library.py <命令> --base <客户库路径>`；加了 `PYTHONIOENCODING=utf-8` 可在 Windows 中文环境稳定输出。

初始化与录入：

```powershell
python .claude\skills\customer-solution-library\scripts\customer_library.py init --base "<你的私有客户库路径>"
python .claude\skills\customer-solution-library\scripts\customer_library.py capture --base "<你的私有客户库路径>" --text "张先生转介绍，杭州，家里两个孩子，想了解重疾险" --apply
python .claude\skills\customer-solution-library\scripts\customer_library.py score-intake --text "<一条客户信息片段>"
python .claude\skills\customer-solution-library\scripts\customer_library.py intake-pool --base "<你的私有客户库路径>"
```

查询与筛选：

```powershell
python .claude\skills\customer-solution-library\scripts\customer_library.py index --base "<你的私有客户库路径>"
python .claude\skills\customer-solution-library\scripts\customer_library.py find --base "<你的私有客户库路径>" 重疾
python .claude\skills\customer-solution-library\scripts\customer_library.py filter --base "<你的私有客户库路径>" --age 41-50 --family 已婚有孩 --no-product 重疾
```

分析与经营：

```powershell
python .claude\skills\customer-solution-library\scripts\customer_library.py analyze-customer --base "<你的私有客户库路径>" --customer-id CUST-0001
python .claude\skills\customer-solution-library\scripts\customer_library.py gaps --base "<你的私有客户库路径>" --customer-id CUST-0001
python .claude\skills\customer-solution-library\scripts\customer_library.py segment --base "<你的私有客户库路径>" --by age
python .claude\skills\customer-solution-library\scripts\customer_library.py product-match --base "<你的私有客户库路径>" --product-id PROD-001 --detail
python .claude\skills\customer-solution-library\scripts\customer_library.py dashboard --base "<你的私有客户库路径>"
python .claude\skills\customer-solution-library\scripts\customer_library.py audit --base "<你的私有客户库路径>"
```

生命周期（预览先行，加 `--apply` 才真正写盘）：

```powershell
python .claude\skills\customer-solution-library\scripts\customer_library.py set-status --base "<你的私有客户库路径>" --customer-id CUST-0001 --status archived --reason 成交结束 --apply
python .claude\skills\customer-solution-library\scripts\customer_library.py merge --base "<你的私有客户库路径>" --keep CUST-0001 --absorb CUST-0006 --apply
```

需要脚本或工具消费时，多数命令支持 `--json` 输出纯 JSON。

## 文档

- [SKILL.md](SKILL.md)：系统入口与全部命令说明
- [客户管理库操作手册](docs/客户管理库操作手册.md)：完整操作手册
- [更新记录](CHANGELOG.md)：8 轮迭代历程
- [客户库保存位置规则](references/storage-location-policy.md)
- [与知识库协同使用规则](references/knowledge-base-integration.md)
- [客户洞察与深度分析规则](references/customer-insights.md)
- [产品/服务反向匹配客户规则](references/product-matching.md)

## 回归测试

```bash
PYTHONIOENCODING=utf-8 python scripts/test_customer_library.py
```

测试用临时客户库 fixture 驱动真实 CLI，覆盖预览不落盘、落盘 frontmatter/变更记录、筛选联动、非法输入拒绝、合并字段并集与事件流迁移等 110 项断言。

## 隐私边界

本仓库只保存规则、脚本和模板，**不含任何真实客户资料**。

- **私有客户库（本机存档）**：保存真实数据——真实姓名、真实联系方式、真实情况；档案文件名与事件流目录都用真实姓名，客户编号只是内部键。
- **公开层（本仓库、知识库、团队分享、对外内容）**：绝不出现真实客户数据；需要引用时先脱敏，真实姓名换成化名或 `ANON-` 编号。
