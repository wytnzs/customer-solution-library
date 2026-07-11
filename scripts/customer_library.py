#!/usr/bin/env python3
"""Utilities for the customer-solution-library skill.

Commands:
  init         --base PATH
  index        --base PATH
  find         --base PATH --query TEXT
  audit        --base PATH
  score-intake --text TEXT | --file PATH
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path


DIRS = [
    "00-入口池/01-待处理",
    "00-入口池/02-待匹配",
    "00-入口池/03-待确认",
    "00-入口池/04-已入档",
    "00-入口池/05-低价值归档",
    "01-客户档案",
    "02-客户事件流",
    "03-业务模块/insurance",
    "03-业务模块/consulting",
    "03-业务模块/partnership",
    "03-业务模块/content",
    "03-业务模块/other",
    "04-方案与分析",
    "05-团队协同/01-待分配",
    "05-团队协同/02-处理中",
    "05-团队协同/03-待复核",
    "05-团队协同/04-已完成",
    "05-团队协同/05-协同摘要",
    "05-团队协同/06-脱敏案例",
    "06-服务跟进",
    "07-客户分层",
    "08-复盘案例",
    "90-索引与看板",
    "99-模板与规则",
]


TEMPLATE_PROFILE = """---
type: customer_profile
customer_id:
display_name:
aliases: []
customer_type: []
business_line: []
status: active
stage: lead
priority: B
source:
owner: self
privacy_level: P2
info_completeness: L0
confidence: low
created: {today}
updated: {today}
next_action:
next_followup_date:
tags: []
---

