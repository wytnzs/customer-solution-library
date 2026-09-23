#!/usr/bin/env python3
"""Utilities for the customer-solution-library skill.

Commands:
  init         [--base PATH]
  index        [--base PATH]
  find         [--base PATH] --query TEXT
  audit        [--base PATH] [--json]
  analyze-customer [--base PATH] (--customer-id ID | --query TEXT)
  gaps         [--base PATH] (--customer-id ID | --query TEXT)
  product-match [--base PATH] (--product-id ID | --product-file PATH)
  dashboard    [--base PATH] [--json]
  score-intake --text TEXT | --file PATH
  intake-pool  [--base PATH] [--json]
  capture      [--base PATH] --text TEXT | --file PATH [--apply] [--json]
  segment      [--base PATH] [--by DIM] [--json]
  set-status   [--base PATH] --customer-id ID --status active|dormant|archived [--reason TEXT] [--apply] [--json]
  merge        [--base PATH] --keep ID --absorb ID [--apply] [--json]

--json on dashboard/audit also prints a machine-readable summary to stdout.

For commands that operate on a customer library, pass --base explicitly,
set CUSTOMER_LIBRARY_BASE, or run interactively and enter the path.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
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
age_range:
income_range:
occupation:
city:
family_structure:
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
age_fit: []
income_fit: []
occupation_fit: []
city_fit: []
family_fit: []
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

    def parse_inline_list(raw: str) -> list[str]:
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [
            item.strip().strip('"').strip("'")
            for item in re.split(r"[,，、;；]", inner)
            if item.strip()
        ]

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
        elif value.startswith("[") and value.endswith("]"):
            data[key] = parse_inline_list(value)
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


def resolve_customer_library_path(base_arg: str | None, *, must_exist: bool = False) -> Path:
    """Resolve customer library path without assuming any OS-specific default."""
    raw = base_arg or os.environ.get("CUSTOMER_LIBRARY_BASE")
    if not raw and sys.stdin.isatty():
        prompt = "请输入私有客户库路径（例如 ~/CustomerSolutionLibrary-Private，或你的云盘/工作目录路径）："
        try:
            raw = input(prompt).strip()
        except EOFError:
            raw = None
    if not raw:
        raise SystemExit(
            "Missing customer library path. Pass --base <客户库路径>, "
            "or set CUSTOMER_LIBRARY_BASE, or run interactively and enter the path."
        )
    path = Path(raw).expanduser().resolve()
    if must_exist and not path.exists():
        raise SystemExit(f"Customer library path does not exist: {path}")
    return path


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
                "age_range": scalar(fm.get("age_range", "")),
                "income_range": scalar(fm.get("income_range", "")),
                "occupation": scalar(fm.get("occupation", "")),
                "city": scalar(fm.get("city", "")),
                "family_structure": scalar(fm.get("family_structure", "")),
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
        "| 显示名 | 编号 | 类型 | 业务线 | 状态 | 阶段 | 完整度 | 优先级 | 下步动作 | 更新日期 | 路径 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        md.append(
            "| {display_name} | {customer_id} | {customer_type} | {business_line} | {status} | "
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
    """Relevance-ranked search. A token matching customer_id/display_name/
    aliases/source ranks far above a hit deep in the body, so the top hits are
    the real people, not generated reports."""
    tokens = [t for t in normalize(query).split() if t]
    if not tokens:
        print("No matches.")
        return
    matches = []
    # Skip generated output roots so searches stay on source records.
    generated_roots = {"04-方案与分析", "10-客户洞察", "90-索引与看板"}
    for path in md_files(base):
        if any(part in generated_roots for part in path.parts):
            continue
        if "09-产品与机会" in path.parts and "matching" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        haystack = normalize(str(path.relative_to(base)) + "\n" + text)
        if not all(tok in haystack for tok in tokens):
            continue
        fm = extract_frontmatter(text)
        record_type = scalar(fm.get("type", ""))
        if record_type and record_type != "customer_profile":
            continue
        cid = normalize(scalar(fm.get("customer_id", "")))
        name = normalize(scalar(fm.get("display_name", "")))
        aliases = normalize(scalar(fm.get("aliases", "")))
        source = normalize(scalar(fm.get("source", "")))
        body = normalize(text)
        score = 2 if record_type == "customer_profile" else 0
        for tok in tokens:
            if tok in cid:
                score += 40
            if tok in name:
                score += 30
            if tok in aliases:
                score += 20
            if tok in source:
                score += 10
            if tok in body:
                score += 5
        matches.append(
            {
                "customer_id": scalar(fm.get("customer_id", "")),
                "display_name": scalar(fm.get("display_name", "")),
                "type": record_type,
                "updated": scalar(fm.get("updated", "")),
                "path": str(path.relative_to(base)),
                "score": score,
            }
        )
    matches.sort(key=lambda m: (-m["score"], m["customer_id"]))
    if not matches:
        print("No matches.")
        return
    for i, item in enumerate(matches[:30], start=1):
        print(
            f"{i}. [{item['score']}] {item['display_name']} | {item['customer_id']} | "
            f"{item['type']} | {item['updated']} | {item['path']}"
        )
    if len(matches) > 30:
        print(f"... and {len(matches) - 30} more")


FILTER_MISSING_KEYS = {
    "age_range", "income_range", "occupation", "city", "family_structure",
    "next_action", "next_followup_date",
}


def _demographic_summary(row: dict[str, str]) -> str:
    parts = [row.get(k) for k in ("age_range", "income_range", "occupation", "city", "family_structure")]
    return "·".join(p for p in parts if p)


def filter_customers(base: Path, args: argparse.Namespace) -> None:
    """Structured customer filter over the profile fields.

    AND across all given criteria; excludes archived unless --status overrides.
    --age/--income accept a bucket ("41-50") or a plain number that is bucketed
    (45 -> 41-50). Text fields (occupation/city/family) match as substring.
    --has-product/--no-product use text-level insurance-type detection, which is
    a coverage/interest signal, not proof of purchase. --missing flags profiles
    lacking a field (e.g. income_range) for follow-up triage.
    """
    rows = build_index(base)
    if args.status:
        rows = [r for r in rows if normalize(r.get("status", "")) == normalize(args.status)]
    else:
        rows = [r for r in rows if r.get("status") != "archived"]

    criteria: list[str] = []
    if args.status:
        criteria.append(f"状态:{args.status}")
    conditions: list[tuple[str, str, bool]] = []  # (field, value, numeric)
    for flag, field, label in (
        ("age", "age_range", "年龄区间"),
        ("income", "income_range", "收入区间"),
        ("occupation", "occupation", "职业"),
        ("city", "city", "城市"),
        ("family", "family_structure", "家庭结构"),
        ("stage", "stage", "阶段"),
        ("priority", "priority", "优先级"),
    ):
        value = (getattr(args, flag, "") or "").strip()
        if not value:
            continue
        numeric = field in ("age_range", "income_range")
        criteria.append(f"{label}:{value}")
        conditions.append((field, value, numeric))

    if args.missing:
        if args.missing not in FILTER_MISSING_KEYS:
            raise SystemExit(
                f"Unknown --missing key: {args.missing}. Use one of: {', '.join(sorted(FILTER_MISSING_KEYS))}"
            )
        criteria.append(f"缺省:{args.missing}")
    if args.has_product:
        criteria.append(f"涉及保险类型:{args.has_product}")
    if args.no_product:
        criteria.append(f"未涉及保险类型:{args.no_product}")

    if not criteria:
        raise SystemExit(
            "No filter criteria. Use any of: --age/--income/--occupation/--city/--family/"
            "--status/--stage/--priority/--has-product/--no-product/--missing."
        )

    text_cache: dict[str, str] = {}

    def customer_text(row: dict[str, str]) -> str:
        key = row["customer_id"]
        if key not in text_cache:
            text_cache[key] = "\n\n".join(t for _, t in customer_documents(base, row))
        return text_cache[key]

    matched: list[dict[str, str]] = []
    for row in rows:
        ok = True
        for field, value, numeric in conditions:
            rv = (row.get(field) or "").strip()
            if not rv:
                ok = False
                break
            if numeric:
                if re.fullmatch(r"\d{1,3}", value):
                    hit = normalize(rv) == normalize(_age_to_bucket(int(value)))
                elif re.fullmatch(r"\d+(?:\.\d+)?", value):
                    hit = normalize(rv) == normalize(_income_to_bucket(float(value)))
                else:
                    hit = normalize(rv) == normalize(value)
            else:
                hit = normalize(value) in normalize(rv)
            if not hit:
                ok = False
                break
        if not ok:
            continue
        if args.has_product and not insurance_type_mentioned(customer_text(row), args.has_product):
            continue
        if args.no_product and insurance_type_mentioned(customer_text(row), args.no_product):
            continue
        if args.missing and (row.get(args.missing) or "").strip():
            continue
        matched.append(row)

    priority_rank = {"A": 0, "B": 1, "C": 2, "": 3}
    matched.sort(key=lambda r: r.get("updated", ""), reverse=True)
    matched.sort(key=lambda r: priority_rank.get(r.get("priority", ""), 3))

    if args.json:
        payload = {
            "criteria": criteria,
            "count": len(matched),
            "customers": [
                {
                    "customer_id": row["customer_id"],
                    "display_name": row["display_name"],
                    "age_range": row.get("age_range", ""),
                    "income_range": row.get("income_range", ""),
                    "occupation": row.get("occupation", ""),
                    "city": row.get("city", ""),
                    "family_structure": row.get("family_structure", ""),
                    "stage": row.get("stage", ""),
                    "priority": row.get("priority", ""),
                    "info_completeness": row.get("info_completeness", ""),
                    "needs": row.get("needs", ""),
                    "risks": row.get("risks", ""),
                    "next_action": row.get("next_action", ""),
                    "updated": row.get("updated", ""),
                    "path": row["path"],
                }
                for row in matched
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    scope_label = "活跃客户" if not (args.status and normalize(args.status) == "archived") else "归档客户"
    print(f"客户筛选：{'，'.join(criteria)}（命中 {len(matched)} 个{scope_label}）")
    print("")
    print("| 显示名 | 编号 | 画像 | 阶段 | 优先级 | 需求 | 下步动作 | 路径 |")
    print("|---|---|---|---|---|---|---|---|")
    for row in matched:
        demog = _demographic_summary(row) or "未填画像"
        needs = "、".join(_split_field(row.get("needs", ""))) or "-"
        action = row.get("next_action") or "-"
        print(
            f"| {row['display_name']} | {row['customer_id']} | {demog} | "
            f"{row.get('stage') or '-'} | {row.get('priority') or '-'} | {needs} | {action} | {row['path']} |"
        )

    if args.detail:
        print("")
        for row in matched:
            docs = customer_documents(base, row)
            one_liner = _customer_one_liner(docs)
            needs = "、".join(_split_field(row.get("needs", ""))) or "-"
            risks = "、".join(_split_field(row.get("risks", ""))) or "-"
            print(f"## {row['display_name']}（{row['customer_id']}）")
            print(f"- 一句话画像：{one_liner or '待补充'}")
            print(f"- 已知需求：{needs}")
            print(f"- 风险点：{risks}")
            print(f"- 下步动作：{row.get('next_action') or '-'}")
            print(f"- 档案路径：{row['path']}")
            print("")


def select_customer(base: Path, customer_id: str | None = None, query: str | None = None) -> dict[str, str]:
    rows = build_index(base)
    if customer_id:
        wanted = customer_id.strip().lower()
        matches = [
            r
            for r in rows
            if r.get("customer_id", "").strip().lower() == wanted
            or r.get("display_name", "").strip().lower() == wanted
            or any(a.strip().lower() == wanted for a in _split_field(r.get("aliases", "")))
        ]
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


def strip_frontmatter(text: str) -> str:
    """Remove the YAML frontmatter block so evidence quotes stay on real content."""
    if not text.startswith("---"):
        return text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return text
    return parts[2].lstrip("\n")


def compact_evidence(text: str, patterns: list[str], limit: int = 5) -> list[str]:
    evidence: list[str] = []
    for line in text.splitlines():
        clean = line.strip(" -\t")
        if not clean or len(clean) < 4:
            continue
        if clean.startswith("#"):
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
    # Only treat a hit as "not confirmed" when the nearby context explicitly
    # marks the item as missing. Avoid bare 缺/补充 which appear inside common
    # words like 缺口 or 建议补充定期寿险.
    not_confirmed = re.compile(
        r"(待补充|未提供|尚缺|缺少|还未|未收到|待客户提供|待客户补充|需要补齐|需补充|"
        r"需要补充|请客户提供|请提供|请补充|待确认|未确认)"
    )
    for match in re.finditer(pattern, text, re.IGNORECASE):
        start = max(0, match.start() - 80)
        end = min(len(text), match.end() + 80)
        window = text[start:end]
        if not_confirmed.search(window):
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

    # Only treat as a consulting engagement when the business line says so or the
    # context names an explicit consulting/project delivery. Generic words such as
    # 方案/合作/咨询 appear in ordinary insurance contexts and would add wrong gaps.
    consulting_signal = re.compile(
        r"(咨询客户|咨询服务|咨询项目|咨询合同|咨询顾问|顾问咨询|项目制|按项目|"
        r"项目交付|交付物|服务协议|咨询费|顾问费|按次|按小时|按年服务|服务合同)"
    )
    if "consulting" in row.get("business_line", "") or consulting_signal.search(text):
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
    # Evidence quotes should come from the real body, not the YAML header.
    body_text = "\n\n".join(strip_frontmatter(text) for _, text in docs)
    evidence = {
        "needs": compact_evidence(body_text, [r"需求|想|了解|保障|保险|咨询|方案|项目|合作"]),
        "risks": compact_evidence(body_text, [r"风险|体检|结节|既往症|病历|核保|理赔|投诉|纠纷|预算|压力"]),
        "opportunities": compact_evidence(body_text, [r"机会|转介绍|合作|渠道|保单整理|缺口|复盘|案例"]),
        "concerns": compact_evidence(body_text, [r"担心|顾虑|犹豫|焦虑|不信任|压力|贵|怕"]),
        "actions": compact_evidence(body_text, [r"下一步|跟进|约|补|确认|周|明天|今天|尽快|方案"]),
    }
    conclusion = make_customer_conclusion(row, insights, gaps)
    out_dir = base / "04-方案与分析" / customer_stem(row)
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
    out_dir = base / "04-方案与分析" / customer_stem(row)
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
    out_dir = base / "10-客户洞察" / customer_stem(row)
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


INTAKE_BUCKETS = [
    ("01-待处理", "pending"),
    ("02-待匹配", "unmatched"),
    ("03-待确认", "confirm"),
]


def scan_intake_pool(base: Path, as_json: bool = False) -> None:
    """Score every entry sitting in the intake pool so积压入口 can be triaged
    in one pass instead of one score-intake call per file."""
    pool = base / "00-入口池"
    entries: list[dict[str, object]] = []
    for bucket_name, bucket_key in INTAKE_BUCKETS:
        bucket_dir = pool / bucket_name
        if not bucket_dir.exists():
            continue
        for path in sorted(bucket_dir.rglob("*.md")):
            text = path.read_text(encoding="utf-8", errors="ignore")
            result = score_by_keywords(text)
            fm = extract_frontmatter(text)
            entries.append(
                {
                    "intake_id": scalar(fm.get("intake_id", "")),
                    "bucket": bucket_key,
                    "bucket_name": bucket_name,
                    "file": str(path.relative_to(base)),
                    "score": int(result["signal_score"]),
                    "level": str(result["signal_level"]),
                    "route": str(result["route"]),
                    "hard_triggers": [str(t) for t in result["hard_triggers"]],
                }
            )
    entries.sort(key=lambda e: (-int(e["score"]), str(e["file"])))

    out = base / "90-索引与看板" / "入口评分汇总.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 入口池评分汇总",
        "",
        f"- 生成日期：{date.today().isoformat()}",
        f"- 待处理：{sum(1 for e in entries if e['bucket'] == 'pending')}",
        f"- 待匹配：{sum(1 for e in entries if e['bucket'] == 'unmatched')}",
        f"- 待确认：{sum(1 for e in entries if e['bucket'] == 'confirm')}",
        "",
        "| 文件 | 池 | 评分 | 级别 | 建议路由 | 硬触发 |",
        "|---|---|---|---|---|---|",
    ]
    lines += [
        f"| {e['file']} | {e['bucket_name']} | {e['score']} | {e['level']} | {e['route']} | "
        f"{'、'.join(e['hard_triggers']) or '-'} |"
        for e in entries
    ] or ["| 暂无入口 | - | - | - | - | - |"]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if as_json:
        print(
            json.dumps(
                {
                    "generated": date.today().isoformat(),
                    "counts": {
                        "pending": sum(1 for e in entries if e["bucket"] == "pending"),
                        "unmatched": sum(1 for e in entries if e["bucket"] == "unmatched"),
                        "confirm": sum(1 for e in entries if e["bucket"] == "confirm"),
                    },
                    "entries": entries,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"Wrote intake pool scoring: {out}")


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

    # 画像匹配（软信号）：产品声明 *_fit 适配画像，客户画像命中加分、偏离减分，
    # 客户画像缺省不奖不罚（容忍缺省）。明确不适合请用 not_suitable_for 硬信号。
    demographic_hits: list[str] = []
    demographic_mismatches: list[str] = []
    for fit_key, row_key in DEMOGRAPHIC_FIT.items():
        allowed = [normalize(x) for x in as_list(product_fm.get(fit_key)) if x]
        if not allowed:
            continue
        raw = (row.get(row_key) or "").strip()
        if not raw:
            continue
        label = DEMOGRAPHIC_FIELDS[row_key]
        if normalize(raw) in allowed:
            demographic_hits.append(label)
        else:
            demographic_mismatches.append(f"{label}：{raw}（产品适配{'、'.join(allowed)}）")

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
    score += len(demographic_hits) * 8
    score -= len(demographic_mismatches) * 8
    score -= len(set(risk_hits)) * 8
    score -= len(set(negative_hits)) * 20
    score -= min(len(set(missing_required)) * 10, 35)
    score = max(0, min(100, score))

    if missing_required:
        score = min(score, 69)
    if len(set(risk_hits)) >= 2:
        score = min(score, 74)
    if len(demographic_mismatches) >= 2:
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
        "demographic_hits": sorted(set(demographic_hits)),
        "demographic_mismatches": sorted(set(demographic_mismatches)),
    }


def _customer_one_liner(docs: list[tuple[Path, str]]) -> str:
    """Pull the 一句话画像 from the profile body. Accepts both inline
    (`- 一句话画像：...`) and section form (`## 一句话画像` followed by the
    sentence on the next line). Returns empty when absent."""
    for _, text in docs:
        lines = text.splitlines()
        for i, line in enumerate(lines):
            clean = line.strip(" #-*\t")
            if "一句话画像" not in clean:
                continue
            if "：" in clean:
                return clean.split("：", 1)[1].strip()[:60]
            # Section heading form: the sentence is the next non-empty line.
            for nxt in lines[i + 1 : i + 3]:
                candidate = nxt.strip(" #-*\t")
                if candidate and not candidate.startswith("|") and not candidate.startswith("#"):
                    return candidate[:60]
    return ""


def _demographic_line(match: dict[str, object]) -> str:
    """One-line rendering of demographic fit for a product match."""
    parts = []
    if match["demographic_hits"]:
        parts.append("画像匹配：" + "、".join(match["demographic_hits"]))
    if match["demographic_mismatches"]:
        parts.append("画像偏离：" + "；".join(match["demographic_mismatches"]))
    if not parts:
        parts.append("画像匹配：无适配约束")
    return "；".join(parts)


def write_product_matches(base: Path, product_id: str | None = None, product_file: str | None = None, detail: bool = False) -> None:
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
    lines.append("")
    lines.append("## 命中客户详情")
    lines.append("")
    lines.append("从名单到详情：每个命中客户的关键情况，便于直接进入沟通准备。")
    lines.append("")
    for row, match in results[:100]:
        docs = customer_documents(base, row)
        one_liner = _customer_one_liner(docs)
        stage_label = row.get("stage", "未设置")
        completeness = row.get("info_completeness", "-")
        needs = "、".join(_split_field(row.get("needs", ""))) or "-"
        gaps = "、".join(match["missing_required"]) or "-"
        risks = "、".join(match["risk_hits"] + match["negative_hits"]) or "-"
        action = "先补齐缺口后再沟通" if match["missing_required"] else "可进入人工复核和沟通准备"
        lines.append(f"### {row['customer_id']} {row['display_name']}（{stage_label} / {completeness}）")
        lines.append("")
        lines.append(f"- 一句话画像：{one_liner or '待补充'}")
        lines.append(f"- 已知需求：{needs}")
        lines.append(f"- 产品匹配原因：{'、'.join(match['matched_signals']) or '待人工判断'}")
        lines.append(f"- {_demographic_line(match)}")
        lines.append(f"- 风险点：{risks}")
        lines.append(f"- 信息缺口：{gaps}")
        lines.append(f"- 建议动作：{action}")
        lines.append(f"- 档案路径：{row['path']}")
        lines.append("")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote product match list: {out}")

    if detail:
        detail_out = out_dir / f"{product_code}-潜在客户详情.md"
        detail_lines = [
            f"# 产品潜在客户详情：{product_name}",
            "",
            f"- 产品编号：{product_code}",
            f"- 生成日期：{date.today().isoformat()}",
            "",
        ]
        for row, match in results[:100]:
            docs = customer_documents(base, row)
            profile_text = docs[0][1] if docs else ""
            body = strip_frontmatter(profile_text)
            one_liner = _customer_one_liner(docs)
            detail_lines.append(f"## {row['customer_id']} {row['display_name']}")
            detail_lines.append("")
            detail_lines.append(f"- 一句话画像：{one_liner or '待补充'}")
            detail_lines.append(f"- 阶段 / 完整度 / 优先级：{row.get('stage', '-')} / {row.get('info_completeness', '-')} / {row.get('priority', '-')}")
            detail_lines.append(f"- 匹配度：{match['score']}（{match['level']}）")
            detail_lines.append(f"- 匹配原因：{'、'.join(match['matched_signals']) or '待人工判断'}")
            detail_lines.append(f"- {_demographic_line(match)}")
            detail_lines.append(f"- 风险点：{'、'.join(match['risk_hits'] + match['negative_hits']) or '-'}")
            detail_lines.append(f"- 缺口：{'、'.join(match['missing_required']) or '-'}")
            detail_lines.append(f"- 建议动作：{'先补齐缺口后再沟通' if match['missing_required'] else '可进入人工复核和沟通准备'}")
            detail_lines.append(f"- 档案路径：{row['path']}")
            detail_lines.append("")
            detail_lines.append("```markdown")
            detail_lines.append(body.strip()[:600] if body.strip() else "（档案正文为空）")
            detail_lines.append("```")
            detail_lines.append("")
        detail_out.write_text("\n".join(detail_lines) + "\n", encoding="utf-8")
        print(f"Wrote product match detail: {detail_out}")


CITY_NAMES = [
    "北京", "上海", "广州", "深圳", "杭州", "南京", "苏州", "成都", "重庆", "武汉",
    "西安", "天津", "宁波", "温州", "青岛", "大连", "厦门", "长沙", "郑州", "济南",
    "福州", "合肥", "昆明", "哈尔滨", "沈阳", "无锡", "佛山", "东莞", "泉州", "福州",
]
FAMILY_TERMS = ["孩子", "儿子", "女儿", "父母", "父亲", "母亲", "配偶", "老公", "老婆", "已婚", "未婚", "单身", "二胎", "孙子", "孙女"]
OCCUPATION_TERMS = ["老师", "医生", "护士", "工程师", "公务员", "个体户", "老板", "企业主", "高管", "程序员", "教师", "会计", "律师", "创业者", "退休", "厂长"]
SOURCE_TERMS = ["转介绍", "朋友介绍", "客户介绍", "同事", "微信", "公众号", "小红书", "社群", "面谈", "展会", "邻居", "抖音"]
HONORIFIC_RE = re.compile(r"([一-龥]{1,3})(先生|女士|小姐|老师|经理|老板|姐姐|妹妹|哥哥|大姐|哥|姐)")
HONORIFIC_TAIL_RE = re.compile(r"(先生|女士|小姐|老师|经理|老板|姐姐|妹妹|哥哥|大姐|哥|姐)$")

# 完整姓名识别（私有客户库存真实姓名，不再用「姓氏-城市-客户」这类脱敏拼名）。
# 只在客户语境里识别，并用排除表挡掉形似姓名的常用词（险种、病症、财务、家庭、城市）。
COMMON_SURNAMES = set(
    "王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤"
)
COMPOUND_SURNAMES = ("欧阳", "司马", "上官", "诸葛", "令狐", "皇甫", "尉迟", "长孙", "慕容", "司徒", "端木")
NAME_TOKEN_SPLIT_RE = re.compile(r"[\s，,。、：:；;！!？?（）()【】\[\]“”\"'\n]+")
NAME_PREFIX_RE = re.compile(r"^([一-龥]{2,3})(转介绍|介绍|来电|咨询|想了解|想|说|问)")
NAME_CONTEXT_TERMS = (
    "保险", "重疾", "寿险", "年金", "医疗", "意外", "咨询", "了解", "想买", "投保",
    "转介绍", "客户", "保单", "保障", "理财",
)
NAME_STOPWORDS = {
    "高血压", "糖尿病", "重疾", "重疾险", "医疗", "医疗险", "意外", "意外险", "寿险", "年金", "年金险",
    "教育金", "养老金", "养老", "甲状腺", "乳腺", "结节", "肺结节", "癌症", "肿瘤", "手术", "住院",
    "体检", "医保", "社保", "公积金", "保单", "理赔", "核保", "保费", "保额", "合同", "条款", "免责",
    "投保", "续保", "退保", "预算", "收入", "支出", "储蓄", "理财", "基金", "股票", "房产", "车贷",
    "房贷", "孩子", "父母", "配偶", "朋友", "客户", "同事", "邻居", "家人", "家庭", "公司", "单位",
    "企业", "门店", "工厂", "学校", "医院", "银行", "杭州", "上海", "北京", "深圳", "广州", "成都",
    "武汉", "南京", "苏州", "西安", "天津", "重庆", "长沙", "青岛", "厦门", "宁波", "无锡", "佛山",
    "东莞", "合肥", "昆明", "济南", "福州", "大连", "沈阳", "郑州", "哈尔滨", "温州", "泉州", "石家庄",
}

# 画像维度：主档案中可聚合的画像字段，用于群体分析。
# age_range/income_range 用区间而非精确值，兼顾隐私与统计稳定。
DEMOGRAPHIC_FIELDS = {
    "age_range": "年龄区间",
    "income_range": "收入区间",
    "occupation": "职业",
    "city": "城市",
    "family_structure": "家庭结构",
}

# 产品画像的适配画像字段：product 侧的 *_fit 声明"这个产品适配哪些画像"，
# 客户的画像字段命中则加分、偏离则减分（软信号）。留空 = 不约束、不参与评分。
DEMOGRAPHIC_FIT = {
    "age_fit": "age_range",
    "income_fit": "income_range",
    "occupation_fit": "occupation",
    "city_fit": "city",
    "family_fit": "family_structure",
}

# 保险类型关键词：从档案文本（已有保单/需求/事件）识别客户涉及的保险类型，
# 用于反推代理人经营侧重。识别不代表投保确认，输出时需标注。
INSURANCE_TYPES = {
    "重疾险": ["重疾", "大病险"],
    "医疗险": ["医疗险", "百万医疗", "高端医疗", "住院医疗"],
    "寿险": ["寿险", "定期寿险", "终身寿险"],
    "意外险": ["意外险", "意外伤害"],
    "年金/储蓄": ["年金", "储蓄险", "增额寿", "养老年金", "教育金", "分红险"],
    "车险": ["车险", "交强险"],
    "少儿险": ["少儿险", "儿童险", "教育金"],
    "团险": ["团体险", "团险", "雇主责任险"],
}

AGE_RE = re.compile(r"(\d{1,3})\s*岁")
INCOME_RE = re.compile(
    r"(?P<period>年收入|月收入|年薪|月薪|收入)\s*[:：]?\s*(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>万|w)"
)


def _age_to_bucket(age: int) -> str:
    if age < 30:
        return "30以下"
    if age <= 40:
        return "31-40"
    if age <= 50:
        return "41-50"
    if age <= 60:
        return "51-60"
    return "61以上"


def _income_to_bucket(wan: float) -> str:
    if wan < 10:
        return "10万以下"
    if wan <= 20:
        return "10-20万"
    if wan <= 50:
        return "20-50万"
    return "50万以上"


def _derive_family_structure(family_terms: list[str]) -> str:
    """从家庭线索词推导结构化家庭结构。仅做保守归纳，未提到即不推断。"""
    has_kid = any(t in family_terms for t in ("孩子", "儿子", "女儿", "二胎", "孙子", "孙女"))
    married = any(t in family_terms for t in ("已婚", "配偶", "老公", "老婆", "夫妻"))
    if "单身" in family_terms or "未婚" in family_terms:
        return "单身"
    if married and has_kid:
        return "已婚有孩"
    if married:
        return "已婚无孩"
    if has_kid:
        return "有孩"
    return ""


def extract_demographics(text: str) -> dict[str, str]:
    """从原始描述中提取可结构化的画像字段（年龄区间/收入区间/职业/城市/家庭结构）。
    与身份锚点分离：锚点用于匹配，画像用于归档与群体统计。
    兼容「35岁」这类原始表述，也兼容档案里已持久化的「年龄区间：31-40」写法，
    因此对存量档案也能做覆盖判断。"""
    dem: dict[str, str] = {}
    age_m = AGE_RE.search(text)
    if age_m:
        dem["age_range"] = _age_to_bucket(int(age_m.group(1)))
    elif "age_range" not in dem:
        m = re.search(r"(?:年龄区间|age_range)\s*[:：]\s*([0-9一-鿿-]+)", text)
        if m:
            dem["age_range"] = m.group(1).strip()
    inc = INCOME_RE.search(text)
    if inc:
        num = float(inc.group("num"))
        wan = num * 12 if inc.group("period") in ("月收入", "月薪") else num
        dem["income_range"] = _income_to_bucket(wan)
    elif "income_range" not in dem:
        m = re.search(r"(?:收入区间|income_range)\s*[:：]\s*([0-9一-鿿-]+)", text)
        if m:
            dem["income_range"] = m.group(1).strip()
    occupations = [o for o in OCCUPATION_TERMS if o in text]
    if occupations:
        dem["occupation"] = occupations[0]
    cities = [c for c in CITY_NAMES if c in text]
    if cities:
        dem["city"] = cities[0]
    family_terms = [t for t in FAMILY_TERMS if t in text]
    derived = _derive_family_structure(family_terms)
    if derived:
        dem["family_structure"] = derived
    elif "family_structure" not in dem:
        m = re.search(r"(?:家庭结构|family_structure)\s*[:：]\s*(\S+)", text)
        if m:
            dem["family_structure"] = m.group(1).strip()
    return dem


def customer_insurance_types(text: str) -> list[str]:
    """识别客户档案文本涉及的保险类型，返回按字典序排好的类型标签。"""
    found = [label for label, keywords in INSURANCE_TYPES.items() if any(kw in text for kw in keywords)]
    return sorted(found)


def insurance_type_mentioned(text: str, query: str) -> bool:
    """客户档案文本是否提及某个保险类型。query 可传类型标签（重疾险/年金/储蓄）
    或关键词（重疾/年金），都归到对应类型后再做文本判断。识别不代表投保确认。"""
    q = normalize(query)
    hay = normalize(text)
    keywords: list[str] | None = None
    for label, type_keywords in INSURANCE_TYPES.items():
        if q == normalize(label) or any(q == normalize(kw) for kw in type_keywords):
            keywords = type_keywords + [label]
            break
    if keywords is None:
        return q in hay
    return any(normalize(kw) in hay for kw in keywords)


# 建议补充项清单：只提示高价值缺项，按优先级排序，非必填。
# field 是已知状态判断的 key，label 是展示名，hint 给用户具体的「知道就补」示例。
SUGGEST_FIELDS = [
    ("family_structure", "家庭结构", "高", "判断保障优先级和保额需求", "如：单身/已婚无孩/三口之家"),
    ("budget", "预算", "高", "判断方案可持续性和产品适配", "如：一年预算1万左右"),
    ("health", "健康情况", "高", "判断核保路径，避免推荐后卡核保", "如：有无结节/既往症/体检异常"),
    ("age", "年龄", "中", "判断年龄对应的费率和保障范围", "如：35岁"),
    ("income", "收入", "中", "判断缴费承受力和保额建议", "如：年收入20万"),
    ("occupation", "职业", "中", "判断职业风险类别与可投保产品", "如：教师/程序员/个体户"),
    ("city", "城市", "中", "判断异地核保和当地产品政策", "如：所在城市"),
    ("source", "来源", "低", "完善客户来源画像", "如：转介绍/社群/小红书"),
]
HEALTH_TERMS = ["体检", "结节", "既往症", "住院", "手术", "病历", "健康", "核保", "三高", "高血压", "糖尿病", "甲状腺"]


def missing_fill_fields(existing_text: str, fragment_text: str, row: dict[str, str] | None) -> list[dict[str, str]]:
    """算出客户信息里的高价值缺项，作为「可补充项」引导，不阻塞录入。

    existing_text：已有客户的全部档案文本（新建场景为空字符串）；
    fragment_text：本次原始描述；row：匹配到的已有客户索引行（新建为 None）。
    已知 = 档案/描述里出现该信号，或已有 frontmatter 字段非空。"""
    combined = (existing_text + "\n" + fragment_text) if existing_text else fragment_text
    dem = extract_demographics(combined)
    known = {
        "family_structure": bool(dem.get("family_structure")) or bool(row and row.get("family_structure")),
        "budget": has_confirmed_budget(combined),
        "health": any(t in combined for t in HEALTH_TERMS),
        "age": bool(dem.get("age_range")) or bool(row and row.get("age_range")),
        "income": bool(dem.get("income_range")) or bool(row and row.get("income_range")),
        "occupation": bool(dem.get("occupation")) or bool(row and row.get("occupation")),
        "city": bool(dem.get("city")) or bool(row and row.get("city")),
        "source": any(s in combined for s in SOURCE_TERMS)
        or bool(row and row.get("source") not in ("", "待确认")),
    }
    suggestions = [
        {
            "field": field,
            "label": label,
            "priority": priority,
            "why": why,
            "hint": hint,
        }
        for field, label, priority, why, hint in SUGGEST_FIELDS
        if not known[field]
    ]
    return suggestions


def _print_suggestions(suggestions: list[dict[str, str]]) -> None:
    prio_order = {"高": 0, "中": 1, "低": 2}
    print("\n【可补充项】知道以下信息可以随时补全（非必填，不确定可跳过）：")
    if not suggestions:
        print("  暂无明显缺项，信息已较完整。")
        return
    for s in sorted(suggestions, key=lambda s: (prio_order.get(s["priority"], 3), s["label"])):
        print(f"  {s['priority']} · {s['label']} —— {s['why']}（{s['hint']}）")
    print("  若当前不知道，可跳过；后续沟通中自然补上即可。")


def _looks_like_full_name(token: str) -> bool:
    """判断一个词是否像真实姓名：2-4 个汉字、以常见姓氏开头，且不是常用词或险种名。"""
    if not (2 <= len(token) <= 4) or not all("一" <= ch <= "龥" for ch in token):
        return False
    if token in NAME_STOPWORDS or any(term in token for term in NAME_STOPWORDS):
        return False
    if HONORIFIC_TAIL_RE.search(token):
        return False
    if token[:2] in COMPOUND_SURNAMES:
        return len(token) >= 3
    return token[0] in COMMON_SURNAMES


def extract_identity_anchors(text: str) -> dict[str, list[str]]:
    """Pull identity anchors out of a raw fragment. Anchors feed matching and
    the new-profile draft. This is the stable layer; semantic interpretation
    (needs/risks/opportunities) stays with the AI in the skill layer.

    `names` keeps every name form found — the full honorific term (张先生) and the
    real full name (张伟) — so both can be stored as aliases and re-matched later;
    `surnames` keeps the bare surname (张) for loose matching. The draft display
    name prefers the real full name, falling back to the honorific term."""
    anchors: dict[str, list[str]] = {
        "names": [], "surnames": [], "phones": [], "cities": [],
        "family": [], "occupations": [], "sources": [],
    }
    for m in HONORIFIC_RE.finditer(text):
        full = (m.group(1) + m.group(2)).strip()
        if full and full not in anchors["names"]:
            anchors["names"].append(full)
        surname = m.group(1).strip()
        if surname and surname not in anchors["surnames"]:
            anchors["surnames"].append(surname)
    # 完整姓名（张伟 / 张伟转介绍）：只在客户语境里识别，并挡掉形似姓名的常用词。
    if any(term in text for term in NAME_CONTEXT_TERMS):
        for raw in NAME_TOKEN_SPLIT_RE.split(text):
            candidate = raw.strip()
            if not candidate:
                continue
            if not _looks_like_full_name(candidate):
                prefix = NAME_PREFIX_RE.match(candidate)
                candidate = prefix.group(1) if prefix and _looks_like_full_name(prefix.group(1)) else ""
            if candidate and candidate not in anchors["names"]:
                anchors["names"].append(candidate)
            if candidate and candidate[0] not in anchors["surnames"]:
                anchors["surnames"].append(candidate[0])
    anchors["phones"] = PHONE_RE.findall(text)
    anchors["cities"] = [c for c in CITY_NAMES if c in text]
    anchors["family"] = [t for t in FAMILY_TERMS if t in text]
    anchors["occupations"] = [t for t in OCCUPATION_TERMS if t in text]
    anchors["sources"] = [t for t in SOURCE_TERMS if t in text]
    return anchors


def match_customer(base: Path, text: str, anchors: dict[str, list[str]]) -> tuple[dict[str, str] | None, int, list[str], bool]:
    """Find the best existing customer for a fragment. A customer matches when
    identity anchors overlap with the profile/docs. Follows the anti-merge rule:
    a name alone is not enough — require name + at least one other anchor, or a
    phone/contact hit, to suggest a merge. Returns
    (best_row, score, reasons, merged). best_row is the top candidate even when
    not merged, so the caller can surface a near-miss ("疑似命中但证据不足")
    instead of silently treating the fragment as a new customer."""
    rows = build_index(base)
    candidates: list[tuple[dict[str, str], int, list[str]]] = []
    for row in rows:
        if row.get("status") == "archived":
            continue
        docs = customer_documents(base, row)
        full_text = "\n\n".join(t for _, t in docs)
        score = 0
        reasons: list[str] = []
        # Phone is the strongest anchor when it actually appears in the archive.
        for ph in anchors["phones"]:
            if ph in full_text:
                score += 60
                reasons.append(f"联系方式匹配 {ph}")
        # Name/alias overlap. A full honorific term (张先生) present verbatim in
        # the profile's aliases/display_name is a strong anchor. A bare surname
        # (张) matching only as a prefix of the stored name is weak: it must be
        # backed by a secondary anchor before it can suggest a merge.
        full_hit = False
        for cand in anchors["names"]:
            nc = cand.lower()
            if nc and (nc in row.get("display_name", "").lower() or nc in row.get("aliases", "").lower()):
                score += 30
                full_hit = True
                reasons.append(f"称呼匹配 {cand}")
                break
        if not full_hit:
            for cand in anchors["surnames"]:
                nc = cand.lower()
                if not nc:
                    continue
                # Prefix match only: 张 matches 张伟, never 王张. Empty prefix
                # guard keeps a lone surname from becoming a merge by itself.
                if row.get("display_name", "").lower().startswith(nc) or any(
                    a.lower().startswith(nc) for a in scalar(row.get("aliases", "")).split(",")
                ):
                    score += 10
                    reasons.append(f"姓氏前缀 {cand}")
                    break
        for city in anchors["cities"]:
            if city in full_text:
                score += 10
                reasons.append(f"城市 {city}")
        for fam in anchors["family"]:
            if fam in full_text:
                score += 8
                reasons.append(f"家庭线索 {fam}")
        for src in anchors["sources"]:
            if src in full_text:
                score += 6
                reasons.append(f"来源 {src}")
        if score:
            candidates.append((row, score, reasons))
    candidates.sort(key=lambda t: -t[1])
    if not candidates:
        return None, 0, [], False
    best_row, best_score, best_reasons = candidates[0]
    # Phone hit alone, or name + any secondary anchor, is enough to suggest a merge.
    if best_score >= 60:
        return best_row, best_score, best_reasons, True
    if best_score >= 38 and any("称呼匹配" in r for r in best_reasons):
        return best_row, best_score, best_reasons, True
    return best_row, best_score, best_reasons, False


def next_customer_id(base: Path) -> str:
    max_num = 0
    for row in build_index(base):
        m = re.fullmatch(r"cust-(\d+)", row.get("customer_id", "").strip().lower())
        if m:
            max_num = max(max_num, int(m.group(1)))
    return f"CUST-{max_num + 1:04d}"


def customer_stem(row: dict[str, str]) -> str:
    """档案文件名（真实姓名）的 stem：事件流、分析输出等目录与主档案同名。"""
    stem = Path(row.get("path", "")).stem
    return stem or row.get("customer_id", "")


def unique_profile_stem(base: Path, display: str) -> str:
    """把显示名（真实姓名）转成可用的档案文件名；同名自动加 -2、-3 后缀。"""
    stem = re.sub(r'[\\/:*?"<>|\r\n\t]', "-", (display or "").strip()).strip(" .") or "待确认客户"
    candidate, n = stem, 2
    while (base / "01-客户档案" / f"{candidate}.md").exists() or (base / "02-客户事件流" / candidate).exists():
        candidate = f"{stem}-{n}"
        n += 1
    return candidate


def build_profile_draft(base: Path, anchors: dict[str, list[str]], text: str) -> tuple[str, dict[str, str]]:
    """Draft a new customer profile from a fragment. The script fills anchorable
    fields only; the AI fills semantic fields (needs/risks/opportunities) after
    review. Returns (file_text, metadata)."""
    cid = next_customer_id(base)
    today = date.today().isoformat()
    # 显示名用真实姓名：优先完整姓名（张伟），其次称呼（张先生），再退到姓氏或待确认。
    plain_names = [n for n in anchors["names"] if not HONORIFIC_TAIL_RE.search(n)]
    if plain_names:
        display = max(plain_names, key=len)
    elif anchors["names"]:
        display = max(anchors["names"], key=len)
    elif anchors["surnames"]:
        display = anchors["surnames"][0]
    else:
        display = f"待确认客户-{today}"
    # Alias stores the full honorific term so a later fragment can re-match it.
    alias_yaml = ", ".join(f'"{n}"' for n in anchors["names"]) if anchors["names"] else "[]"
    source = "、".join(anchors["sources"]) if anchors["sources"] else "待确认"
    completeness = "L1"
    if anchors["family"] or anchors["occupations"]:
        completeness = "L2"
    body = TEMPLATE_PROFILE.format(today=today)
    body = body.replace("customer_id:", f"customer_id: {cid}")
    body = body.replace("display_name:", f"display_name: {display}")
    body = body.replace("aliases: []", f"aliases: [{alias_yaml}]" if anchors["names"] else "aliases: []")
    body = body.replace("source:", f"source: {source}")
    body = body.replace("info_completeness: L0", f"info_completeness: {completeness}")
    # 画像字段写入 frontmatter：有明确表述才填，缺省留空（容忍缺省，兼容历史档案）。
    dem = extract_demographics(text)
    for key in DEMOGRAPHIC_FIELDS:
        value = dem.get(key, "")
        if value:
            body = body.replace(f"{key}:\n", f"{key}: {value}\n", 1)
    # Persist identity anchors into the body's 基础事实 section so later
    # fragments can match on secondary anchors (family/city/source), not just
    # the name. This is what makes the "already exists → update" loop work.
    fact_lines = [
        f"- 称呼：{'、'.join(anchors['names']) or '待确认'}",
        f"- 城市：{'、'.join(anchors['cities']) or '待确认'}",
        f"- 家庭：{'、'.join(anchors['family']) or '待确认'}",
        f"- 职业：{'、'.join(anchors['occupations']) or '待确认'}",
        f"- 来源：{'、'.join(anchors['sources']) or '待确认'}",
        f"- 年龄区间：{dem.get('age_range') or '待确认'}",
        f"- 收入区间：{dem.get('income_range') or '待确认'}",
    ]
    body = body.replace("## 基础事实\n\n", "## 基础事实\n\n" + "\n".join(fact_lines) + "\n", 1)
    return body, {"customer_id": cid, "display_name": display, "completeness": completeness}


def capture_customer(base: Path, text: str, apply: bool = False, as_json: bool = False) -> None:
    """Closed loop for a raw customer fragment: extract anchors, match against
    existing customers, then either draft a new profile or suggest field updates.
    With --apply, write the new profile (or an event record for an existing
    customer). Default is report-only so the AI/human can confirm first."""
    anchors = extract_identity_anchors(text)
    row, score, reasons, merged = match_customer(base, text, anchors)
    # 疑似命中但证据不足：只提到称呼、缺第二锚点。不自动并档（防误并档），
    # 但把候选暴露出来引导确认，避免「已有记录却静默新建」。
    near_miss = (
        not merged
        and row is not None
        and score >= 30
        and any("称呼匹配" in r for r in reasons)
    )
    use_candidate = merged or near_miss
    if use_candidate:
        existing_text = "\n\n".join(t for _, t in customer_documents(base, row))
    else:
        existing_text = ""
    suggestions = missing_fill_fields(existing_text, text, row if use_candidate else None)

    if as_json:
        payload: dict[str, object] = {
            "anchors": anchors,
            "match": None,
            "action": "create",
            "suggestions": suggestions,
        }
        if merged:
            payload["match"] = {
                "customer_id": row.get("customer_id", ""),
                "display_name": row.get("display_name", ""),
                "path": row.get("path", ""),
                "score": score,
                "reasons": reasons,
            }
            payload["action"] = "update"
        elif near_miss:
            payload["near_miss"] = {
                "customer_id": row.get("customer_id", ""),
                "display_name": row.get("display_name", ""),
                "path": row.get("path", ""),
                "score": score,
                "reasons": reasons,
            }
        if not merged:
            body, meta = build_profile_draft(base, anchors, text)
            stem = unique_profile_stem(base, meta["display_name"])
            payload["draft"] = {
                "customer_id": meta["customer_id"],
                "display_name": meta["display_name"],
                "path": f"01-客户档案/{stem}.md",
            }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        if apply:
            _capture_apply(base, text, anchors, row if merged else None)
        return

    print("=" * 60)
    print("抓取入档分析")
    print("=" * 60)
    print("\n【身份锚点】")
    if not any(anchors.values()):
        print("  未提取到明确身份锚点，身份待确认")
    else:
        print(f"  称呼: {'、'.join(anchors['names']) or '无'}")
        print(f"  城市: {'、'.join(anchors['cities']) or '无'}")
        print(f"  家庭: {'、'.join(anchors['family']) or '无'}")
        print(f"  职业: {'、'.join(anchors['occupations']) or '无'}")
        print(f"  来源: {'、'.join(anchors['sources']) or '无'}")
        if anchors["phones"]:
            print(f"  联系方式: {anchors['phones'][0]}")

    if merged:
        print(f"\n【匹配结果】命中已有客户（得分 {score}）")
        print(f"  {row['customer_id']} | {row['display_name']} | {row['path']}")
        if reasons:
            print(f"  依据: {'、'.join(reasons)}")
        print("\n【建议】本次为更新场景：")
        print("  1. 将描述中的新事实作为事件记录追加（--apply 落盘）；")
        print("  2. 语义字段（needs/risks/opportunities/next_action）由 AI 比对后更新主档案 frontmatter，不覆盖历史。")
        _print_suggestions(suggestions)
        if apply:
            _capture_apply(base, text, anchors, row)
        return

    if near_miss:
        print(f"\n【疑似命中】存在相近客户 {row['customer_id']} | {row['display_name']}（得分 {score}），但证据不足未自动并档。")
        print(f"  依据: {'、'.join(reasons)}")
        print("  如确认是同一人：补充一条锚点（城市/家庭/来源）后重新抓取，或人工确认并档；")
        print("  如不是同一人，忽略此提示继续新建。")

    print("\n【匹配结果】未命中已有客户 → 建议新建档案")
    body, meta = build_profile_draft(base, anchors, text)
    print(f"  拟用姓名: {meta['display_name']}")
    print(f"  拟建档文件: 01-客户档案/{unique_profile_stem(base, meta['display_name'])}.md")
    print(f"  内部编号: {meta['customer_id']}")
    print(f"  完整度初判: {meta['completeness']}")
    print("\n【结构化草稿】")
    print(body)
    print("【建议】确认草稿后运行 --apply 落盘；needs/risks/opportunities 由 AI 从描述中补充。")
    _print_suggestions(suggestions)
    if apply:
        _capture_apply(base, text, anchors, None)


def _capture_apply(base: Path, text: str, anchors: dict[str, list[str]], row: dict[str, str] | None) -> None:
    """Persist the capture result: write a new profile, or append an event
    record for an existing customer. Confirmations go to stderr so stdout stays
    clean for --json consumers."""
    if row:
        cid = row.get("customer_id", "")
        event_dir = base / "02-客户事件流" / customer_stem(row)
        event_dir.mkdir(parents=True, exist_ok=True)
        fname = f"{date.today().isoformat()}-抓取入档.md"
        path = event_dir / fname
        if path.exists():
            path = event_dir / f"{date.today().isoformat()}-抓取入档-{len(list(event_dir.glob('*-抓取入档*.md'))) + 1}.md"
        path.write_text(
            "---\n"
            f"type: customer_event\nevent_type: capture\ndate: {date.today().isoformat()}\n"
            f"customer_id: {cid}\n"
            "---\n\n"
            "# 抓取入档\n\n"
            "## 原始描述\n\n"
            f"{text}\n\n"
            "## 锚点\n\n"
            + "\n".join(f"- {k}: {'、'.join(v) or '无'}" for k, v in anchors.items())
            + "\n",
            encoding="utf-8",
        )
        print(f"Wrote event record: {path}", file=sys.stderr)
        return
    body, meta = build_profile_draft(base, anchors, text)
    profile_dir = base / "01-客户档案"
    profile_dir.mkdir(parents=True, exist_ok=True)
    path = profile_dir / f"{unique_profile_stem(base, meta['display_name'])}.md"
    path.write_text(body, encoding="utf-8")
    print(f"Wrote new profile: {path}", file=sys.stderr)


# ---------------------------------------------------------------- lifecycle

VALID_STATUS = ("active", "dormant", "archived")
COMPLETENESS_LEVELS = ("L0", "L1", "L2", "L3", "L4", "L5")
PRIORITY_RANK = {"A": 0, "B": 1, "C": 2}

# merge：并集字段（两份档案都可能是空值或列表）
LIST_MERGE_FIELDS = ("aliases", "tags", "needs", "risks", "opportunities", "concerns", "customer_type", "business_line")
# merge：保留档案缺省时用并入档案补全的标量（含画像字段）
SCALAR_FILL_FIELDS = ("age_range", "income_range", "occupation", "city", "family_structure", "source", "owner")


def _fmt_list(items: list[str]) -> str:
    if not items:
        return "[]"
    return "[" + ", ".join(f'"{x}"' if any(ch in x for ch in ",，、;；") else x for x in items) + "]"


def _set_frontmatter_fields(text: str, updates: dict[str, object]) -> str:
    """返回改写后的档案文本：仅替换/追加给定 frontmatter 字段，保留其余字段顺序与正文。
    新字段（如 merged_from/merged_into）追加到 frontmatter 末尾。"""
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("no YAML frontmatter")
    out: list[str] = []
    changed: set[str] = set()
    for line in parts[1].splitlines():
        stripped = line.strip()
        if stripped.startswith("-"):
            out.append(line)
            continue
        if ":" not in line:
            out.append(line)
            continue
        key = line.split(":", 1)[0].strip()
        if key in updates:
            val = updates[key]
            out.append(f"{key}: {_fmt_list([str(v) for v in val])}" if isinstance(val, list) else f"{key}: {val}")
            changed.add(key)
        else:
            out.append(line)
    for key, val in updates.items():
        if key not in changed:
            out.append(f"{key}: {_fmt_list([str(v) for v in val])}" if isinstance(val, list) else f"{key}: {val}")
    return parts[0] + "---" + "\n".join(out) + "---" + parts[2]


def _append_change_note(text: str, note: str) -> str:
    """把一条变更记录追加到「## 变更记录」小节；没有该小节则补建。"""
    marker = "## 变更记录"
    idx = text.find(marker)
    if idx == -1:
        return text.rstrip() + "\n\n## 变更记录\n\n- " + note + "\n"
    rest = text[idx:]
    next_heading = rest.find("\n## ")
    if next_heading != -1:
        section, tail = rest[:next_heading], rest[next_heading:]
    else:
        section, tail = rest, ""
    return text[:idx] + section + "\n" + note + tail


