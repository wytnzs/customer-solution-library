#!/usr/bin/env python3
"""代理人旅程验收：安装 → 构建 → 使用 → 持续更新。

与 test_customer_library.py 的分工：
- test_customer_library.py 验「命令本身对不对」；
- 本文件验「一个代理人照着文档走，四步能不能走完」。

跑法：
  PYTHONIOENCODING=utf-8 python scripts/test_agent_journeys.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import date, timedelta
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "customer_library.py"
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(condition), detail))


def run(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        input=stdin,
    )


def is_json(text: str) -> bool:
    try:
        json.loads(text)
        return True
    except Exception:
        return False


def init_vault(path: Path) -> None:
    r = run("init", "--base", str(path))
    if r.returncode != 0:
        raise SystemExit(f"init failed: {r.stderr}")


def write_profile(base: Path, name: str, cid: str, **fields: str) -> Path:
    """直接写一份最小档案，用来测已有客户场景（不经过导入）。"""
    today = date.today().isoformat()
    fm = {
        "type": "customer_profile",
        "customer_id": cid,
        "display_name": name,
        "status": "active",
        "stage": "lead",
        "priority": "B",
        "city": fields.get("city", ""),
        "birthday": fields.get("birthday", ""),
        "info_completeness": "L2",
        "created": today,
        "updated": today,
        "next_action": fields.get("next_action", ""),
        "next_followup_date": fields.get("next_followup_date", ""),
    }
    lines = ["---"]
    for key, value in fm.items():
        lines.append(f"{key}: {value}" if value != "" else f"{key}:")
    lines += ["---", "", "# 客户档案", "", "## 一句话画像", "", fields.get("body", ""), "", "## 变更记录", ""]
    path = base / "01-客户档案" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def profile_count(base: Path) -> int:
    d = base / "01-客户档案"
    return len(list(d.glob("*.md"))) if d.exists() else 0


def event_files(base: Path, name: str) -> list[Path]:
    d = base / "02-客户事件流" / name
    return sorted(d.glob("*.md")) if d.exists() else []


# ---------------------------------------------------------------- J1 安装

def journey_install(tmp: Path) -> Path:
    vault = tmp / "安装测试库"
    r = run("init", "--base", str(vault))
    check("J1 init 成功", r.returncode == 0, r.stderr.strip())
    expected_dirs = [
        "00-入口池/01-待处理", "01-客户档案", "02-客户事件流",
        "03-业务模块/insurance", "04-方案与分析", "05-团队协同/01-待分配",
        "06-服务跟进", "07-客户分层", "08-复盘案例",
        "09-产品与机会/products", "10-客户洞察", "90-索引与看板", "99-模板与规则",
    ]
    missing = [d for d in expected_dirs if not (vault / d).exists()]
    check("J1 init 目录齐全", not missing, str(missing))

    info_file = vault / "库信息.json"
    check("J1 init 生成库信息.json", info_file.exists())
    info = json.loads(info_file.read_text(encoding="utf-8")) if info_file.exists() else {}
    check("J1 库信息带 schema_version", info.get("schema_version") == "4", str(info))
    check("J1 库信息记录目录数", info.get("directories") == 27, str(info.get("directories")))

    r = run("doctor", "--base", str(vault), "--json")
    check("J1 doctor --json 是纯 JSON", r.returncode == 0 and is_json(r.stdout), r.stdout[:120])
    doc = json.loads(r.stdout) if is_json(r.stdout) else {}
    check("J1 doctor 判定ok", doc.get("ok") is True, str(doc)[:200])
    check("J1 doctor 判定已初始化", doc.get("initialized") is True, str(doc)[:200])
    check("J1 doctor 无失败项", not [i for i in doc.get("issues", []) if i.get("level") == "fail"], str(doc.get("issues")))

    r = run("doctor", "--base", str(vault))
    check("J1 doctor 人读输出有结论", "通过" in r.stdout and "失败" in r.stdout, r.stdout[-200:])
    check("J1 doctor 给出下一步", "下一步" in r.stdout, r.stdout[-200:])

    shutil.rmtree(vault / "02-客户事件流")
    r = run("doctor", "--base", str(vault), "--json")
    doc = json.loads(r.stdout) if is_json(r.stdout) else {}
    hit = [i for i in doc.get("issues", []) if "02-客户事件流" in i.get("message", "")]
    check("J1 doctor 能报缺目录", bool(hit), str(doc.get("issues"))[:200])

    r = run("init", "--base", str(vault))
    check("J1 再次 init 能补回目录", (vault / "02-客户事件流").exists() and r.returncode == 0, r.stderr.strip())

    empty = tmp / "还没建库"
    r = run("doctor", "--base", str(empty), "--json")
    doc = json.loads(r.stdout) if is_json(r.stdout) else {}
    check("J1 doctor 识别未初始化", doc.get("initialized") is False, str(doc)[:200])
    check("J1 doctor 未初始化时给建库命令", "init" in str(doc.get("next", "")), str(doc.get("next")))

    not_dir = tmp / "不是目录.txt"
    not_dir.write_text("x", encoding="utf-8")
    r = run("doctor", "--base", str(not_dir), "--json")
    doc = json.loads(r.stdout) if is_json(r.stdout) else {}
    check("J1 doctor 能报路径传成文件", doc.get("ok") is False and any("文件" in i.get("message", "") for i in doc.get("issues", [])), str(doc)[:200])
    return vault


# ---------------------------------------------------------------- J2 构建

def journey_build(tmp: Path) -> Path:
    vault = tmp / "构建测试库"
    init_vault(vault)

    csv_path = tmp / "客户名单.csv"
    csv_path.write_text(
        "姓名,手机,城市,生日,备注,来源\n"
        "张伟,13800138001,杭州,1985-03-12,关注重疾,朋友介绍\n"
        "李娜,13800138002,上海,1990-07-20,有孩子,微信\n"
        "王芳,13800138003,北京,,想了解年金,公众号\n"
        "张伟,13800138001,杭州,,重复行,朋友介绍\n"
        ",13900139009,天津,,无姓名行,微信\n",
        encoding="utf-8",
    )

    r = run("import", "--base", str(vault), "--file", str(csv_path))
    check("J2 导入默认只预览", r.returncode == 0 and profile_count(vault) == 0, r.stdout[:200])
    check("J2 预览不落盘", not (vault / "01-客户档案" / "张伟.md").exists(), "")

    r = run("import", "--base", str(vault), "--file", str(csv_path), "--apply", "--json")
    check("J2 导入 --json 是纯 JSON", r.returncode == 0 and is_json(r.stdout), r.stdout[:160])
    summary = json.loads(r.stdout) if is_json(r.stdout) else {}
    check("J2 导入新建 3 人", summary.get("created") == 3, str(summary))
    check("J2 导入识别 1 行重复", summary.get("duplicates") == 1, str(summary))
    check("J2 无姓名行被跳过", summary.get("skipped") == 1, str(summary))
    check("J2 导入结果记录来源文件", str(summary.get("file", "")).endswith("客户名单.csv"), str(summary.get("file")))
    check("J2 档案用真实姓名命名", (vault / "01-客户档案" / "张伟.md").exists(), str(list((vault / "01-客户档案").glob("*"))))

    ids = []
    for p in (vault / "01-客户档案").glob("*.md"):
        m = re.search(r"^customer_id:\s*(\S+)", p.read_text(encoding="utf-8"), re.M)
        if m:
            ids.append(m.group(1))
    check("J2 每个客户有唯一编号", len(ids) == len(set(ids)) == profile_count(vault), str(ids))

    profile = (vault / "01-客户档案" / "张伟.md").read_text(encoding="utf-8")
    check("J2 备注进档案正文", "关注重疾" in profile, profile[:200])
    check("J2 手机号进档案", "13800138001" in profile, profile[:200])
    check("J2 生日写入 frontmatter", "birthday: 1985-03-12" in profile, profile[:300])
    check("J2 来源写入", "朋友介绍" in profile, profile[:300])

    pool = vault / "00-入口池" / "03-待确认"
    pool_text = "\n".join(p.read_text(encoding="utf-8") for p in pool.glob("*.md"))
    check("J2 重复行进待确认池", "张伟" in pool_text, pool_text[:200])
    check("J2 待确认池记录来源文件", "客户名单.csv" in pool_text, pool_text[:200])

    r = run("import", "--base", str(vault), "--file", str(csv_path), "--apply", "--json")
    again = json.loads(r.stdout) if is_json(r.stdout) else {}
    check("J2 重复导入不造重档", again.get("created") == 0 and profile_count(vault) == 3, str(again))

    gbk_path = tmp / "gbk名单.csv"
    gbk_path.write_bytes(
        "客户姓名,联系电话,所在城市,客户生日\n陈明,13900139001,南京,1988/05/06\n刘洋,13900139002,苏州,\n".encode("gbk")
    )
    r = run("import", "--base", str(vault), "--file", str(gbk_path), "--apply", "--json")
    summary = json.loads(r.stdout) if is_json(r.stdout) else {}
    check("J2 能读 GBK 编码", summary.get("created") == 2, str(summary))
    check("J2 GBK 姓名不乱码", (vault / "01-客户档案" / "陈明.md").exists(), str(summary))
    chen_path = vault / "01-客户档案" / "陈明.md"
    chen = chen_path.read_text(encoding="utf-8") if chen_path.exists() else ""
    check("J2 生日斜杠格式归一", "birthday: 1988-05-06" in chen, chen[:300])

    index = vault / "90-索引与看板" / "customer-index.json"
    rows = json.loads(index.read_text(encoding="utf-8")) if index.exists() else []
    check("J2 导入后刷新索引", len(rows) == 5, f"rows={len(rows)}")

    mapped = tmp / "自定义列.csv"
    mapped.write_text("称呼,电话\n赵敏,13700137001\n", encoding="utf-8")
    r = run("import", "--base", str(vault), "--file", str(mapped), "--map", "称呼=name", "--map", "电话=phone", "--apply", "--json")
    summary = json.loads(r.stdout) if is_json(r.stdout) else {}
    check("J2 支持自定义列映射", summary.get("created") == 1 and (vault / "01-客户档案" / "赵敏.md").exists(), str(summary))

    r = run("capture", "--base", str(vault), "--text", "王磊，生日 1982年11月3日，南京，想了解医疗险", "--apply", "--json")
    wang_path = vault / "01-客户档案" / "王磊.md"
    wang = wang_path.read_text(encoding="utf-8") if wang_path.exists() else ""
    check("J2 一段话录入能识别生日", "birthday: 1982-11-03" in wang, wang[:300])
    return vault


# ---------------------------------------------------------------- J3 使用

def journey_use(tmp: Path, vault: Path) -> None:
    follow = (date.today() + timedelta(days=7)).isoformat()
    r = run(
        "event", "--base", str(vault), "--customer", "张伟",
        "--kind", "面谈", "--text", "聊了重疾和预算，先做保障盘点",
        "--next-action", "发方案", "--followup-date", follow,
    )
    check("J3 event 默认只预览", r.returncode == 0 and not event_files(vault, "张伟"), r.stdout[:200])
    check("J3 预览写明需要 --apply", "--apply" in r.stdout, r.stdout[-200:])

    r = run(
        "event", "--base", str(vault), "--customer", "张伟", "--apply",
        "--kind", "面谈", "--text", "聊了重疾和预算，先做保障盘点",
        "--next-action", "发方案", "--followup-date", follow, "--json",
    )
    check("J3 event --apply --json 是纯 JSON", r.returncode == 0 and is_json(r.stdout), r.stdout[:160])
    files = event_files(vault, "张伟")
    check("J3 生成事件文件", len(files) == 1, str(files))
    check("J3 事件按日期命名", files and files[0].name.startswith(date.today().isoformat()), str(files))
    ev = files[0].read_text(encoding="utf-8") if files else ""
    check("J3 事件带结构化 frontmatter", "type: customer_event" in ev and "event_type: 面谈" in ev, ev[:250])
    check("J3 事件保留原文", "先做保障盘点" in ev, ev[:250])

    prof = (vault / "01-客户档案" / "张伟.md").read_text(encoding="utf-8")
    check("J3 更新 next_action", "next_action: 发方案" in prof, prof[:400])
    check("J3 更新 next_followup_date", f"next_followup_date: {follow}" in prof, prof[:400])
    check("J3 写变更记录", "面谈" in prof and "变更记录" in prof, prof[-300:])
    check("J3 事件后 frontmatter 收口正常", "not_ready---" not in prof and "\n---\n" in prof, prof[:420])

    r = run(
        "event", "--base", str(vault), "--customer", "张伟", "--apply",
        "--kind", "面谈", "--text", "第二次沟通", "--json",
    )
    files = event_files(vault, "张伟")
    check("J3 同日同类事件不覆盖", len(files) == 2 and any(f.name.endswith("-2.md") for f in files), str([f.name for f in files]))

    r = run("analyze-customer", "--base", str(vault), "--customer-id", "张伟")
    check("J3 分析带出最近沟通", "最近沟通" in r.stdout and "先做保障盘点" in r.stdout, r.stdout[-400:])

    # 生日与回访提醒
    soon = (date.today() + timedelta(days=10)).strftime("%m-%d")
    overdue = (date.today() - timedelta(days=3)).isoformat()
    write_profile(vault, "周敏", "CUST-0009", birthday=soon, next_action="回访", next_followup_date=overdue, body="生日临近")
    write_profile(vault, "吴强", "CUST-0010", birthday="01-01", next_followup_date=(date.today() + timedelta(days=5)).isoformat(), next_action="送资料")

    r = run("remind", "--base", str(vault), "--days", "30", "--json")
    check("J3 remind --json 是纯 JSON", r.returncode == 0 and is_json(r.stdout), r.stdout[:160])
    rem = json.loads(r.stdout) if is_json(r.stdout) else {}
    groups = rem.get("groups", {})
    check("J3 提醒分出逾期组", any("周敏" in str(x) for x in groups.get("overdue", [])), str(groups)[:300])
    check("J3 提醒分出未来组", any("吴强" in str(x) for x in groups.get("upcoming", [])), str(groups)[:300])
    check("J3 生日按下一次计算", any("周敏" in str(x) for x in groups.get("birthdays", [])), str(groups)[:300])

    r = run("remind", "--base", str(vault), "--days", "30")
    check("J3 remind 人读分组", "已逾期" in r.stdout and "未来" in r.stdout, r.stdout[:300])

    r = run("remind", "--base", str(vault), "--days", "-1")
    check("J3 拒绝负数提醒天数", r.returncode != 0, r.stdout[:120])

    r = run("event", "--base", str(vault), "--customer", "张伟", "--kind", "电话",
            "--text", "日期格式测试", "--followup-date", "2026/12/03", "--apply")
    check("J3 拒绝非法回访日期", r.returncode != 0, r.stderr[:160])

    out = tmp / "客户名单导出.csv"
    r = run("export", "--base", str(vault), "--format", "csv", "--out", str(out))
    check("J3 导出 CSV 成功", r.returncode == 0 and out.exists(), r.stderr.strip())
    raw = out.read_bytes() if out.exists() else b""
    check("J3 CSV 带 BOM 可直接用 Excel 打开", raw.startswith(b"\xef\xbb\xbf"), raw[:10])
    text = raw.decode("utf-8-sig", errors="replace")
    check("J3 导出含客户与手机号", "张伟" in text and "13800138001" in text, text[:200])

    out2 = tmp / "脱敏名单.csv"
    r = run("export", "--base", str(vault), "--format", "csv", "--mask", "--out", str(out2))
    masked = out2.read_text(encoding="utf-8-sig") if out2.exists() else ""
    check("J3 脱敏导出无手机号", "13800138001" not in masked, masked[:200])
    check("J3 脱敏导出无完整姓名", "张伟" not in masked and "张*" in masked, masked[:200])

    out3 = tmp / "客户名单.md"
    r = run("export", "--base", str(vault), "--format", "md", "--out", str(out3))
    md = out3.read_text(encoding="utf-8") if out3.exists() else ""
    check("J3 支持导出 Markdown", "|" in md and "张伟" in md, md[:200])

    r = run("doctor", "--base", str(vault), "--json")
    doc = json.loads(r.stdout) if is_json(r.stdout) else {}
    check("J3 doctor 能报索引过期", any("索引" in i.get("message", "") for i in doc.get("issues", [])), str(doc.get("issues"))[:250])
    run("index", "--base", str(vault))


# ---------------------------------------------------------------- J4 更新

def journey_update(tmp: Path, vault: Path) -> None:
    backup_dir = tmp / "备份"
    r = run("backup", "--base", str(vault), "--out", str(backup_dir), "--json")
    check("J4 backup 成功", r.returncode == 0, r.stderr.strip())
    result = json.loads(r.stdout) if is_json(r.stdout) else {}
    archive = Path(result.get("archive", "")) if result.get("archive") else None
    manifest_path = Path(result.get("manifest", "")) if result.get("manifest") else None
    check("J4 生成压缩包", archive is not None and archive.exists(), str(result))
    check("J4 生成清单", manifest_path is not None and manifest_path.exists(), str(result))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path and manifest_path.exists() else {}
    check("J4 清单记文件数", manifest.get("file_count", 0) > 0, str(manifest)[:200])
    check("J4 清单记 sha256", archive is not None and manifest.get("sha256") == hashlib.sha256(archive.read_bytes()).hexdigest(), str(manifest)[:200])

    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
    check("J4 备份不含 .git", not any(".git" in n for n in names), str(names[:5]))
    check("J4 备份不含缓存", not any("__pycache__" in n or ".tmp" in n for n in names), str(names[:5]))

    inside_out = vault / "本地备份"
    r = run("backup", "--base", str(vault), "--out", str(inside_out), "--json")
    inside = json.loads(r.stdout) if is_json(r.stdout) else {}
    inside_names: list[str] = []
    if inside.get("archive"):
        with zipfile.ZipFile(inside["archive"]) as zf:
            inside_names = zf.namelist()
    check("J4 备份目录放在库内也不自吞", not any(n.startswith("本地备份/") for n in inside_names), str(inside_names[:5]))

    restored = tmp / "新电脑"
    r = run("restore", "--from", str(archive), "--base", str(restored), "--json")
    check("J4 恢复到空目录成功", r.returncode == 0, r.stderr.strip())
    check("J4 恢复后档案数一致", profile_count(restored) == profile_count(vault), f"{profile_count(restored)} vs {profile_count(vault)}")
    check("J4 恢复后事件流在", bool(event_files(restored, "张伟")), str(event_files(restored, "张伟")))
    r = run("doctor", "--base", str(restored), "--json")
    doc = json.loads(r.stdout) if is_json(r.stdout) else {}
    check("J4 恢复后 doctor 通过", doc.get("ok") is True, str(doc)[:200])

    r = run("restore", "--from", str(archive), "--base", str(restored))
    check("J4 拒绝覆盖非空目录", r.returncode != 0 and "非空" in r.stderr, r.stderr[:200])

    tampered = tmp / "清单"
    tampered.mkdir(exist_ok=True)
    bad_manifest = tampered / "坏清单.json"
    bad = dict(manifest)
    bad["sha256"] = "0" * 64
    bad_manifest.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    r = run("restore", "--from", str(archive), "--base", str(tmp / "被篡改恢复"), "--manifest", str(bad_manifest))
    check("J4 校验不符拒绝恢复", r.returncode != 0 and ("校验" in r.stderr or "sha256" in r.stderr.lower()), r.stderr[:200])

    # 升级迁移
    legacy = tmp / "老库"
    init_vault(legacy)
    (legacy / "库信息.json").unlink()
    old = write_profile(legacy, "老客户", "CUST-0001", body="老档案正文")
    r = run("migrate", "--base", str(legacy), "--json")
    check("J4 migrate 默认只预览", r.returncode == 0 and not (legacy / "库信息.json").exists(), r.stdout[:200])
    r = run("migrate", "--base", str(legacy), "--apply", "--json")
    check("J4 migrate --apply 补齐库信息", (legacy / "库信息.json").exists(), r.stderr.strip())
    migrated = old.read_text(encoding="utf-8")
    check("J4 migrate 补 birthday 字段", "birthday:" in migrated, migrated[:300])
    check("J4 migrate 不改档案正文", "老档案正文" in migrated, migrated[:300])
    r = run("migrate", "--base", str(legacy), "--apply", "--json")
    check("J4 migrate 幂等", "无需迁移" in r.stdout or "无需迁移" in r.stderr, r.stdout[:200])


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="journeys-"))
    try:
        vault = journey_install(tmp)
        vault = journey_build(tmp)
        journey_use(tmp, vault)
        journey_update(tmp, vault)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    failed = [n for n, ok, _ in RESULTS if not ok]
    print()
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"FAIL: {name}" + (f" | {detail}" if detail else ""))
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
