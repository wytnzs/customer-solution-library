# 客户库保存位置规则

## 核心原则

公开 Skill 不得假设用户的操作系统、磁盘结构或个人目录。

不要把任何个人电脑路径作为默认值，例如：

- `D:\Claude\...`
- `C:\Users\...`
- `/Users/someone/...`
- `/home/someone/...`

这些只能作为用户自己的示例，不能作为通用默认路径。

## 路径确认顺序

当需要创建或使用真实客户库时，Agent 必须按顺序确认：

1. 用户是否已经明确提供客户库路径。
2. 是否设置了环境变量 `CUSTOMER_LIBRARY_BASE`。
3. 当前项目是否有明确配置说明。
4. 如果没有，询问用户希望存放在哪里。

推荐提问：

```text
你希望把私有客户库存放在哪里？

请提供一个本机路径或同步盘路径。建议选择：
- 当前项目外的私有目录；
- 你的用户主目录下的私有文件夹；
- 已设置权限的云盘/同步盘目录；
- 团队共享目录，但需确认权限。
```

## 推荐但不强制的示例

Windows 示例：

```text
%USERPROFILE%\CustomerSolutionLibrary-Private
```

macOS / Linux 示例：

```text
~/CustomerSolutionLibrary-Private
```

这些只是示例，不是默认路径。

## 不推荐位置

不推荐把真实客户库放在：

- 公开 GitHub 仓库内；
- 知识库正文目录内；
- Skill 仓库内；
- 未加权限控制的团队共享目录；
- 会自动公开同步的目录。

## 脚本支持

脚本支持三种方式确定客户库路径：

显式传入：

```bash
python scripts/customer_library.py init --base "<客户库路径>"
```

环境变量：

```bash
CUSTOMER_LIBRARY_BASE="<客户库路径>"
python scripts/customer_library.py index
```

交互式输入：

```bash
python scripts/customer_library.py init
```

如果脚本在非交互环境中运行且没有路径，会报错并要求提供 `--base` 或 `CUSTOMER_LIBRARY_BASE`。
