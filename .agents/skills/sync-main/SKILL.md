---
name: sync-main
description: Synchronize the selected GitHub repository's main before work or after a PR merge. Preserve unfinished changes on main with recoverable snapshots and actively resolve synchronization conflicts. Explicit invocation only; no submission or deployment.
---

# Sync Main

Update the selected repository's main baseline and preserve unfinished work. Dirty main is supported; synchronization must not require submitting an unfinished repair.

## Repository and safety contract

Locate this installed skill's `scripts/sync-main.ps1` and bind its actual resource path to `$SyncScript`; bind `scripts/inspect-repository.ps1` to `$InspectScript`. Use the repository explicitly selected by the user, otherwise the current Git working directory, as `$RepositoryPath`. The skill's location does not define the target repository. Resolve paths with Git and optional repo-local `.agents/git-workflow.json`; read [Repository context](references/repository-context.md) when topology/configuration requires it. No workspace path, product name or fixed GitHub account belongs in the shared skill.

Read applicable AGENTS.md once. Preserve local work; never `reset --hard`, `clean`, overwrite checkout, force-delete, `stash pop/drop/clear`, or choose ours/theirs wholesale. Only the helper's named recovery stash is permitted. Keep ignored files in place; never `stash --all`. Guarded tracked/unignored runtime databases, credentials, actual environment files, backups, attachments and configured project data stop snapshotting. Reviewed dummy environment templates may be tracked. Inspect path names beyond known guards.

Do not proceed through an unrelated merge/rebase/cherry-pick/revert/sequencer. Invocation authorizes fetch, fast-forward, a named local recovery snapshot/ref, restoration and in-scope conflict resolution; no ordinary commit, push, PR or deployment. Do not run/edit another synchronizer concurrently.

## Workflow

1. Inspect local status/path names once, without reading the whole repair or product documents. Resolve target Git root and configuration. If canonical upstream is unknown, use `$InspectScript -RepositoryPath $RepositoryPath -ResolveUpstream`: GitHub repository metadata resolves a fork to its source. A repo-local upstream assertion avoids that API query. If a verified fork lacks a source remote, add a new remote for the verified source; preserve origin and stop on a mismatched existing name. Do not request upstream write access.
2. Dirty main is supported. Dirty non-main branches and local-only main commits require a separate preservation decision; suggest commit-push-pr only for ready-to-submit work. Do not print credentials.
3. Let the helper validate Git state, upstream and protected paths, fetch once, and judge ahead/divergence. Do not duplicate its commands or rewrite main:

   ```powershell
   pwsh -NoProfile -File $SyncScript -RepositoryPath $RepositoryPath
   ```

   When canonical upstream was already resolved, also pass `-ExpectedRepository $UpstreamRepository -Remote $UpstreamRemote` to reuse it. The selected upstream remote may be origin or another verified source remote; never assume origin is the source when it is a contributor fork.

   The helper pins one fetched OID. Dirty main with incoming commits receives a named stash of tracked plus nonignored untracked files, an immutable OID, durable `refs/sync-main/<id>` and a per-worktree journal. After fast-forward it restores the exact snapshot with `--index`. With no incoming commits, dirty main remains untouched without a snapshot. Existing stashes/refs remain; use immutable IDs rather than numeric stash positions.

   Consumers needing clean return pass `-RequireClean`; this never snapshots WIP. In the same submission, `-FetchedMainCommit <exact-oid>` reuses a previously fetched base only with `-RequireClean` and an exact current upstream-ref match. Never reuse fetch evidence for a standalone sync or later session. `-ValidateOriginOnly` is local read-only context inspection, not online verification or product PASS.

   | Result | Action |
   | --- | --- |
   | `0`, unchanged | Finish immediately; no further fetch, snapshots, diff analysis or tests. Local WIP may remain. |
   | `0`, clean | Report clean switch/fast-forward; no product tests by default. |
   | `0`, wip | Review preservation and incoming path/dependency impact; use a focused check only when relevant. |
   | `0`, recovered | Report completed resolution/evidence; do not repeat checks. |
   | `20`, recovery/resolve required | Follow [Active conflict resolution](references/conflict-resolution.md) and finish restoration, not just report ordinary conflicts. |
   | `21`, update failed | Inspect journal, HEAD and snapshot; restore work and address in-scope obstruction. |
   | `10/11/12/13/15/16/17` | Preserve unsupported state, local-only commits, invalid topology, protected data or stale fetch reuse; explain exact boundary. |
   | Other nonzero | Diagnose evidence; no destructive bypass or success claim. |

   Missing local main is created from the verified upstream. Existing main is fast-forwarded only to its pinned upstream main, never from a feature branch. Ignored-file collisions are not overwritten.

4. Unchanged/clean success ends here; do not turn synchronization into acceptance testing of every coworker change. For WIP integration, compare paths/dependencies first; no textual conflicts alone does not prove compatible interfaces or state. Reuse adequate PASS; check resolved/local/affected upstream behavior proportionately. Full regression is exceptional.
5. Report main/base, received commits, remaining work and needed checks briefly. WIP success allows preserved dirty work with no unresolved conflicts; it does not claim an unfinished repair passed acceptance. Keep old branches and recovery references; cleanup needs separate authorization.

## Recovery and remote movement

The generic journal is located by `git rev-parse --git-path git-workflow-sync-main.json`; configured legacy names are recognized to preserve existing recovery. Inspect the helper's reported journal path, phase and immutable IDs before resuming. A pending journal blocks a fresh snapshot of partially restored work.

Each invocation integrates one fetched target. If a background fetch advances the remote ref during recovery, finish against the journal's pinned target and report the newer observed reference separately. Do not chase every later commit or require a quiet window.

Resolve ordinary textual conflicts within this invocation. Stop for incompatible product intent, protected data, missing authority or an unsupported state not recoverable in scope. Stop the same failed resolution/check after three attempts; changing upstream commits alone is not a failed repair cycle. Preserve work and state the precise resumable step.
