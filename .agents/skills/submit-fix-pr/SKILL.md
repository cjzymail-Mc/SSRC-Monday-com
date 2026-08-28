---
name: submit-fix-pr
description: Move completed Flowboard fixes made directly on local main into a temporary fix branch, rebase onto current origin/main, verify them, push, and open a GitHub pull request. Use only when the user explicitly invokes $submit-fix-pr after local testing; do not merge or deploy the pull request.
---

# Submit Fix PR

Turn novice work performed directly on local `main` into a reviewable temporary `fix/*` branch without losing or pushing unrelated state. The outcome is an open pull request targeting `main`; approval, merge, deployment, and release remain human actions.

## Safety contract

- Read `AGENTS.md`, the relevant current feature state, and `README.md` test instructions before acting.
- Preserve every pre-existing user change. Never use `reset --hard`, `clean`, checkout-overwrite, automatic stash, or destructive recovery.
- Never stage, commit, copy, migrate, or test against the real `flowboard.db`, its WAL/SHM files, `backups/`, credentials, `.env` files, or machine-local state.
- Stage explicit paths only. Never use `git add .`, `git add -A`, or a wildcard that can sweep unrelated files into the pull request.
- Do not weaken, delete, or rewrite existing tests to accommodate an incorrect implementation.
- Do not commit, push, create a PR, merge, delete branches, publish, or deploy beyond the workflow and approval described below.

## Preconditions and inspection

1. Verify the repository root, current branch, status, origin, GitHub CLI, and absence of an in-progress Git operation:

   ```powershell
   git rev-parse --show-toplevel
   git branch --show-current
   git status --short --branch
   git remote get-url origin
   git log --oneline origin/main..main
   gh --version
   gh auth status
   ```

2. Review tracked, staged, and untracked paths plus the actual diff. Separate intended fix files from unrelated user work. If the grouping is materially ambiguous, ask one concise question before staging anything.

3. Derive a short lowercase branch slug from the user's summary; use a unique name such as `fix/20260828-timeline-node-menu`. Validate it with `git check-ref-format --branch` and ensure it does not already exist locally or remotely.

## Preserve the novice `main` work

4. When the user is on `main`, create and switch to the fix branch immediately. Uncommitted changes remain in the worktree and move with the checkout:

   ```powershell
   git switch -c <fix-branch>
   ```

   If local `main` already has commits ahead of `origin/main`, record its original commit ID and create a uniquely named `rescue/pre-submit-main-*` branch before any rebase. This safety reference must remain until the PR is merged.

5. Stage only the reviewed paths, inspect the staged diff, and commit with a concise conventional message such as `fix: correct timeline node actions`. Do not commit when there is no intended diff.

## Synchronize and verify

6. Fetch the newest remote state and rebase the fix branch, never local `main`:

   ```powershell
   git fetch --prune origin
   git rebase origin/main
   ```

   Resolve only conflicts whose intended behavior is supported by current code, tests, or frozen contracts. After each resolution inspect the combined diff. If resolution is ambiguous, abort the rebase and report; do not guess.

7. Run the bundled complete-check script from the root. It uses the repository test commands, isolated temporary databases and ports, syntax/whitespace checks, and a before/after SHA-256 guard for the real database:

   ```powershell
   pwsh -NoProfile -File .agents/skills/submit-fix-pr/scripts/run-flowboard-checks.ps1
   ```

   `FLOWBOARD_CHECKS_OK` is required. Any real-database hash change is a hard failure. If sandboxing blocks Chromium or Node subprocesses, request controlled execution rather than skipping coverage. Use `-PlanOnly` only to inspect the planned commands, never as PR acceptance evidence.

8. When checks fail, diagnose and repair only within the submitted fix scope, then rerun the relevant test. Inspect and commit the repair through explicit paths before rerunning the full checks; the final index and worktree must be clean. Stop after two consecutive failed implementation/test cycles, on contract conflict, or when a product decision is required. Never push a failing or dirty branch.

## External submission gate

9. Before the first external write, show the user:

   - branch and commit list relative to `origin/main`;
   - intended changed paths and diff summary;
   - complete test results;
   - proposed PR title and short body;
   - confirmation that the real database was not changed.

   Ask for one explicit confirmation to push and create the PR. Earlier permission to edit or test is not permission to perform these external writes.

10. After confirmation, push without force and create the pull request:

    ```powershell
    git push -u origin <fix-branch>
    gh pr create --base main --head <fix-branch> --title <title> --body <body>
    ```

    If push succeeds but PR creation fails, do not create another branch or force-push. Report the pushed branch and retry only the PR creation step after correcting authentication or metadata.

11. Verify the returned PR URL and remote branch commit. If local `main` had novice commits, realign its pointer to the fetched `origin/main` only after the same work is verified on the pushed fix branch and the rescue reference exists. Because the fix branch is checked out, use an explicit branch-pointer update rather than checking out or overwriting files. Keep the rescue branch and the fix branch until the PR is merged.

12. Leave the checkout on the fix branch and report that the administrator must review and merge the PR. Do not merge, deploy, or delete either branch. After the administrator merges, the next command is `$sync-main`.

## Stop conditions

Stop safely when GitHub CLI is missing or unauthenticated, origin/main is unavailable, unrelated changes cannot be separated, a conflict is ambiguous, tests remain failing after two cycles, the real database changes, or the external submission confirmation is withheld. Report preserved branches/commits and the exact resumable step.
