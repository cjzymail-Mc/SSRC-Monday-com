#!/usr/bin/env python3
"""Independent, read-only validator for the B-003 CP0 coverage map."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path


EXPECTED = [
    ("GET", "/api/workspaces/{id}/timeline", "200", "CP1"),
    ("GET", "/api/timeline/projects/{id}", "200", "CP1"),
    ("GET", "/api/workspaces/{id}/timeline/review", "200", "CP1"),
    ("POST", "/api/workspaces/{id}/timeline/projects", "201", "CP1"),
    ("DELETE", "/api/workspaces/{id}/timeline/projects/{project_id}", "200", "CP1"),
    ("POST", "/api/workspaces/{id}/timeline/batches", "200", "CP2"),
    ("POST", "/api/workspaces/{id}/timeline/batches/undo", "200", "CP2"),
    ("POST", "/api/workspaces/{id}/timeline/batches/initial-correction", "200", "CP2"),
    ("POST", "/api/workspaces/{id}/timeline/imports/preview", "201", "CP3"),
    ("POST", "/api/workspaces/{id}/timeline/imports/commit", "201", "CP3"),
    ("POST", "/api/workspaces/{id}/timeline/export", "200", "CP4"),
]
LEGAL_STATES = {"PASS", "GAP-B003", "CONFLICT", "OUT-OF-SCOPE"}


def clean(cell: str) -> str:
    return cell.strip().replace("`", "").replace("**", "")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_methods(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name.startswith("test_"):
                    found.add(f"{node.name}.{child.name}")
    return found


def validate(map_path: Path, tests_path: Path) -> dict:
    text = map_path.read_text(encoding="utf-8")
    rows = []
    for line in text.splitlines():
        if re.match(r"^\|\s*\d+\s*\|", line):
            cells = [clean(c) for c in line.strip().strip("|").split("|")]
            if len(cells) == 13:
                rows.append(cells)

    failures: list[dict] = []
    actual_keys = [(r[1], r[2]) for r in rows]
    expected_keys = [(m, p) for m, p, _, _ in EXPECTED]
    missing = [f"{m} {p}" for m, p in expected_keys if (m, p) not in actual_keys]
    extra = [f"{m} {p}" for m, p in actual_keys if (m, p) not in expected_keys]
    if missing:
        failures.append({"failure_key": "ROUTE_MISSING", "details": missing})
    if extra:
        failures.append({"failure_key": "ROUTE_EXTRA", "details": extra})
    if len(rows) != 11:
        failures.append({"failure_key": "ROUTE_COUNT", "details": {"expected": 11, "actual": len(rows)}})

    methods = test_methods(tests_path)
    referenced: list[str] = []
    required_columns = {
        3: "success_status", 4: "request", 5: "response", 6: "auth_csrf",
        7: "permission_errors", 8: "server_wiring", 9: "service", 10: "http_test",
        11: "state", 12: "cp",
    }
    expected_by_key = {(m, p): (status, cp) for m, p, status, cp in EXPECTED}
    for row in rows:
        key = (row[1], row[2])
        for idx, label in required_columns.items():
            if not row[idx].strip():
                failures.append({"failure_key": "FIELD_MISSING", "details": {"route": key, "field": label}})
        if key in expected_by_key:
            status, cp = expected_by_key[key]
            if row[3] != status:
                failures.append({"failure_key": "STATUS_MISMATCH", "details": {"route": key, "expected": status, "actual": row[3]}})
            if row[12] != cp:
                failures.append({"failure_key": "CP_MISMATCH", "details": {"route": key, "expected": cp, "actual": row[12]}})
        state = row[11].split("：", 1)[0].split(":", 1)[0].strip()
        if state not in LEGAL_STATES:
            failures.append({"failure_key": "STATE_INVALID", "details": {"route": key, "actual": state}})
        for ref in re.findall(r"([A-Za-z_]\w*\.test_[A-Za-z0-9_]+)", row[10]):
            referenced.append(ref)
            if ref not in methods:
                failures.append({"failure_key": "TEST_NOT_FOUND", "details": ref})

    if not referenced:
        failures.append({"failure_key": "TEST_REFERENCE_MISSING", "details": "at least one existing named HTTP test is required at CP0"})

    return {
        "result": "PASS" if not failures else "REWORK",
        "route_count": len(rows),
        "routes_exact": not missing and not extra and len(rows) == 11,
        "referenced_tests": referenced,
        "loadable_ast_tests": sorted(methods),
        "failures": failures,
        "inputs": {str(map_path): sha256(map_path), str(tests_path): sha256(tests_path)},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("map", type=Path)
    parser.add_argument("--tests", type=Path, default=Path("tests/test_timeline.py"))
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    result = validate(args.map, args.tests)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.json:
        args.json.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
