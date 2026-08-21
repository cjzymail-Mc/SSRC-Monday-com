from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BASELINE = "2e906c5"
EXPECTED_CHANGED_OLD = {
    "tests/test_collaboration.py",
    "tests/test_dashboards.py",
    "tests/test_i12.py",
    "tests/test_i13.py",
    "tests/test_i13_e2e.py",
    "tests/test_i13_operations.py",
    "tests/test_schedule.py",
    "tests/test_secure_foundation.py",
}
EXPECTED_LOCKED = {
    "flowboard.db": "9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D",
    ".copilot-task.md": "34A9814963951EB0ACD0A886F33D8746C0ABDE23BD3ABC3317370B9D328F1BCA",
    ".copilot-state.json": "C9EB2A0A0B4E48B7A66DCE279B704DEA32854AB3E5FDA78BDFB0679BB3EE96A7",
    ".copilot-message.md": "FCEEEE50F16D6A85C8FC26DA3847E88BA53C64B9542D57DFF6A299D778515F72",
}
EVIDENCE = (
    "team-progress/planner-report-B-002-wave4.md",
    "team-progress/planner-report-B003-CP5.md",
    "team-progress/planner-report-B004-CP6.md",
    "team-progress/verification/B-004-CP6/outside-run.txt",
    "team-progress/planner-report-B005-CP1.md",
    "team-progress/verification/B-005-CP1/results.md",
    "team-progress/planner-report-B005-CP2.md",
    "team-progress/verification/B-005-CP2/main-agent-external-python-results.md",
    "team-progress/verification/B-005-CP2/d07-final.md",
    "team-progress/codex-report-B005-CP3.md",
    "team-progress/verification/B-005-CP3/results.md",
    "team-progress/verification/B-005-CP3/verify_cp3.py",
)
SKIP_RE = re.compile(
    r"unittest\.(?:skip|skipIf|skipUnless|expectedFailure)\b"
    r"|pytest\.mark\.(?:skip|skipif)\b|\.skip\s*\(|skipTest\s*\("
    r"|\b(?:test|it|describe)\.skip\s*\(|\bskip\s*:\s*true\b"
)


def git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=ROOT, text=True, encoding="utf-8", errors="replace", capture_output=True
    )
    if completed.returncode:
        raise AssertionError(f"git {' '.join(args)} failed: {completed.stderr}")
    return completed.stdout


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def methods(source: str) -> list[str]:
    tree = ast.parse(source)
    return sorted(
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
    )


def main() -> int:
    tracked = git("ls-tree", "-r", "--name-only", BASELINE, "--", "tests").splitlines()
    old_python = sorted(path for path in tracked if re.fullmatch(r"tests/test_.*\.py", path))
    old_node = sorted(path for path in tracked if re.fullmatch(r"tests/.*\.test\.js", path))
    assert len(old_python) == 12 and len(old_node) == 5
    assert all((ROOT / path).is_file() for path in old_python + old_node)

    changed_lines = git("diff", "--name-status", BASELINE, "--", *old_python, *old_node).splitlines()
    assert all(line.startswith("M\t") for line in changed_lines)
    changed = {line.split("\t", 1)[1] for line in changed_lines}
    assert changed == EXPECTED_CHANGED_OLD
    assert not (set(old_node) & changed)

    baseline_names: list[str] = []
    current_names: list[str] = []
    for path in old_python:
        baseline_source = git("show", f"{BASELINE}:{path}")
        current_source = (ROOT / path).read_text(encoding="utf-8")
        before = methods(baseline_source)
        after = methods(current_source)
        assert before == after
        baseline_names.extend(f"{path}:{name}" for name in before)
        current_names.extend(f"{path}:{name}" for name in after)
    assert len(baseline_names) == len(current_names) == 79

    skip_hits: list[str] = []
    for path in sorted((ROOT / "tests").glob("test_*.py")) + sorted((ROOT / "tests").glob("*.test.js")):
        source = path.read_text(encoding="utf-8")
        skip_hits.extend(f"{path.name}:{m.group(0)}" for m in SKIP_RE.finditer(source))
    assert skip_hits == []

    timeline_source = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in ("timeline-ui.js", "timeline.css", "flowboard/timeline.py")
    )
    forbidden = re.compile(
        r"dark|theme|暗色|weekly|每周|workload|\bokr\b|工时|预算|审批|automation|webhook|\bcrm\b|\bsso\b|原生\s*app",
        re.IGNORECASE,
    )
    scope_hits = [m.group(0) for m in forbidden.finditer(timeline_source)]
    assert scope_hits == []

    server = (ROOT / "server.py").read_text(encoding="utf-8")
    start = server.index('parts[3]=="timeline"')
    end = server.index('parts[3:]==["events","poll"]', start)
    timeline_routes = server[start:end]
    assert '"timeline","restore"' not in timeline_routes
    assert '"timeline","rename"' not in timeline_routes
    export_start = timeline_routes.index('["timeline","export"]')
    export_end = timeline_routes.index('["timeline","projects"]', export_start)
    export_block = timeline_routes[export_start:export_end]
    assert 'method=="POST"' in export_block
    assert "reject_unknown(data, set())" in export_block
    assert "project_ids" not in export_block

    transfer = (ROOT / "flowboard" / "transfer.py").read_text(encoding="utf-8")
    assert 'lower.endswith(".csv")' in transfer and 'lower.endswith(".xlsx")' in transfer
    assert "仅支持 .csv 和 .xlsx" in transfer

    evidence = {}
    for rel in EVIDENCE:
        path = ROOT / rel
        assert path.is_file() and path.stat().st_size > 0
        evidence[rel] = {"sha256": sha(path), "bytes": path.stat().st_size}

    locked = {name: sha(ROOT / name) for name in EXPECTED_LOCKED}
    assert locked == EXPECTED_LOCKED

    result = {
        "status": "PASS",
        "old_tests": {
            "python_files": len(old_python),
            "node_files": len(old_node),
            "methods": len(current_names),
            "authorized_changed_files": sorted(changed),
            "skip_hits": skip_hits,
        },
        "scope_audit": {
            "forbidden_timeline_hits": scope_hits,
            "timeline_restore_route": False,
            "timeline_rename_route": False,
            "export_accepts_project_ids": False,
            "import_formats": ["csv", "xlsx"],
        },
        "evidence": evidence,
        "locked": locked,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
