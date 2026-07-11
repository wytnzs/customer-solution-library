# Customer Solution Library

客户解决方案库是一个面向客户长期服务、客户信息入库、客户分析、专属方案、团队协同和数据质检的 Codex Skill。

它适合用 Markdown 作为客户长期档案层，同时配合结构化索引、入口评分、身份匹配和数据质量检查，支撑从个人客户管理到团队协同的渐进式客户系统。

## 核心能力

- 统一客户信息入口
- 100 分制客户信息价值评分
- 录音转写、聊天记录、口述记录摘录
- 客户身份匹配与同名防误并档
- 多类型客户管理：保险、咨询、知识库服务、合作、内容受众等
- Markdown 客户档案与客户事件流
- 客户分析 brief 与专属方案草稿
- 团队协同、分享、复核与脱敏规则
- 数据质量检查：缺跟进、疑似重复、隐私风险、待匹配入口等

## 目录结构

```text
.
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── conversation-ingestion.md
│   ├── data-model.md
│   ├── data-quality-audit.md
│   ├── intake-routing.md
│   ├── output-formats.md
│   ├── team-collaboration.md
│   └── workflows.md
└── scripts/
    └── customer_library.py
```

## 常用命令

初始化一个私有客户库：

```powershell
python scripts/customer_library.py init --base D:\Claude\客户解决方案库-私有
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

对入口信息评分：

```powershell
python scripts/customer_library.py score-intake --text "张先生说孩子刚上小学，最近体检发现甲状腺结节，想看看重疾险，周五晚上有空。"
```

## 隐私原则

本仓库只保存 Skill、方法论、脚本和模板，不应保存真实客户资料。

真实客户数据应放在单独的私有客户库中，并避免明文保存完整姓名、手机号、身份证号、银行卡号、完整保单号、病历原件等敏感信息。

