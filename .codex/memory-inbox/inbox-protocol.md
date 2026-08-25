# Codex Memory Inbox Protocol

Codex may read `.claude/auto-memory`, but it must not write there directly. Put proposed reusable knowledge in this directory for review.

## File format

- Filename: `YYYY-MM-DD-short-kebab-topic.md`.
- One reusable claim or workflow per file.
- Required frontmatter (**schema v2** — `scope` + `applicability` are two independent axes since Plan14 P1, §7.2):

```yaml
---
title: Short descriptive title
date: YYYY-MM-DD
source: codex
status: proposed          # proposed | accepted | rejected
review: pending           # pending | deferred (deferred = produced by $today full-autopilot finalizer, awaiting batch review)
scope: project|cross-project|machine-specific      # WHERE it lives (storage axis)
applicability: shared|codex-only|claude-only|skill-bound  # WHO it applies to (consumer axis)
producer_platform: codex
destination_candidate: <path-or-class>              # suggested destination, reviewer may change
evidence:
  - path, command, or URL supporting the claim
---
```

## The two axes are independent

`scope` answers "where does this live"; `applicability` answers "who applies it". A `codex-only` claim with `scope: project` still lives in the shared `.claude/memory/` tree but must be filtered out when Claude reads it. Do not collapse them into a single field.

## Admission test

Admit only knowledge that is evidenced, likely to recur, and changes a future action or decision. Do not admit session summaries, speculative ideas, credentials, raw transcripts, or facts already indexed by `.claude/auto-memory/MEMORY.md`.

## Two proposal modes (Plan14 P1, §7.4)

| mode | producer | `status` / `review` | when |
|--|--|--|--|
| interactive | manual `$mc-update` | `proposed` / `pending` | user lists candidates, picks, then proposal staged |
| deferred-review | `$today` full-autopilot finalizer | `proposed` / `deferred` | mc-expert pre-screens, proposal staged without waiting for user; batch-reviewed later |

Deferred-review does not bypass the human memory gate — the gate moves from "can a proposal be saved" to "can canonical memory be written", matching `signal → proposal → review → apply`.

## Review and destination

1. A human or the existing Claude `/mc-update` review flow checks evidence, duplication, scope, applicability, and wording. It also scans `.codex/memory-inbox/` (M1-Scope, Plan14 P6) so Codex proposals have a consumer.
2. Change `status` to `accepted` or `rejected`; record reviewer and date.
3. Route accepted items per the applicability table in `$mc-update` §③ (shared → auto-memory/memory, codex-only → memory with marker, skill-bound → skill, etc.). `accepted` and `applied` are recorded separately (destination path/date written back).
4. Merge only after explicit human approval. Preserve this inbox file as the audit record or record the destination commit/path before archiving it.

## Legacy files

- Accepted legacy files with a noted destination may remain as audit; do not retro-rewrite their schema solely for formatting.
- Older `proposed` files get missing schema v2 fields filled in on first review, not by an unrelated batch rewrite.
- No pending/accepted/rejected directory tree is created until file count justifies a separate index/state machine.
