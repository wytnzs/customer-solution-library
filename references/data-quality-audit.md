# 数据质量检查

## 目标

客户库规模扩大后，必须定期检查数据质量，避免客户档案过期、重复、无人跟进或隐私裸露。

## 检查维度

| 维度 | 检查问题 |
|---|---|
| 完整度 | 是否缺少客户类型、业务线、下一步动作、更新时间 |
| 跟进 | 活跃客户是否有 `next_action` 和 `next_followup_date` |
| 逾期 | 活跃客户的 `next_followup_date` 是否已过期且仍未处理（`audit`/`dashboard` 会给出逾期天数） |
| 重复 | 是否存在同名、同来源、同手机号后四位的疑似重复客户 |
| 待匹配 | 入口池是否有长期未匹配信息 |
| 过期 | 客户是否长期未更新 |
| 隐私 | 是否出现手机号、身份证、银行卡、完整保单号等敏感明文 |
| 方案 | 是否存在方案已生成但未复盘 |
| 协同 | 是否有待复核、逾期协同任务 |

## 自动检查命令

```powershell
python scripts/customer_library.py audit --base "<你的私有客户库路径>"
python scripts/customer_library.py audit --base "<你的私有客户库路径>" --json
```

`--json` 会把总览、逾期跟进、隐私风险、疑似重复客户等汇总输出到 stdout，便于接入定时脚本或团队工具。

## 客户生命周期检查

统一使用：

```yaml
status: active | dormant | archived
stage: lead | contacted | qualified | analysis | solution | servicing | review
```

规则：

- `status: active` 的客户应尽量有 `next_action`。
- `stage: solution` 或 `stage: servicing` 的客户应尽量有 `next_followup_date`。
- `status: archived` 的客户不进入日常跟进问题。
- `status: dormant` 的客户应说明沉睡原因或保留最近一次状态说明。

## 建议频率

| 频率 | 检查 |
|---|---|
| 每日 | 待处理入口、今日跟进 |
| 每周 | 待匹配、逾期跟进、协同任务 |
| 每月 | 重复客户、沉睡客户、隐私抽查、方案复盘 |
| 每季度 | 客户分层、业务线统计、团队协作质量 |

## 输出格式

```markdown
# 客户库数据质量报告

## 总览

## 高风险问题

## 待处理入口

## 疑似重复客户

## 逾期跟进

## 信息缺口

## 隐私风险

## 建议动作
```
