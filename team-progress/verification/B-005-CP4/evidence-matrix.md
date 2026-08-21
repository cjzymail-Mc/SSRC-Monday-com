# B-005 CP4 D1–D4 evidence matrix

Date: 2026-08-20

| ID | State | Dynamic/original evidence |
|---|---|---|
| A01 | PASS | `verification/B-005-CP3/verify_cp3.py` + `results.md`: non-empty v15 users/workspaces/boards/groups/tasks counts and five task sentinels |
| A02 | PASS | CP3 final JSON: five timeline tables, user_version 16, migration row/checksum v16 exactly once |
| A03 | PASS | CP3 final JSON: non-empty pre-v16 snapshot independently opened as v15 with equal counts/sentinels |
| A04 | PASS | CP3 final JSON: second migrate returned no backup; schema/index/migration count unchanged |
| A05 | PASS | CP3 final JSON: legacy counts equal, five new tables empty, FK clean, integrity ok |
| A06 | PASS | CP3 authorizer failure control: no half table/v16 row; real `flowboard_ops.py` backup→verify→restore→remigrate passed |
| B01 | PASS | `planner-report-B-002-wave4.md` SHA `2B8A...F21A`; `planner-report-B003-CP5.md` SHA `BFA0...FC0C` |
| B02 | PASS | B-003 CP5: R01–R11 success, eight write routes CSRF/zero-write negatives, no GAP/CONFLICT |
| C01 | PASS | `planner-report-B004-CP6.md` SHA `9C54...7876`; independent Chromium stdout SHA `5127...AA4`, E2E 24/24 |
| D01 | PASS | CP4 validator: baseline 12 Python + 5 Node files present; old Python methods 79/79 unchanged |
| D02 | PASS | CP4 validator: exactly eight user-authorized Python schema-contract files changed; old Node unchanged; method names/counts and skip=0; CP2a/CP2b semantic audits retained |
| D03 | PASS | CP2 external full Python/Chromium: 142/142, 323.846s, exit 0 |
| D04 | PASS | CP2 Node: 6/6 files, skip 0 |
| D05 | PASS | CP2 py_compile 28/28; CP3 product/verifier compile exit 0 |
| D06 | PASS | CP2 node --check 13/13 |
| D07 | PASS | User-authorized whitespace-only cleanup; literal full-repo `git diff --check` exit 0 |
| D11 | PASS | This matrix binds every row to original reports, runnable validators and dynamic outputs; verifier computes evidence hashes at runtime |
| D12 | PASS | CP4 static route/UI/source audit: no timeline dark/theme/weekly/future capability; no timeline rename/restore; import only csv/xlsx; export POST has empty-body contract and rejects project_ids |

Deferred by unique ownership, not gaps in CP4:

- A07/D13: CP6 final locked-file comparison.
- D08–D10/E01–E02: CP5 README and `WAIT_GATE5_HUMAN` delivery.
- F01–F07: remain `OUT_OF_SCOPE` for Gate 5/user authorization.

Verifier: `team-progress/verification/B-005-CP4/verify_cp4.py`
SHA-256: `8AF4AC17F571F2299DEE2B7BD0C76EE94DC9F1EB8805D26F256AC8B36E939FE6`
Command: `python -X utf8 team-progress/verification/B-005-CP4/verify_cp4.py`
Result: exit 0, `status=PASS`.
