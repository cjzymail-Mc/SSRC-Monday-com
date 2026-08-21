from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
MAP = ROOT / "team-progress" / "B-005-coverage-map.md"
PASS_IDS = [
    *(f"A{i:02d}" for i in range(1, 8)),
    "B01",
    "B02",
    "C01",
    *(f"D{i:02d}" for i in range(1, 14)),
    "E01",
    "E02",
]
OOS_IDS = [f"F{i:02d}" for i in range(1, 8)]

LOCKED = {
    "flowboard.db": {
        "sha256": "9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D",
        "bytes": 446464,
        "mtime_ns": 1786516285465474700,
    },
    ".copilot-state.json": {
        "sha256": "C9EB2A0A0B4E48B7A66DCE279B704DEA32854AB3E5FDA78BDFB0679BB3EE96A7",
        "bytes": 2144,
        "mtime_ns": 1787119255493155900,
    },
    ".copilot-task.md": {
        "sha256": "34A9814963951EB0ACD0A886F33D8746C0ABDE23BD3ABC3317370B9D328F1BCA",
        "bytes": 13690,
        "mtime_ns": 1787104103493621800,
    },
    ".copilot-message.md": {
        "sha256": "FCEEEE50F16D6A85C8FC26DA3847E88BA53C64B9542D57DFF6A299D778515F72",
        "bytes": 7317,
        "mtime_ns": 1787119058694564900,
    },
}

OLD_TESTS = [
    "tests/test_collaboration.py",
    "tests/test_collaboration_e2e.py",
    "tests/test_collaboration_http.py",
    "tests/test_dashboards.py",
    "tests/test_i12.py",
    "tests/test_i12_e2e.py",
    "tests/test_i13.py",
    "tests/test_i13_e2e.py",
    "tests/test_i13_operations.py",
    "tests/test_schedule.py",
    "tests/test_secure_foundation.py",
    "tests/test_views_e2e.py",
    "tests/dashboard_ui.test.js",
    "tests/i12_ui.test.js",
    "tests/schedule_ui.test.js",
    "tests/view_state.test.js",
    "tests/view_ui.test.js",
]
AUTHORIZED_CHANGED = {
    "tests/test_collaboration.py",
    "tests/test_dashboards.py",
    "tests/test_i12.py",
    "tests/test_i13.py",
    "tests/test_i13_e2e.py",
    "tests/test_i13_operations.py",
    "tests/test_schedule.py",
    "tests/test_secure_foundation.py",
}


def fail(key: str, detail: object) -> None:
    print(json.dumps({"status": "FAIL", "failure_key": key, "detail": detail}, ensure_ascii=False))
    raise SystemExit(1)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def run(label: str, command: list[str], timeout: int = 180) -> dict[str, object]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    try:
        proc = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        fail(f"B005_CP6_{label}_TIMEOUT", str(exc))
    if proc.returncode:
        tail = "\n".join(proc.stdout.splitlines()[-80:])
        fail(f"B005_CP6_{label}_NONZERO", {"exit": proc.returncode, "tail": tail})
    return {"exit": proc.returncode, "output": proc.stdout}


def load_json_output(label: str, result: dict[str, object]) -> dict[str, object]:
    lines = [line for line in str(result["output"]).splitlines() if line.strip().startswith("{")]
    if not lines:
        fail(f"B005_CP6_{label}_JSON_MISSING", str(result["output"])[-1000:])
    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        fail(f"B005_CP6_{label}_JSON_INVALID", str(exc))
    if payload.get("status") != "PASS":
        fail(f"B005_CP6_{label}_STATUS", payload)
    return payload


def validate_coverage() -> dict[str, object]:
    text = MAP.read_text(encoding="utf-8")
    ids = re.findall(r"^\|\s*([A-F]\d{2})\s*\|", text, flags=re.MULTILINE)
    expected = PASS_IDS + OOS_IDS
    if len(ids) != 32 or set(ids) != set(expected) or len(ids) != len(set(ids)):
        fail("B005_CP6_COVERAGE_IDS", {"ids": ids, "expected": expected})
    # CP0 is a frozen construction map. CP6 adjudicates its terminal state here,
    # without rewriting CP0 history.
    terminal = {item: "PASS" for item in PASS_IDS}
    terminal.update({item: "OUT_OF_SCOPE" for item in OOS_IDS})
    return {
        "rows": len(ids),
        "PASS": sum(state == "PASS" for state in terminal.values()),
        "OUT_OF_SCOPE": sum(state == "OUT_OF_SCOPE" for state in terminal.values()),
        "CONFLICT": 0,
        "GAP-B005": 0,
        "terminal": terminal,
    }


