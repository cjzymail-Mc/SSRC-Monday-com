# B-005 CP3 verification results

Date: 2026-08-20

## Initial failure and root cause

- First verifier run: exit 1.
- Product failure key: `B005_CP3_V16_MIGRATION_PARTIAL_WRITE` (first occurrence).
- Injection: SQLite authorizer denied `CREATE TABLE timeline_nodes` while `_migration_v16` was running.
- Evidence: `PRAGMA user_version` and legacy rows remained at v15, but `timeline_projects` had already persisted.
- Root cause: `_migration_v16` used `conn.executescript()` inside `transaction(conn)`; `executescript()` implicitly committed the outer transaction.

Before modifying the core migration file, the required mc-expert review was performed. It was a Codex custom simulation, not the native Claude mc-expert. The review found no sealed SQLite-specific central-KB decision, but cited the repository's existing `_execute_ddl()` helper, whose stated purpose is avoiding `executescript` implicit commits. Confidence: high.

## Minimal product repair

- File: `flowboard/database.py`
- Change: `_migration_v16` now calls the existing `_execute_ddl(conn, script)` inside the existing `transaction(conn)`.
- Unchanged: all five table definitions, indexes, migration checksum/description, `PRAGMA user_version=16`, APIs and business behavior.
- Final SHA-256: `28F75EAA14B60B8CF46E70C1E6EDE8C186062E108E9330F7C36DA91F348F7959`.

## Verifier history

- One verifier-only key occurred after the product fix: `B005_CP3_VERIFY_CLI_PRETTY_JSON`. The CLI emits indented multi-line JSON; the verifier was corrected to parse complete stdout. This did not represent a product failure.
- Final verifier SHA-256: `1639CEF4D500EB6AB657E2A6A3783F44772A7F3C526F483A8E0572324CE0949B`.
- Final command: `python -X utf8 team-progress/verification/B-005-CP3/verify_cp3.py`
- Final exit: `0`

Final JSON facts:

- v15 baseline counts: users 2, workspaces 1, boards 1, groups 2, tasks 5; five task sentinel rows.
- Normal v15→v16: one non-empty `pre-v16` snapshot; all legacy counts/rows preserved; five timeline tables present and empty; migration row v16 exactly once; FK/integrity clean.
- Idempotence: second `migrate()` returned `None`; no additional backup; table/index shape unchanged.
- Injected failure: `DatabaseError: not authorized`; database remained v15; no timeline table and no v16 migration row persisted; legacy rows and integrity/FK remained clean.
- Offline CLI: `flowboard_ops.py backup` → `verify` reported schema 15 → migrate to v16 → `restore` returned schema 15 → migrate again to v16 successfully.
- Real `flowboard.db` and `.copilot-task.md` / `.copilot-state.json` / `.copilot-message.md`: SHA-256, size and mtime_ns unchanged.

## Existing regression

- Command: `python -X utf8 -m unittest discover -s tests -p "test_timeline.py" -v`
- Result: `Ran 29 tests in 26.105s` — `OK`.
- `python -m py_compile` for product/verifier: exit 0.
- Literal `git diff --check`: exit 0.

Conclusion: `CP3 PASS`.
