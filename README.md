# Customer Solution Library

客户解决方案库是一套面向 Claude Code / Codex / Agent 的客户管理 Skill。

它不是传统 CRM，也不是普通通讯录，而是一套面向长期客户服务的「客户信息管理与解决方案系统」。

它用 Markdown、YAML、入口评分、身份匹配、事件流和自动索引，帮助 Agent 把聊天、录音转写、面谈纪要、资料补充等零散信息，沉淀为客户档案、客户分析、专属方案、跟进动作和复盘记录。

本仓库只保存规则、脚本和模板，不保存真实客户资料。

## 一条指令安装

Windows：

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.codex\skills" | Out-Null; git clone https://github.com/wytnzs/customer-solution-library.git "$env:USERPROFILE\.codex\skills\customer-solution-library"
```

macOS / Linux：

```bash
mkdir -p ~/.codex/skills && git clone https://github.com/wytnzs/customer-solution-library.git ~/.codex/skills/customer-solution-library
```

## 一句话使用

```text
使用 $customer-solution-library，帮我初始化并管理客户库。
```

## 操作手册

请先阅读：

[docs/客户管理库操作手册.md](docs/客户管理库操作手册.md)

手册重点说明：

1. 这套客户管理库是什么
2. 为什么这样构建
3. 最小计量单位是什么
4. 具体怎么用
5. 与传统 CRM / Excel / 知识库的区别和优势

## 隐私提醒

真实客户资料应放到单独的私有客户库，不要提交到本仓库。
