---
name: sync-main
description: Update Flowboard main before work, during unfinished bug fixes, or after a PR merge; preserve uncommitted work and actively resolve synchronization conflicts. Use only when the user explicitly invokes $sync-main; this does not submit fixes.
---

# Sync Main

Update the main baseline and let the user continue working. Dirty main is supported: unfinished work must not be routed into submission merely to synchronize.

## Safety contract

- Read the repository `AGENTS.md` before acting.
- Never use `reset --hard`, `clean`, checkout-overwrite, forced deletion, `stash pop/drop/clear`, or unattended whole-file ours/theirs selection. Only the bundled script's named recovery stash is permitted; no arbitrary automatic stash.
- Never write, migrate, restore, rebuild, stage, commit or snapshot `flowboard.db`, its WAL/SHM files, `backups/`, attachments, credentials, `.env` files, or machine-local state. Review paths for sensitive/local files beyond the script's known guards. Ignored files stay in place; never use `stash --all`. Guarded tracked or unignored files stop the operation before saving work.
- Do not proceed through an in-progress merge, rebase, cherry-pick, or revert.
- Accept only the configured Flowboard repository `cjzymail-Mc/SSRC-Monday-com` as `origin`; normalize ordinary GitHub HTTPS and SSH URL forms before comparing, and stop on any other host or repository.
- Invocation authorizes fetch, fast-forward, a local recovery stash/ref, restoration and in-scope conflict resolution; not ordinary commits, push, PR creation or deployment. Honor tool approval for network access. Do not edit or run another synchronizer concurrently.

## Workflow

1. Read AGENTS.md once; reuse it if already read and unchanged in this session. Review path names for protected/sensitive work, without reading the repair's full diff or product documents:

   ```powershell
   git status --short --branch
   ```

2. Dirty main is supported. Dirty non-main branches and local-only main commits need a separate recovery decision; suggest `$commit-push-pr` only when that work is ready to submit. Do not print credential contents. Do not inspect application behavior until the result below requires it.

3. Let the helper validate origin, Git operation state and protected paths, fetch once, then judge ahead/diverged. Do not duplicate those commands manually or rewrite main.

4. Use the bundled deterministic script:

   ```powershell
   pwsh -NoProfile -File .agents/skills/sync-main/scripts/sync-main.ps1
   ```

   The script pins one fetched target commit. Dirty main with incoming commits gets a named stash including nonignored untracked files, an immutable snapshot OID, a durable `refs/sync-main/<id>` ref and a per-worktree recovery journal. After fast-forward it applies that exact snapshot with `--index` to preserve staging. With no incoming commits, dirty main remains untouched without a snapshot. Existing stashes remain; numeric positions can change, so identify backups by OID/message.

   Consumers requiring a clean return, especially `commit-push-pr`, must pass `-RequireClean`; it never creates a WIP snapshot. Within the same submission invocation, `-FetchedMainCommit <exact-oid>` also reuses the already-fetched base: it requires `-RequireClean` and an exact match with current origin/main. If that reference changed, exit 17 preserves the checkout; inspect the change or retry normal clean synchronization. Never use fetch reuse for a standalone user sync or a later session. `-ValidateOriginOnly` remains read-only.

   | Result | Required next action |
   | --- | --- |
   | `0`, `mode=unchanged` | Finish immediately. No diff analysis, product tests, snapshots or further fetch. Local uncommitted work may remain. |
   | `0`, `mode=clean` | Clean switch/fast-forward completed. Report synchronization; no product tests by default. |
   | `0`, `mode=wip` | Work restored without Git conflicts. Review local preservation and incoming path/dependency impact only. If unrelated, finish without tests; if relevant, use the smallest affected check. |
   | `0`, `mode=recovered` | Conflict recovery completed. Report the resolution and checks already performed; do not repeat them. |
   | `20 / *_RESOLVE_REQUIRED` or pending recovery | Read [conflict-resolution.md](references/conflict-resolution.md) and actively finish restoration and conflict resolution. This is a handoff to the agent, not a reason to stop on ordinary conflicts. |
   | `21 / *_UPDATE_FAILED` | Inspect journal, HEAD and snapshot; follow the same recovery reference to restore work and address an in-scope obstruction. |
   | `10`, `11`, `12`, `13`, `15`, `16`, `17` | Unsupported start, missing remote, protection guard or stale fetch reuse: preserve work and explain the exact boundary. |
   | Other nonzero | Inspect evidence; no success claim or destructive bypass. |

   The script creates a missing local `main` from `origin/main`. If it exists and has no local-only commits, its effective update is:

   ```powershell
   git switch main
   git merge --ff-only origin/main
   ```

   Never merge a feature branch into `main` locally. `main` is fast-forwarded only from `origin/main`.

5. A successful unchanged/clean route ends here. Do not turn a sync into acceptance testing of all incoming coworker changes. The script does not delete local branches or old snapshots; mention merged branches only if useful to the user.

6. For WIP integration, compare affected paths and dependencies first. No textual conflict alone does not prove compatibility: changed interfaces, shared state or coupled code may require a focused check even across different files. Reuse credible PASS for unchanged relevant behavior. Permission, migration, deletion/recovery and broad coupled changes require proportionate evidence, but do not automatically duplicate an existing adequate PASS. Distinguish unfinished-fix failures from synchronization regressions. Full product regression is exceptional, never a consequence of invoking this skill alone.

7. Keep normal reports to a few lines: main/base, commits received, whether local work remains and whether tests were needed. Include resolution/recovery identifiers when used. WIP success permits a dirty tree but requires preserved work and no unresolved conflicts; synchronization success is not a claim that an unfinished repair passed product acceptance.

## Remote movement and recovery

Each invocation integrates one fetched main commit. Main may advance again during development; do not chase it indefinitely or require a quiet window. Finish the current batch, then a later invocation can integrate further updates. If an IDE background fetch changes origin/main during recovery, the helper still completes against the journal's pinned target and reports `observed_remote_commit` and `remote_reference_changed`; do not claim those additional commits were integrated.

The journal is at `git rev-parse --git-path flowboard-sync-main.json`. It blocks a fresh snapshot of partially restored work. Resume from its phase and immutable IDs using the conflict-resolution reference. Keep recovery stashes/refs even on success; cleanup needs separate explicit authorization.

## Stop conditions

Pause for a real product-intent conflict, missing authority, protected data, invalid origin/network, or unsupported state that cannot be recovered within this workflow. Ordinary textual conflicts must be resolved by the agent. Stop a repair path after three consecutive failures of the same implementation/test or on contract conflict; changing remote commits alone is not a failed repair cycle. Preserve work and state the exact resumable step.
