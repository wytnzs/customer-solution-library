#!/usr/bin/env python3
"""Lightweight regression tests for the customer-solution-library utilities.

Builds a throwaway customer library in a temp directory, drives the real CLI via
subprocess, and asserts the behaviors that regressed or were added:

  - inline YAML lists ([a, b]) no longer leak brackets into outputs
  - consulting gaps no longer fire for pure insurance clients
  - next_followup_date overdue is surfaced by dashboard and audit
  - dashboard/audit --json emit pure JSON on stdout
  - find returns source records only, not generated reports

Run from anywhere:
  python scripts/test_customer_library.py
Exit code 0 on pass, 1 on failure.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "customer_library.py"
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    RESULTS.append((name, condition, detail))
    mark = "PASS" if condition else "FAIL"
    print(f"[{mark}] {name}" + (f"  -- {detail}" if detail and not condition else ""))


def run(*args: str) -> subprocess.CompletedProcess:
    # The CLI prints to stdout in the locale encoding (cp936/GBK) unless forced;
    # pin PYTHONIOENCODING so we can decode as UTF-8 deterministically.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


def yesterday_iso() -> str:
    return (date.today() - timedelta(days=1)).isoformat()


def build_fixture(base: Path) -> None:
    run("init", "--base", str(base))
    (base / "01-客户档案" / "CUST-0001.md").write_text(
        f"""---
type: customer_profile
customer_id: CUST-0001
display_name: 张伟
aliases: [张先生]
customer_type: [insurance_client]
business_line: [insurance]
status: active
stage: solution
priority: A
source: 李姐转介绍
age_range: 31-40
city: 杭州
family_structure: 已婚有孩
info_completeness: L4
next_action: 发送家庭保障方案
next_followup_date: {yesterday_iso()}
needs: [家庭保障规划]
risks: [健康告知不确定性]
---

# 客户档案

## 一句话画像
杭州已婚一孩，李姐转介绍，考虑重疾险。

## 已知资料
- 已有保单：重疾险20万、医疗险
""",
        encoding="utf-8",
    )
    (base / "03-业务模块" / "insurance" / "CUST-0001.md").write_text(
        """---
type: business_module
business_line: insurance
customer_id: CUST-0001
---

# 保险业务

- 已有保单：重疾险20万、医疗险
- 核保关注：甲状腺结节2级，需提供体检报告
""",
        encoding="utf-8",
    )
    (base / "01-客户档案" / "CUST-0002.md").write_text(
        """---
type: customer_profile
customer_id: CUST-0002
display_name: 王芳
customer_type: [insurance_client]
business_line: [insurance]
status: active
stage: lead
priority: B
source: 小红书私信
info_completeness: L1
next_action:
next_followup_date:
---

# 客户档案

## 一句话画像
小红书私信了解医疗险。
""",
        encoding="utf-8",
    )
    (base / "09-产品与机会" / "products" / "PROD-001.md").write_text(
        """---
type: product_profile
product_id: PROD-001
product_name: 家庭重疾险
business_line: insurance
suitable_for: [有家庭责任, 有保障缺口]
not_suitable_for: [明确拒绝长期缴费]
matching_signals: [重疾险, 家庭保障, 房贷]
risk_signals: [甲状腺结节, 预算压力]
required_information: [已有保单, 体检报告]
age_fit: [31-40, 41-50]
income_fit: [20-50万, 50万以上]
family_fit: [已婚有孩]
---

# 家庭重疾险
""",
        encoding="utf-8",
    )
    (base / "00-入口池" / "01-待处理" / "INTAKE-001.md").write_text(
        """---
type: intake
intake_id: INTAKE-001
status: pending
---

# 待处理入口

一位客户想了解医疗险，还没有详细信息。
""",
        encoding="utf-8",
    )
    (base / "00-入口池" / "02-待匹配" / "INTAKE-002.md").write_text(
        """---
type: intake
intake_id: INTAKE-002
status: unmatched
---

# 待匹配入口