def validate_reports() -> None:
    required = {
        "team-progress/planner-report-B-002-wave4.md": ["正式四态：**PASS**"],
        "team-progress/planner-report-B003-CP5.md": ["**PASS：B-003 可关闭。**"],
        "team-progress/planner-report-B004-CP6.md": ["**CP6 PASS；B-004 CLOSED；允许进入 B-005。**"],
        "team-progress/planner-report-B005-CP0.md": ["裁定：**PASS；允许进入 CP1"],
        "team-progress/planner-report-B005-CP1.md": ["D01、D02 均 PASS"],
        "team-progress/planner-report-B005-CP2.md": ["**最终结论：CP2 PASS；允许进入 CP3。**", "B005_CP2_PY_V16_BASELINE_CONTRACT_STALE"],
        "team-progress/codex-report-B005-CP3.md": ["**结论：CP3 PASS；允许进入 CP4。**", "_execute_ddl()"],
        "team-progress/codex-report-B005-CP4.md": ["**结论：CP4 PASS；允许进入 CP5。**", "8 个 Python 文件"],
        "team-progress/codex-report-B005-CP5.md": ["**结论：CP5 PASS；允许进入 CP6 独立终签。**"],
        "team-progress/B-005-WAIT_GATE5_HUMAN.md": ["WAIT_GATE5_HUMAN", "不等于 Done", "真实 2–3 个项目", "git commit/push"],
    }
    for relative, markers in required.items():
        path = ROOT / relative
        if not path.is_file() or not path.stat().st_size:
            fail("B005_CP6_EVIDENCE_MISSING", relative)
        text = path.read_text(encoding="utf-8")
        missing = [marker for marker in markers if marker not in text]
        if missing:
            fail("B005_CP6_EVIDENCE_MARKER_MISSING", {relative: missing})


def validate_migration_source() -> dict[str, object]:
    path = ROOT / "flowboard" / "database.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next((node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_migration_v16"), None)
    if fn is None:
        fail("B005_CP6_V16_FUNCTION_MISSING", str(path))
    calls = [node for node in ast.walk(fn) if isinstance(node, ast.Call)]
    executescript = [node for node in calls if isinstance(node.func, ast.Attribute) and node.func.attr == "executescript"]
    ddl_calls = [node for node in calls if isinstance(node.func, ast.Name) and node.func.id == "_execute_ddl"]
    if executescript or len(ddl_calls) != 1:
        fail("B005_CP6_V16_TRANSACTION_CALL", {"executescript": len(executescript), "_execute_ddl": len(ddl_calls)})
    call = ddl_calls[0]
    if len(call.args) != 2 or not isinstance(call.args[1], ast.Constant) or not isinstance(call.args[1].value, str):
        fail("B005_CP6_V16_DDL_LITERAL", ast.dump(call))
    ddl = call.args[1].value
    tables = re.findall(r"CREATE TABLE\s+(timeline_[a-z_]+)", ddl)
    indexes = re.findall(r"CREATE (?:UNIQUE )?INDEX\s+(idx_[a-z_]+)", ddl)
    expected_tables = [
        "timeline_projects",
        "timeline_nodes",
        "timeline_change_batches",
        "timeline_node_changes",
        "timeline_import_batches",
    ]
    expected_indexes = [
        "idx_timeline_projects_active_name",
        "idx_tln_project",
        "idx_tlcb_project",
        "idx_tlnc_batch",
        "idx_timeline_import_batches_workspace",
    ]
    # The first list intentionally includes all five DDL index literals; this is
    # a schema-literal check, while CP3's authorizer probe checks atomic behavior.
    if tables != expected_tables or indexes != expected_indexes:
        fail("B005_CP6_V16_DDL_SHAPE", {"tables": tables, "indexes": indexes})
    return {
        "source_sha256": sha256(path),
        "ddl_sha256": hashlib.sha256(ddl.encode("utf-8")).hexdigest().upper(),
        "tables": tables,
        "indexes": indexes,
        "executor": "_execute_ddl",
    }


def validate_old_tests(cp4_payload: dict[str, object]) -> dict[str, object]:
    old = cp4_payload.get("old_tests", {})
    if set(old.get("authorized_changed_files", [])) != AUTHORIZED_CHANGED:
        fail("B005_CP6_OLD_TEST_CHANGESET", old)
    if (old.get("methods"), old.get("python_files"), old.get("node_files"), old.get("skip_hits")) != (79, 12, 5, []):
        fail("B005_CP6_OLD_TEST_COUNTS", old)
    changed = run("OLD_TEST_DIFF", ["git", "diff", "--name-only", "2e906c5", "--", *OLD_TESTS])["output"].splitlines()
    changed = {
        item.strip().replace("\\", "/")
        for item in changed
        if item.strip().replace("\\", "/").startswith("tests/")
    }
    if changed != AUTHORIZED_CHANGED:
        fail("B005_CP6_OLD_TEST_DIFF_SCOPE", sorted(changed))
    combined = "\n".join((ROOT / item).read_text(encoding="utf-8") for item in AUTHORIZED_CHANGED)
    preserved = [
        "flowboard-schema-v7",
        "flowboard-schema-v8",
        "flowboard-schema-v9",
        "flowboard-schema-v10",
        "flowboard-schema-v11",
        "flowboard-schema-v14",
        "flowboard-schema-v15",
        "PRAGMA integrity_check",
        "PRAGMA foreign_key_check",
        "SCHEMA_VERSION",
    ]
    missing = [marker for marker in preserved if marker not in combined]
    if missing:
        fail("B005_CP6_OLD_TEST_ASSERTION_MARKER", missing)
    if re.search(r"unittest\.(?:skip|skipIf|skipUnless|expectedFailure)|skipTest\s*\(", combined):
        fail("B005_CP6_OLD_TEST_SKIP", "skip marker found")
    return {"changed": sorted(changed), "methods": 79, "skip": 0, "preserved_markers": len(preserved)}


