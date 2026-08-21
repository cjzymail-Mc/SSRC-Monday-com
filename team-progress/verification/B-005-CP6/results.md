# B-005 CP6 independent verification results

Date: 2026-08-20
Role: independent terminal reviewer
Highest permitted state: `WAIT_GATE5_HUMAN`

## Final validator

- Command: `python -X utf8 team-progress/verification/B-005-CP6/verify_cp6.py`
- Environment: controlled sandbox-external run, required because `node --test` cannot spawn workers in the Windows sandbox.
- Final exit: `0`
- Final JSON status: `PASS`
- Validator SHA-256: `CC5EEAEBB81A35B9BA9F9A60A79FD43252B345367A9F5CFA68829C5D6214FDD2`
- Coverage adjudication: 32/32 unique rows; `PASS=25 / OUT_OF_SCOPE=7 / GAP-B005=0 / CONFLICT=0`.

The CP0 map remains a frozen construction-time record. CP6 does not rewrite its historical `GAP-B005` cells; the terminal states are emitted by the final validator and signed in the CP6 report.

## Representative dynamic rerun

| Check | Final result |
|---|---|
| CP3 validator | exit 0, PASS; authorizer injection remained complete v15 with no timeline tables |
| CP4 validator | exit 0, PASS; 12/12 evidence files and scope audit passed |
| CP5 validator | exit 0, PASS; README/Gate 5 boundary and read-only DB check passed |
| `test_timeline.py` | 29/29, `Ran 29 tests in 26.869s`, OK |
| `test_timeline_http.py` | 10/10, `Ran 10 tests in 18.870s`, OK |
| Node full suite | 6/6 files, exit 0, skip 0 |
| Python `py_compile` | 54/54 repository Python files, exit 0 |
| JavaScript `node --check` | 13/13 repository JS files, exit 0 |
| Literal full-repository `git diff --check` | exit 0; LF/CRLF warnings only, no whitespace error |

The main agent separately ran the post-repair README Python command outside the sandbox. Its reported terminal value is `exit 0`, `Ran 142 tests in 413.528s`, `OK`, including real Chromium. CP6 incorporates that as main-agent external dynamic evidence; the independent reviewer does not claim to have run that 142-test command locally.

## Migration transaction audit

- `flowboard/database.py` SHA-256: `28F75EAA14B60B8CF46E70C1E6EDE8C186062E108E9330F7C36DA91F348F7959`.
- AST inspection found exactly one `_execute_ddl(conn, <literal>)` call in `_migration_v16` and no `executescript()` call.
- DDL literal SHA-256: `026655EE79D45088B2D22CD23DD3E72EE08B3C8FD8C26F0C31A8A1FDA48FF88D`.
- The literal still contains exactly the five frozen timeline tables and five indexes. No column, constraint, index, migration checksum, API or business-rule change is hidden in the transaction repair.
- The CP3 authorizer positive control independently denies `CREATE TABLE timeline_nodes`; final behavior remains v15 with no timeline table or v16 migration row. This directly verifies that replacing `executescript()` with the repository's statement-wise `_execute_ddl()` closes the partial-commit defect.

## Old-test authorization audit

Against Gate 3 commit `2e906c5`, changes among the 17 old test files are exactly these eight Python files:

- `tests/test_collaboration.py`
- `tests/test_dashboards.py`
- `tests/test_i12.py`
- `tests/test_i13.py`
- `tests/test_i13_e2e.py`
- `tests/test_i13_operations.py`
- `tests/test_schedule.py`
- `tests/test_secure_foundation.py`

Old Python methods remain 79/79; old files remain 12 Python + 5 Node; skip hits are zero. The diffs are restricted to current-schema/current-backup-prefix expectations via `SCHEMA_VERSION`. Historical checksums v7/v8/v9/v10/v11/v14/v15, old backup schema assertions, data counts, FK/integrity and permission behavior remain. No old Node file changed.

## Scope and Gate 5 boundary

- CP4 static audit reconfirmed no dark runtime/theme switch, weekly board, timeline rename/restore, md/json import, `project_ids` export, pagination/cache or frozen-out future business capability.
- README and `B-005-WAIT_GATE5_HUMAN.md` state that the real DB remains v15 and that the automatic endpoint is only `WAIT_GATE5_HUMAN`.
- They do not claim Gate 5 PASS, real deployment, real DB migration, commit/push, publication or launch.
- F01–F07 therefore remain `OUT_OF_SCOPE`, not silently converted to PASS.

## Locked objects and read-only runtime DB

| Object | SHA-256 | bytes | mtime_ns |
|---|---|---:|---:|
| `flowboard.db` | `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D` | 446464 | 1786516285465474700 |
| `.copilot-state.json` | `C9EB2A0A0B4E48B7A66DCE279B704DEA32854AB3E5FDA78BDFB0679BB3EE96A7` | 2144 | 1787119255493155900 |
| `.copilot-task.md` | `34A9814963951EB0ACD0A886F33D8746C0ABDE23BD3ABC3317370B9D328F1BCA` | 13690 | 1787104103493621800 |
| `.copilot-message.md` | `FCEEEE50F16D6A85C8FC26DA3847E88BA53C64B9542D57DFF6A299D778515F72` | 7317 | 1787119058694564900 |

All match CP0 exactly. A URI `mode=ro` connection independently returned `PRAGMA user_version=15` and `PRAGMA integrity_check=ok`.

## Preserved validation history

No product failure key occurred in CP6.

1. `B005_CP6_NODE_SANDBOX_SPAWN_EPERM`: one environmental run; all six Node files failed before their test bodies because the sandbox denied worker spawn. The identical suite then passed 6/6 outside the sandbox.
2. `B005_CP6_CP3_NONZERO`: validator-only path construction error (`B-005-3` instead of `B-005-CP3`), corrected without touching product/tests.
3. `B005_CP6_OLD_TEST_DIFF_SCOPE`: validator-only parser admitted Git LF/CRLF warnings into a `--name-only` set, corrected to accept only `tests/` path lines.

The three keys are distinct, each occurred once, and none represents a repeated product failure. Final rerun passed all gates.

Conclusion: CP6 independent verification is PASS. B-005 automatic work is closed only to `WAIT_GATE5_HUMAN`.