赵女士，杭州，咨询重疾险，电话13800001111。
""",
        encoding="utf-8",
    )


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="custlib-test-"))
    try:
        base = tmp / "lib"
        build_fixture(base)

        # 1. index
        r = run("index", "--base", str(base))
        check("index reports 2 profiles", "Indexed 2 customer profiles" in r.stdout, r.stdout.strip())

        # 2. analyze: inline lists must not leak brackets; consulting gaps must not fire
        r = run("analyze-customer", "--base", str(base), "--customer-id", "CUST-0001")
        analysis = (base / "04-方案与分析" / "CUST-0001" / "客户深度分析.md").read_text(encoding="utf-8")
        check("analyze succeeds", r.returncode == 0, r.stderr.strip())
        check("analyze: no bracket leak", "[insurance_client]" not in analysis and "[家庭保障规划]" not in analysis, "brackets still present")
        check("analyze: no consulting gap for insurance client", "明确目标" not in analysis, "spurious consulting gap")
        check("analyze: existing policy not flagged missing", "已有保单" not in analysis, "existing policy treated as missing")
        check("analyze: no YAML noise in evidence", "next_action:" not in analysis, "frontmatter leaked into evidence")

        # 3. dashboard --json: pure JSON + overdue surfaced
        r = run("dashboard", "--base", str(base), "--json")
        try:
            dash = json.loads(r.stdout)
            ok = True
        except json.JSONDecodeError:
            dash, ok = {}, False
        check("dashboard --json is pure JSON", ok, r.stdout[:120])
        check("dashboard flags overdue", dash.get("counts", {}).get("overdue", 0) >= 1, "no overdue detected")
        overdue_ids = [e.get("customer_id") for e in dash.get("overdue", [])]
        check("dashboard overdue has CUST-0001", "CUST-0001" in overdue_ids, str(overdue_ids))
        # confirmation line must NOT pollute stdout when --json
        check("dashboard --json stdout unpolluted", "Wrote" not in r.stdout, "confirmation leaked to stdout")

        # 4. audit --json
        r = run("audit", "--base", str(base), "--json")
        try:
            audit = json.loads(r.stdout)
            ok = True
        except json.JSONDecodeError:
            audit, ok = {}, False
        check("audit --json is pure JSON", ok, r.stdout[:120])
        check("audit counts overdue", audit.get("counts", {}).get("overdue", 0) >= 1, str(audit.get("counts")))

        # 5. find: source records only, ranked
        r = run("find", "--base", str(base), "--query", "张伟")
        check("find succeeds", r.returncode == 0, r.stderr.strip())
        check("find excludes generated reports", "04-方案与分析" not in r.stdout and "09-产品与机会" not in r.stdout, r.stdout)
        check("find ranks profile first", r.stdout.strip().startswith("1. ["), r.stdout.strip().splitlines()[0] if r.stdout.strip() else "")

        # 6. product-match
        r = run("product-match", "--base", str(base), "--product-id", "PROD-001")
        match_file = base / "09-产品与机会" / "matching" / "PROD-001-潜在客户清单.md"
        check("product-match writes list", r.returncode == 0 and match_file.exists(), str(match_file))
        match_text = match_file.read_text(encoding="utf-8") if match_file.exists() else ""
        # 名单→详情联动：清单现在带命中客户详情区（一句话画像/阶段/缺口/路径）
        check("product-match list has detail section", "命中客户详情" in match_text and "一句话画像" in match_text, "detail section missing")

        # 6b. product-match --detail 生成完整详情文件
        r = run("product-match", "--base", str(base), "--product-id", "PROD-001", "--detail")
        detail_file = base / "09-产品与机会" / "matching" / "PROD-001-潜在客户详情.md"
        check("product-match --detail writes detail file", r.returncode == 0 and detail_file.exists(), str(detail_file))
        detail_text = detail_file.read_text(encoding="utf-8") if detail_file.exists() else ""
        # 详情应从档案正文取到一句话画像（fixture: 杭州已婚一孩，李姐转介绍，考虑重疾险。）
        check("product-match detail extracts one-liner", "杭州已婚一孩" in detail_text, "one-liner not extracted")
        check("product-match detail has stage/route", "solution / L4 / A" in detail_text, "stage line missing")

        # 6c. product-match 画像匹配：产品 *_fit 字段命中客户画像 → 详情标注画像匹配；
        #     客户缺省某画像维度（CUST-0001 无 income_range）→ 该维度不奖不罚、不误报。
        r = run("product-match", "--base", str(base), "--product-id", "PROD-001", "--detail")
        detail_text = (base / "09-产品与机会" / "matching" / "PROD-001-潜在客户详情.md").read_text(encoding="utf-8")
        demog_line = next((l for l in detail_text.splitlines() if "画像匹配" in l), "")
        check("product-match 画像命中含年龄与家庭", "年龄区间" in demog_line and "家庭结构" in demog_line, demog_line)
        check("product-match 缺省收入维度不误报", "收入区间" not in demog_line, demog_line)
        check("product-match 无画像偏离误报", "画像偏离" not in detail_text, "spurious mismatch")

        # 6d. product-match 画像偏离：客户画像偏离产品适配 → 减分并标注偏离原因（软信号不硬排除）
        (base / "09-产品与机会" / "products" / "PROD-002.md").write_text(
            """---
