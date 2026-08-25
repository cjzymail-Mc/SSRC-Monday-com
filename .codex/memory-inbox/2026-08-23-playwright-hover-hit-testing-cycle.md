---
title: Playwright hover-reveal hit-testing cycle
date: 2026-08-23
source: codex
status: accepted
reviewer: Mc
accepted_at: 2026-08-25
applied_at: 2026-08-25
destination: .claude/memory/browser-event-order-testing.md
review: pending
scope: cross-project
applicability: shared
producer_platform: codex
destination_candidate: .claude/memory/browser-event-order-testing.md
evidence:
  - timeline.css:89
  - timeline.css:130
  - feature-01-项目时间管理-仪表盘/11-GATE5_UX_REALIGNMENT_TASK.md:447
  - feature-01-项目时间管理-仪表盘/11-GATE5_UX_REALIGNMENT_TASK.md:457
  - tests/test_timeline_e2e.py:581
  - tests/test_gate5_home_e2e.py:206
  - .claude/memory/browser-event-order-testing.md
---

# Proposed canonical addition

Append this as a Playwright actionability sub-pattern under the existing true browser event-order memory.

Symptom: a hover-revealed control resolves as attached, visible, enabled, and stable, but a physical click times out because its center point is intercepted by the row button, a sibling layer, or another underlying element.

Root cause pattern: the control is made pointerable only after the parent enters `:hover`, while Playwright's actionability hit test needs a valid target before the pointer can complete the hover transition. Combining `opacity: 0` with `pointer-events: none` can therefore create a hit-testing cycle even when the locator's visibility assertions appear to pass.

Diagnostic workflow:

1. Capture `getBoundingClientRect()` and computed `opacity`, `visibility`, and `pointer-events` for the intended control.
2. Probe `document.elementFromPoint()` at the control's center and inspect the closest actionable ancestor.
3. Reproduce with a physical pointer click; do not close the test with `force`, DOM `.click()`, or direct handler calls.

Fix rule: preserve the desired visual fade while keeping the action layer eligible for hit-testing, retain `:focus-within` for keyboard access, and show controls directly under `@media (hover: none)`. Validate the final state with real pointer movement and physical click so the test covers browser hit-testing and event order, not just application handlers.
