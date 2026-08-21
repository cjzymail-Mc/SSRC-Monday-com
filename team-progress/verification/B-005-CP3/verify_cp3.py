from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from flowboard import database
from flowboard.database import connect, migrate
from test_secure_foundation import create_legacy_database


BASE_TABLES = ("users", "workspaces", "boards", "groups_", "tasks")
TIMELINE_TABLES = {
    "timeline_projects",
    "timeline_nodes",
    "timeline_change_batches",
    "timeline_node_changes",
    "timeline_import_batches",
}
LOCKED = (
    REPO / "flowboard.db",
    REPO / ".copilot-task.md",
    REPO / ".copilot-state.json",
    REPO / ".copilot-message.md",
)


def digest(path: Path) -> dict[str, object]:
    stat = path.stat()
    return {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest().upper(),
        "bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def snapshot_locked() -> dict[str, dict[str, object]]:
    return {path.name: digest(path) for path in LOCKED}


def tables(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {name: conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in BASE_TABLES}


def sentinels(conn: sqlite3.Connection) -> list[tuple[object, ...]]:
    return [
        tuple(row)
        for row in conn.execute(
            "SELECT id,title,status,priority,due,owner_id,description FROM tasks ORDER BY id"
        )
    ]


def create_v15(path: Path) -> tuple[dict[str, int], list[tuple[object, ...]]]:
    create_legacy_database(path)
    conn = connect(path)
    try:
        database._migration_v1(conn, "test-password")
        for version in range(2, 16):
            getattr(database, f"_migration_v{version}")(conn)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 15
        assert conn.execute("SELECT checksum FROM schema_migrations WHERE version=15").fetchone()[0] == "flowboard-schema-v15"
        before = counts(conn)
        rows = sentinels(conn)
        assert all(before[name] > 0 for name in BASE_TABLES)
        assert rows
        assert TIMELINE_TABLES.isdisjoint(tables(conn))
        return before, rows
    finally:
        conn.close()


def assert_v15(path: Path, before: dict[str, int], rows: list[tuple[object, ...]]) -> None:
    conn = connect(path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 15
        assert counts(conn) == before
        assert sentinels(conn) == rows
        assert TIMELINE_TABLES.isdisjoint(tables(conn))
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=16").fetchone()[0] == 0
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def assert_v16(path: Path, before: dict[str, int], rows: list[tuple[object, ...]]) -> dict[str, object]:
    conn = connect(path)
    try:
        current_tables = tables(conn)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 16
        assert TIMELINE_TABLES <= current_tables
        assert counts(conn) == before
        assert sentinels(conn) == rows
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=16").fetchone()[0] == 1
        assert conn.execute("SELECT checksum FROM schema_migrations WHERE version=16").fetchone()[0] == "flowboard-schema-v16"
        timeline_counts = {
            name: conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            for name in sorted(TIMELINE_TABLES)
        }
        assert set(timeline_counts.values()) == {0}
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        shape = {
            name: [tuple(row) for row in conn.execute(f"PRAGMA table_info({name})")]
            for name in sorted(TIMELINE_TABLES)
        }
        indexes = [tuple(row) for row in conn.execute("SELECT name,tbl_name,sql FROM sqlite_master WHERE type='index' AND tbl_name LIKE 'timeline_%' ORDER BY name")]
        return {"timeline_counts": timeline_counts, "shape": shape, "indexes": indexes}
    finally:
        conn.close()


def run_cli(*args: str) -> dict[str, object]:
    command = [sys.executable, "-X", "utf8", str(REPO / "flowboard_ops.py"), *args]
    completed = subprocess.run(command, cwd=REPO, text=True, encoding="utf-8", capture_output=True)
    if completed.returncode != 0:
        raise AssertionError(
            f"CLI failed ({completed.returncode}): {' '.join(command)}\nstdout={completed.stdout}\nstderr={completed.stderr}"
        )
    assert completed.stdout.strip(), "CLI produced no JSON"
    return json.loads(completed.stdout)


def main() -> int:
    locked_before = snapshot_locked()
    result: dict[str, object] = {"status": "REWORK"}
    with tempfile.TemporaryDirectory(prefix="flowboard-b005-cp3-") as temp_name:
        root = Path(temp_name)

        normal = root / "normal" / "seeded-v15.db"
        normal.parent.mkdir(parents=True)
        before, rows = create_v15(normal)
        backup = migrate(normal)
        assert backup is not None
        backup_path = Path(backup)
        assert backup_path.is_file() and backup_path.stat().st_size > 0
        assert "-pre-v16-" in backup_path.name
        assert_v15(backup_path, before, rows)
        first_v16 = assert_v16(normal, before, rows)
        backup_names = sorted(path.name for path in backup_path.parent.iterdir())
        second = migrate(normal)
        assert second is None
        second_v16 = assert_v16(normal, before, rows)
        assert first_v16["shape"] == second_v16["shape"]
        assert first_v16["indexes"] == second_v16["indexes"]
        assert sorted(path.name for path in backup_path.parent.iterdir()) == backup_names

        failure = root / "failure" / "seeded-v15.db"
        failure.parent.mkdir(parents=True)
        fail_before, fail_rows = create_v15(failure)
        original_v16 = database._migration_v16

        def denied_v16(conn: sqlite3.Connection) -> None:
            def authorizer(action: int, arg1: str | None, _arg2: str | None, _db: str | None, _source: str | None) -> int:
                if action == sqlite3.SQLITE_CREATE_TABLE and arg1 == "timeline_nodes":
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK

            conn.set_authorizer(authorizer)
            try:
                original_v16(conn)
            finally:
                conn.set_authorizer(None)

        database._migration_v16 = denied_v16
        failure_error = ""
        try:
            migrate(failure)
        except sqlite3.DatabaseError as error:
            failure_error = f"{type(error).__name__}: {error}"
        finally:
            database._migration_v16 = original_v16
        assert failure_error, "failure injection did not fail"
        assert_v15(failure, fail_before, fail_rows)

        attachments = root / "failure" / "attachments"
        backups = root / "failure" / "ops-backups"
        attachments.mkdir()
        backup_json = run_cli(
            "--db", str(failure), "--attachments", str(attachments), "--backups", str(backups), "backup"
        )
        package = Path(str(backup_json["package"]))
        verify_json = run_cli(
            "--db", str(failure), "--attachments", str(attachments), "--backups", str(backups), "verify", str(package)
        )
        assert verify_json["schema_version"] == 15
        migrate(failure)
        assert_v16(failure, fail_before, fail_rows)
        restore_json = run_cli(
            "--db", str(failure), "--attachments", str(attachments), "--backups", str(backups), "restore", str(package)
        )
        assert restore_json["restored"] is True and restore_json["schema_version"] == 15
        assert_v15(failure, fail_before, fail_rows)
        migrate(failure)
        restored_v16 = assert_v16(failure, fail_before, fail_rows)

        locked_after = snapshot_locked()
        assert locked_after == locked_before
        result = {
            "status": "PASS",
            "normal": {
                "baseline_counts": before,
                "sentinel_rows": len(rows),
                "backup": backup_path.name,
                "timeline_counts": first_v16["timeline_counts"],
                "idempotent": True,
            },
            "failure_injection": {
                "error": failure_error,
                "remained_v15_without_timeline_tables": True,
            },
            "offline_cli": {
                "backup_verified_schema": verify_json["schema_version"],
                "restore_schema": restore_json["schema_version"],
                "remigrated_to_v16": restored_v16["timeline_counts"],
            },
            "locked": locked_after,
        }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