type: product_profile
product_id: PROD-002
product_name: 老年防癌险
business_line: insurance
age_fit: [61以上]
family_fit: [单身]
---

# 老年防癌险
""",
            encoding="utf-8",
        )
        r = run("product-match", "--base", str(base), "--product-id", "PROD-002", "--detail")
        detail2 = base / "09-产品与机会" / "matching" / "PROD-002-潜在客户详情.md"
        text2 = detail2.read_text(encoding="utf-8") if detail2.exists() else ""
        check("product-match 画像偏离标注年龄", "画像偏离" in text2 and "年龄区间：31-40（产品适配61以上）" in text2, text2[:200])
        check("product-match 画像偏离标注家庭结构", "家庭结构：已婚有孩（产品适配单身）" in text2, "family mismatch not surfaced")

        # 7. intake-pool
        r = run("intake-pool", "--base", str(base), "--json")
        try:
            pool = json.loads(r.stdout)
            ok = True
        except json.JSONDecodeError:
            pool, ok = {}, False
        check("intake-pool --json is pure JSON", ok, r.stdout[:120])
        check("intake-pool sees both entries", len(pool.get("entries", [])) >= 2, str(pool.get("counts")))

        # 8. score-intake
        r = run("score-intake", "--text", "张先生转介绍，想了解重疾险，周五晚有空，有甲状腺结节")
        try:
            scored = json.loads(r.stdout)
            ok = True
        except json.JSONDecodeError:
            scored, ok = {}, False
        check("score-intake is JSON", ok, r.stdout[:120])
        check("score-intake score in range", 0 <= int(scored.get("signal_score", -1)) <= 100, str(scored.get("signal_score")))

        # 9. capture: new customer draft -> apply -> second fragment re-matches.
        # Use a distinct identity (李先生/成都/单身) that shares no anchors with
        # the fixture customers (张先生杭州 / 王芳小红书).
        new_desc = "李先生转介绍，成都，单身，想咨询寿险"
        r = run("capture", "--base", str(base), "--text", new_desc)
        check("capture draft reports new customer", r.returncode == 0 and "未命中已有客户" in r.stdout, r.stdout.strip()[:120])
        check("capture draft has structured YAML", "customer_id: CUST-0003" in r.stdout and "info_completeness: L2" in r.stdout, r.stdout.strip()[:200])

        r = run("capture", "--base", str(base), "--text", new_desc, "--apply")
        new_profile = base / "01-客户档案" / "CUST-0003.md"
        check("capture apply writes profile", r.returncode == 0 and new_profile.exists(), str(new_profile))
        draft_text = new_profile.read_text(encoding="utf-8") if new_profile.exists() else ""
        check("capture persists identity anchors", "李先生" in draft_text and "成都" in draft_text and "单身" in draft_text, "anchors missing from profile body")

        r = run("capture", "--base", str(base), "--text", "李先生成都单身，预算一年一万，想先咨询寿险")
        check("capture re-matches existing customer", "命中已有客户" in r.stdout and "CUST-0003" in r.stdout, r.stdout.strip()[:120])

        r = run("capture", "--base", str(base), "--text", "李先生今天打电话说预算一年一万，单身，先咨询寿险", "--apply")
        event_files = list((base / "02-客户事件流" / "CUST-0003").glob("*-抓取入档*.md")) if (base / "02-客户事件流" / "CUST-0003").exists() else []
        check("capture update appends event record", len(event_files) >= 1, str([f.name for f in event_files]))
        # profile body untouched by the update path (no history overwrite)
        after = new_profile.read_text(encoding="utf-8") if new_profile.exists() else ""
        check("capture update does not overwrite profile", after == draft_text, "profile body changed on update")

        # capture --json: pure JSON, action=update for matched customer
        r = run("capture", "--base", str(base), "--text", "李先生预算一年一万，单身", "--json")
        try:
            cap = json.loads(r.stdout)
            ok = True
        except json.JSONDecodeError:
            cap, ok = {}, False
        check("capture --json is pure JSON", ok, r.stdout[:120])
        check("capture --json action update", cap.get("action") == "update" and cap.get("match", {}).get("customer_id") == "CUST-0003", str(cap.get("action")))

        # 9b. surname-only fragment must NOT merge into an unrelated customer.
        # 张 is an alias of CUST-0001, so 张先生 would legitimately hit it; use
        # 赵 instead — no fixture customer starts with 赵 — and confirm a lone
        # surname with no secondary anchor stays "new customer", while the
        # 可补充项 guidance still fires for the sparse record.
        r = run("capture", "--base", str(base), "--text", "赵先生想了解储蓄险")
        check("capture surname-only stays new", "未命中已有客户" in r.stdout, r.stdout.strip()[:120])
        check("capture sparse fragment suggests fill-ins",
              "可补充项" in r.stdout and "家庭结构" in r.stdout and "预算" in r.stdout and "健康情况" in r.stdout,
              "guidance missing")

        # 9c. demographic-rich fragment: draft fills profile fields + body lines,
        # and the 可补充项 only lists the genuinely-missing high-value items.
        rich_desc = "陈先生，上海，45岁，年收入30万，个体户，已婚一个孩子，朋友介绍，咨询年金"
        r = run("capture", "--base", str(base), "--text", rich_desc)
        check("capture draft fills demographic frontmatter",
              "age_range: 41-50" in r.stdout and "income_range: 20-50万" in r.stdout
              and "occupation: 个体户" in r.stdout and "city: 上海" in r.stdout
              and "family_structure: 已婚有孩" in r.stdout,
              r.stdout.strip()[:200])
        check("capture draft body has age/income lines",
              "年龄区间：41-50" in r.stdout and "收入区间：20-50万" in r.stdout,
              "body lines missing")
        # 家庭/年龄/收入/职业/城市/来源 已就位，只应提示健康与预算。
        # 用 --json 检查 suggestions 标签，避免正文「城市：上海」等干扰子串判断。
        r = run("capture", "--base", str(base), "--text", rich_desc, "--json")
        try:
            cap = json.loads(r.stdout)
            ok = True
        except json.JSONDecodeError:
            cap, ok = {}, False
        sug_labels = [s.get("label") for s in cap.get("suggestions", [])] if ok else []
        check("capture rich fragment narrows suggestions",
              "健康情况" in sug_labels and "预算" in sug_labels
              and "家庭结构" not in sug_labels and "城市" not in sug_labels,
              str(sug_labels))

        # 9d. near-miss: name-only fragment for an existing customer must warn
        # instead of silently creating a duplicate (anti-merge keeps it safe).
        r = run("capture", "--base", str(base), "--text", "李先生想先看看寿险方案")
        check("capture near-miss warns", "疑似命中" in r.stdout and "CUST-0003" in r.stdout, r.stdout.strip()[:120])
        r = run("capture", "--base", str(base), "--text", "李先生想先看看寿险方案", "--json")
        try:
            cap = json.loads(r.stdout)
            ok = True
        except json.JSONDecodeError:
            cap, ok = {}, False
        check("capture near-miss JSON", ok and cap.get("action") == "create"
              and cap.get("near_miss", {}).get("customer_id") == "CUST-0003", str(cap.get("near_miss")))

        # 9e. 画像字段持久化到新建档案：--apply 后 frontmatter 有 age_range 等。
        r = run("capture", "--base", str(base), "--text", rich_desc, "--apply")
        rich_profile = base / "01-客户档案" / "CUST-0004.md"
        check("capture apply writes demographic profile", rich_profile.exists(), str(rich_profile))
        if rich_profile.exists():
            rich_text = rich_profile.read_text(encoding="utf-8")
            check("capture persists demographic frontmatter",
                  "age_range: 41-50" in rich_text and "family_structure: 已婚有孩" in rich_text,
                  "demographics not persisted")

        # 9f. 直接写入一个高画像客户，凑齐群体统计的众数样本。
        (base / "01-客户档案" / "CUST-0005.md").write_text(
            """---