def set_customer_status(base: Path, customer_id: str, status: str, reason: str | None,
                        apply: bool = False, as_json: bool = False) -> None:
    """归档/唤醒/转入沉睡：改 frontmatter status 并记变更记录。默认仅预览，--apply 才落盘。"""
    status = status.strip().lower()
    if status not in VALID_STATUS:
        raise SystemExit(f"Invalid status: {status}. Use one of: active, dormant, archived.")
    row = select_customer(base, customer_id=customer_id)
    before = row.get("status", "") or "active"
    if status == before:
        raise SystemExit(f"{row['customer_id']} is already {status}; nothing to change.")
    path = base / row["path"]
    if not apply:
        if as_json:
            print(json.dumps({
                "customer_id": row["customer_id"], "display_name": row["display_name"],
                "before": before, "after": status, "reason": reason,
                "applied": False, "file": row["path"],
            }, ensure_ascii=False, indent=2))
        else:
            print(f"# 状态变更预览：{row['customer_id']} {row['display_name']}")
            print(f"- 当前状态：{before}")
            print(f"- 变更后：{status}")
            if reason:
                print(f"- 原因：{reason}")
            print(f"- 将更新 {row['path']} 的 status/updated，并追加一条变更记录。")
            print("执行需加 --apply。")
        return
    note = f"- {date.today().isoformat()}：状态变更 {before} → {status}" + (f"（{reason}）" if reason else "")
    new_text = _append_change_note(
        _set_frontmatter_fields(path.read_text(encoding="utf-8"), {"status": status, "updated": date.today().isoformat()}),
        note,
    )
    path.write_text(new_text, encoding="utf-8")
    if as_json:
        print(json.dumps({
            "customer_id": row["customer_id"], "display_name": row["display_name"],
            "before": before, "after": status, "reason": reason,
            "applied": True, "file": row["path"],
        }, ensure_ascii=False, indent=2))
    else:
        print(f"已变更 {row['customer_id']} 状态：{before} → {status}。", file=sys.stderr)


