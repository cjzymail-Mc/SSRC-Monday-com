# B-005 CP0 independent validation evidence

Date: 2026-08-20  
Command: `python -X utf8 team-progress/verification/B-005-CP0/validate_cp0_map.py`  
Exit: `0`  
Overall: `PASS`

## Real map

- Parsed clause rows: 32; missing/duplicate/extra rows: 0.
- Four-state counts: `PASS=3`, `GAP-B005=22`, `CONFLICT=0`, `OUT_OF_SCOPE=7`.
- CP declarations: CP0 through CP6 each occur exactly once in the CP ownership table.
- Every A01–F07 row has its exact expected single owner/destination and clause-specific semantic tokens.
- D1–D5 are closed structurally without prematurely closing dynamic work: all A/D/E dynamic rows remain `GAP-B005`.
- Gate 5/external exclusions F01–F07 are complete: real 2–3-project trial, precise colours/strong magnet/pixels, the four-part 15-minute smoke, device/deployment, real DB migration, commit/push/deploy, and frozen-scope future abilities.
- Allowed-write parsing accepted only README plus B-005 evidence/report paths. Governance/freeze files, production/tests, real DB, backups, `.git/`, and deprecated `.copilot-*` are not in the allowed subset.

## Inherited PASS evidence

All cited files exist and their terminal text is a real PASS/CLOSED disposition, rather than an earlier REWORK:

| Evidence | SHA-256 | Terminal marker |
|---|---|---|
| `team-progress/planner-report-B-002-wave4.md` | `2B8A2DF80A1CFE59C81219FFE0317D32E0576F7EE5D36B756683F36DBFC5F21A` | `正式四态：PASS` |
| `team-progress/planner-report-B003-CP5.md` | `BFA06519F34344CAEE4C4D2FDAE5E3CAA81C9C443D27A1042AFF8C73C899FC0C` | `PASS：B-003 可关闭` |
| `team-progress/planner-report-B004-CP6.md` | `9C549F688AA7A6A0EC657010E6BDED0AFABB73930933AE8234AEB01F48F87876` | `CP6 PASS；B-004 CLOSED` |

Map SHA-256: `D98FC4115320A672E32ECD6B5845E8E97BABD627AF40E357F0DFFA1FD7DA9F5A`.

## Positive controls (in memory only)

| Mutation | Expected failure | Result |
|---|---|---|
| Delete required A01 mapping | validator rejects with `MISSING_ID` | PASS; validator false, failure keys `MISSING_ID`, `STATE_COUNTS` |
| Replace the B-003 terminal report with a nonexistent evidence path | validator rejects the evidence reference | PASS; validator false, failure key `EVIDENCE_REFERENCE_MISSING` |

Neither mutation was written to the coverage map.

## Locked objects

Before/after hash, byte count, and `mtime_ns` were identical within the validator run:

| Object | SHA-256 | Bytes | mtime_ns |
|---|---|---:|---:|
| `flowboard.db` | `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D` | 446464 | 1786516285465474700 |
| `.copilot-state.json` | `C9EB2A0A0B4E48B7A66DCE279B704DEA32854AB3E5FDA78BDFB0679BB3EE96A7` | 2144 | 1787119255493155900 |
| `.copilot-task.md` | `34A9814963951EB0ACD0A886F33D8746C0ABDE23BD3ABC3317370B9D328F1BCA` | 13690 | 1787104103493621800 |
| `.copilot-message.md` | `FCEEEE50F16D6A85C8FC26DA3847E88BA53C64B9542D57DFF6A299D778515F72` | 7317 | 1787119058694564900 |

Validator SHA-256: `D5CF70F747E88958BEABBC60C4771BBB4459CCE6DF3CEB27CE3E4FA0CB12E7BF`.

The recurring PowerShell profile emitted unrelated sandbox warnings about user-level Git/npm configuration before the command. The validator itself executed and returned the JSON result above with exit 0; no dependency install or external write was attempted.
