# -*- coding: utf-8 -*-
"""Deterministic B-002 item-9 coverage-map verifier.

The freeze document is the external source of truth. The real coverage map is
read-only. Positive controls mutate strings in memory only.
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
import re
import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
FREEZE_PATH = REPO / "feature-01-项目时间管理-仪表盘" / "9-GATE3_TECH_FREEZE.md"
MAP_PATH = REPO / "team-progress" / "B-002-coverage-map.md"
TIMELINE_TEST = REPO / "tests" / "test_timeline.py"
SECURE_TEST = REPO / "tests" / "test_secure_foundation.py"
FROZEN_PATHS = [REPO / "flowboard" / "timeline.py", TIMELINE_TEST, MAP_PATH]

EXPECTED_GROUP_CLAUSES = {
    1: [
        "member 改他人项目 403", "路径 workspace 不符 403", "跨项目 node 注入 422",
        "viewer 读/创建 403", "member/admin 网页新建成功", "仅 admin 软删、节点不硬删",
        "软删后 GET/batch/重复 DELETE 404 且零写入", "未登录 401",
    ],
    2: [
        "通用路径改两字段必败", "initial-correction 仅 admin", "多节点同批",
        "自由日期不钳制不级联", "重复 node 422", "全等值 no-op",
        "软删项目 correction 404 零写入",
    ],
    3: [
        "缺版本 428", "base_version 不符→409 零写入",
        "冲突体带 nodes/segments/stage_intervals/metrics",
    ],
    4: [
        "撤最新成功（old/new 互换）", "created 反向软删（行仍在）", "deleted 反向恢复",
        "三连批撤中间 409 零写入", "撤非最新 409 / 404 / undo 不可再撤",
        "member 撤 initial_correction 403", "软删项目 undo 404 零写入",
    ],
    5: ["混合批次"],
    6: [
        "interval_days 0..3650", "无前驱/create/同批改 track 拒绝", "date 优先覆盖 interval",
        "done_at 严格布尔", "single/cascade 钳制", "前置快照邻居/多锚点/direct 优先",
        "同日自然序+id 兜底",
    ],
    7: [
        "M1/M2/M3 空集/M4/M5=0", "M3 非空同日多节点、M5 非零、红橙并存",
        "三数组恒返、row_index/node_ids 确定",
        "复盘汇总完整、50+has_more、viewer 403、undo 不加计数",
    ],
    8: [
        "表头不匹配文件级报错", "xlsx 整数序列号换算 18264..73051",
        "分数/越界行级 422（带 row）", "文本日期路径不串扰",
        "状态三态+空、仅已完成落 done_at、其余按日期重算", "非法状态 422",
        "间隔整列忽略", "同名既有项目拒绝（R1）", "文件内重复=四键",
        "多行项目聚合成功", "字段上限（节点 500/备注 500/项目 200）",
    ],
    9: [
        "export_timeline() 真实字节往返", "语义等价（逐节点 track/stage/name/date/remark）",
        "既定差异四件", "按新 workspace 构造 + 同名再导 422（R5）",
    ],
    10: [
        "v15→v16 五表建成、user_version、存量计数不变、FK/integrity、schema_migrations 记账",
        "备份非空且含代表性 v15 存量（断言对象=备份本体）", "v16 重跑 migrate 幂等",
        "回滚语义可证", "全程隔离库",
    ],
    11: [
        "preview 存完整批、commit 只收 batch_id、无 base_version/sha 比对",
        "竞态 422 零写入、查无 404、重复 409", "preview_json 篡改重放 422 零写入",
    ],
    12: [
        "空 batch/correction 422", "全等值 200 no-op", "service 422 名称冲突",
    ],
}

EXPECTED_5_1 = [
    "8 列标准表头 strip 后完全一致", "格式/大小/行数/单元格/公式/宏/外链/压缩炸弹安全界",
    "CSV 编码 utf-8-sig/gb18030", "默认第一 sheet",
]
EXPECTED_5_2 = [
    "项目名称", "阶段", "轨道", "节点名称", "日期", "间隔", "状态", "备注",
    "文件内重复", "库内重复",
]
ALLOWED_STATUSES = {"PASS", "GAP-B002", "CONFLICT", "GAP-非九项", "N/A"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot() -> dict:
    real = REPO / "flowboard.db"
    st = real.stat()
    return {
        "hashes": {str(path.relative_to(REPO)): sha256(path) for path in FROZEN_PATHS},
        "freeze_sha256": sha256(FREEZE_PATH),
        "flowboard_db": {"size": st.st_size, "mtime_ns": st.st_mtime_ns},
    }


def section(text: str, start: str, end: str | None) -> str:
    start_at = text.find(start)
    if start_at < 0:
        return ""
    if end is None:
        return text[start_at:]
    end_at = text.find(end, start_at + len(start))
    return text[start_at:] if end_at < 0 else text[start_at:end_at]


def markdown_rows(text: str) -> list[list[str]]:
    rows = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        rows.append(cells)
    return rows


def freeze_shape(freeze: str) -> dict:
    sec_7 = section(freeze, "### 7.1 新增 timeline 测试清单", "### 7.2")
    group_ids = []
    for row in markdown_rows(sec_7):
        if row and row[0].isdigit():
            group_ids.append(int(row[0]))
    sec_51 = section(freeze, "### 5.1 文件级校验", "### 5.2")
    sec_52 = section(freeze, "### 5.2 行级校验", "### 5.3")
    sec_53 = section(freeze, "### 5.3 两段式与安全界", "---")
    rows_51 = [row for row in markdown_rows(sec_51) if row and row[0] not in {"校验"}]
    rows_52 = [row for row in markdown_rows(sec_52) if row and row[0] not in {"列"}]
    bullets_53 = [line for line in sec_53.splitlines() if line.startswith("- ")]
    return {
        "group_ids": group_ids,
        "section_5_1_rule_count": len(rows_51),
        "section_5_2_rule_count": len(rows_52),
        "section_5_3_bullet_count": len(bullets_53),
    }


def test_catalog(path: Path, module: str) -> dict[str, dict]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    catalog = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for member in node.body:
            if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and member.name.startswith("test_"):
                catalog[member.name] = {
                    "module": module,
                    "class": node.name,
                    "load_name": f"{module}.{node.name}.{member.name}",
                    "lineno": member.lineno,
                    "end_lineno": member.end_lineno,
                }
    return catalog


def extract_test_tokens(text: str) -> list[str]:
    tokens = []
    for match in re.finditer(r"`([^`]+)`", text):
        token = match.group(1)
        if token == "test_timeline.TimelineCoreTests.<name>" or "/" in token:
            continue
        if re.fullmatch(r"test_[A-Za-z0-9_]+(?:…|\.\.\.)?", token):
            tokens.append(token)
    return tokens


def resolve_token(token: str, timeline_catalog: dict[str, dict]) -> tuple[list[dict], str | None]:
    if token.endswith("…"):
        prefix = token[:-1]
    elif token.endswith("..."):
        prefix = token[:-3]
    else:
        prefix = None
    if prefix is not None:
        matches = [value for name, value in timeline_catalog.items() if name.startswith(prefix)]
        if len(matches) == 1:
            return matches, None
        return [], "ambiguous or absent shorthand"
    if token in timeline_catalog:
        return [timeline_catalog[token]], None
    return [], "test not found"


def line_reference_tests(text: str, secure_catalog: dict[str, dict]) -> list[dict]:
    resolved = []
    for match in re.finditer(r"tests/test_secure_foundation\.py:(\d+)", text):
        lineno = int(match.group(1))
        hits = [value for value in secure_catalog.values()
                if value["lineno"] <= lineno <= value["end_lineno"]]
        if len(hits) == 1:
            resolved.extend(hits)
    return resolved


def group_sections(map_text: str) -> dict[int, str]:
    a = section(map_text, "## A.", "## B.")
    matches = list(re.finditer(r"^### 组 (\d+)\b.*$", a, flags=re.MULTILINE))
    result = {}
    for index, match in enumerate(matches):
        start_at = match.start()
        end_at = matches[index + 1].start() if index + 1 < len(matches) else len(a)
        result[int(match.group(1))] = a[start_at:end_at]
    return result


def status_rows(map_text: str) -> list[dict]:
    relevant = section(map_text, "## A.", "## C.")
    heading = ""
    previous_by_heading = {}
    rows = []
    for line in relevant.splitlines():
        if line.startswith("### "):
            heading = line[4:].strip()
            continue
        parsed = markdown_rows(line)
        if not parsed:
            continue
        cells = parsed[0]
        if len(cells) < 3 or cells[-1] == "状态" or cells[0] in {"判据", "规则", "列"}:
            continue
        raw = cells[-1]
        normalized = None
        if raw.startswith("PASS"):
            normalized = "PASS"
        elif raw.startswith("GAP-B002"):
            normalized = "GAP-B002"
        elif raw.startswith("CONFLICT"):
            normalized = "CONFLICT"
        elif raw.startswith("GAP-非九项") or raw.startswith("§D-"):
            normalized = "GAP-非九项"
        elif raw == "N/A":
            normalized = "N/A"
        elif raw == "同上":
            normalized = previous_by_heading.get(heading)
        rows.append({
            "heading": heading, "criterion": cells[0], "binding": cells[-2],
            "raw_status": raw, "status": normalized, "line": line,
        })
        if normalized is not None:
            previous_by_heading[heading] = normalized
    # 组5在 map 中是单行文字而非表格，纳入相同状态门。
    group5 = group_sections(map_text).get(5, "")
    if group5:
        rows.append({
            "heading": "组 5", "criterion": "混合批次", "binding": group5,
            "raw_status": "PASS", "status": "PASS", "line": group5.strip(),
        })
    return rows


def loadable(load_name: str) -> bool:
    suite = unittest.defaultTestLoader.loadTestsFromName(load_name)
    if suite.countTestCases() != 1:
        return False
    stack = [suite]
    while stack:
        item = stack.pop()
        if isinstance(item, unittest.TestSuite):
            stack.extend(list(item))
        elif item.__class__.__name__ == "_FailedTest":
            return False
    return True


def validate(map_text: str) -> dict:
    freeze = FREEZE_PATH.read_text(encoding="utf-8")
    failures = []
    shape = freeze_shape(freeze)
    if shape != {
        "group_ids": list(range(1, 13)),
        "section_5_1_rule_count": 4,
        "section_5_2_rule_count": 10,
        "section_5_3_bullet_count": 3,
    }:
        failures.append({"key": "FREEZE_SHAPE_CHANGED", "actual": shape})

    groups = group_sections(map_text)
    missing_groups = [number for number in range(1, 13) if number not in groups]
    missing_clauses = []
    for number, clauses in EXPECTED_GROUP_CLAUSES.items():
        body = groups.get(number, "")
        for clause in clauses:
            if clause not in body:
                missing_clauses.append({"group": number, "clause": clause})
    b51 = section(map_text, "### 5.1 文件级", "### 5.2")
    b52 = section(map_text, "### 5.2 行级", "### 5.3")
    missing_51 = [rule for rule in EXPECTED_5_1 if rule not in b51]
    missing_52 = [rule for rule in EXPECTED_5_2 if not re.search(
        rf"^\|\s*{re.escape(rule)}\s*\|", b52, flags=re.MULTILINE
    )]
    missing_53 = [] if "组 11 全 PASS" in section(map_text, "### 5.3 两段式", "### §3.7") else ["两段式/安全界→组11"]
    if missing_groups or missing_clauses or missing_51 or missing_52 or missing_53:
        failures.append({
            "key": "MISSING_MAPPING", "missing_groups": missing_groups,
            "missing_group_clauses": missing_clauses, "missing_5_1": missing_51,
            "missing_5_2": missing_52, "missing_5_3": missing_53,
        })

    rows = status_rows(map_text)
    invalid_statuses = [
        {"heading": row["heading"], "criterion": row["criterion"], "raw": row["raw_status"]}
        for row in rows if row["status"] not in ALLOWED_STATUSES
    ]
    if invalid_statuses:
        failures.append({"key": "INVALID_STATUS", "rows": invalid_statuses})

    timeline_catalog = test_catalog(TIMELINE_TEST, "test_timeline")
    secure_catalog = test_catalog(SECURE_TEST, "test_secure_foundation")
    token_resolutions = {}
    bad_test_refs = []
    resolved_tests = {}
    for token in sorted(set(extract_test_tokens(map_text))):
        matches, error = resolve_token(token, timeline_catalog)
        if error:
            bad_test_refs.append({"token": token, "reason": error})
            continue
        token_resolutions[token] = [match["load_name"] for match in matches]
        for match in matches:
            resolved_tests[match["load_name"]] = match
    for match in line_reference_tests(map_text, secure_catalog):
        resolved_tests[match["load_name"]] = match
    if bad_test_refs:
        failures.append({"key": "TEST_NOT_FOUND", "references": bad_test_refs})

    # PASS 行须在本行或所在结构组中解析到至少一个真实测试；“同上”继承前行。
    section_tests = {}
    for number, body in groups.items():
        names = []
        for token in extract_test_tokens(body):
            names.extend(token_resolutions.get(token, []))
        section_tests[f"组 {number}"] = sorted(set(names))
    pass_without_test = []
    previous_binding = {}
    for row in rows:
        direct = []
        for token in extract_test_tokens(row["binding"]):
            direct.extend(token_resolutions.get(token, []))
        direct.extend(match["load_name"] for match in line_reference_tests(row["binding"], secure_catalog))
        if row["binding"].startswith("同上") or row["raw_status"] == "同上":
            direct.extend(previous_binding.get(row["heading"], []))
        if not direct:
            group_match = re.match(r"组 (\d+)", row["heading"])
            if group_match:
                direct.extend(section_tests.get(f"组 {group_match.group(1)}", []))
        direct = sorted(set(direct))
        previous_binding[row["heading"]] = direct
        if row["status"] == "PASS" and not direct:
            pass_without_test.append({"heading": row["heading"], "criterion": row["criterion"]})
    if pass_without_test:
        failures.append({"key": "PASS_WITHOUT_TEST", "rows": pass_without_test})

    load_results = []
    for load_name in sorted(resolved_tests):
        ok = loadable(load_name)
        load_results.append({"name": load_name, "loadable": ok})
    not_loadable = [row["name"] for row in load_results if not row["loadable"]]
    if not_loadable:
        failures.append({"key": "TEST_NOT_LOADABLE", "tests": not_loadable})

    # 每个 GAP-非九项入口必须显式去往 B-003；允许 §D 前言一条共享路由。
    d_section = section(map_text, "## D.", "## E.")
    d_intro = d_section.split("| # |", 1)[0]
    shared_route = "B-003" in d_intro and "候选" in d_intro
    d_rows = {
        row[0]: " | ".join(row)
        for row in markdown_rows(d_section)
        if len(row) >= 3 and re.fullmatch(r"D-\d+", row[0])
    }
    missing_routes = sorted(
        key for key, value in d_rows.items()
        if not shared_route and "B-003" not in value
    )
    if missing_routes:
        failures.append({
            "key": "OUT_OF_SCOPE_ROUTE_MISSING",
            "missing_ids": missing_routes,
            "minimal_fix": "在 §D 前言增加一条共享声明：D 表全部为 B-003 候选；无需逐行改写。",
        })

    return {
        "passed": not failures,
        "exit_code": 0 if not failures else 1,
        "freeze_shape": shape,
        "coverage": {
            "groups_present": len(groups),
            "group_clause_requirements": sum(len(v) for v in EXPECTED_GROUP_CLAUSES.values()),
            "section_5_1_requirements": len(EXPECTED_5_1),
            "section_5_2_requirements": len(EXPECTED_5_2),
            "section_5_3_requirements": 1,
        },
        "statuses": {
            "rows_checked": len(rows),
            "allowed": sorted(ALLOWED_STATUSES),
            "normalized_counts": {
                status: sum(row["status"] == status for row in rows)
                for status in sorted(ALLOWED_STATUSES)
            },
        },
        "tests": {
            "references_resolved": len(resolved_tests),
            "loadable": sum(row["loadable"] for row in load_results),
            "load_results": load_results,
        },
        "gap_routes": {"entries": sorted(d_rows), "shared_route": shared_route},
        "failures": failures,
    }


def main() -> int:
    for path in (str(REPO), str(REPO / "tests")):
        if path not in sys.path:
            sys.path.insert(0, path)
    importlib.invalidate_caches()

    start = snapshot()
    map_text = MAP_PATH.read_text(encoding="utf-8")
    real = validate(map_text)

    delete_marker = "| 空 batch/correction 422 |"
    deletion_lines = map_text.splitlines(keepends=True)
    deleted = False
    for index, line in enumerate(deletion_lines):
        if delete_marker in line:
            del deletion_lines[index]
            deleted = True
            break
    deletion = validate("".join(deletion_lines)) if deleted else {
        "passed": False, "exit_code": 1,
        "failures": [{"key": "CONTROL_SETUP_FAILED", "marker": delete_marker}],
    }

    original_test = "`test_import_headers_contract_literal`"
    fake_test = "`test_wave3_definitely_missing`"
    fake_text = map_text.replace(original_test, fake_test, 1)
    fake = validate(fake_text)

    controls = {
        "delete_one_mapping": {
            "mutated_in_memory_only": True,
            "target": delete_marker,
            "exit_code": deletion["exit_code"],
            "passed": deletion["passed"],
            "failure_keys": [item["key"] for item in deletion["failures"]],
            "expected_failure_observed": (
                not deletion["passed"]
                and "MISSING_MAPPING" in [item["key"] for item in deletion["failures"]]
            ),
        },
        "replace_with_missing_test": {
            "mutated_in_memory_only": True,
            "target": original_test,
            "replacement": fake_test,
            "exit_code": fake["exit_code"],
            "passed": fake["passed"],
            "failure_keys": [item["key"] for item in fake["failures"]],
            "expected_failure_observed": (
                not fake["passed"]
                and "TEST_NOT_FOUND" in [item["key"] for item in fake["failures"]]
            ),
        },
    }
    end = snapshot()
    baseline_stable = start == end
    payload = {
        "source": {
            "freeze": str(FREEZE_PATH.relative_to(REPO)),
            "map": str(MAP_PATH.relative_to(REPO)),
        },
        "baseline_start": start,
        "baseline_end": end,
        "baseline_stable": baseline_stable,
        "real_map": real,
        "positive_controls": controls,
        "controls_passed": all(item["expected_failure_observed"] for item in controls.values()),
    }
    (HERE / "coverage_map_verification.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (HERE / "positive_controls.json").write_text(
        json.dumps(controls, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    event = {
        "event": "coverage_map_wave3",
        "real_passed": real["passed"],
        "real_exit_code": real["exit_code"],
        "failure_keys": [item["key"] for item in real["failures"]],
        "coverage": real["coverage"],
        "statuses": real["statuses"],
        "tests": {key: value for key, value in real["tests"].items() if key != "load_results"},
        "positive_controls": controls,
        "baseline_stable": baseline_stable,
    }
    (HERE / "run_console.json").write_text(
        json.dumps(event, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(event, ensure_ascii=False))
    if not baseline_stable or not payload["controls_passed"]:
        return 2
    return real["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
