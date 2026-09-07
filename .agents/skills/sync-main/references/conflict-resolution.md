# Active conflict resolution

Read this when either sync-main restoration or commit-push-pr rebase conflicts. The agent owns resolving ordinary conflicts and verifying the combined behavior within this invocation. A script exit or conflict list is evidence, not completion.

## Decide and resolve

1. Read the actual base, incoming main change and local repair, surrounding callers, tests and contracts. Preserve both intended behaviors where compatible. Adapt the repair to renamed files, new interfaces or upstream refactors as needed; do not expand unrelated product scope. For deletions, check whether the behavior moved before restoring an obsolete file.
2. Make the smallest supported resolution, stage explicit resolved paths and inspect the combined diff. Never select ours/theirs for all files. In a rebase these labels are easy to reverse: inspect commits/content. Continue through subsequent conflicting commits. Routine textual conflicts do not require approval.
3. Verify that both the repair and relevant incoming behavior survive, then run appropriate tests on the combined result. Do not delete tests or rewrite expectations merely to force PASS. Stop after three consecutive failures of the same resolution/check, on a contract conflict, or when evidence cannot determine an incompatible product decision. Show the concrete decision and preserve resumable state.

## sync-main: recovering unfinished work

Read the per-worktree journal; confirm target, originalHead, snapshot OID and snapshotRef. Never assume the backup is `stash@{0}`. For snapshot `S`, `S^1` is the original HEAD, `S^2` the original index, `S` the tracked working tree, and `S^3` (when present) the untracked tree. Quote revision arguments in PowerShell.

- `git diff S^1 S^2`: previously staged edits.
- `git diff S^2 S`: previously unstaged edits.
- `git ls-tree -r S^3`: saved untracked inventory.

For `restoring` / `restore_failed`:

1. Inspect status and the journal first. `stash apply --index` may fail before restoring anything when its index patch conflicts, or may partially restore files. Never blindly apply again.
2. Only if status/diff prove both index and worktree remain clean at the journal target, including no restored untracked files, apply the saved OID **once without `--index`** to obtain the tracked three-way merge. Otherwise resolve from the current partial result and snapshot blobs, without double-applying hunks. Leave ignored-file collisions in place; do not force restoration over them.
3. Resolve using the shared procedure. Restore every saved untracked path, or reconcile its content with an incoming tracked counterpart. Account for all local paths/hunks, including deletions, renames and binary files. Do not execute arbitrary snapshot content to recover files.
4. Preserve staging where it maps cleanly. `git add -- <resolved-path>` clears an unmerged entry. For formerly entirely unstaged paths, `git restore --staged -- <path>` then returns only that resolved path to unstaged status without changing worktree content. For partially staged paths reconstruct intended staged hunks from `S^2` with an explicit patch or temporary index; do not sweep in unrelated edits. If overlapping edits make the previous split meaningless, keep the resolved file unstaged and disclose this; original staged content remains in the backup. This staging adjustment is not permission to discard content.
5. Verify the combined diff/behavior and absence of unmerged entries, then acknowledge completion:

   ```powershell
   pwsh -NoProfile -File .agents/skills/sync-main/scripts/sync-main.ps1 -CompleteRecovery -RecoverySnapshot <exact-oid>
   ```

   This checks journal identity, branch/base, unmerged entries and diff integrity; it does not replace semantic review/tests. Do not initiate fetch during recovery. If a background fetch has advanced origin/main anyway, finish against the journal target and report the newer observed reference separately before another sync batch.

For `saving` / `saved` or an update failure: inspect the stash reflog for the journal's unique label if its OID is not recorded. Confirm which writes completed. If HEAD remains originalHead and index/worktree are clean, restore the exact snapshot with `--index`, verify original tracked/index/untracked content, then remove only this journal and retry after fixing the obstruction. If HEAD reached target, continue restoration as above; change journal phase only after proving that state. If HEAD moved elsewhere or the snapshot is missing, preserve everything and report the recovery decision. Never clear a journal to suppress an unexplained failure. Keep all recovery stashes/refs.

## commit-push-pr: rebasing completed work

Record the pre-rebase fix OID and retain it under a unique local `rescue/pre-rebase-*` reference before each rebase, protecting work across interruptions and refreshes. Rebase onto the recorded fetched origin/main OID; resolve each conflict as above, stage explicit paths, then `git -c core.editor=true rebase --continue`. Do not skip commits just to finish. If Git omits a patch already upstream, prove its effect is present.

Compare pre/post repair commits (for example `git range-diff` with recorded old/new bases) and the final diff against the new base. Verify local fixes and relevant upstream behavior. Resolution changes test evidence: run checks required by that impact.

When intent is ambiguous, keep the pre-rebase reference; abort only when safe and retain useful resolution work first. Describe the specific semantic decision. Do not stop or abort solely because Git reported a routine conflict.
