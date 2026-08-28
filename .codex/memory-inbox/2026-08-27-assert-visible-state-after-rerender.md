---
title: Assert user-visible state rather than stale DOM detachment after rerender
date: 2026-08-27
source: codex
status: proposed
review: pending
scope: cross-project
applicability: shared
producer_platform: codex
destination_candidate: .claude/memory/browser-event-order-testing.md
evidence:
  - timeline-ui.js:28
  - timeline-ui.js:323
  - timeline-ui.js:346
  - tests/test_timeline_e2e.py:1050
  - .claude/memory/browser-event-order-testing.md
---

# Proposed canonical addition

Append this as a rerender-aware assertion pattern under the existing browser event-order testing memory.

When an interaction closes a modal, popover, or transient control and then rerenders its owner, assert the user-observable end state rather than requiring the previously located DOM node to detach.

A valid implementation may first set the old control to `hidden` and then replace its subtree with a newly rendered control that is also hidden. Waiting only for `detached` can therefore time out even though the UI is correctly closed. Conversely, checking only that an old handle disappeared can miss a newly rendered visible replacement.

Testing rule:

1. Re-resolve the locator after the state-changing action when the framework may replace the subtree.
2. Assert `hidden`, `not visible`, or an equivalent accessibility state that matches the user contract.
3. Require `detached` only when DOM removal itself is the specified behavior.
4. Where regressions are plausible, also assert that no visible replacement matching the same semantic locator exists.

This keeps browser tests aligned with observable behavior while remaining robust to legitimate render-cycle replacement.
