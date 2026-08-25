#!/usr/bin/env python3
"""Deterministic B-005 CP0 coverage-map validator (stdlib only)."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MAP_PATH = ROOT / "team-progress" / "B-005-coverage-map.md"
LOCKED = (
    "flowboard.db",
    ".copilot-state.json",
    ".copilot-task.md",
    ".copilot-message.md",
)
LEGAL_STATES = {"PASS", "GAP-B005", "CONFLICT", "OUT_OF_SCOPE"}

EXPECTED: dict[str, tuple[str, str]] = {
    **{f"A{i:02d}": ("GAP-B005", "CP3") for i in range(1, 7)},
    "A07": ("GAP-B005", "CP6"),
    "B01": ("PASS", "CP4"),
    "B02": ("PASS", "CP4"),
    "C01": ("PASS", "CP4"),
    **{f"D{i:02d}": ("GAP-B005", "CP1") for i in range(1, 3)},
    **{f"D{i:02d}": ("GAP-B005", "CP2") for i in range(3, 8)},
    **{f"D{i:02d}": ("GAP-B005", "CP5") for i in range(8, 11)},
    **{f"D{i:02d}": ("GAP-B005", "CP4") for i in range(11, 13)},
    "D13": ("GAP-B005", "CP6"),
    "E01": ("GAP-B005", "CP5"),
    "E02": ("GAP-B005", "CP5"),
    "F01": ("OUT_OF_SCOPE", "Gate 5"),
    "F02": ("OUT_OF_SCOPE", "Gate 5"),
    "F03": ("OUT_OF_SCOPE", "Gate 5"),
    "F04": ("OUT_OF_SCOPE", "Gate 5"),
    "F05": ("OUT_OF_SCOPE", "Gate 5"),
    "F06": ("OUT_OF_SCOPE", "用户显式授权"),
    "F07": ("OUT_OF_SCOPE", "新立项+用户拍板"),
}

# These clause-specific tokens prevent a structurally complete but semantically
# hollow map from passing. They distill D1-D5, freeze 7.2/7.3/9.3, and slice 5.
REQUIRED_TOKENS: dict[str, tuple[str, ...]] = {
    "A01": ("v15", "users/workspaces/boards/groups_/tasks", "计数"),
    "A02": ("v16", "五张 timeline 表", "schema_migrations"),
    "A03": ("备份", "v15", "代表"),
    "A04": ("幂等", "第二次", "不新增备份"),
    "A05": ("foreign_key_check", "integrity_check", "初始为空"),
    "A06": ("失败回滚", "backup→verify→restore", "无半表"),
    "A07": ("真实库锁", "hash/size/mtime", "flowboard.db"),
    "B01": ("权限", "审计", "undo", "Excel"),
    "B02": ("HTTP", "负路径"),
    "C01": ("浅色", "Chromium", "B01–B38"),
    "D01": ("12 Python", "5 Node", "2e906c5"),
    "D02": ("blob", "语义 diff", "test_collaboration.py"),
    "D03": ("unittest discover", "零 fail/error/skip"),
    "D04": ("node --test", "6 文件"),
    "D05": ("py_compile", "exit 0"),
    "D06": ("node --check", "exit 0"),
    "D07": ("git diff --check", "GAP"),
    "D08": ("README", "临时 DB", "Chromium"),
    "D09": ("12 Python", "5 Node", "迁移"),
    "D10": ("v16 五表", "verify/restore", "Gate 5"),
    "D11": ("原始命令输出", "独立 probe", "正式报告"),
    "D12": ("暗色运行态", "主题切换", "每周看板", "project_ids"),
    "D13": ("flowboard.db", ".copilot-state/task/message", "CP0", "CP6"),
    "E01": ("WAIT_GATE5_HUMAN", "未完成门 5/上线"),
    "E02": ("2–3 项目", "15 分钟", "commit/push", "真实库"),
    "F01": ("2–3 个项目", "体验判断"),
    "F02": ("精确色值", "强磁吸", "像素"),
    "F03": ("开板拖卡/刷新", "甘特切视图", "widgets", "普通成员登录"),
    "F04": ("真机/部署", "上线决策"),
    "F05": ("flowboard.db", "人工拍板"),
    "F06": ("commit/push", "deploy/发布", "无授权"),
    "F07": ("工作负载/OKR", "AI/CRM", "新立项"),
}

PASS_EVIDENCE = {
    "team-progress/planner-report-B-002-wave4.md": ("正式四态：**PASS**",),
    "team-progress/planner-report-B003-CP5.md": ("**PASS：B-003 可关闭。**",),
    "team-progress/planner-report-B004-CP6.md": ("**CP6 PASS；B-004 CLOSED",),
}


def fingerprint() -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for rel in LOCKED:
        path = ROOT / rel
        data = path.read_bytes()
        stat = path.stat()
        result[rel] = {
            "sha256": hashlib.sha256(data).hexdigest().upper(),
            "bytes": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }
    return result


def split_markdown_row(line: str) -> list[str]:
    """Split a table row while preserving PowerShell pipes inside code spans."""
    cells: list[str] = []
    current: list[str] = []
    in_code = False
    for char in line.strip()[1:-1]:
        if char == "`":
            in_code = not in_code
            current.append(char)
        elif char == "|" and not in_code:
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    cells.append("".join(current).strip())
    return cells


def parse_rows(text: str) -> tuple[dict[str, list[str]], list[str]]:
    rows: dict[str, list[str]] = {}
    duplicates: list[str] = []
    for line in text.splitlines():
        if not line.strip().startswith("|") or not line.strip().endswith("|"):
            continue
        cells = split_markdown_row(line)
        if not cells or not re.fullmatch(r"[A-F]\d{2}", cells[0]):
            continue
        if cells[0] in rows:
            duplicates.append(cells[0])
        rows[cells[0]] = cells
    return rows, duplicates


def validate(text: str) -> dict[str, object]:
    errors: list[dict[str, object]] = []
    rows, duplicates = parse_rows(text)
    for row_id in duplicates:
        errors.append({"key": "DUPLICATE_ID", "id": row_id})

    missing = sorted(set(EXPECTED) - set(rows))
    extra = sorted(set(rows) - set(EXPECTED))
    if missing:
        errors.append({"key": "MISSING_ID", "ids": missing})
    if extra:
        errors.append({"key": "UNEXPECTED_ID", "ids": extra})

    states: Counter[str] = Counter()
    for row_id, cells in rows.items():
        if row_id not in EXPECTED:
            continue
        if len(cells) != 5:
            errors.append({"key": "COLUMN_COUNT", "id": row_id, "actual": len(cells)})
            continue
        text_row = " | ".join(cells)
        state, owner = cells[-2], cells[-1]
        states[state] += 1
        if state not in LEGAL_STATES:
            errors.append({"key": "ILLEGAL_STATE", "id": row_id, "state": state})
        expected_state, expected_owner = EXPECTED[row_id]
        if state != expected_state:
            errors.append({"key": "STATE_MISMATCH", "id": row_id, "expected": expected_state, "actual": state})
        if owner != expected_owner:
            errors.append({"key": "OWNER_MISMATCH", "id": row_id, "expected": expected_owner, "actual": owner})
        if any(sep in owner for sep in ("/", "、", ",", "，")):
            errors.append({"key": "MULTIPLE_OWNERS", "id": row_id, "owner": owner})
        absent_tokens = [token for token in REQUIRED_TOKENS[row_id] if token not in text_row]
        if absent_tokens:
            errors.append({"key": "CLAUSE_TOKEN_MISSING", "id": row_id, "tokens": absent_tokens})

    expected_counts = {"PASS": 3, "GAP-B005": 22, "CONFLICT": 0, "OUT_OF_SCOPE": 7}
    actual_counts = {state: states.get(state, 0) for state in LEGAL_STATES}
    if actual_counts != expected_counts:
        errors.append({"key": "STATE_COUNTS", "expected": expected_counts, "actual": actual_counts})

    # CP0-CP6 must each be declared exactly once in the ownership table.
    cp_declared = Counter(re.findall(r"^\| (CP[0-6]) \|", text, flags=re.MULTILINE))
    if cp_declared != Counter({f"CP{i}": 1 for i in range(7)}):
        errors.append({"key": "CP_DECLARATION", "actual": dict(cp_declared)})

    # Inherited PASS evidence must be loadable and terminal, not merely an old REWORK.
    for rel, terminal_markers in PASS_EVIDENCE.items():
        if f"`{rel}`" not in text:
            errors.append({"key": "EVIDENCE_REFERENCE_MISSING", "path": rel})
            continue
        path = ROOT / rel
        if not path.is_file():
            errors.append({"key": "EVIDENCE_MISSING", "path": rel})
            continue
        report = path.read_text(encoding="utf-8")
        for marker in terminal_markers:
            if marker not in report:
                errors.append({"key": "EVIDENCE_NOT_TERMINAL_PASS", "path": rel, "marker": marker})

    # No B-005 dynamic row may claim inherited PASS.
    for row_id in [*([f"A{i:02d}" for i in range(1, 8)]), *([f"D{i:02d}" for i in range(1, 14)]), "E01", "E02"]:
        cells = rows.get(row_id)
        if cells and len(cells) == 5 and cells[-2] == "PASS":
            errors.append({"key": "DYNAMIC_PREMATURE_PASS", "id": row_id})

    # Allowed-write list is parsed separately from the explicit deny list.
    allowed_match = re.search(
        r"B-005 后续唯一允许修改集：(?P<body>.*?)明确禁止修改：",
        text,
        flags=re.DOTALL,
    )
    if not allowed_match:
        errors.append({"key": "ALLOWED_SET_MISSING"})
    else:
        allowed = allowed_match.group("body")
        required_allowed = ("README.md", "team-progress/B-005-coverage-map.md", "team-progress/verification/B-005-CP*/")
        forbidden_allowed = ("STATE.md", "AGENTS.md", "CLAUDE.md", ".copilot-", "flowboard.db", "backups/", ".git/", "tests/", "生产代码")
        for token in required_allowed:
            if token not in allowed:
                errors.append({"key": "ALLOWED_ITEM_MISSING", "token": token})
        for token in forbidden_allowed:
            if token in allowed:
                errors.append({"key": "FORBIDDEN_ITEM_ALLOWED", "token": token})

    # Map's locked-disk SHA values must agree with the current immutable inputs.
    current = fingerprint()
    for rel, info in current.items():
        if str(info["sha256"]) not in text:
            errors.append({"key": "LOCK_FINGERPRINT_NOT_MAPPED", "path": rel, "sha256": info["sha256"]})

    return {
        "ok": not errors,
        "row_count": len(rows),
        "state_counts": actual_counts,
        "cp_declarations": dict(cp_declared),
        "errors": errors,
    }


def main() -> int:
    before = fingerprint()
    source = MAP_PATH.read_text(encoding="utf-8")
    real = validate(source)

    deleted = re.sub(r"^\| A01 \|.*\r?\n", "", source, count=1, flags=re.MULTILINE)
    delete_control = validate(deleted)
    forged = source.replace(
        "team-progress/planner-report-B003-CP5.md",
        "team-progress/planner-report-B003-CP5-NOT-REAL.md",
    )
    evidence_control = validate(forged)
    after = fingerprint()

    controls = {
        "delete_required_mapping": {
            "ok": (not delete_control["ok"] and any(e["key"] == "MISSING_ID" and "A01" in e.get("ids", []) for e in delete_control["errors"])),
            "validator_ok": delete_control["ok"],
            "failure_keys": sorted({e["key"] for e in delete_control["errors"]}),
        },
        "forge_evidence_path": {
            "ok": (not evidence_control["ok"] and any(e["key"] in {"EVIDENCE_REFERENCE_MISSING", "EVIDENCE_MISSING"} for e in evidence_control["errors"])),
            "validator_ok": evidence_control["ok"],
            "failure_keys": sorted({e["key"] for e in evidence_control["errors"]}),
        },
    }
    lock_ok = before == after
    result = {
        "validator": "B-005-CP0",
        "real": real,
        "positive_controls": controls,
        "locked_fingerprints_before": before,
        "locked_fingerprints_after": after,
        "locked_unchanged": lock_ok,
        "overall_pass": bool(real["ok"] and all(item["ok"] for item in controls.values()) and lock_ok),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["overall_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