type: customer_profile
customer_id: CUST-0005
display_name: 孙立
customer_type: [insurance_client]
business_line: [insurance]
status: active
stage: lead
priority: B
source: 朋友介绍
age_range: 41-50
income_range: 50万以上
occupation: 企业主
city: 上海
family_structure: 已婚无孩
info_completeness: L3
needs: [年金]
---

# 客户档案

## 一句话画像
上海企业主，咨询储蓄型年金。

## 已知资料
- 已有保单：储蓄型年金、增额寿
""",
            encoding="utf-8",
        )

        # 10. segment: group-level aggregation across dimensions
        r = run("segment", "--base", str(base), "--json")
        try:
            seg = json.loads(r.stdout)
            ok = True
        except json.JSONDecodeError:
            seg, ok = {}, False
        check("segment --json is pure JSON", ok, r.stdout[:120])
        # CUST-0001/0002 + capture CUST-0003/0004 + fixture CUST-0005 = 5 active
        check("segment counts active customers", seg.get("active", 0) == 5, str(seg.get("active")))
        stage = seg.get("dimensions", {}).get("stage", {})
        check("segment groups by stage", "lead" in stage and "solution" in stage, str(stage))
        # needs aggregation pulls from the needs field of CUST-0001
        needs = seg.get("needs", {})
        check("segment aggregates needs", "家庭保障规划" in needs, str(list(needs.keys())))

        # 10b. 主要客户画像：众数 + 覆盖率 + 分布
        profile = seg.get("profile", {})
        age_top = profile.get("age_range", {}).get("top", {})
        check("segment profile age mode", age_top.get("value") == "41-50" and age_top.get("count") == 2, str(age_top))
        check("segment profile city mode", profile.get("city", {}).get("top", {}).get("value") == "上海", str(profile.get("city")))
        check("segment profile covers known/total", profile.get("age_range", {}).get("known") == 3
              and profile.get("age_range", {}).get("total") == 5, str(profile.get("age_range", {}).get("known")))
        check("segment profile has distribution", "41-50" in profile.get("age_range", {}).get("distribution", {}), "no distribution")

        # 10c. 保险类型 × 画像：从档案文本识别，反推经营侧重
        itypes = seg.get("insurance_types", {})
        check("segment detects insurance types", "重疾险" in itypes and "医疗险" in itypes and "年金/储蓄" in itypes, str(list(itypes.keys())))
        check("segment insurance groups customers", sorted(itypes.get("医疗险", [])) == ["CUST-0001", "CUST-0002"], str(itypes.get("医疗险")))
        cross = seg.get("insurance_cross", [])
        annuity = next((c for c in cross if c.get("type") == "年金/储蓄"), {})
        check("segment insurance typical profile", annuity.get("typical") == "41-50·上海·已婚无孩·企业主·50万以上", str(annuity.get("typical")))

        # markdown report includes both new sections
        seg_file = base / "90-索引与看板" / "客户群体分析.md"
        check("segment writes report", seg_file.exists(), str(seg_file))
        seg_text = seg_file.read_text(encoding="utf-8") if seg_file.exists() else ""
        check("segment report has profile section", "主要客户画像" in seg_text, "profile section missing")
        check("segment report has insurance cross", "保险类型 × 客户画像" in seg_text, "insurance cross missing")

        # 11. filter: 按画像/保险类型/缺省维度结构化筛客户
        # 11a. --age 数字自动归桶（45 → 41-50，命中 CUST-0004/0005，排除 31-40 的 CUST-0001）
        r = run("filter", "--base", str(base), "--age", "45")
        check("filter age number buckets",
              "CUST-0004" in r.stdout and "CUST-0005" in r.stdout and "CUST-0001" not in r.stdout,
              r.stdout.strip()[:160])

        # 11b. --family 文本子串匹配（已婚有孩 → CUST-0001/0004，不命中 已婚无孩 的 CUST-0005）
        r = run("filter", "--base", str(base), "--family", "已婚有孩")
        check("filter family substring",
              "CUST-0001" in r.stdout and "CUST-0004" in r.stdout and "CUST-0005" not in r.stdout,
              r.stdout.strip()[:160])

        # 11c. --no-product：输入"重疾"匹配类型标签"重疾险"的关键词，排除持重疾客户
        r = run("filter", "--base", str(base), "--no-product", "重疾")
        check("filter no-product excludes holders",
              "CUST-0001" not in r.stdout and "CUST-0005" in r.stdout,
              r.stdout.strip()[:160])

        # 11d. --has-product：关键词反向命中类型
        r = run("filter", "--base", str(base), "--has-product", "重疾")
        check("filter has-product keyword", "CUST-0001" in r.stdout, r.stdout.strip()[:160])

        # 11e. --missing：筛缺省某画像字段的客户（CUST-0004/0005 有收入区间，应排除）
        r = run("filter", "--base", str(base), "--missing", "income_range")
        check("filter missing field",
              "CUST-0001" in r.stdout and "CUST-0004" not in r.stdout and "CUST-0005" not in r.stdout,
              r.stdout.strip()[:160])

        # 11f. --json 纯 JSON + 计数正确（杭州只有 CUST-0001）
        r = run("filter", "--base", str(base), "--city", "杭州", "--json")
        try:
            fjson = json.loads(r.stdout)
            fok = True
        except json.JSONDecodeError:
            fjson, fok = {}, False
        check("filter --json is pure JSON", fok, r.stdout[:120])
        check("filter --json count and ids",
              fjson.get("count") == 1 and fjson["customers"][0]["customer_id"] == "CUST-0001",
              str(fjson.get("count")))

        # 11g. 无任何筛选条件时报错（不能把全员当结果）
        r = run("filter", "--base", str(base))
        check("filter requires criterion", r.returncode != 0 and "No filter criteria" in r.stderr, (r.stderr or r.stdout)[:120])

        # 12. segment --by 单维度钻取：按年龄区间逐桶看客户与典型画像
        # 12a. --json 纯 JSON：维度/标签/活跃数/未填数正确，41-50 桶含 CUST-0004/0005
        r = run("segment", "--base", str(base), "--by", "age", "--json")
        try:
            drill = json.loads(r.stdout)
            dok = True
        except json.JSONDecodeError:
            drill, dok = {}, False
        check("segment --by --json is pure JSON", dok, r.stdout[:120])
        check("segment --by reports dimension", drill.get("dimension") == "age_range" and drill.get("label") == "年龄区间", str(drill.get("dimension")))
        check("segment --by counts active/unknown", drill.get("active") == 5 and drill.get("unknown") >= 2, f"active={drill.get('active')} unknown={drill.get('unknown')}")
        age414 = next((b for b in drill.get("buckets", []) if b.get("value") == "41-50"), {})
        check("segment --by age bucket ids", sorted(age414.get("customers", [])) == ["CUST-0004", "CUST-0005"], str(age414.get("customers")))
        check("segment --by typical excludes drilled dim",
              "41-50" not in age414.get("typical", "") and "上海" in age414.get("typical", ""),
              age414.get("typical", ""))

        # 12b. 文本输出：标题 + 表格，逐桶覆盖
        r = run("segment", "--base", str(base), "--by", "city")
        check("segment --by text header", "客户群体钻取：城市" in r.stdout, r.stdout.strip()[:120])
        check("segment --by text rows", "上海" in r.stdout and "杭州" in r.stdout and "成都" in r.stdout, r.stdout.strip()[:160])
        check("segment --by text typical column", "该取值典型画像" in r.stdout, "typical column header missing")

        # 12c. 非法维度拒绝
        r = run("segment", "--base", str(base), "--by", "bogus")
        check("segment --by rejects unknown dim", r.returncode != 0 and "Unknown --by" in r.stderr, (r.stderr or r.stdout)[:120])

        # 13. set-status：归档/唤醒/沉睡，预览先行、--apply 才落盘
        # 13a. 预览不落盘
        r = run("set-status", "--base", str(base), "--customer-id", "CUST-0001", "--status", "archived", "--reason", "成交结束")
        check("set-status preview shows plan", "状态变更预览" in r.stdout and "CUST-0001" in r.stdout, r.stdout.strip()[:120])
        c1_text = (base / "01-客户档案" / "CUST-0001.md").read_text(encoding="utf-8")
        check("set-status preview keeps status", "status: active" in c1_text, "frontmatter changed on preview")

        # 13b. --apply 落盘：frontmatter + 变更记录
        r = run("set-status", "--base", str(base), "--customer-id", "CUST-0001", "--status", "archived", "--reason", "成交结束", "--apply")
        check("set-status apply exits 0", r.returncode == 0, r.stderr.strip())
        c1_text = (base / "01-客户档案" / "CUST-0001.md").read_text(encoding="utf-8")
        check("set-status writes archived", "status: archived" in c1_text, "status not archived")
        check("set-status writes change note", "状态变更 active → archived" in c1_text and "成交结束" in c1_text, "change note missing")

        # 13c. filter 联动：默认排除、--status archived 可查且表头写归档客户
        r = run("filter", "--base", str(base), "--city", "杭州")
        check("filter excludes archived", "CUST-0001" not in r.stdout, r.stdout.strip()[:120])
        r = run("filter", "--base", str(base), "--status", "archived")
        check("filter lists archived alone", "CUST-0001" in r.stdout and "归档客户" in r.stdout, r.stdout.strip()[:120])

        # 13d. 非法 status / 重复归档拒绝
        r = run("set-status", "--base", str(base), "--customer-id", "CUST-0001", "--status", "bogus")
        check("set-status rejects invalid status", r.returncode != 0 and "Invalid status" in r.stderr, r.stderr[:80])
        r = run("set-status", "--base", str(base), "--customer-id", "CUST-0001", "--status", "archived", "--apply")
        check("set-status rejects already archived", r.returncode != 0 and "already archived" in r.stderr, r.stderr[:80])

        # 13e. 唤醒：archived → active
        r = run("set-status", "--base", str(base), "--customer-id", "CUST-0001", "--status", "active", "--apply")
        check("set-status reactivate ok", r.returncode == 0, r.stderr.strip())
        c1_text = (base / "01-客户档案" / "CUST-0001.md").read_text(encoding="utf-8")
        check("set-status reactivate writes active", "status: active" in c1_text, c1_text[:120])

        # 13f. set-status --json 纯 JSON（预览 applied:false，apply applied:true）
        r = run("set-status", "--base", str(base), "--customer-id", "CUST-0001", "--status", "dormant", "--json")
        try:
            st = json.loads(r.stdout); st_ok = True
        except json.JSONDecodeError:
            st, st_ok = {}, False
        check("set-status --json preview is pure JSON", st_ok and st.get("applied") is False and st.get("after") == "dormant", r.stdout[:120])
        r = run("set-status", "--base", str(base), "--customer-id", "CUST-0001", "--status", "dormant", "--apply", "--json")
        try:
            st = json.loads(r.stdout); st_ok = True
        except json.JSONDecodeError:
            st, st_ok = {}, False
        check("set-status --json apply is pure JSON", st_ok and st.get("applied") is True and st.get("after") == "dormant", r.stdout[:120])

        # 14. merge：确认同一人后合并档案，预览先行、--apply 才落盘
        # 14a. 建一份并入档案 + 事件流（CUST-0006 与 CUST-0005 同一人：孙立）
        (base / "01-客户档案" / "CUST-0006.md").write_text(
            """---
