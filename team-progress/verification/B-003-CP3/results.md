# B-003 CP3 independent evidence

- Date: 2026-08-20
- Probe: `python -X utf8 team-progress/verification/B-003-CP3/probe_cp3_http.py`
- Runtime: temporary migrated DB, OS-selected random port (`61041` on recorded run), real HTTP.
- Result: PASS; no response was 500.

| Area | Observed result |
|---|---|
| R09 auth | no CSRF `403 CSRF_INVALID`; viewer `403 PROJECT_FORBIDDEN`; zero project/node/change writes |
| R09 file boundary | bad base64 `422 IMPORT_FILE_INVALID`; wrong header `422 IMPORT_HEADERS_MISMATCH` |
| R09→R10 | preview `201`, commit `201`, exactly 1 project + 1 node |
| R10 state/ownership | replay `409 TIMELINE_IMPORT_ALREADY_COMMITTED`; other user `404 TIMELINE_IMPORT_BATCH_NOT_FOUND`; cross workspace `403`; demoted viewer `403 PROJECT_FORBIDDEN` |
| R10 race | active same-name created after preview causes `422 NAME_CONFLICT`; count tuple unchanged |
| D4 | same existing project at upload rows 2 and 4 both returned in `details.rows=[2,4]` |
| D5 | multi-sheet preview `201` with `仅导入第一个 sheet`; transformed CSV integer date `422` with xlsx advice |
| D7 | numeric XLSX serial succeeds in positive journey; text integer and fractional numeric each return controlled row-2 `422 VALIDATION_ERROR` |

Regression runs:

- `test_timeline_http.py`: 9/9 PASS.
- `test_timeline.py`: 29/29 PASS.
- `test_secure_foundation.py -k transfer`: 1/1 PASS.

Runtime DB lock:

- SHA-256 before/after: `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D`.
- Size: `446464`; mtime UTC: `2026-08-12 06:31:25`.

Failure-key ledger:

- `TEST_INVOCATION`: one planner occurrence (used dotted module path against non-package tests); corrected to discovery.
- `TEST_PROBE_IMPORT_PATH`: one planner occurrence (standalone probe initially added tests path but not repo root); corrected.
- No failure key repeated twice; no product failure.
