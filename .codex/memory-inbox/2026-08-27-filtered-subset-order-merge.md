---
title: Merge filtered-subset reorder into canonical full order by visible anchor
date: 2026-08-27
source: codex
status: proposed
review: pending
scope: cross-project
applicability: shared
producer_platform: codex
destination_candidate: .claude/memory/filtered-subset-order-merge.md
evidence:
  - app.js:400
  - app.js:404
  - tests/test_timeline_e2e.py:288
  - feature-01-项目时间管理-仪表盘/STATE.md:168
---

# Proposed canonical addition

When users reorder items in a filtered or time-scoped view, do not persist only the visible subset and do not create an independent order for that view. Treat the complete user-owned sequence as the canonical order and merge the visible move back into it by anchor.

For one moved item:

1. Remove the moved item from the canonical full sequence.
2. Identify the visible item immediately before or after it in the reordered subset.
3. Insert the moved item before or after that visible anchor in the full sequence.
4. Preserve the relative order of every hidden item.
5. Submit the complete canonical ID sequence, together with the applicable context/version contract, to the server.

Example: canonical order `A, B, C, D, E`, visible subset `A, C, E`, user order `E, A, C` produces canonical order `E, A, B, C, D`. This keeps a single source of truth across full, weekly, monthly, tagged, and other filtered views while preventing hidden-item loss, 409 scope mismatch, or a saved order jumping back after rerender.
