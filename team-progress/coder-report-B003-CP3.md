# B-003 CP3 coder report — R09/R10 + D4/D5/D7

Date: 2026-08-20

## Scope

- Modified only `server.py`, `flowboard/timeline.py`, `flowboard/transfer.py`, and `tests/test_timeline_http.py`.
- Did not touch export, UI, orchestration state, `team-task.md`, `team-progress.md`, or `.copilot-*`.

## Implementation

- Made both six-segment HTTP routes reachable and imported `require_text` at the boundary:
  - `POST /api/workspaces/{id}/timeline/imports/preview`
  - `POST /api/workspaces/{id}/timeline/imports/commit`
- Commit now rechecks current workspace membership inside its transaction before reading the preview batch. Demoted viewer, cross-workspace, other-user and replay cases return dedicated 4xx without project/node writes.
- Existing active project names are pre-scanned and all offending upload rows are returned in `NAME_CONFLICT.details.rows` (with the first row retained in `details.row` for compatibility).
- Multi-sheet XLSX defaults to the first sheet and adds warning `仅导入第一个 sheet`.
- CSV integer-like transformed dates now advise `在 Excel 中编辑请改用 .xlsx 导入`.
- Shared transfer parsing retains OOXML numeric-cell provenance via a string-compatible marker. Only numeric integer XLSX cells are converted as serial dates; text integers are rejected; fractional numeric cells remain an explicit row-level 422.

## HTTP evidence

`python -X utf8 -m unittest discover -s tests -p test_timeline_http.py`

- PASS: 9/9.
- Added real preview→commit journey plus CSRF/viewer checks, replay, other-user, cross-workspace, preview-after-demotion, name race with zero writes, all-row conflicts, multi-sheet warning, CSV hint, and XLSX numeric-vs-text cases.
- Each test uses a temporary database and an OS-selected random port.

## Regression evidence

- `python -X utf8 -m unittest discover -s tests -p test_timeline.py` → PASS 29/29.
- `python -X utf8 -m unittest discover -s tests -p test_secure_foundation.py -k transfer` → PASS 1/1.
- `python -X utf8 -m py_compile server.py flowboard/timeline.py flowboard/transfer.py tests/test_timeline_http.py` → PASS.
- `git diff --check -- server.py flowboard/timeline.py flowboard/transfer.py tests/test_timeline_http.py` → PASS (only existing LF/CRLF advisory).

## Failure-key ledger

- `TEST_INVOCATION`: one occurrence; initial dotted-module invocation was incompatible with the non-package `tests/` layout. Corrected to discovery; no product failure.
- `TEST_HELPER_BADZIP`: one occurrence; new two-sheet fixture read sheet bytes after archive writes. Fixed by caching source sheet bytes first.
- `XLSX_TYPE_MARKER_NORMALIZED`: one occurrence; `_check_table` converted the numeric marker to plain `str`. Fixed by preserving the string subclass during bounded normalization.
- No failure key repeated twice; coder fuse did not trigger.

## Frozen hashes / runtime DB safety

- `server.py`: `6B30F05B3DA16AB3D1263B014610702B41765F5C111D701A04E528572E999110`
- `flowboard/timeline.py`: `7E0A6DC8B5300F3FF367648EEA78218B9CDFB8B6D47F54619088BAAC55BBDBBA`
- `flowboard/transfer.py`: `5364288E96A5ED16133471F5F02742DD8CCA258E7E6D1B7EF5B6311DB96CBC9E`
- `tests/test_timeline_http.py`: `82E46FFEBD6392A29E6365D2C1A12530EC2A520E49BA7CE6D9FCF1BAD1202105`
- Real `flowboard.db` before/after SHA-256: `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D`.
- Real DB stat unchanged: length `446464`, mtime UTC `2026-08-12T06:31:25.4654747Z`.

## Coder disposition

CP3 implementation and coder-side verification: PASS. Await independent planner acceptance.
