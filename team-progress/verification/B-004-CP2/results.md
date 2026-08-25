# B-004 CP2 independent verification results

## Dynamic browser result

Planner-owned `probe_cp2_browser.py` ran from the production `index.html` / `app.js`
entry against a migrated temporary database, random localhost port and real
headless Chromium. The main agent ran it in a context that permits Playwright's
driver process. Exit 0, JSON `status=PASS`.

It verified:

- real mouse hit-testing for context-menu and menu-item sequences;
- exactly four context actions and a fresh single/cascade selection for every drag;
- `±10 days ×8` zoom-band behavior, cascade predecessor clamp and same-track-only
  propagation, and single-mode predecessor/successor clamps;
- a mixed date/status local draft, exact date and six-stage display sort orders,
  discarded DOM restoration, dismissed navigation preserving the draft, and a
  cancelling `beforeunload` event;
- zero requests throughout context selection, drag, status and sort, plus an
  observed `GET /api/session` positive control proving the request observer was live;
- a fail-capable swallowed-click canary: bad control emitted only `mousedown` and
  action 0; good control emitted `mousedown -> mouseup -> click` and action 1;
- no write to `timeline_projects`, `timeline_nodes`, `timeline_change_batches` or
  `timeline_node_changes`: their canonical content hash and row counts were equal
  before/after discard;
- real `flowboard.db` and all three `.copilot-*` guard files remained byte-identical.

Execution summary: `outside-run.txt`.

## Regression evidence

- `node tests\timeline_ui.test.js`: 9/9 PASS.
- `python -X utf8 -m unittest discover -s tests -p 'test_timeline_http.py'`: 10/10 PASS.
- `python -X utf8 -m unittest discover -s tests -p 'test_timeline.py'`: 29/29 PASS.
- `python -X utf8 -m unittest discover -s tests -p test_timeline_e2e.py -v`,
  executed by the main agent outside the restricted sandbox after CP2 landed:
  exit 0, 4/4 PASS in 13.543s. This includes the CP2 local-draft real-mouse journey
  and all three CP1 browser journeys.
- The restricted planner sandbox itself could not launch Playwright because Windows
  denied the overlapped pipe; no static result was substituted for either of the
  two successful outside browser runs.

## Probe correction log

These were validator defects, not product failures, and each was corrected without
weakening a product assertion:

1. `SORT_DID_NOT_CHANGE_DISPLAY`: the first fixture accidentally had stage order
   equal to date order. The final fixture deliberately differs and asserts exact
   orders (`date=[1,2,3]`, `stage=[2,3,1]`).
2. `SWALLOWED_CLICK_CANARY_BLIND`: the injected control sat behind the production
   modal. The final canary uses an isolated page, proves visibility/bounding boxes,
   then asserts both the bad and good physical hit-testing paths exactly.

There is no outstanding CP2 product failure key.
