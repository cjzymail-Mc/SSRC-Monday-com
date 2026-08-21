from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
README = ROOT / "README.md"
EXPECTED_LOCKED = {
    "flowboard.db": "9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D",
    ".copilot-task.md": "34A9814963951EB0ACD0A886F33D8746C0ABDE23BD3ABC3317370B9D328F1BCA",
    ".copilot-state.json": "C9EB2A0A0B4E48B7A66DCE279B704DEA32854AB3E5FDA78BDFB0679BB3EE96A7",
    ".copilot-message.md": "FCEEEE50F16D6A85C8FC26DA3847E88BA53C64B9542D57DFF6A299D778515F72",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> int:
    text = README.read_text(encoding="utf-8")
    commands = (
        "python -m unittest discover -s tests -p 'test_*.py' -v",
        "node --test (Get-ChildItem tests -Filter *.test.js | ForEach-Object FullName)",
        "Get-ChildItem -Recurse -Filter *.py | ForEach-Object { python -m py_compile $_.FullName }",
        "Get-ChildItem -Recurse -Filter *.js | ForEach-Object { node --check $_.FullName }",
        "git diff --check",
    )
    assert all(command in text for command in commands)
    required = (
        "schema v16",
        "timeline_projects",
        "timeline_nodes",
        "timeline_change_batches",
        "timeline_node_changes",
        "timeline_import_batches",
        "pre-v16",
        "142/142",
        "service 29",
        "HTTP 10",
        "Chromium 24",
        "WAIT_GATE5_HUMAN",
        "真实 2–3 个项目",
        "15 分钟手工冒烟",
        "真实 `flowboard.db`",
        "git commit/push",
    )
    assert all(value in text for value in required)
    assert all(value not in text for value in ("门 5 已完成", "已完成上线", "已完成部署"))

    uri = (ROOT / "flowboard.db").resolve().as_uri().replace("file:///", "file:/") + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        real_schema = conn.execute("PRAGMA user_version").fetchone()[0]
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()
    assert real_schema == 15 and integrity == "ok"

    locked = {name: sha(ROOT / name) for name in EXPECTED_LOCKED}
    assert locked == EXPECTED_LOCKED
    print(json.dumps({
        "status": "PASS",
        "commands": len(commands),
        "required_markers": len(required),
        "real_db": {"schema": real_schema, "integrity": integrity},
        "locked": locked,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
