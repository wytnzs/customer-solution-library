---
title: 代理人首次使用路线
type: guide
description: 从零到第一次用上客户库的 30 分钟路径，按顺序做，不跳步
created: 2026-11-26
updated: 2026-11-26
tags: [客户管理, 首次使用, 安装]
---

# 代理人首次使用路线

> 这份是给「第一次用」的人看的。不解释原理，只给顺序和判断标准。
> 全部命令都在 `.claude/skills/customer-solution-library/scripts/customer_library.py`。

## 先用一句话判断：你现在在哪一步

| 你现在的情况 | 从哪开始 |
|---|---|
| 还没装 | 第 1 步 |
| 装好了，不知道库建哪 | 第 2 步 |
| 库建好了，客户还在微信/Excel 里 | 第 3 步 |
| 已经有客户，想每天用起来 | 第 4 步 |
| 用了一阵，怕数据丢 | 第 5 步 |

## 第 1 步：装（5 分钟）

装到你的知识库项目里，不要装全局：

```powershell
cd "<你的知识库项目路径>"
New-Item -ItemType Directory -Force ".claude\skills" | Out-Null
git clone https://github.com/wytnzs/customer-solution-library.git ".claude\skills\customer-solution-library"
```

clone 不下来时，任选一条：

```powershell
# SSH 走 443 端口，国内更稳
git clone ssh://git@ssh.github.com:443/wytnzs/customer-solution-library.git ".claude\skills\customer-solution-library"

# 或者浏览器打开仓库 → Code → Download ZIP，解压到 .claude\skills\customer-solution-library
```

装完先自检：

```powershell
python .claude\skills\customer-solution-library\scripts\customer_library.py doctor --base "<你打算放客户库的路径>"
```

看到「通过 X 项，失败 0 项」再往下。失败项照着提示处理，别硬走。

如果 `python --version` 就报错，说明本机没装 Python：去 python.org 或 Microsoft Store 装 3.10 以上，装完重开终端。装不了 Python 的，让 Claude Code / Codex 代跑命令，不要自己硬敲。

## 第 2 步：建库（3 分钟）

客户库不要建在知识库项目里，也不要放进公开仓库。选一个私有目录：

- 本机私有文件夹；
- 你已经在用的云盘/同步盘私有目录；
- 不要选团队共享目录，除非你确认过权限。

```powershell
python .claude\skills\customer-solution-library\scripts\customer_library.py init --base "<私有客户库路径>"
python .claude\skills\customer-solution-library\scripts\customer_library.py doctor --base "<私有客户库路径>"
```

第二次 `doctor` 应该全绿。想省掉每次传路径，可以设环境变量：

```powershell
$env:CUSTOMER_LIBRARY_BASE="<私有客户库路径>"
```

## 第 3 步：把客户搬进来（10 分钟）

先把微信、Excel、名片里的名字整理成一个 CSV，最少三列：`姓名,手机,城市`。有生日就加 `生日`，有备注就加 `备注`。

先预览，不落盘：

```powershell
python .claude\skills\customer-solution-library\scripts\customer_library.py import --base "<客户库>" --file "<名单.csv>"
```

看清楚三件事再执行：

1. **识别列**对不对（姓名列找没找到）；
2. **将新建**多少人；
3. **重复**多少行——重复的不会新建，会进待确认池。

确认后加 `--apply`：

```powershell
python .claude\skills\customer-solution-library\scripts\customer_library.py import --base "<客户库>" --file "<名单.csv>" --apply
```

Excel 另存的 CSV 常是 GBK，脚本会自动识别；如果报「无法识别编码」，用 Excel「另存为 → CSV UTF-8」再导。

不要一次导 500 人。先导 20 个最近联系的人，确认档案长得对，再导全量。

## 第 4 步：每天用起来（10 分钟上手）

三个动作，形成习惯：

### 见完客户，记一条

```powershell
python .claude\skills\customer-solution-library\scripts\customer_library.py event --base "<客户库>" --customer "张伟" --kind 面谈 --text "聊了重疾和预算，先做保障盘点" --next-action "发方案" --followup-date 2026-12-03 --apply
```

事件按日期落到 `02-客户事件流/张伟/`，主档案只更新下一步和回访日期。

### 每周一看该找谁

```powershell
python .claude\skills\customer-solution-library\scripts\customer_library.py remind --base "<客户库>" --days 30
```

分三组：已逾期、未来 30 天、生日。先处理逾期，再看生日。

### 要发名单给客户或自己看

```powershell
# 自己用，带真实信息
python .claude\skills\customer-solution-library\scripts\customer_library.py export --base "<客户库>" --format csv --out "客户名单.csv"

# 给团队/对外，先脱敏
python .claude\skills\customer-solution-library\scripts\customer_library.py export --base "<客户库>" --format csv --mask --out "脱敏名单.csv"
```

## 第 5 步：每周备份（2 分钟）

```powershell
python .claude\skills\customer-solution-library\scripts\customer_library.py backup --base "<客户库>" --out "<备份目录>"
```

备份目录选另一个盘或云盘。换电脑时：

```powershell
python .claude\skills\customer-solution-library\scripts\customer_library.py restore --from "<备份.zip>" --base "<新电脑上的空目录>"
python .claude\skills\customer-solution-library\scripts\customer_library.py doctor --base "<新电脑上的空目录>"
```

恢复会先校验 sha256；目标目录非空时会拒绝，确认覆盖才加 `--force`。

升级 skill 版本后，老库先跑一次迁移（幂等，不会重复改）：

```powershell
python .claude\skills\customer-solution-library\scripts\customer_library.py migrate --base "<客户库>" --apply
```

## 什么时候不用这套

- 客户不到 10 个：先用备忘录，别急着建库。
- 你真正的问题是不会聊客户，不是记不住客户：先解决前者。
- 你要的是多人实时协作：本地 Markdown 库不擅长这个，别硬套。

## 每周固定动作

| 时间 | 做什么 | 命令 |
|---|---|---|
| 每天见完客户 | 记一条事件 | `event` |
| 周一早上 | 看该找谁 | `remind` |
| 周五下午 | 刷新索引、看数据质量 | `index` + `audit` |
| 周日晚 | 备份 | `backup` |
