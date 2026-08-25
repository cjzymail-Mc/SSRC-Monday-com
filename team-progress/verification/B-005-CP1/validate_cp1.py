from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BASELINE = "2e906c5"
EXPECTED_PYTHON = 12
EXPECTED_NODE = 5
LOCKED = (
    "flowboard.db",
    ".copilot-state.json",
    ".copilot-task.md",
    ".copilot-message.md",
)
SKIP_RE = re.compile(
    r"unittest\.(?:skip|skipIf|skipUnless|expectedFailure)\b"
    r"|pytest\.mark\.(?:skip|skipif)\b|\.skip\s*\(|skipTest\s*\("
    r"|\b(?:test|it|describe)\.skip\s*\(|\bskip\s*:\s*true\b"
)


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=ROOT, text=True, encoding="utf-8",
        errors="replace", capture_output=True, check=check,
    )


def flatten(suite: unittest.TestSuite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def ast_tests(source: str) -> list[str]:
    tree = ast.parse(source)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            found.append(node.name)
    return sorted(found)


def fingerprint(path: Path) -> dict[str, object]:
    stat = path.stat()
    digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    return {"sha256": digest, "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def skip_hits(name: str, source: str) -> list[str]:
    return [f"{name}:{source.count(chr(10), 0, match.start()) + 1}:{match.group(0)}"
            for match in SKIP_RE.finditer(source)]


def sha_lines(lines: list[str]) -> str:
    return hashlib.sha256(("\n".join(sorted(lines)) + "\n").encode()).hexdigest().upper()


def main() -> int:
    errors: list[str] = []
    before = {name: fingerprint(ROOT / name) for name in LOCKED}

    baseline_full = git("rev-parse", "--verify", f"{BASELINE}^{{commit}}").stdout.strip()
    tracked = git("ls-tree", "-r", "--name-only", BASELINE, "--", "tests").stdout.splitlines()
    old_python = sorted(p for p in tracked if re.fullmatch(r"tests/test_.*\.py", p))
    old_node = sorted(p for p in tracked if re.fullmatch(r"tests/.*\.test\.js", p))
    if len(old_python) != EXPECTED_PYTHON:
        errors.append(f"OLD_PYTHON_COUNT:{len(old_python)}")
    if len(old_node) != EXPECTED_NODE:
        errors.append(f"OLD_NODE_COUNT:{len(old_node)}")

    blob_rows: list[dict[str, object]] = []
    baseline_test_names: dict[str, list[str]] = {}
    current_test_names: dict[str, list[str]] = {}
    for rel in old_python + old_node:
        path = ROOT / rel
        exists = path.is_file()
        baseline_blob = git("rev-parse", f"{BASELINE}:{rel}").stdout.strip()
        current_blob = ""
        if exists:
            current_blob = git("hash-object", f"--path={rel}", rel).stdout.strip()
        same = exists and baseline_blob == current_blob
        blob_rows.append({
            "path": rel, "exists": exists, "baseline_blob": baseline_blob,
            "current_clean_blob": current_blob, "same": same,
        })
        if not exists:
            errors.append(f"MISSING_OLD_FILE:{rel}")
        elif not same:
            errors.append(f"OLD_BLOB_CHANGED:{rel}")
        if rel.endswith(".py"):
            base_source = git("show", f"{BASELINE}:{rel}").stdout
            current_source = path.read_text(encoding="utf-8")
            baseline_test_names[rel] = ast_tests(base_source)
            current_test_names[rel] = ast_tests(current_source)
            if baseline_test_names[rel] != current_test_names[rel]:
                errors.append(f"OLD_TEST_NAMES_CHANGED:{rel}")

    diff = git("diff", "--name-status", "--find-renames", BASELINE, "--", *old_python, *old_node)
    diff_lines = [line for line in diff.stdout.splitlines() if line.strip()]
    if diff.returncode != 0 or diff_lines:
        errors.append(f"OLD_TEST_DIFF_NONEMPTY:{diff.returncode}:{diff_lines}")

    all_python = sorted((ROOT / "tests").glob("test_*.py"))
    all_node = sorted((ROOT / "tests").glob("*.test.js"))
    all_ast: dict[str, int] = {}
    skip_findings: list[str] = []
    for path in [*all_python, *all_node]:
        source = path.read_text(encoding="utf-8")
        skip_findings.extend(skip_hits(path.relative_to(ROOT).as_posix(), source))
        if path.suffix == ".py":
            all_ast[path.name] = len(ast_tests(source))
    if skip_findings:
        errors.append(f"SKIP_MARKERS:{skip_findings}")

    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_*.py")
    dynamic_ids = sorted(test.id() for test in flatten(suite))
    dynamic_old = [test_id for test_id in dynamic_ids
                   if f"tests/{test_id.split('.')[0]}.py" in old_python]
    dynamic_timeline = [test_id for test_id in dynamic_ids
                        if test_id.split('.')[0] in {"test_timeline", "test_timeline_http", "test_timeline_e2e"}]
    ast_total = sum(all_ast.values())
    baseline_ast_total = sum(len(v) for v in baseline_test_names.values())
    current_old_ast_total = sum(len(v) for v in current_test_names.values())
    timeline_ast = {k: v for k, v in all_ast.items() if k.startswith("test_timeline")}
    if (baseline_ast_total, current_old_ast_total, len(dynamic_old)) != (79, 79, 79):
        errors.append(f"OLD_METHOD_TOTALS:{baseline_ast_total}:{current_old_ast_total}:{len(dynamic_old)}")
    if (ast_total, len(dynamic_ids), len(dynamic_timeline)) != (142, 142, 63):
        errors.append(f"CURRENT_METHOD_TOTALS:{ast_total}:{len(dynamic_ids)}:{len(dynamic_timeline)}")
    if timeline_ast != {"test_timeline.py": 29, "test_timeline_e2e.py": 24, "test_timeline_http.py": 10}:
        errors.append(f"TIMELINE_SPLIT:{timeline_ast}")
    if len(all_node) != 6:
        errors.append(f"CURRENT_NODE_FILES:{len(all_node)}")

    # Positive controls operate only on in-memory values and must be detected.
    missing_control = old_python[1:]
    positive_missing = len(missing_control) != EXPECTED_PYTHON
    positive_skip_hits = skip_hits("memory_control.py", "@unittest.skip('control')\ndef test_control(): pass\n")
    if not positive_missing:
        errors.append("POSITIVE_DELETE_CONTROL_NOT_DETECTED")
    if not positive_skip_hits:
        errors.append("POSITIVE_SKIP_CONTROL_NOT_DETECTED")

    after = {name: fingerprint(ROOT / name) for name in LOCKED}
    if before != after:
        errors.append("LOCKED_FINGERPRINT_CHANGED")

    result = {
        "status": "PASS" if not errors else "FAIL",
        "baseline": baseline_full,
        "old_files": {"python": old_python, "node": old_node},
        "blob_rows": blob_rows,
        "old_diff": {"exit": diff.returncode, "lines": diff_lines, "stderr": diff.stderr.strip()},
        "skip_findings": skip_findings,
        "python_counts": {
            "baseline_old_ast": baseline_ast_total,
            "current_old_ast": current_old_ast_total,
            "current_all_ast": ast_total,
            "current_dynamic": len(dynamic_ids),
            "dynamic_old": len(dynamic_old),
            "dynamic_timeline": len(dynamic_timeline),
            "timeline_ast_split": timeline_ast,
            "old_ids_sha256": sha_lines(dynamic_old),
            "timeline_ids_sha256": sha_lines(dynamic_timeline),
            "all_ids_sha256": sha_lines(dynamic_ids),
        },
        "node_counts": {"old_files": len(old_node), "current_files": len(all_node)},
        "positive_controls": {
            "delete_old_file_detected": positive_missing,
            "skip_marker_detected": bool(positive_skip_hits),
            "skip_marker_hits": positive_skip_hits,
        },
        "locked_before": before,
        "locked_after": after,
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