type: customer_profile
customer_id: CUST-0006
display_name: 孙立
aliases: [孙老板]
customer_type: [insurance_client]
business_line: [insurance]
status: active
stage: lead
priority: C
city: 苏州
income_range: 20-50万
info_completeness: L1
needs: [教育金]
created: 2026-06-01
updated: 2026-06-01
---

# 客户档案

## 一句话画像
苏州客户，咨询教育金。
""",
            encoding="utf-8",
        )
        ev6 = base / "02-客户事件流" / "CUST-0006"
        ev6.mkdir(parents=True, exist_ok=True)
        (ev6 / "2026-06-15-微信沟通.md").write_text("# 微信沟通\n\n聊教育金。\n", encoding="utf-8")

        # 14b. 预览不落盘
        r = run("merge", "--base", str(base), "--keep", "CUST-0005", "--absorb", "CUST-0006")
        check("merge preview shows plan", "合并预览" in r.stdout and "孙老板" in r.stdout and "教育金" in r.stdout, r.stdout.strip()[:160])
        check("merge preview no write",
              "status: archived" not in (base / "01-客户档案" / "CUST-0006.md").read_text(encoding="utf-8")
              and "merged_from" not in (base / "01-客户档案" / "CUST-0005.md").read_text(encoding="utf-8"),
              "preview changed files")

        # 14c. 同 id 拒绝
        r = run("merge", "--base", str(base), "--keep", "CUST-0005", "--absorb", "CUST-0005")
        check("merge rejects same id", r.returncode != 0 and "same customer" in r.stderr, r.stderr[:80])

        # 14d. --apply 落盘：字段并集 + absorb 转 archived + 事件流迁移 + 变更记录
        r = run("merge", "--base", str(base), "--keep", "CUST-0005", "--absorb", "CUST-0006", "--apply")
        check("merge apply exits 0", r.returncode == 0, r.stderr.strip())
        c5 = (base / "01-客户档案" / "CUST-0005.md").read_text(encoding="utf-8")
        check("merge keep gains union aliases", "孙老板" in c5, "alias not merged")
        check("merge keep gains union needs", "教育金" in c5 and "年金" in c5, "needs not unioned")
        check("merge keep tracks merged_from", "merged_from: [CUST-0006]" in c5, "merged_from missing")
        check("merge keep keeps its own city", "city: 上海" in c5, "keep city overwritten")
        check("merge keep change note", "并入 CUST-0006" in c5, "keep change note missing")
        check("merge keep appends absorb body", "咨询教育金" in c5, "absorb body not appended")
        c6 = (base / "01-客户档案" / "CUST-0006.md").read_text(encoding="utf-8")
        check("merge absorb archived", "status: archived" in c6 and "merged_into: CUST-0005" in c6, "absorb not archived/merged")
        ev6_now = sorted((base / "02-客户事件流" / "CUST-0006").glob("*.md")) if (base / "02-客户事件流" / "CUST-0006").exists() else []
        ev5_now = sorted((base / "02-客户事件流" / "CUST-0005").glob("*.md")) if (base / "02-客户事件流" / "CUST-0005").exists() else []
        check("merge moves event files", len(ev6_now) == 0 and any("2026-06-15" in f.name for f in ev5_now), str([f.name for f in ev5_now]))

        # 14e. 已合并的 absorb 再合并拒绝
        r = run("merge", "--base", str(base), "--keep", "CUST-0004", "--absorb", "CUST-0006")
        check("merge rejects already merged absorb", r.returncode != 0 and "already been merged" in r.stderr, r.stderr[:80])

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    failed = [n for n, ok, _ in RESULTS if not ok]
    print()
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