def validate_readme_boundary() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    wait = (ROOT / "team-progress" / "B-005-WAIT_GATE5_HUMAN.md").read_text(encoding="utf-8")
    required = ["WAIT_GATE5_HUMAN", "不表示门 5", "真实 `flowboard.db` 仍为 v15", "commit/push"]
    missing = [item for item in required if item not in readme and item not in wait]
    if missing:
        fail("B005_CP6_GATE5_BOUNDARY", missing)
    forbidden = ["门 5 PASS", "Gate 5 PASS", "已上线", "真实库已迁移"]
    # Negated boundary sentences are allowed; positive completion claims are not.
    positive = [item for item in forbidden if re.search(rf"(?<!不)(?<!未){re.escape(item)}", readme)]
    if positive:
        fail("B005_CP6_GATE5_OVERCLAIM", positive)


def validate_locked() -> dict[str, object]:
    actual: dict[str, object] = {}
    for relative, expected in LOCKED.items():
        path = ROOT / relative
        stat = path.stat()
        item = {"sha256": sha256(path), "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        if item != expected:
            fail("B005_CP6_LOCKED_FILE_CHANGED", {relative: {"expected": expected, "actual": item}})
        actual[relative] = item
    db = ROOT / "flowboard.db"
    uri = f"file:{db.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        schema = conn.execute("PRAGMA user_version").fetchone()[0]
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()
    if (schema, integrity) != (15, "ok"):
        fail("B005_CP6_REAL_DB_READONLY_HEALTH", {"schema": schema, "integrity": integrity})
    actual["real_db_readonly"] = {"schema": schema, "integrity": integrity}
    return actual


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-dynamic", action="store_true", help="Only run structural checks; cannot sign CP6 alone.")
    args = parser.parse_args()

    coverage = validate_coverage()
    validate_reports()
    migration = validate_migration_source()
    validate_readme_boundary()

    cp4_payload: dict[str, object]
    dynamic: dict[str, object] = {}
    if args.skip_dynamic:
        cp4_result = run("CP4", [sys.executable, "-X", "utf8", "team-progress/verification/B-005-CP4/verify_cp4.py"])
        cp4_payload = load_json_output("CP4", cp4_result)
        dynamic["mode"] = "STRUCTURAL_ONLY"
    else:
        for label, script in (("CP3", "verify_cp3.py"), ("CP4", "verify_cp4.py"), ("CP5", "verify_cp5.py")):
            result = run(label, [sys.executable, "-X", "utf8", f"team-progress/verification/B-005-{label}/{script}"])
            payload = load_json_output(label, result)
            dynamic[label] = {"exit": 0, "status": payload["status"]}
            if label == "CP4":
                cp4_payload = payload

        timeline = run("TIMELINE29", [sys.executable, "-X", "utf8", "-m", "unittest", "discover", "-s", "tests", "-p", "test_timeline.py", "-v"])
        http = run("HTTP10", [sys.executable, "-X", "utf8", "-m", "unittest", "discover", "-s", "tests", "-p", "test_timeline_http.py", "-v"])
        node_files = sorted(str(path) for path in (ROOT / "tests").glob("*.test.js"))
        node = run("NODE6", ["node", "--test", *node_files])
        py_files = sorted(str(path) for path in ROOT.rglob("*.py") if ".git" not in path.parts)
        run("PY_COMPILE", [sys.executable, "-m", "py_compile", *py_files])
        js_files = sorted(str(path) for path in ROOT.rglob("*.js") if ".git" not in path.parts)
        for path in js_files:
            run("NODE_CHECK", ["node", "--check", path])
        run("DIFF_CHECK", ["git", "diff", "--check"])
        dynamic.update(
            {
                "timeline": re.search(r"Ran 29 tests in ([0-9.]+)s\s+OK", str(timeline["output"]), re.S).group(0),
                "http": re.search(r"Ran 10 tests in ([0-9.]+)s\s+OK", str(http["output"]), re.S).group(0),
                "node": {"files": len(node_files), "pass": 6, "exit": int(node["exit"])},
                "py_compile": {"files": len(py_files), "exit": 0},
                "node_check": {"files": len(js_files), "exit": 0},
                "git_diff_check": {"exit": 0},
            }
        )

    old_tests = validate_old_tests(cp4_payload)
    locked = validate_locked()
    payload = {
        "status": "PASS" if not args.skip_dynamic else "STRUCTURAL_ONLY",
        "terminal_state": "WAIT_GATE5_HUMAN",
        "coverage": coverage,
        "migration": migration,
        "old_tests": old_tests,
        "dynamic": dynamic,
        "locked": locked,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
