# Customer Solution Library

客户解决方案库是一套面向 Claude Code / Codex / Agent 的客户管理 Skill。

它用 Markdown、YAML、入口评分、身份匹配、事件流和自动索引，帮助 Agent 管理客户信息、生成分析、跟进客户、检查数据质量。

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

手册包含：

1. 仓库包含的内容及用途
2. 具体功能及使用方法
3. 最小计量单位
4. 与传统方案的区别及优势
5. 安装方式

## 隐私提醒

真实客户资料应放到单独的私有客户库，不要提交到本仓库。