def merge_customers(base: Path, keep_id: str, absorb_id: str, apply: bool = False, as_json: bool = False) -> None:
    """用户确认两份档案是同一人后，把 absorb 并入 keep。默认仅预览，--apply 才落盘。

    并集：aliases/tags/needs/risks/opportunities/concerns/customer_type/business_line；
    补全：keep 缺省的画像/来源等标量用 absorb 补；信息完整度与优先级取较高者；
    事件流：02-客户事件流/<absorb>/ 文件迁入 <keep>/（重名加前缀，不覆盖）；
    归档：absorb 转 archived 并标 merged_into，正文全文追加进 keep（不丢内容）。
    """
    keep = select_customer(base, customer_id=keep_id)
    absorb = select_customer(base, customer_id=absorb_id)
    # 允许用真实姓名指定客户；落盘时统一换算回内部编号，保证 merged_from / merged_into 可对账。
    keep_id = keep["customer_id"]
    absorb_id = absorb["customer_id"]
    if keep_id == absorb_id:
        raise SystemExit(f"--keep and --absorb are the same customer: {keep_id}")
    keep_path = base / keep["path"]
    absorb_path = base / absorb["path"]
    keep_text = keep_path.read_text(encoding="utf-8")
    absorb_text = absorb_path.read_text(encoding="utf-8")
    absorb_merged_into = scalar(extract_frontmatter(absorb_text).get("merged_into", ""))
    if absorb_merged_into:
        raise SystemExit(f"{absorb_id} has already been merged into {absorb_merged_into}; nothing to do.")
    keep_fm = extract_frontmatter(keep_text)
    absorb_fm = extract_frontmatter(absorb_text)

    # ---- 计算合并后的 frontmatter ----
    merged: dict[str, object] = {}
    for f in LIST_MERGE_FIELDS:
        merged[f] = list(dict.fromkeys(as_list(keep_fm.get(f)) + as_list(absorb_fm.get(f))))
    for f in SCALAR_FILL_FIELDS:
        merged[f] = scalar(keep_fm.get(f, "")) or scalar(absorb_fm.get(f, ""))
    merged["info_completeness"] = max(
        (scalar(keep_fm.get("info_completeness", "")), scalar(absorb_fm.get("info_completeness", ""))),
        key=lambda x: COMPLETENESS_LEVELS.index(x) if x in COMPLETENESS_LEVELS else -1,
    )
    merged["priority"] = min(
        (scalar(keep_fm.get("priority", "")), scalar(absorb_fm.get("priority", ""))),
        key=lambda x: PRIORITY_RANK.get(x, 9),
    )
    merged["next_action"] = scalar(keep_fm.get("next_action", "")) or scalar(absorb_fm.get("next_action", ""))
    merged["next_followup_date"] = scalar(keep_fm.get("next_followup_date", "")) or scalar(absorb_fm.get("next_followup_date", ""))
    created = [c for c in (scalar(keep_fm.get("created", "")), scalar(absorb_fm.get("created", ""))) if c]
    merged["created"] = min(created) if created else date.today().isoformat()
    merged["updated"] = date.today().isoformat()
    merged_from = as_list(keep_fm.get("merged_from"))
    if absorb_id not in merged_from:
        merged_from.append(absorb_id)
    merged["merged_from"] = merged_from

    # ---- 预览 diff ----
    added_fields: list[tuple[str, list[str]]] = []
    for f in LIST_MERGE_FIELDS:
        existing = set(as_list(keep_fm.get(f)))
        added = [v for v in as_list(absorb_fm.get(f)) if v not in existing]
        if added:
            added_fields.append((f, added))
    filled_scalars: list[tuple[str, str]] = []
    for f in SCALAR_FILL_FIELDS:
        if not scalar(keep_fm.get(f, "")) and scalar(absorb_fm.get(f, "")):
            filled_scalars.append((f, scalar(absorb_fm.get(f, ""))))
    event_src = base / "02-客户事件流" / customer_stem(absorb)
    event_dst = base / "02-客户事件流" / customer_stem(keep)
    events = sorted(event_src.glob("*.md")) if event_src.exists() else []

    if not apply:
        if as_json:
            print(json.dumps({
                "keep": {"customer_id": keep_id, "display_name": keep["display_name"], "status": keep.get("status", "")},
                "absorb": {"customer_id": absorb_id, "display_name": absorb["display_name"], "status": absorb.get("status", "")},
                "applied": False,
                "add_fields": [{"field": f, "values": v} for f, v in added_fields],
                "fill_fields": [{"field": f, "value": v} for f, v in filled_scalars],
                "completeness": merged["info_completeness"],
                "priority": merged["priority"],
                "event_files_to_move": len(events),
                "absorb_becomes": "archived",
            }, ensure_ascii=False, indent=2))
        else:
            print(f"# 合并预览：{keep_id}（{keep['display_name']}）← {absorb_id}（{absorb['display_name']}）")
            print(f"- 保留档案状态：{keep.get('status', '')}；并入档案状态：{absorb.get('status', '')}")
            if added_fields:
                print("- 将并入字段：")
                for f, v in added_fields:
                    print(f"  - {f}: {'、'.join(v)}")
            if filled_scalars:
                print("- 将补全画像字段：")
                for f, v in filled_scalars:
                    print(f"  - {f}: {v}")
            print(f"- 信息完整度取较高者：{merged['info_completeness']}；优先级取较高者：{merged['priority']}")
            print(f"- 事件流迁移：{len(events)} 个文件 {absorb_id}/ → {keep_id}/")
            print(f"- 并入档案将转为 archived，并标记 merged_into: {keep_id}")
            print("- 正文：并入档案全文追加到保留档案末尾（不丢内容）。")
            print("执行需加 --apply。")
        return

    # ---- 落盘：keep 档案 ----
    keep_note = f"- {date.today().isoformat()}：并入 {absorb_id}（{absorb['display_name']}），字段并集合并、事件流迁移"
    keep_merged = _append_change_note(_set_frontmatter_fields(keep_text, merged), keep_note)
    absorb_body = strip_frontmatter(absorb_text).strip()
    keep_merged = keep_merged.rstrip() + f"\n\n## 并入档案：{absorb_id}（{absorb['display_name']}）\n\n{absorb_body}\n"
    keep_path.write_text(keep_merged, encoding="utf-8")

    # ---- 落盘：事件流迁移 ----
    moved: list[str] = []
    if events:
        event_dst.mkdir(parents=True, exist_ok=True)
        for ev in events:
            dest = event_dst / ev.name
            if dest.exists():
                dest = event_dst / f"{absorb_id}-{ev.name}"
            ev.rename(dest)
            moved.append(str(dest.relative_to(base)))

    # ---- 落盘：absorb 档案转 archived ----
    absorb_merged = _append_change_note(
        _set_frontmatter_fields(absorb_text, {
            "status": "archived",
            "merged_into": keep_id,
            "updated": date.today().isoformat(),
        }),
        f"- {date.today().isoformat()}：并入 {keep_id}（{keep['display_name']}），本档案转为 archived",
    )
    absorb_path.write_text(absorb_merged, encoding="utf-8")

    if as_json:
        print(json.dumps({
            "keep": keep_id, "absorb": absorb_id, "applied": True,
            "merged_into": keep_id, "absorb_status": "archived",
            "add_fields": [{"field": f, "values": v} for f, v in added_fields],
            "event_files_moved": moved,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"已合并：{absorb_id} → {keep_id}；{absorb_id} 已转为 archived。", file=sys.stderr)
        if moved:
            print(f"事件流迁移 {len(moved)} 个文件：{keep_id}/。", file=sys.stderr)


SEGMENT_DIMENSIONS = {
    "customer_type": "客户类型",
    "business_line": "业务线",
    "stage": "阶段",
    "info_completeness": "信息完整度",
    "priority": "优先级",
    "status": "状态",
}


def _split_field(value: str) -> list[str]:
    """Split a comma-joined index field into clean items (handles YAML lists)."""
    parts = []
    for chunk in value.split(","):
        chunk = chunk.strip().strip("[]").strip()
        if chunk:
            parts.append(chunk)
    return parts


def _typical_profile(members: list[dict[str, str]]) -> str:
    """从一组客户里取画像维度众数，拼成一行「典型画像」；容忍缺省，无数据返回 -。"""
    parts: list[str] = []
    for key in ("age_range", "city", "family_structure", "occupation", "income_range"):
        counts: dict[str, int] = defaultdict(int)
        for r in members:
            v = r.get(key, "").strip()
            if v:
                counts[v] += 1
        if counts:
            top = max(counts, key=lambda k: (counts[k], k))
            parts.append(top)
    return "·".join(parts) if parts else "-"


def _typical_profile_excluding(members: list[dict[str, str]], exclude_key: str | None) -> str:
    """取一组客户的典型画像，但跳过被钻取的维度（该维度已固定），
    其余维度取众数，回答「这个取值里到底是什么样的客户」。"""
    parts: list[str] = []
    for key in ("age_range", "city", "family_structure", "occupation", "income_range"):
        if key == exclude_key:
            continue
        counts: dict[str, int] = defaultdict(int)
        for r in members:
            v = r.get(key, "").strip()
            if v:
                counts[v] += 1
        if counts:
            parts.append(max(counts, key=lambda k: (counts[k], k)))
    return "·".join(parts) if parts else "-"


# segment --by 支持的单维度钻取：别名 -> (字段, 展示名)
DRILL_DIMENSIONS = {
    "age": ("age_range", "年龄区间"),
    "income": ("income_range", "收入区间"),
    "occupation": ("occupation", "职业"),
    "city": ("city", "城市"),
    "family": ("family_structure", "家庭结构"),
    "customer_type": ("customer_type", "客户类型"),
    "business_line": ("business_line", "业务线"),
    "stage": ("stage", "阶段"),
    "priority": ("priority", "优先级"),
    "status": ("status", "状态"),
    "info_completeness": ("info_completeness", "信息完整度"),
}


def segment_drill(base: Path, dim: str, as_json: bool = False) -> None:
    """按单个维度钻取客户群体：每个取值的客户数、覆盖率、客户清单与「该取值典型画像」。

    与 segment 的整体聚合互补：整体回答「群体集中在哪」，钻取回答「某个取值里到底
    是什么样的客户」。只输出到 stdout，不落盘（钻取是临时问答，不是周期产物）。
    """
    if dim not in DRILL_DIMENSIONS:
        raise SystemExit(
            f"Unknown --by dimension: {dim}. Use one of: {', '.join(sorted(DRILL_DIMENSIONS))}"
        )
    field, label = DRILL_DIMENSIONS[dim]
    rows = build_index(base)
    active = [r for r in rows if r.get("status") != "archived"]

    buckets: dict[str, list[dict[str, str]]] = defaultdict(list)
    unknown = 0
    for row in active:
        values = _split_field(row.get(field, ""))
        if not values:
            unknown += 1
            continue
        for value in values:
            buckets[value].append(row)
    ordered = sorted(buckets.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    exclude = field if field in DEMOGRAPHIC_FIELDS else None

    if as_json:
        payload = {
            "generated": date.today().isoformat(),
            "dimension": field,
            "label": label,
            "active": len(active),
            "unknown": unknown,
            "buckets": [
                {
                    "value": value,
                    "count": len(members),
                    "coverage": f"{round(len(members) / len(active) * 100)}%（{len(members)}/{len(active)}）",
                    "customers": [r["customer_id"] for r in members],
                    "typical": _typical_profile_excluding(members, exclude),
                }
                for value, members in ordered
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(f"# 客户群体钻取：{label}")
    print("")
    print(f"- 生成日期：{date.today().isoformat()}")
    print(f"- 活跃客户：{len(active)}")
    print(f"- 未填该维度：{unknown} 人（不计入分布）")
    print("")
    print("| 取值 | 客户数 | 覆盖率 | 客户 | 该取值典型画像 |")
    print("|---|---:|---|---|---|")
    for value, members in ordered:
        names = "、".join(f"{r['customer_id']}({r['display_name']})" for r in members[:10])
        if len(members) > 10:
            names += f" 等{len(members)}人"
        coverage = f"{round(len(members) / len(active) * 100)}%（{len(members)}/{len(active)}）"
        print(
            f"| {value} | {len(members)} | {coverage} | {names} | "
            f"{_typical_profile_excluding(members, exclude)} |"
        )
    if not ordered:
        print("| 暂无 | 0 | - | - | - |")


def segment_customers(base: Path, as_json: bool = False) -> None:
    """Aggregate the customer index across several dimensions and write a
    group-level picture: how many customers share each type/line/stage/
    completeness/priority, and which ones. Answers "客户群体分析" — the group
    view that single-customer analysis does not provide."""
    rows = build_index(base)
    active = [r for r in rows if r.get("status") != "archived"]

    groups: dict[str, dict[str, list[dict[str, str]]]] = {}
    for dim_key, dim_label in SEGMENT_DIMENSIONS.items():
        buckets: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in active:
            values = _split_field(row.get(dim_key, "")) or ["未设置"]
            for value in values:
                buckets[value].append(row)
        groups[dim_key] = dict(sorted(buckets.items(), key=lambda kv: -len(kv[1])))

    # 需求标签从 needs 字段聚合，与维度分开。
    needs_buckets: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in active:
        for value in _split_field(row.get("needs", "")):
            needs_buckets[value].append(row)
    needs_groups = dict(sorted(needs_buckets.items(), key=lambda kv: -len(kv[1])))

    # 主要客户画像：按画像字段聚合并取众数，回答「我的客户群体集中在哪」。
    profile_buckets: dict[str, dict[str, list[str]]] = {}
    for key in DEMOGRAPHIC_FIELDS:
        buckets: dict[str, list[str]] = defaultdict(list)
        for row in active:
            value = row.get(key, "").strip()
            if value:
                buckets[value].append(row["customer_id"])
        profile_buckets[key] = dict(sorted(buckets.items(), key=lambda kv: (-len(kv[1]), kv[0])))

    # 保险类型 × 客户画像：从档案文本识别客户涉及的保险类型，反推经营侧重。
    insurance_buckets: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in active:
        docs = customer_documents(base, row)
        full_text = "\n\n".join(t for _, t in docs)
        for itype in customer_insurance_types(full_text):
            insurance_buckets[itype].append(row)
    insurance_sorted = sorted(insurance_buckets.items(), key=lambda kv: (-len(kv[1]), kv[0]))

    out = base / "90-索引与看板" / "客户群体分析.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    lines = [
        "# 客户群体分析",
        "",
        f"- 生成日期：{today}",
        f"- 活跃客户：{len(active)}",
        f"- 归档客户：{len(rows) - len(active)}",
        "",
    ]
    for dim_key, dim_label in SEGMENT_DIMENSIONS.items():
        lines.append(f"## 按{dim_label}分组")
        lines.append("")
        lines.append("| 分组 | 数量 | 客户 |")
        lines.append("|---|---:|---|")
        buckets = groups[dim_key]
        if not buckets:
            lines.append("| 暂无 | 0 | - |")
        for value, members in buckets.items():
            names = "、".join(f"{r['customer_id']}({r['display_name']})" for r in members[:12])
            if len(members) > 12:
                names += f" 等{len(members)}人"
            lines.append(f"| {value} | {len(members)} | {names} |")
        lines.append("")

    lines.append("## 按需求标签分组")
    lines.append("")
    lines.append("| 需求 | 数量 | 客户 |")
    lines.append("|---|---:|---|")
    if not needs_groups:
        lines.append("| 暂无 | 0 | - |")
    for value, members in needs_groups.items():
        names = "、".join(f"{r['customer_id']}({r['display_name']})" for r in members[:12])
        if len(members) > 12:
            names += f" 等{len(members)}人"
        lines.append(f"| {value} | {len(members)} | {names} |")
        lines.append("")

    # 主要客户画像：众数 + 覆盖率 + 分布。未填字段的客户不计入该维度。
    lines.append("## 主要客户画像")
    lines.append("")
    lines.append("> 基于已结构化画像字段统计；未填字段的客户不计入该维度，数据不全时结论仅供参考。")
    lines.append("")
    lines.append("| 维度 | 主要取值 | 覆盖客户 | 覆盖率 | 分布 |")
    lines.append("|---|---|---:|---|---|")
    for key, label in DEMOGRAPHIC_FIELDS.items():
        buckets = profile_buckets[key]
        known = sum(len(v) for v in buckets.values())
        if not buckets:
            lines.append(f"| {label} | 暂无画像数据 | 0 | 0%（0/{len(active)}） | - |")
            continue
        top_value, top_members = next(iter(buckets.items()))
        coverage = f"{round(known / len(active) * 100)}%（{known}/{len(active)}）"
        dist = "、".join(f"{value}:{len(m)}" for value, m in buckets.items())
        lines.append(f"| {label} | {top_value}（{len(top_members)}人） | {known} | {coverage} | {dist} |")
    lines.append("")

    # 保险类型 × 客户画像：反推代理人经营侧重。
    lines.append("## 保险类型 × 客户画像（反推经营侧重）")
    lines.append("")
    lines.append("> 基于档案文本（已有保单/需求/事件）识别客户涉及的保险类型，不构成投保确认；用于反推经营侧重，需人工复核。")
    lines.append("")
    lines.append("| 保险类型 | 客户数 | 涉及客户 | 典型画像 |")
    lines.append("|---|---:|---|---|")
    if not insurance_sorted:
        lines.append("| 暂无识别 | 0 | - | - |")
    for itype, members in insurance_sorted:
        names = "、".join(f"{r['customer_id']}({r['display_name']})" for r in members[:10])
        if len(members) > 10:
            names += f" 等{len(members)}人"
        lines.append(f"| {itype} | {len(members)} | {names} | {_typical_profile(members)} |")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if as_json:
        payload = {
            "generated": today,
            "active": len(active),
            "archived": len(rows) - len(active),
            "dimensions": {dim_key: {k: [r["customer_id"] for r in v] for k, v in groups[dim_key].items()} for dim_key in SEGMENT_DIMENSIONS},
            "needs": {k: [r["customer_id"] for r in v] for k, v in needs_groups.items()},
            "profile": {
                key: {
                    "label": DEMOGRAPHIC_FIELDS[key],
                    "top": {
                        "value": next(iter(profile_buckets[key])) if profile_buckets[key] else None,
                        "count": len(next(iter(profile_buckets[key].values()))) if profile_buckets[key] else 0,
                    },
                    "known": sum(len(v) for v in profile_buckets[key].values()),
                    "total": len(active),
                    "distribution": profile_buckets[key],
                }
                for key in DEMOGRAPHIC_FIELDS
            },
            "insurance_types": {itype: [r["customer_id"] for r in members] for itype, members in insurance_sorted},
            "insurance_cross": [
                {
                    "type": itype,
                    "count": len(members),
                    "customers": [r["customer_id"] for r in members],
                    "typical": _typical_profile(members),
                }
                for itype, members in insurance_sorted
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Wrote customer segment analysis: {out}")


def days_overdue(d: str, today: date) -> int:
    """Whole days the follow-up is late; 0 when unparsable or not yet due."""
    if not d:
        return 0
    try:
        due = date.fromisoformat(d)
    except ValueError:
        return 0
    return max(0, (today - due).days)


def overdue_followups(rows: list[dict[str, str]], today: date | None = None) -> list[dict[str, str]]:
    """Active customers whose next_followup_date has passed and no action was taken."""
    today = today or date.today()
    overdue = [r for r in rows if r.get("status") == "active" and r.get("next_followup_date")]
    overdue = [r for r in overdue if r["next_followup_date"] < today.isoformat()]
    return sorted(overdue, key=lambda r: r["next_followup_date"])


def write_operation_dashboard(base: Path, as_json: bool = False) -> None:
    rows = build_index(base)
    today = date.today()
    active = [r for r in rows if r.get("status") == "active"]
    missing_action = [r for r in active if not r.get("next_action")]
    high_value = [r for r in active if r.get("priority") in {"A", "B"} and r.get("info_completeness") in {"L3", "L4", "L5"}]
    low_info = [r for r in active if r.get("info_completeness") in {"", "L0", "L1"}]
    solution_ready = [r for r in active if r.get("info_completeness") in {"L4", "L5"} and r.get("solution_status") != "ready"]
    overdue = overdue_followups(rows, today)

    out = base / "90-索引与看板" / "本周经营看板.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 本周经营看板",
        "",
        f"- 生成日期：{today.isoformat()}",
        f"- 活跃客户：{len(active)}",
        f"- 逾期未跟进：{len(overdue)}",
        f"- 缺下一步动作：{len(missing_action)}",
        f"- 高价值可经营客户：{len(high_value)}",
        f"- 信息不足客户：{len(low_info)}",
        f"- 可进入方案复核客户：{len(solution_ready)}",
        "",
        "## 逾期未跟进",
        "",
        "| 客户 | 阶段 | 完整度 | 优先级 | 应跟进日期 | 逾期天数 | 下一步动作 | 路径 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    lines += [
        f"| {r['customer_id']} {r['display_name']} | {r['stage']} | {r['info_completeness']} | {r['priority']} | "
        f"{r['next_followup_date']} | {days_overdue(r['next_followup_date'], today)} 天 | {r['next_action'] or '未设置'} | {r['path']} |"
        for r in overdue
    ] or ["| 暂无 | - | - | - | - | - | - | - |"]
    lines += ["", "## 本周优先跟进"]
    lines += ["", "| 客户 | 阶段 | 完整度 | 优先级 | 下一步动作 | 路径 |", "|---|---|---|---|---|---|"]
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
    if as_json:
        print(json.dumps({
            "generated": today.isoformat(),
            "counts": {
                "active": len(active),
                "overdue": len(overdue),
                "missing_action": len(missing_action),
                "high_value": len(high_value),
                "low_info": len(low_info),
                "solution_ready": len(solution_ready),
            },
            "overdue": [
                {
                    "customer_id": r["customer_id"],
                    "display_name": r["display_name"],
                    "next_followup_date": r["next_followup_date"],
                    "days_overdue": days_overdue(r["next_followup_date"], today),
                    "next_action": r["next_action"] or "",
                    "path": r["path"],
                }
                for r in overdue
            ],
            "missing_action": [{"customer_id": r["customer_id"], "display_name": r["display_name"], "path": r["path"]} for r in missing_action[:50]],
            "low_info": [{"customer_id": r["customer_id"], "display_name": r["display_name"], "info_completeness": r["info_completeness"], "path": r["path"]} for r in low_info[:50]],
            "solution_ready": [{"customer_id": r["customer_id"], "display_name": r["display_name"], "info_completeness": r["info_completeness"], "path": r["path"]} for r in solution_ready[:50]],
        }, ensure_ascii=False, indent=2))
    if not as_json:
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


def audit_library(base: Path, as_json: bool = False) -> None:
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

    overdue = overdue_followups(rows)
    today = date.today()

    report = [
        "# 客户库数据质量报告",
        "",
        "## 总览",
        "",
        f"- 客户档案数：{len(rows)}",
        f"- 逾期未跟进：{len(overdue)}",
        f"- 活跃客户缺少下一步动作：{len(missing_next_action)}",
        f"- 方案/服务阶段缺少跟进日期：{len(missing_followup)}",
        f"- 信息完整度 L0/L1 或缺失：{len(low_completeness)}",
        f"- 待处理入口：{len(pending_intakes)}",
        f"- 待匹配入口：{len(unmatched_intakes)}",
        f"- 疑似重复客户组：{len(duplicate_groups)}",
        f"- 隐私风险文件：{len(privacy_findings)}",
        f"- 待复核协同任务：{len(review_tasks)}",
        "",
        "## 逾期未跟进",
    ]
    for r in overdue[:50]:
        report.append(
            f"- {r['customer_id']} | {r['display_name']} | 应跟进 {r['next_followup_date']} | "
            f"已逾期 {days_overdue(r['next_followup_date'], today)} 天 | {r['next_action'] or '未设置'} | {r['path']}"
        )

    report += ["", "## 活跃客户缺少下一步动作"]
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
    if as_json:
        print(json.dumps({
            "generated": today.isoformat(),
            "counts": {
                "profiles": len(rows),
                "overdue": len(overdue),
                "missing_next_action": len(missing_next_action),
                "missing_followup": len(missing_followup),
                "low_completeness": len(low_completeness),
                "pending_intakes": len(pending_intakes),
                "unmatched_intakes": len(unmatched_intakes),
                "duplicate_groups": len(duplicate_groups),
                "privacy_risks": len(privacy_findings),
                "review_tasks": len(review_tasks),
            },
            "overdue": [
                {
                    "customer_id": r["customer_id"],
                    "display_name": r["display_name"],
                    "next_followup_date": r["next_followup_date"],
                    "days_overdue": days_overdue(r["next_followup_date"], today),
                    "path": r["path"],
                }
                for r in overdue[:50]
            ],
            "privacy_risks": privacy_findings[:50],
            "duplicate_groups": [
                {"key": key, "members": [{"customer_id": r["customer_id"], "display_name": r["display_name"], "path": r["path"]} for r in group]}
                for key, group in duplicate_groups[:50]
            ],
        }, ensure_ascii=False, indent=2))
    if not as_json:
        print(f"Wrote audit report: {out}")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init")
    p_init.add_argument("--base")

    p_index = sub.add_parser("index")
    p_index.add_argument("--base")

    p_find = sub.add_parser("find")
    p_find.add_argument("--base")
    p_find.add_argument("--query", required=True)

    p_filter = sub.add_parser("filter")
    p_filter.add_argument("--base")
    p_filter.add_argument("--age", help="年龄区间（41-50）或年龄数字（45 自动归桶）")
    p_filter.add_argument("--income", help="收入区间（50万以上）或月/年收入数字（自动折算归桶）")
    p_filter.add_argument("--occupation")
    p_filter.add_argument("--city")
    p_filter.add_argument("--family")
    p_filter.add_argument("--status")
    p_filter.add_argument("--stage")
    p_filter.add_argument("--priority")
    p_filter.add_argument("--has-product", help="档案涉及该保险类型（识别不代表投保确认）")
    p_filter.add_argument("--no-product", help="档案未涉及该保险类型（初筛用，需人工复核）")
    p_filter.add_argument("--missing", help="缺省该字段的客户（如 income_range/next_action）")
    p_filter.add_argument("--detail", action="store_true", help="额外打印每个命中客户的一句话画像与下步动作")
    p_filter.add_argument("--json", action="store_true", help="向 stdout 输出纯 JSON 结果")

    p_audit = sub.add_parser("audit")
    p_audit.add_argument("--base")
    p_audit.add_argument("--json", action="store_true", help="同时向 stdout 输出 JSON 汇总，便于脚本/工具消费")

    p_analyze = sub.add_parser("analyze-customer")
    p_analyze.add_argument("--base")
    analyze_group = p_analyze.add_mutually_exclusive_group(required=True)
    analyze_group.add_argument("--customer-id")
    analyze_group.add_argument("--query")

    p_gaps = sub.add_parser("gaps")
    p_gaps.add_argument("--base")
    gaps_group = p_gaps.add_mutually_exclusive_group(required=True)
    gaps_group.add_argument("--customer-id")
    gaps_group.add_argument("--query")

    p_match = sub.add_parser("product-match")
    p_match.add_argument("--base")
    product_group = p_match.add_mutually_exclusive_group(required=True)
    product_group.add_argument("--product-id")
    product_group.add_argument("--product-file")
    p_match.add_argument("--detail", action="store_true", help="额外生成每个命中客户的完整详情文件")

    p_dashboard = sub.add_parser("dashboard")
    p_dashboard.add_argument("--base")
    p_dashboard.add_argument("--json", action="store_true", help="同时向 stdout 输出 JSON 汇总，便于脚本/工具消费")

    p_score = sub.add_parser("score-intake")
    group = p_score.add_mutually_exclusive_group(required=True)
    group.add_argument("--text")
    group.add_argument("--file")

    p_pool = sub.add_parser("intake-pool")
    p_pool.add_argument("--base")
    p_pool.add_argument("--json", action="store_true", help="向 stdout 输出 JSON 汇总")

    p_capture = sub.add_parser("capture")
    p_capture.add_argument("--base")
    group_cap = p_capture.add_mutually_exclusive_group(required=True)
    group_cap.add_argument("--text")
    group_cap.add_argument("--file")
    p_capture.add_argument("--apply", action="store_true", help="确认后落盘：新建档案或追加事件记录")
    p_capture.add_argument("--json", action="store_true", help="向 stdout 输出纯 JSON（含锚点/匹配/草稿）")

    p_segment = sub.add_parser("segment")
    p_segment.add_argument("--base")
    p_segment.add_argument("--by", help="按单维度钻取群体：age/income/occupation/city/family/stage/priority/customer_type/business_line/status/info_completeness")
    p_segment.add_argument("--json", action="store_true", help="向 stdout 输出纯 JSON 汇总")

    p_set_status = sub.add_parser("set-status")
    p_set_status.add_argument("--base")
    p_set_status.add_argument("--customer-id", required=True)
    p_set_status.add_argument("--status", required=True, help="active / dormant / archived")
    p_set_status.add_argument("--reason", help="变更原因（写入变更记录）")
    p_set_status.add_argument("--apply", action="store_true", help="确认后落盘；默认仅预览")
    p_set_status.add_argument("--json", action="store_true", help="向 stdout 输出纯 JSON")

    p_merge = sub.add_parser("merge")
    p_merge.add_argument("--base")
    p_merge.add_argument("--keep", required=True, help="保留档案 customer_id")
    p_merge.add_argument("--absorb", required=True, help="并入档案 customer_id（合并后转 archived）")
    p_merge.add_argument("--apply", action="store_true", help="确认后执行；默认仅预览")
    p_merge.add_argument("--json", action="store_true", help="向 stdout 输出纯 JSON")

    args = parser.parse_args()

    if args.command == "score-intake":
        text = args.text if args.text is not None else Path(args.file).read_text(encoding="utf-8", errors="ignore")
        score_intake(text)
        return

    if args.command == "intake-pool":
        base = resolve_customer_library_path(args.base, must_exist=True)
        scan_intake_pool(base, as_json=args.json)
        return

    if args.command == "capture":
        base = resolve_customer_library_path(args.base, must_exist=True)
        text = args.text if args.text is not None else Path(args.file).read_text(encoding="utf-8", errors="ignore")
        capture_customer(base, text, apply=args.apply, as_json=args.json)
        return

    if args.command == "segment":
        base = resolve_customer_library_path(args.base, must_exist=True)
        if args.by:
            segment_drill(base, args.by, as_json=args.json)
        else:
            segment_customers(base, as_json=args.json)
        return

    if args.command == "set-status":
        base = resolve_customer_library_path(args.base, must_exist=True)
        set_customer_status(base, args.customer_id, args.status, args.reason, apply=args.apply, as_json=args.json)
        return

    if args.command == "merge":
        base = resolve_customer_library_path(args.base, must_exist=True)
        merge_customers(base, args.keep, args.absorb, apply=args.apply, as_json=args.json)
        return

    base = resolve_customer_library_path(args.base, must_exist=args.command != "init")

    if args.command == "init":
        init_library(base)
    elif args.command == "index":
        write_index(base)
    elif args.command == "find":
        find_customer(base, args.query)
    elif args.command == "filter":
        filter_customers(base, args)
    elif args.command == "audit":
        audit_library(base, as_json=args.json)
    elif args.command == "analyze-customer":
        write_customer_analysis(base, customer_id=args.customer_id, query=args.query)
    elif args.command == "gaps":
        write_information_gaps(base, customer_id=args.customer_id, query=args.query)
    elif args.command == "product-match":
        write_product_matches(base, product_id=args.product_id, product_file=args.product_file, detail=args.detail)
    elif args.command == "dashboard":
        write_operation_dashboard(base, as_json=args.json)


if __name__ == "__main__":
    main()
