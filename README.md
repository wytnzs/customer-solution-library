# Customer Solution Library

客户解决方案库是一套面向 Claude Code / Codex / Agent 的客户管理 Skill。

它不是传统 CRM，也不是简单通讯录，而是一套用 Markdown、结构化字段和 Agent 工作流搭建的“客户长期服务大脑”。

适合以下场景：

- 保险代理人管理客户、保单整理、健康告知、理赔协助
- 咨询顾问管理客户需求、方案、跟进和复盘
- 知识服务/AI 服务从业者管理客户项目与协作
- 团队希望用 Agent 自动处理客户信息、生成分析和跟进清单

## 它能做什么

- 接收客户聊天记录、录音转写、口述记录、资料补充
- 判断一段客户信息是否有价值，给出 S/A/B/C/D 等级
- 匹配客户身份，避免同名客户误并档
- 建立客户主档案和客户事件流
- 管理保险、咨询、合作、内容等不同业务线客户
- 生成客户速览、客户分析 brief、专属方案草稿
- 设置下一步跟进和跟进日期
- 支持团队协同、任务分派、脱敏摘要和复核
- 自动生成索引和数据质量报告

## 推荐理解

这套系统由三部分组成：

```text
Skill 仓库
  保存规则、脚本、模板和 Agent 操作说明

私有客户库
  保存真实客户档案、事件流、方案、跟进记录

Agent / Claude Code
  负责执行录入、分析、匹配、更新、质检等动作
```

重要原则：

> 本仓库不存真实客户资料。真实客户资料应放到单独的私有客户库。

## 仓库结构

```text
customer-solution-library/
  SKILL.md
  README.md
  agents/
    openai.yaml
  docs/
    客户管理库操作手册.md
  references/
    conversation-ingestion.md
    data-model.md
    data-quality-audit.md
    intake-routing.md
    output-formats.md
    team-collaboration.md
    workflows.md
  scripts/
    customer_library.py
```

## 安装方式一：作为个人 Skill 安装

适合你希望所有 Codex / Agent 任务都能调用这个 Skill。

### Windows

```powershell
mkdir $env:USERPROFILE\.codex\skills -Force
git clone https://github.com/wytnzs/customer-solution-library.git $env:USERPROFILE\.codex\skills\customer-solution-library
```

### macOS / Linux

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/wytnzs/customer-solution-library.git ~/.codex/skills/customer-solution-library
```

安装后可以这样对 Agent 说：

```text
使用 $customer-solution-library，帮我录入/分析/查询客户信息。
```

## 安装方式二：作为某个项目的本地 Skill

适合你只想在某个客户库项目中使用。

在目标项目下创建：

```text
.claude/skills/customer-solution-library/
```

然后把本仓库内容复制进去，或者直接 clone：

```powershell
git clone https://github.com/wytnzs/customer-solution-library.git .claude\skills\customer-solution-library
```

之后在 Claude Code 中打开该项目，并告诉 Agent：

```text
使用 .claude/skills/customer-solution-library 这个 Skill，帮我管理客户库。
```

## 安装方式三：作为独立工具使用

适合你只想使用脚本初始化客户库、刷新索引、做质检。

```powershell
git clone https://github.com/wytnzs/customer-solution-library.git D:\Claude\customer-solution-library
cd D:\Claude\customer-solution-library
```

检查是否可运行：

```powershell
python scripts/customer_library.py score-intake --text "张先生说孩子刚上小学，最近体检发现甲状腺结节，想看看重疾险，周五晚上有空。"
```

如果能看到 `signal_score`、`signal_level`、`route`，说明脚本可用。

## 第一次使用

创建一个私有客户库：

```powershell
python scripts/customer_library.py init --base D:\Claude\客户解决方案库-私有
```

这会生成：

```text
客户解决方案库-私有/
  00-入口池/
  01-客户档案/
  02-客户事件流/
  03-业务模块/
  04-方案与分析/
  05-团队协同/
  06-服务跟进/
  07-客户分层/
  08-复盘案例/
  90-索引与看板/
  99-模板与规则/
```

然后你可以对 Agent 说：

```text
使用 $customer-solution-library，在 D:\Claude\客户解决方案库-私有 中录入客户：
张先生，杭州，李姐转介绍，已婚一孩，想了解重疾险，最近体检发现甲状腺结节，周五晚上有空。
```

## 常用命令

入口信息评分：

```powershell
python scripts/customer_library.py score-intake --text "客户信息片段"
```

刷新客户索引：

```powershell
python scripts/customer_library.py index --base D:\Claude\客户解决方案库-私有
```

搜索客户：

```powershell
python scripts/customer_library.py find --base D:\Claude\客户解决方案库-私有 --query 张先生
```

生成数据质量报告：

```powershell
python scripts/customer_library.py audit --base D:\Claude\客户解决方案库-私有
```

## 给 Agent 的推荐启动语

```text
你现在使用 customer-solution-library Skill。
客户库路径是：D:\Claude\客户解决方案库-私有

请遵守：
1. 先判断入口信息价值，再决定是否入档。
2. 同名客户不能自动并档。
3. 主档案只写稳定摘要，历史细节写入事件流。
4. 不确定的信息标记为待确认。
5. 涉及隐私、健康、理赔、保单、承诺的信息要保守处理。
```

## 操作手册

详细教程见：

[docs/客户管理库操作手册.md](docs/客户管理库操作手册.md)

## 隐私提醒

不要把以下内容提交到 GitHub：

- 真实客户完整姓名
- 手机号
- 身份证号
- 银行卡号
- 完整保单号
- 病历原件
- 体检报告原件
- 微信聊天截图原图

建议真实客户资料另建私有目录，并加入 `.gitignore`。