# 客户档案

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
"""


PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
ID_CARD_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
BANK_CARD_RE = re.compile(r"(?<!\d)\d{16,19}(?!\d)")
POLICY_RE = re.compile(r"(保单号|合同号|保单编号)[:：]?\s*[A-Za-z0-9-]{6,}")


def extract_frontmatter(text: str) -> dict[str, object]:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    data: dict[str, object] = {}
    current_list_key: str | None = None
    for line in parts[1].splitlines():
        stripped = line.strip()
        if stripped.startswith("-") and current_list_key:
            value = stripped[1:].strip().strip('"').strip("'")
            existing = data.setdefault(current_list_key, [])
            if isinstance(existing, list):
                existing.append(value)
            continue
        current_list_key = None
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if value == "":
            data[key] = []
            current_list_key = key
        elif value == "[]":
            data[key] = []
        else:
            data[key] = value
    return data


def md_files(base: Path):
    skip = {".git", ".obsidian", ".claude"}
    for path in base.rglob("*.md"):
        if any(part in skip for part in path.parts):
            continue
        yield path


def scalar(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return "" if value is None else str(value)


def init_library(base: Path) -> None:
    base.mkdir(parents=True, exist_ok=True)
    for item in DIRS:
        (base / item).mkdir(parents=True, exist_ok=True)

    template_dir = base / "99-模板与规则"
    profile_template = template_dir / "客户档案模板.md"
    if not profile_template.exists():
        profile_template.write_text(
            TEMPLATE_PROFILE.format(today=date.today().isoformat()),
            encoding="utf-8",
        )

    index_file = base / "90-索引与看板" / "客户总索引.md"
    if not index_file.exists():
        index_file.write_text(
            "# 客户总索引\n\n"
            "| customer_id | 显示名 | 类型 | 业务线 | 状态 | 阶段 | 完整度 | 优先级 | 下步动作 | 更新日期 | 路径 |\n"
            "|---|---|---|---|---|---|---|---|---|---|---|\n",
            encoding="utf-8",
        )
    print(f"Initialized customer library: {base}")


def build_index(base: Path) -> list[dict[str, str]]:
    rows = []
    for path in md_files(base):
        if "99-模板与规则" in path.parts or "99-模板" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        fm = extract_frontmatter(text)
        if fm.get("type") != "customer_profile":
            continue
        rows.append(
            {
                "customer_id": scalar(fm.get("customer_id", "")),
                "display_name": scalar(fm.get("display_name", "")),
                "aliases": scalar(fm.get("aliases", "")),
                "source": scalar(fm.get("source", "")),
                "customer_type": scalar(fm.get("customer_type", "")),
                "business_line": scalar(fm.get("business_line", "")),
                "status": scalar(fm.get("status", "")),
                "stage": scalar(fm.get("stage", "")),
                "info_completeness": scalar(fm.get("info_completeness", "")),
                "priority": scalar(fm.get("priority", "")),
                "next_action": scalar(fm.get("next_action", "")),
                "next_followup_date": scalar(fm.get("next_followup_date", "")),
                "updated": scalar(fm.get("updated", "")),
                "path": str(path.relative_to(base)),
            }
        )
    rows.sort(key=lambda r: (r["customer_id"], r["display_name"]))
    return rows


def write_index(base: Path) -> None:
    rows = build_index(base)
    index_dir = base / "90-索引与看板"
    index_dir.mkdir(parents=True, exist_ok=True)
    md = [
        "# 客户总索引",
        "",
        "| customer_id | 显示名 | 类型 | 业务线 | 状态 | 阶段 | 完整度 | 优先级 | 下步动作 | 更新日期 | 路径 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        md.append(
            "| {customer_id} | {display_name} | {customer_type} | {business_line} | {status} | "
            "{stage} | {info_completeness} | {priority} | {next_action} | {updated} | {path} |".format(**r)
        )
    (index_dir / "客户总索引.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (index_dir / "customer-index.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Indexed {len(rows)} customer profiles.")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower()


def find_customer(base: Path, query: str) -> None:
    q = normalize(query)
    matches = []
    for path in md_files(base):
        if "90-索引与看板" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        haystack = normalize(str(path.relative_to(base)) + "\n" + text)
        if q in haystack:
            fm = extract_frontmatter(text)
            record_type = scalar(fm.get("type", ""))
            if record_type and record_type != "customer_profile":
                continue
            matches.append(
                {
                    "customer_id": scalar(fm.get("customer_id", "")),
                    "display_name": scalar(fm.get("display_name", "")),
                    "type": record_type,
                    "updated": scalar(fm.get("updated", "")),
                    "path": str(path.relative_to(base)),
                }
            )
    if not matches:
        print("No matches.")
        return
    for i, item in enumerate(matches[:30], start=1):
        print(
            f"{i}. {item['customer_id']} | {item['display_name']} | "
            f"{item['type']} | {item['updated']} | {item['path']}"
        )
    if len(matches) > 30:
        print(f"... and {len(matches) - 30} more")


def score_by_keywords(text: str) -> dict[str, object]:
    """Heuristic intake scorer. It complements, not replaces, human review."""
    t = text.lower()

    identity_score = 0
    if re.search(r"(cust-\d{4}|org-\d{4}|anon-\d{4})", t):
        identity_score = 15
    elif PHONE_RE.search(text) or re.search(r"(手机后四位|微信|来源人|转介绍|来自|介绍)", text):
        identity_score = 10
    elif re.search(r"(先生|女士|老师|总)", text) and re.search(r"(孩子|父母|配偶|已婚|城市|杭州|上海|北京|职业|公司|来源|介绍)", text):
        identity_score = 10
    elif re.search(r"(先生|女士|老师|总|客户|朋友|同事|家人)", text):
        identity_score = 6
    elif re.search(r"(某个客户|一个客户|有人)", text):
        identity_score = 3

    business_score = 0
    if re.search(r"(保单|体检|健康告知|核保|理赔|拒赔|重疾|医疗险|寿险|意外险|预算|缴费|续保)", text):
        business_score = 20
    elif re.search(r"(保险|咨询|合作|知识库|方案|项目|转介绍|客户需求|需求)", text):
        business_score = 15
    elif re.search(r"(了解|问一下|看看|想知道|感兴趣)", text):
        business_score = 10
    elif re.search(r"(互动|点赞|寒暄|问候)", text):
        business_score = 5

    action_score = 0
    if re.search(r"(今天|明天|后天|下周|周一|周二|周三|周四|周五|周六|周日|晚上|上午|下午|截止|到期|必须|马上|尽快)", text) and re.search(r"(约|发|补|回|联系|确认|处理|提交|给|出)", text):
        action_score = 25
    elif re.search(r"(调整方案|出方案|方案大纲|报价|核对|整理|协助|复核)", text):
        action_score = 20
    elif re.search(r"(约时间|补资料|发资料|回访|跟进|建档|下次)", text):
        action_score = 15
    elif re.search(r"(回复|看看|了解|问问)", text):
        action_score = 10
    elif re.search(r"(背景|记录一下)", text):
        action_score = 5

    risk_score = 0
    if re.search(r"(投诉|纠纷|误导|法律|起诉|隐私|身份证|银行卡|病历|重大|必须保留证据)", text):
        risk_score = 25
    elif re.search(r"(拒赔|承诺|期限|缴费|退保|保全|完整保单号|手机号)", text):
        risk_score = 20
    elif re.search(r"(甲状腺|结节|既往症|住院|手术|体检异常|核保|理赔|病史)", text):
        risk_score = 15
    elif re.search(r"(预算压力|房贷|孩子|父母|家庭责任|收入|职业风险|顾虑)", text):
        risk_score = 10
    elif re.search(r"(担心|焦虑|不信任|犹豫)", text):
        risk_score = 5

    asset_score = 0
    if re.search(r"(复盘|案例|培训|方法论|流程|知识卡片|选题|团队经验)", text):
        asset_score = 15
    elif re.search(r"(异议|话术|常见问题|经验|可复用)", text):
        asset_score = 10
    elif re.search(r"(画像|家庭结构|孩子|父母|配偶|已婚|偏好|顾虑)", text):
        asset_score = 6
    elif re.search(r"(本次对话|当前对话)", text):
        asset_score = 3

    penalty = 0
    if re.search(r"(重复|已经记录|之前记过)", text):
        penalty += 10
    if re.search(r"(很久以前|去年随便聊|过期)", text):
        penalty += 10
    if re.search(r"(寒暄|闲聊|点赞)", text) and business_score <= 5:
        penalty += 15
    if identity_score <= 3 and business_score == 0:
        penalty += 20

    hard_triggers = []
    trigger_patterns = {
        "明确下一步动作/预约/补资料": r"(约时间|补资料|回访|下次|下周|周[一二三四五六日]|明天|今天|尽快|发.*方案|方案大纲)",
        "健康/核保/病历": r"(健康告知|体检|病历|既往症|住院|手术|结节|核保)",
        "理赔/投诉/纠纷": r"(理赔|拒赔|投诉|纠纷|误导|起诉)",
        "保单/缴费/续保/退保": r"(保单|缴费|续保|退保|保全)",
        "承诺/期限": r"(承诺|答应|保证|截止|到期)",
        "敏感信息": r"(身份证|银行卡|手机号|病历)",
        "转介绍/合作机会": r"(转介绍|介绍|合作|决策人)",
        "强烈情绪/购买意愿": r"(很焦虑|很生气|不信任|马上买|现在就买|强烈)",
    }
    for name, pattern in trigger_patterns.items():
        if re.search(pattern, text):
            hard_triggers.append(name)

    raw_score = identity_score + business_score + action_score + risk_score + asset_score
    score = max(0, min(100, raw_score - penalty))

    if score >= 75:
        level, route = "S", "immediate_process"
    elif score >= 55:
        level, route = "A", "pending_process"
    elif score >= 35:
        level, route = "B", "light_record"
    elif score >= 15:
        level, route = "C", "low_value_archive"
    else:
        level, route = "D", "discard_or_ignore"

    if hard_triggers and level in {"B", "C", "D"}:
        level, route = "A", "pending_process"

    return {
        "signal_score": score,
        "signal_level": level,
        "route": route,
        "dimensions": {
            "identity": identity_score,
            "business": business_score,
            "action": action_score,
            "risk": risk_score,
            "asset": asset_score,
            "penalty": penalty,
        },
        "hard_triggers": hard_triggers,
    }


def score_intake(text: str) -> None:
    result = score_by_keywords(text)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def scan_privacy(base: Path) -> list[dict[str, str]]:
    findings = []
    for path in md_files(base):
        text = path.read_text(encoding="utf-8", errors="ignore")
        labels = []
        if PHONE_RE.search(text):
            labels.append("手机号")
        if ID_CARD_RE.search(text):
            labels.append("身份证号")
        if BANK_CARD_RE.search(text):
            labels.append("银行卡号疑似")
        if POLICY_RE.search(text):
            labels.append("完整保单号疑似")
        if labels:
            findings.append({"path": str(path.relative_to(base)), "labels": "、".join(labels)})
    return findings


def duplicate_candidates(rows: list[dict[str, str]]) -> list[tuple[str, list[dict[str, str]]]]:
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        names = [r.get("display_name", "")]
        aliases = r.get("aliases", "")
        if aliases:
            names.extend([part.strip() for part in aliases.split(",") if part.strip()])
        for name_value in names:
            name = normalize(name_value)
            if name:
                groups[f"name_or_alias:{name}"].append(r)
    return [(k, v) for k, v in groups.items() if len(v) > 1]


def audit_library(base: Path) -> None:
    rows = build_index(base)
    missing_next_action = [r for r in rows if r["status"] == "active" and not r["next_action"]]
    missing_followup = [
        r
        for r in rows
        if r["status"] == "active" and r["stage"] in {"solution", "servicing"} and not r["next_followup_date"]
    ]
    low_completeness = [r for r in rows if r["status"] != "archived" and r["info_completeness"] in {"", "L0", "L1"}]
    duplicate_groups = duplicate_candidates(rows)
    privacy_findings = scan_privacy(base)

    intake_base = base / "00-入口池"
    pending_intakes = list(intake_base.glob("01-待处理/**/*.md")) if intake_base.exists() else []
    unmatched_intakes = list(intake_base.glob("02-待匹配/**/*.md")) if intake_base.exists() else []

    collab_base = base / "05-团队协同"
    review_tasks = list(collab_base.glob("03-待复核/**/*.md")) if collab_base.exists() else []

    report = [
        "# 客户库数据质量报告",
        "",
        "## 总览",
        "",
        f"- 客户档案数：{len(rows)}",
        f"- 活跃客户缺少下一步动作：{len(missing_next_action)}",
        f"- 方案/服务阶段缺少跟进日期：{len(missing_followup)}",
        f"- 信息完整度 L0/L1 或缺失：{len(low_completeness)}",
        f"- 待处理入口：{len(pending_intakes)}",
        f"- 待匹配入口：{len(unmatched_intakes)}",
        f"- 疑似重复客户组：{len(duplicate_groups)}",
        f"- 隐私风险文件：{len(privacy_findings)}",
        f"- 待复核协同任务：{len(review_tasks)}",
        "",
        "## 活跃客户缺少下一步动作",
    ]
    for r in missing_next_action[:50]:
        report.append(f"- {r['customer_id']} | {r['display_name']} | {r['path']}")

    report += ["", "## 方案/服务阶段缺少跟进日期"]
    for r in missing_followup[:50]:
        report.append(f"- {r['customer_id']} | {r['display_name']} | {r['stage']} | {r['path']}")

    report += ["", "## 信息完整度偏低"]
    for r in low_completeness[:50]:
        report.append(f"- {r['customer_id']} | {r['display_name']} | {r['info_completeness']} | {r['path']}")

    report += ["", "## 疑似重复客户"]
    for key, group in duplicate_groups[:50]:
        report.append(f"- {key}")
        for r in group:
            report.append(f"  - {r['customer_id']} | {r['display_name']} | {r['source']} | {r['path']}")

    report += ["", "## 隐私风险"]
    for item in privacy_findings[:50]:
        report.append(f"- {item['labels']} | {item['path']}")

    report += ["", "## 待匹配入口"]
    for p in unmatched_intakes[:50]:
        report.append(f"- {p.relative_to(base)}")

    report += ["", "## 待复核协同任务"]
    for p in review_tasks[:50]:
        report.append(f"- {p.relative_to(base)}")

    out = base / "90-索引与看板" / "数据质量报告.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"Wrote audit report: {out}")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init")
    p_init.add_argument("--base", required=True)

    p_index = sub.add_parser("index")
    p_index.add_argument("--base", required=True)

    p_find = sub.add_parser("find")
    p_find.add_argument("--base", required=True)
    p_find.add_argument("--query", required=True)

    p_audit = sub.add_parser("audit")
    p_audit.add_argument("--base", required=True)

    p_score = sub.add_parser("score-intake")
    group = p_score.add_mutually_exclusive_group(required=True)
    group.add_argument("--text")
    group.add_argument("--file")

    args = parser.parse_args()

    if args.command == "score-intake":
        text = args.text if args.text is not None else Path(args.file).read_text(encoding="utf-8", errors="ignore")
        score_intake(text)
        return

    base = Path(args.base).resolve()

    if args.command == "init":
        init_library(base)
    elif args.command == "index":
        write_index(base)
    elif args.command == "find":
        find_customer(base, args.query)
    elif args.command == "audit":
        audit_library(base)


if __name__ == "__main__":
    main()
