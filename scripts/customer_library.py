#!/usr/bin/env python3
"""Utilities for the customer-solution-library skill.

Commands:
  init         --base PATH
  index        --base PATH
  find         --base PATH --query TEXT
  audit        --base PATH
  analyze-customer --base PATH (--customer-id ID | --query TEXT)
  gaps         --base PATH (--customer-id ID | --query TEXT)
  product-match --base PATH (--product-id ID | --product-file PATH)
  dashboard    --base PATH
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
    "09-产品与机会/products",
    "09-产品与机会/matching",
    "10-客户洞察",
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
needs: []
risks: []
opportunities: []
concerns: []
product_fit: []
analysis_status: not_started
solution_status: not_ready
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

## 需求、风险与机会

## 下一步动作

## 重要记录索引

## 变更记录
"""


TEMPLATE_PRODUCT = """---
type: product_profile
product_id:
product_name:
business_line:
status: active
suitable_for: []
not_suitable_for: []
matching_signals: []
risk_signals: []
required_information: []
created: {today}
updated: {today}
---

# 产品/服务画像

## 一句话说明

## 适合谁

## 不适合谁

## 匹配信号

## 风险信号

## 需要的前置信息

## 推荐沟通方式
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


def as_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"[,，、;；]", text) if part.strip()]


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

    product_template = template_dir / "产品服务画像模板.md"
    if not product_template.exists():
        product_template.write_text(
            TEMPLATE_PRODUCT.format(today=date.today().isoformat()),
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
                "needs": scalar(fm.get("needs", "")),
                "risks": scalar(fm.get("risks", "")),
                "opportunities": scalar(fm.get("opportunities", "")),
                "concerns": scalar(fm.get("concerns", "")),
                "product_fit": scalar(fm.get("product_fit", "")),
                "analysis_status": scalar(fm.get("analysis_status", "")),
                "solution_status": scalar(fm.get("solution_status", "")),
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


def select_customer(base: Path, customer_id: str | None = None, query: str | None = None) -> dict[str, str]:
    rows = build_index(base)
    if customer_id:
        wanted = customer_id.strip().lower()
        matches = [r for r in rows if r["customer_id"].lower() == wanted]
    else:
        q = normalize(query or "")
        matches = [
            r
            for r in rows
            if q
            and (
                q in normalize(r.get("customer_id", ""))
                or q in normalize(r.get("display_name", ""))
                or q in normalize(r.get("aliases", ""))
                or q in normalize(r.get("path", ""))
            )
        ]
    if not matches:
        raise SystemExit("No matching customer profile.")
    if len(matches) > 1:
        print("Multiple matching customers. Please specify --customer-id:")
        for r in matches[:20]:
            print(f"- {r['customer_id']} | {r['display_name']} | {r['path']}")
        raise SystemExit(2)
    return matches[0]


def customer_documents(base: Path, row: dict[str, str]) -> list[tuple[Path, str]]:
    customer_id = row.get("customer_id", "")
    docs: list[tuple[Path, str]] = []
    profile_path = base / row["path"]
    if profile_path.exists():
        docs.append((profile_path, profile_path.read_text(encoding="utf-8", errors="ignore")))
    allowed_roots = {"01-客户档案", "02-客户事件流", "03-业务模块", "06-服务跟进"}
    if customer_id:
        for path in md_files(base):
            rel = str(path.relative_to(base))
            if rel == row["path"]:
                continue
            if not path.relative_to(base).parts or path.relative_to(base).parts[0] not in allowed_roots:
                continue
            if customer_id.lower() in rel.lower():
                docs.append((path, path.read_text(encoding="utf-8", errors="ignore")))
    return docs


def compact_evidence(text: str, patterns: list[str], limit: int = 5) -> list[str]:
    evidence: list[str] = []
    for line in text.splitlines():
        clean = line.strip(" -\t")
        if not clean or len(clean) < 4:
            continue
        if any(re.search(pattern, clean, re.IGNORECASE) for pattern in patterns):
            if clean not in evidence:
                evidence.append(clean[:160])
        if len(evidence) >= limit:
            break
    return evidence


def has_confirmed_signal(text: str, signal: str) -> bool:
    """Return true when a signal appears outside an obvious missing/pending context."""
    if not signal:
        return False
    pattern = re.escape(signal)
    for match in re.finditer(pattern, text, re.IGNORECASE):
        start = max(0, match.start() - 80)
        end = min(len(text), match.end() + 80)
        window = text[start:end]
        if re.search(r"(待补充|未提供|缺少|缺|需要补充|需要整理|待确认|未确认|补齐|补充|请客户提供)", window):
            continue
        return True
    return False


def has_confirmed_budget(text: str) -> bool:
    """Budget is confirmed only when an amount/range/preference is explicit, not just pressure."""
    if re.search(r"(预算|保费|缴费).{0,12}(\d+|一千|两千|三千|四千|五千|六千|七千|八千|九千|一万|两万|三万|上限|以内|左右|区间|每年|每月|年缴|月缴)", text):
        return True
    if re.search(r"(\d+|一千|两千|三千|四千|五千|一万|两万).{0,12}(预算|保费|缴费)", text):
        return True
    return False


def infer_customer_insights(text: str, row: dict[str, str]) -> dict[str, list[str]]:
    t = text.lower()
    needs = as_list(row.get("needs")) or []
    risks = as_list(row.get("risks")) or []
    opportunities = as_list(row.get("opportunities")) or []
    concerns = as_list(row.get("concerns")) or []

    def add(target: list[str], item: str) -> None:
        if item not in target:
            target.append(item)

    if re.search(r"(重疾|医疗险|寿险|意外险|保单|保障|保险)", text):
        add(needs, "保险保障规划")
    if re.search(r"(孩子|子女|父母|配偶|已婚|家庭|房贷|家庭责任)", text):
        add(needs, "家庭责任保障")
        add(opportunities, "家庭保障缺口分析")
    if re.search(r"(体检|结节|甲状腺|既往症|住院|手术|病历|健康告知|核保)", text):
        add(risks, "健康告知/核保不确定性")
    if re.search(r"(预算|缴费|保费|压力|贵|便宜|收入)", text):
        add(concerns, "预算与缴费压力")
    if re.search(r"(理赔|拒赔|投诉|纠纷)", text):
        add(risks, "理赔/纠纷处理风险")
    if re.search(r"(愿意转介绍|可以转介绍|继续介绍|渠道合作|合作机会|资源互换|机构合作)", text):
        add(opportunities, "转介绍/合作机会")
    if re.search(r"(知识库|ai|agent|自动化|工作流|系统)", t):
        add(needs, "AI/知识库工作流服务")
        add(opportunities, "知识服务或系统搭建机会")
    if re.search(r"(犹豫|担心|不信任|焦虑|怕|顾虑)", text):
        add(concerns, "信任或决策顾虑")

    return {
        "needs": needs,
        "risks": risks,
        "opportunities": opportunities,
        "concerns": concerns,
    }


def infer_information_gaps(text: str, row: dict[str, str]) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []

    def add(item: str, why: str, how: str, priority: str) -> None:
        if not any(g["信息项"] == item for g in gaps):
            gaps.append({"信息项": item, "为什么需要": why, "获取方式": how, "优先级": priority})

    if "insurance" in row.get("business_line", "") or re.search(r"(保险|保单|重疾|医疗险|核保)", text):
        if not any(has_confirmed_signal(text, item) for item in ["已有保单", "保单截图", "保障责任", "保额"]):
            add("已有保单", "判断保障缺口和重复配置", "请客户提供保单截图或保单整理表", "高")
        if re.search(r"(体检|结节|既往症|住院|手术|病历|核保)", text) and not any(
            has_confirmed_signal(text, item) for item in ["检查报告", "体检报告", "病历", "复查", "分级", "大小"]
        ):
            add("健康异常详情", "判断核保路径和沟通边界", "补充体检报告、病历或复查结果", "高")
        if not has_confirmed_budget(text) and not any(has_confirmed_signal(text, item) for item in ["年收入", "收入区间"]):
            add("预算/缴费承受能力", "判断方案是否可持续", "下次沟通确认预算区间和缴费偏好", "中")
        if not any(has_confirmed_signal(text, item) for item in ["家庭责任", "房贷", "孩子", "父母", "配偶", "收入来源"]):
            add("家庭责任与收入结构", "判断保障优先级", "补充家庭成员、负债、收入来源", "中")

    if "consulting" in row.get("business_line", "") or re.search(r"(咨询|项目|方案|交付|合作)", text):
        if not any(has_confirmed_signal(text, item) for item in ["目标", "期望", "要解决", "结果", "交付"]):
            add("明确目标", "判断服务范围和交付结果", "请客户描述理想结果和当前问题", "高")
        if not has_confirmed_budget(text) and not any(has_confirmed_signal(text, item) for item in ["报价", "费用区间", "投入上限"]):
            add("预算范围", "判断方案颗粒度和投入边界", "确认可接受预算或资源投入", "中")
        if not any(has_confirmed_signal(text, item) for item in ["决策人", "负责人", "老板", "团队", "审批"]):
            add("决策链条", "判断推进方式", "确认决策人、使用人和影响人", "中")

    if not row.get("next_action"):
        add("下一步动作", "避免客户进入无人跟进状态", "设定最小下一步动作和日期", "高")
    if row.get("info_completeness") in {"", "L0", "L1"}:
        add("基础客户信息", "当前信息不足以形成稳定判断", "补充来源、联系方式锚点、需求背景", "高")

    return gaps


def make_customer_conclusion(row: dict[str, str], insights: dict[str, list[str]], gaps: list[dict[str, str]]) -> str:
    needs = "、".join(insights.get("needs", [])[:2]) or "需求尚不明确"
    risks = "、".join(insights.get("risks", [])[:2]) or "暂未识别明显风险"
    high_gaps = [g["信息项"] for g in gaps if g.get("优先级") == "高"]
    if high_gaps:
        return (
            f"当前客户具备 {needs}，但仍缺少 {'、'.join(high_gaps[:3])}；"
            f"主要风险是 {risks}。建议先补齐关键资料，再进入方案或产品推荐。"
        )
    if row.get("info_completeness") in {"L4", "L5"}:
        return f"当前客户资料相对充分，可围绕 {needs} 进入方案复核；仍需关注 {risks}。"
    return f"当前客户已出现 {needs}，主要风险是 {risks}；建议继续补充信息并设置下一步跟进。"


def write_customer_analysis(base: Path, customer_id: str | None = None, query: str | None = None) -> None:
    row = select_customer(base, customer_id=customer_id, query=query)
    docs = customer_documents(base, row)
    full_text = "\n\n".join(text for _, text in docs)
    insights = infer_customer_insights(full_text, row)
    gaps = infer_information_gaps(full_text, row)
    evidence = {
        "needs": compact_evidence(full_text, [r"需求|想|了解|保障|保险|咨询|方案|项目|合作"]),
        "risks": compact_evidence(full_text, [r"风险|体检|结节|既往症|病历|核保|理赔|投诉|纠纷|预算|压力"]),
        "opportunities": compact_evidence(full_text, [r"机会|转介绍|合作|渠道|保单整理|缺口|复盘|案例"]),
        "concerns": compact_evidence(full_text, [r"担心|顾虑|犹豫|焦虑|不信任|压力|贵|怕"]),
        "actions": compact_evidence(full_text, [r"下一步|跟进|约|补|确认|周|明天|今天|尽快|方案"]),
    }
    conclusion = make_customer_conclusion(row, insights, gaps)
    out_dir = base / "04-方案与分析" / row["customer_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "客户深度分析.md"
    lines = [
        f"# 客户深度分析：{row['display_name'] or row['customer_id']}",
        "",
        "## 结论先行",
        "",
        conclusion,
        "",
        "> 本分析基于已有档案、事件流和业务模块生成。推断仅作辅助判断，不替代人工复核。",
        "",
        "## 当前状态",
        "",
        f"- 客户编号：{row['customer_id']}",
        f"- 客户类型：{row['customer_type']}",
        f"- 业务线：{row['business_line']}",
        f"- 阶段：{row['stage']}",
        f"- 信息完整度：{row['info_completeness']}",
        f"- 下一步动作：{row['next_action'] or '未设置'}",
        "",
        "## 关键需求",
    ]
    lines += [f"- {item}" for item in insights["needs"]] or ["- 暂未形成明确需求洞察"]
    lines += ["", "## 关键风险"]
    lines += [f"- {item}" for item in insights["risks"]] or ["- 暂未识别明显风险"]
    lines += ["", "## 潜在机会"]
    lines += [f"- {item}" for item in insights["opportunities"]] or ["- 暂未识别明显机会"]
    lines += ["", "## 关键顾虑"]
    lines += [f"- {item}" for item in insights["concerns"]] or ["- 暂未识别明显顾虑"]
    lines += ["", "## 信息缺口", "", "| 信息项 | 为什么需要 | 获取方式 | 优先级 |", "|---|---|---|---|"]
    lines += [f"| {g['信息项']} | {g['为什么需要']} | {g['获取方式']} | {g['优先级']} |" for g in gaps] or ["| 暂无 | 暂无明显缺口 | - | - |"]
    lines += ["", "## 证据摘录", "", "### 需求相关"]
    lines += [f"- {item}" for item in evidence["needs"]] or ["- 暂无直接摘录"]
    lines += ["", "### 风险相关"]
    lines += [f"- {item}" for item in evidence["risks"]] or ["- 暂无直接摘录"]
    lines += ["", "### 动作相关"]
    lines += [f"- {item}" for item in evidence["actions"]] or ["- 暂无直接摘录"]
    lines += [
        "",
        "## 下一步建议",
        "",
        "- 先补齐高优先级信息缺口。",
        "- 只在事实足够时生成客户可读版方案。",
        "- 涉及健康、理赔、法律、财务承诺时保守表达并人工复核。",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_insight_cards(base, row, insights, evidence)
    print(f"Wrote customer analysis: {out}")


def write_information_gaps(base: Path, customer_id: str | None = None, query: str | None = None) -> None:
    row = select_customer(base, customer_id=customer_id, query=query)
    docs = customer_documents(base, row)
    full_text = "\n\n".join(text for _, text in docs)
    gaps = infer_information_gaps(full_text, row)
    out_dir = base / "04-方案与分析" / row["customer_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "信息缺口清单.md"
    lines = [
        f"# 信息缺口清单：{row['display_name'] or row['customer_id']}",
        "",
        "| 信息项 | 为什么需要 | 获取方式 | 优先级 |",
        "|---|---|---|---|",
    ]
    lines += [f"| {g['信息项']} | {g['为什么需要']} | {g['获取方式']} | {g['优先级']} |" for g in gaps] or ["| 暂无 | 暂无明显缺口 | - | - |"]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote information gaps: {out}")


def write_insight_cards(base: Path, row: dict[str, str], insights: dict[str, list[str]], evidence: dict[str, list[str]]) -> None:
    out_dir = base / "10-客户洞察" / row["customer_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    type_map = {
        "needs": "需求洞察",
        "risks": "风险洞察",
        "opportunities": "机会洞察",
        "concerns": "顾虑洞察",
    }
    for key, label in type_map.items():
        for idx, conclusion in enumerate(insights.get(key, [])[:8], start=1):
            safe = re.sub(r"[^\w\u4e00-\u9fff-]+", "", conclusion)[:24] or label
            out = out_dir / f"INSIGHT-{today}-{label}-{idx}-{safe}.md"
            if out.exists():
                continue
            evidence_key = {
                "needs": "needs",
                "risks": "risks",
                "opportunities": "opportunities",
                "concerns": "concerns",
            }.get(key, "needs")
            evidence_items = evidence.get(evidence_key, [])
            lines = [
                "---",
                "type: customer_insight",
                f"customer_id: {row['customer_id']}",
                f"insight_type: {label}",
                f"confidence: medium",
                f"status: pending_review",
                f"created: {today}",
                "---",
                "",
                f"# {label}：{conclusion}",
                "",
                "## 洞察结论",
                "",
                conclusion,
                "",
                "## 证据",
            ]
            lines += [f"- {item}" for item in evidence_items] or ["- 待补充证据"]
            lines += ["", "## 建议动作", "", "- 人工复核后决定是否进入方案或跟进计划。"]
            out.write_text("\n".join(lines) + "\n", encoding="utf-8")


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


def load_product(base: Path, product_id: str | None = None, product_file: str | None = None) -> tuple[Path, dict[str, object], str]:
    if product_file:
        path = Path(product_file)
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        text = path.read_text(encoding="utf-8", errors="ignore")
        return path, extract_frontmatter(text), text
    wanted = (product_id or "").strip().lower()
    products_dir = base / "09-产品与机会" / "products"
    matches: list[tuple[Path, dict[str, object], str]] = []
    for path in products_dir.glob("*.md") if products_dir.exists() else []:
        text = path.read_text(encoding="utf-8", errors="ignore")
        fm = extract_frontmatter(text)
        haystack = normalize(
            scalar(fm.get("product_id", "")) + "\n" + scalar(fm.get("product_name", "")) + "\n" + path.name
        )
        if wanted and wanted in haystack:
            matches.append((path, fm, text))
    if not matches:
        raise SystemExit("No matching product profile. Create one under 09-产品与机会/products or pass --product-file.")
    if len(matches) > 1:
        print("Multiple matching products. Please specify --product-id or --product-file:")
        for path, fm, _ in matches[:20]:
            print(f"- {scalar(fm.get('product_id', ''))} | {scalar(fm.get('product_name', ''))} | {path}")
        raise SystemExit(2)
    return matches[0]


def score_product_match(customer_text: str, row: dict[str, str], product_fm: dict[str, object], product_text: str) -> dict[str, object]:
    signals = as_list(product_fm.get("matching_signals"))
    risks = as_list(product_fm.get("risk_signals"))
    suitable = as_list(product_fm.get("suitable_for"))
    not_suitable = as_list(product_fm.get("not_suitable_for"))
    required = as_list(product_fm.get("required_information"))
    haystack = normalize(customer_text + "\n" + json.dumps(row, ensure_ascii=False))

    matched_signals: list[str] = []
    risk_hits: list[str] = []
    negative_hits: list[str] = []
    missing_required: list[str] = []

    for item in signals + suitable:
        if item and normalize(item) in haystack:
            matched_signals.append(item)
    for item in risks:
        if item and normalize(item) in haystack:
            risk_hits.append(item)
    for item in not_suitable:
        if item and normalize(item) in haystack:
            negative_hits.append(item)
    for item in required:
        if item and not has_confirmed_signal(customer_text, item):
            missing_required.append(item)

    # Keyword fallback when product profile is still rough.
    product_haystack = product_text + "\n" + scalar(product_fm.get("product_name", ""))
    fallback_keywords = []
    if re.search(r"(重疾|医疗|保险|保单|保障)", product_haystack):
        fallback_keywords = ["保险", "保障", "重疾", "医疗险", "保单", "家庭责任", "孩子", "父母", "体检", "核保"]
    elif re.search(r"(知识库|ai|agent|自动化|系统|工作流)", product_haystack, re.IGNORECASE):
        fallback_keywords = ["知识库", "AI", "Agent", "自动化", "工作流", "系统", "文档"]
    for keyword in fallback_keywords:
        if normalize(keyword) in haystack and keyword not in matched_signals:
            matched_signals.append(keyword)

    completeness_bonus = {"L5": 15, "L4": 12, "L3": 8, "L2": 4, "L1": 1, "L0": 0}.get(row.get("info_completeness", ""), 0)
    stage_bonus = 10 if row.get("stage") in {"qualified", "analysis", "solution", "servicing"} else 0
    priority_bonus = {"A": 10, "B": 5, "C": 2}.get(row.get("priority", ""), 0)
    score = len(set(matched_signals)) * 10 + completeness_bonus + stage_bonus + priority_bonus
    score -= len(set(risk_hits)) * 8
    score -= len(set(negative_hits)) * 20
    score -= min(len(set(missing_required)) * 10, 35)
    score = max(0, min(100, score))

    if missing_required:
        score = min(score, 69)
    if len(set(risk_hits)) >= 2:
        score = min(score, 74)
    if negative_hits:
        score = min(score, 49)

    if score >= 75:
        level = "高匹配"
    elif score >= 50:
        level = "中匹配"
    elif score >= 25:
        level = "低匹配"
    else:
        level = "暂不匹配"

    return {
        "score": score,
        "level": level,
        "matched_signals": sorted(set(matched_signals)),
        "risk_hits": sorted(set(risk_hits)),
        "negative_hits": sorted(set(negative_hits)),
        "missing_required": sorted(set(missing_required)),
    }


def write_product_matches(base: Path, product_id: str | None = None, product_file: str | None = None) -> None:
    product_path, product_fm, product_text = load_product(base, product_id=product_id, product_file=product_file)
    product_name = scalar(product_fm.get("product_name", "")) or product_path.stem
    product_code = scalar(product_fm.get("product_id", "")) or product_path.stem
    rows = [r for r in build_index(base) if r.get("status") != "archived"]
    results = []
    for row in rows:
        docs = customer_documents(base, row)
        full_text = "\n\n".join(text for _, text in docs)
        match = score_product_match(full_text, row, product_fm, product_text)
        if match["score"] > 0:
            results.append((row, match))
    results.sort(key=lambda item: int(item[1]["score"]), reverse=True)
    out_dir = base / "09-产品与机会" / "matching"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{product_code}-潜在客户清单.md"
    lines = [
        f"# 产品潜在客户清单：{product_name}",
        "",
        f"- 产品编号：{product_code}",
        f"- 生成日期：{date.today().isoformat()}",
        "",
        "| 客户 | 匹配度 | 等级 | 匹配原因 | 风险点 | 缺口 | 建议动作 | 路径 |",
        "|---|---:|---|---|---|---|---|---|",
    ]
    for row, match in results[:100]:
        reasons = "、".join(match["matched_signals"]) or "待人工判断"
        risks = "、".join(match["risk_hits"] + match["negative_hits"]) or "-"
        gaps = "、".join(match["missing_required"]) or "-"
        action = "先补齐缺口后再沟通" if match["missing_required"] else "可进入人工复核和沟通准备"
        lines.append(
            f"| {row['customer_id']} {row['display_name']} | {match['score']} | {match['level']} | "
            f"{reasons} | {risks} | {gaps} | {action} | {row['path']} |"
        )
    if not results:
        lines.append("| 暂无 | 0 | 暂不匹配 | - | - | - | - | - |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote product match list: {out}")


def write_operation_dashboard(base: Path) -> None:
    rows = build_index(base)
    active = [r for r in rows if r.get("status") == "active"]
    missing_action = [r for r in active if not r.get("next_action")]
    high_value = [r for r in active if r.get("priority") in {"A", "B"} and r.get("info_completeness") in {"L3", "L4", "L5"}]
    low_info = [r for r in active if r.get("info_completeness") in {"", "L0", "L1"}]
    solution_ready = [r for r in active if r.get("info_completeness") in {"L4", "L5"} and r.get("solution_status") != "ready"]

    out = base / "90-索引与看板" / "本周经营看板.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 本周经营看板",
        "",
        f"- 生成日期：{date.today().isoformat()}",
        f"- 活跃客户：{len(active)}",
        f"- 缺下一步动作：{len(missing_action)}",
        f"- 高价值可经营客户：{len(high_value)}",
        f"- 信息不足客户：{len(low_info)}",
        f"- 可进入方案复核客户：{len(solution_ready)}",
        "",
        "## 本周优先跟进",
        "",
        "| 客户 | 阶段 | 完整度 | 优先级 | 下一步动作 | 路径 |",
        "|---|---|---|---|---|---|",
    ]
    prioritized = sorted(active, key=lambda r: (r.get("priority") != "A", r.get("next_followup_date") or "9999-99-99"))[:30]
    lines += [
        f"| {r['customer_id']} {r['display_name']} | {r['stage']} | {r['info_completeness']} | {r['priority']} | {r['next_action'] or '未设置'} | {r['path']} |"
        for r in prioritized
    ] or ["| 暂无 | - | - | - | - | - |"]
    lines += ["", "## 缺少下一步动作"]
    lines += [f"- {r['customer_id']} | {r['display_name']} | {r['path']}" for r in missing_action[:50]] or ["- 暂无"]
    lines += ["", "## 信息不足但仍活跃"]
    lines += [f"- {r['customer_id']} | {r['display_name']} | {r['info_completeness']} | {r['path']}" for r in low_info[:50]] or ["- 暂无"]
    lines += ["", "## 可进入深度分析/方案复核"]
    lines += [f"- {r['customer_id']} | {r['display_name']} | {r['info_completeness']} | {r['path']}" for r in solution_ready[:50]] or ["- 暂无"]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote operation dashboard: {out}")


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

    p_analyze = sub.add_parser("analyze-customer")
    p_analyze.add_argument("--base", required=True)
    analyze_group = p_analyze.add_mutually_exclusive_group(required=True)
    analyze_group.add_argument("--customer-id")
    analyze_group.add_argument("--query")

    p_gaps = sub.add_parser("gaps")
    p_gaps.add_argument("--base", required=True)
    gaps_group = p_gaps.add_mutually_exclusive_group(required=True)
    gaps_group.add_argument("--customer-id")
    gaps_group.add_argument("--query")

    p_match = sub.add_parser("product-match")
    p_match.add_argument("--base", required=True)
    product_group = p_match.add_mutually_exclusive_group(required=True)
    product_group.add_argument("--product-id")
    product_group.add_argument("--product-file")

    p_dashboard = sub.add_parser("dashboard")
    p_dashboard.add_argument("--base", required=True)

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
    elif args.command == "analyze-customer":
        write_customer_analysis(base, customer_id=args.customer_id, query=args.query)
    elif args.command == "gaps":
        write_information_gaps(base, customer_id=args.customer_id, query=args.query)
    elif args.command == "product-match":
        write_product_matches(base, product_id=args.product_id, product_file=args.product_file)
    elif args.command == "dashboard":
        write_operation_dashboard(base)


if __name__ == "__main__":
    main()
