# Customer Solution Library

客户解决方案库是一套面向 Claude Code / Codex / Agent 的客户信息管理与客户经营 Skill。

它不是传统 CRM，也不是简单通讯录。它的目标是把聊天记录、录音转写、面谈纪要、保单资料、客户口述、团队反馈等零散信息，沉淀为可分析、可筛选、可跟进、可复盘的长期客户资产。

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
- 从聊天记录、录音转写、口述记录中摘录客户情况
- 防止同名客户误并档
- 建立客户主档案和客户事件流
- 生成客户深度分析、客户洞察卡、信息缺口清单
- 根据某个产品/服务反向筛选潜在客户
- 生成本周经营看板和数据质量报告
- 支持团队协同、脱敏分享、客户复盘
- 与个人知识库协同使用：知识库保存方法论，私有客户库保存真实客户资料

## 推荐安装方式：项目级安装

推荐把本 Skill 安装到当前 Claude Code / Codex 项目的 `.claude/skills` 目录中，而不是默认全局安装。

这样当前项目中的 AI 更容易稳定识别和使用本 Skill，尤其适合“知识库项目 + 客户管理库”联动场景。

### Windows：安装到当前项目

先进入你的项目目录，例如知识库项目：

```powershell
cd D:\Claude\wyt知识库
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
- 私有客户库保存真实客户资料。
- Skill 安装在知识库项目的 `.claude/skills/customer-solution-library` 中。
- AI 生成客户方案时，可以参考知识库中的产品知识和话术。
- 可复用经验进入知识库前必须脱敏。

推荐启动语：

```text
使用项目内 .claude/skills/customer-solution-library。

当前项目是我的知识库，用于保存方法论、模板、产品知识和脱敏案例。
真实客户库路径是：D:\Claude\客户解决方案库-私有。

处理客户信息时：
1. 真实客户资料只写入私有客户库；
2. 可复用方法论、脱敏案例、复盘内容才写入知识库；
3. 生成方案时可以参考知识库中的产品知识和话术；
4. 输出中请区分事实、推断、知识库参考和待确认信息。
```

## 第一次使用

初始化私有客户库：

```text
使用项目内 .claude/skills/customer-solution-library。
请在 D:\Claude\客户解决方案库-私有 初始化一个客户库。
```

或手动运行：

```powershell
python .claude\skills\customer-solution-library\scripts\customer_library.py init --base D:\Claude\客户解决方案库-私有
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
客户库路径是 D:\Claude\客户解决方案库-私有。

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

## 常用脚本

```powershell
python .claude\skills\customer-solution-library\scripts\customer_library.py index --base D:\Claude\客户解决方案库-私有
python .claude\skills\customer-solution-library\scripts\customer_library.py audit --base D:\Claude\客户解决方案库-私有
python .claude\skills\customer-solution-library\scripts\customer_library.py analyze-customer --base D:\Claude\客户解决方案库-私有 --customer-id CUST-0001
python .claude\skills\customer-solution-library\scripts\customer_library.py gaps --base D:\Claude\客户解决方案库-私有 --customer-id CUST-0001
python .claude\skills\customer-solution-library\scripts\customer_library.py product-match --base D:\Claude\客户解决方案库-私有 --product-id PROD-001
python .claude\skills\customer-solution-library\scripts\customer_library.py dashboard --base D:\Claude\客户解决方案库-私有
```

## 文档

- [客户管理库操作手册](docs/客户管理库操作手册.md)
- [与知识库协同使用规则](references/knowledge-base-integration.md)
- [客户洞察与深度分析规则](references/customer-insights.md)
- [产品/服务反向匹配客户规则](references/product-matching.md)

## 隐私提醒

本仓库只保存规则、脚本和模板，不保存真实客户资料。

真实客户资料应放到单独的私有客户库，不要提交到本仓库，也不要直接写入知识库。
