# B-003 CP5 planner evidence

Date: 2026-08-20

## Independent same-disk probe

Command: `python -X utf8 team-progress/verification/B-003-CP5/verify_cp5.py`

Result: PASS. One `TemporaryDirectory` database and one OS-assigned random port carried all checks.

- 11/11 success routes: R01/R02/R03/R06/R07/R08/R11 returned 200; R04/R09/R10 returned 201; R05 returned 200.
- R04–R11 (all eight write routes) each returned 403 `CSRF_INVALID` without a token.
- Each CSRF request had an exact before/after snapshot of all rows in `timeline_projects`, `timeline_nodes`, `timeline_change_batches`, `timeline_node_changes`, `timeline_import_batches`, and `audit_log`; counts and serialized-content SHA-256 were unchanged.
- Independent negative controls passed: viewer read 403, member writes another user's project 403, member admin-only delete 403, cross-workspace delete 403, version conflict 409, stale undo 409, import replay 409, import race 422, export GET 404, soft-deleted correction 404.
- Every negative control used the same six-table full-row snapshot, so UPDATE changes as well as inserts/deletes would be detected.
- R11 decoded base64 SHA-256 equalled the response envelope.

The verifier is retained beside this evidence and is directly rerunnable.

## Regression/static checks

- `python -X utf8 -m unittest discover -s tests -p test_timeline_http.py -v` -> 10/10 OK.
- `python -X utf8 -m unittest discover -s tests -p test_timeline.py` -> 29/29 OK.
- Four directed transfer/timeline tests selected with `-k` -> 4/4 OK.
- `python -X utf8 -m py_compile server.py flowboard/timeline.py flowboard/transfer.py tests/test_timeline_http.py team-progress/verification/B-003-CP5/verify_cp5.py` -> exit 0.
- B-003 scoped `git diff --check` -> exit 0. Repository-wide check still reports pre-existing trailing whitespace in `mc-plan/Mc思考01-阶段完工-下阶段计划.md` lines 1053/1121, outside B-003 and untouched by planner.

## Safety locks

Real `flowboard.db` before/after: SHA-256 `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D`, 446464 bytes, mtime UTC `2026-08-12 06:31:25`; unchanged.

Frozen protocol files before/after:

- `.copilot-state.json`: `C9EB2A0A0B4E48B7A66DCE279B704DEA32854AB3E5FDA78BDFB0679BB3EE96A7`
- `.copilot-task.md`: `34A9814963951EB0ACD0A886F33D8746C0ABDE23BD3ABC3317370B9D328F1BCA`
- `.copilot-message.md`: `FCEEEE50F16D6A85C8FC26DA3847E88BA53C64B9542D57DFF6A299D778515F72`

Implementation/test hashes were stable relative to CP4: server `509862B6...621FD8`, timeline `D68FA1BD...A8D5`, transfer `5364288E...BC9E`, HTTP tests `A8F95CEC...D432`.

## Failure-key ledger

- Product failure key: none.
- `PLANNER_TEST_IMPORT_PATH`: once; initial module-style unittest invocation was invalid because `tests` is not a package. Discovery rerun passed 10/10.
- `PLANNER_TRANSFER_PATTERN`: once; `test_transfer.py` does not exist. Correct four named tests in `test_timeline.py` passed 4/4.
- No same key occurred twice consecutively.
