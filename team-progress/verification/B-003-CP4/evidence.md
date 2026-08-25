# B-003 CP4 planner evidence

Date: 2026-08-20

## Independent black-box probe

Command: `$env:PYTHONPATH='.'; python -X utf8 team-progress\verification\B-003-CP4\verify_cp4.py`

Final result: `CP4_PLANNER_PASS`.

- Random OS-assigned localhost port and a `TemporaryDirectory` database; no real database used.
- R11 `POST` returned 200 JSON. Strict base64 decode succeeded and SHA-256 of decoded bytes equalled the envelope value.
- Decoded XLSX parsed through the production `parse_upload`: exact 8 headers and one sheet.
- Full active workspace observed: both projects appeared, grouped in stable project-id order.
- Negative controls: GET 404; missing CSRF 403 `CSRF_INVALID`; viewer 403 `PROJECT_FORBIDDEN`; `project_id` and `project_ids` bodies 422 and never succeeded.
- D6 observed order: project → `main, parallel` → date → natural node-name → id.
- Natural-key algorithm confirmed from implementation and adversarial data: split on digit runs, compare numeric runs as integers and text runs lower-cased. Thus `N2 < N10`; `Same` and `same` have the same natural key and preserve creation/id order.
- Decoded R11 bytes passed real R09 preview (201, 7 rows), real R10 commit into workspace 2 (201, 2 projects/7 nodes), then R01 read-back (200, 2 projects/7 nodes).
- After adding rows to exactly 1001, R11 returned 422 `EXPORT_LIMIT`, details `{total:1001,max:1000}`; node count was unchanged across request.

## Regression and static checks

- `python -X utf8 -m unittest discover -s tests -p test_timeline_http.py` → 10/10 OK.
- `python -X utf8 -m unittest discover -s tests -p test_timeline.py` → 29/29 OK.
- Transfer-directed four tests (`group8_excel_negative_controls`, `group9_excel_round_trip_in_new_workspace`, `excel_import_preview_commit_and_export`, `export_exact_1000_and_over_limit_fail_closed`) → 4/4 OK.
- `python -X utf8 -m py_compile server.py flowboard/timeline.py flowboard/transfer.py tests/test_timeline_http.py team-progress/verification/B-003-CP4/verify_cp4.py` → exit 0.

## Safety and hashes

Real `flowboard.db` before/after: SHA-256 `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D`, 446464 bytes, mtime UTC `2026-08-12 06:31:25`; stable.

- `server.py`: `509862B60E8DB7FAB23F61CC8B67C7E39F87A7148D46C77C489EFFECC9621FD8`
- `flowboard/timeline.py`: `D68FA1BD3797263FEAFDA75BD508F86BFCCB73D603E81681A9AB1D878357A8D5`
- `flowboard/transfer.py`: `5364288E96A5ED16133471F5F02742DD8CCA258E7E6D1B7EF5B6311DB96CBC9E`
- `tests/test_timeline_http.py`: `A8F95CEC755CC9C6CFA79820EA3A2774A9C5FC0F2755CC234622EC9FCF41D432`
- `verify_cp4.py`: `BD314EAEC7B9FF5DB03699C98AD0FEEA51EDDA5CA56AED01A7AC499030820837`

## Failure-key ledger

- Product failure keys: none.
- `PLANNER_PYTHONPATH`: once; nested-script import path, corrected by setting repository root in `PYTHONPATH`.
- `PLANNER_IMPORT_FIXTURE_DUPLICATE`: once; exact duplicate row was correctly rejected by R09. Replaced with `Same`/`same`, which shares the natural key but is not a duplicate row.
- No same key occurred twice consecutively.

