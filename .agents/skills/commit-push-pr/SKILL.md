---
name: commit-push-pr
description: Move completed Flowboard fixes made directly on local main into a fresh fix branch, verify them proportionately, commit and push the branch, create a GitHub pull request, then safely return the checkout to current main. Use only when the user explicitly invokes $commit-push-pr after local testing; do not expand the fix, merge, or deploy the pull request.
---

# Commit Push PR

Turn novice work performed directly on local `main` into a reviewable temporary `fix/*` branch without losing or pushing unrelated state. The outcome is an open pull request targeting `main` and a clean checkout returned to current `origin/main`; approval, merge, deployment, and release remain human actions.

## Safety contract

- Read `AGENTS.md`, the relevant current feature state, and `README.md` test instructions before acting.
- Preserve every pre-existing user change. Never use `reset --hard`, `clean`, checkout-overwrite, automatic stash, or destructive recovery.
- Never stage, commit, copy, migrate, or test against the real `flowboard.db`, its WAL/SHM files, `backups/`, credentials, `.env` files, or machine-local state.
- Stage explicit paths only. Never use `git add .`, `git add -A`, or a wildcard that can sweep unrelated files into the pull request.
- Never append a new fix to a branch that already has an open, merged, or closed pull request. Each invocation creates a fresh `fix/*` branch from work that began on `main`.
- Do not weaken, delete, or rewrite existing tests to accommodate an incorrect implementation.
- Submission is a packaging workflow, not a new implementation task. Do not modify code or tests outside the reviewed submission merely to make a broad checker green. A test failure authorizes diagnosis, not repair beyond the user's submitted scope.
- Do not commit, push, create a PR, merge, delete branches, publish, or deploy beyond the workflow and approval described below.

## Preconditions and inspection

1. Verify the repository root, current branch, status, origin, GitHub CLI, and absence of an in-progress Git operation without mutation:

   ```powershell
   git rev-parse --show-toplevel
   git branch --show-current
   git status --short --branch
   git remote get-url origin
   gh --version
   gh auth status
   ```

2. Use the shared deterministic origin validator; `SYNC_MAIN_ORIGIN_OK` is required. It normalizes ordinary GitHub HTTPS and SSH URL forms and accepts only `github.com/cjzymail-Mc/SSRC-Monday-com`:

   ```powershell
   pwsh -NoProfile -File .agents/skills/sync-main/scripts/sync-main.ps1 -ValidateOriginOnly
   ```

   Stop before fetch, staging, or other mutation if the host or repository differs.

3. Require an attached checkout on local `main` before handling the fix. If the current branch is detached or is not `main`, do not stage, commit, rebase, push, or create a PR:

   - Preserve and list any dirty paths. A non-`main` dirty checkout needs an explicit recovery decision because the work may already be mixed with an earlier pull request.
   - For a clean `fix/*` branch, inspect its pull-request state with `gh pr list --state all --head <branch>`. Report whether the earlier PR is open, merged, or closed without merge, then route to `$sync-main`; never reuse that branch.
   - For any other clean branch, report it as an unsupported starting state and route to `$sync-main`.

4. Fetch the newest `origin` state, then inspect the relationship of `main` to `origin/main`:

   ```powershell
   git fetch --prune origin
   git rev-list --left-right --count main...origin/main
   git log --oneline origin/main..main
   ```

   Fetch must happen before deciding whether `main` is ahead or diverged. Record the original `main` commit ID when local-only commits exist.

5. Review tracked, staged, and untracked paths plus the actual diff. Separate intended fix files from unrelated user work. If the grouping is materially ambiguous, ask one concise question before staging anything.

6. Derive a short lowercase branch slug from the user's summary; use a unique name such as `fix/20260828-timeline-node-menu`. Validate it with `git check-ref-format --branch` and ensure it does not already exist locally or remotely after the fetch.

## Preserve the novice `main` work

7. Create and switch to the fresh fix branch immediately. Uncommitted changes remain in the worktree and move with the checkout:

   ```powershell
   git switch -c <fix-branch>
   ```

8. If local `main` already has commits ahead of `origin/main`, create a uniquely named `rescue/pre-submit-main-*` branch pointing at the recorded original `main` commit before any rebase. This safety reference must remain until the PR is merged.

9. Stage only the reviewed paths, inspect the staged diff, and commit with a concise conventional message such as `fix: correct timeline node actions`. Do not commit when there is no intended diff.

## Synchronize and verify

10. Rebase the fix branch, never local `main`, onto the `origin/main` fetched during preflight:

   ```powershell
   git rebase origin/main
   ```

   Resolve only conflicts whose intended behavior is supported by current code, tests, or frozen contracts. After each resolution inspect the combined diff. If resolution is ambiguous, abort the rebase and report; do not guess.

11. Verify in proportion to the submitted diff and reuse credible PASS evidence from the just-completed work. The minimum submission checks are `git diff --check`, syntax checks for changed executable files, focused tests for the touched behavior, and confirmation that protected real-data paths were not changed. Use isolated temporary databases and ports.

    Run the bundled complete checker only when the diff touches permissions, migrations, API/data semantics, deletion/recovery, or several coupled product areas; when existing evidence is insufficient; or when the user explicitly requests full regression:

   ```powershell
   pwsh -NoProfile -File .agents/skills/commit-push-pr/scripts/run-flowboard-checks.ps1
   ```

   When the complete checker is required, `FLOWBOARD_CHECKS_OK` is required. Any guarded-path change is always a hard failure. If sandboxing blocks Chromium or Node subprocesses, request controlled execution rather than skipping required coverage. Use `-PlanOnly` only to inspect the planned commands, never as acceptance evidence.

12. When checks fail, first classify the failure as an in-scope regression, an unrelated/pre-existing failure, a stale test expectation, or an environment/tooling failure. Repair only an in-scope regression. For every other class, preserve the evidence and stop that repair path; do not edit unrelated production files or tests without the user's explicit authorization. Rerun only the relevant check after an in-scope repair, and expand verification only if its risk requires it. Stop after two consecutive failed implementation/test cycles, on contract conflict, scope ambiguity, or when a product decision is required. Never hide a known relevant failure or push a dirty branch.

## External submission gate

13. Before the first external write, show the user:

   - branch and commit list relative to `origin/main`;
   - intended changed paths and diff summary;
   - tests/checks run, their results, and why that verification level matches the diff;
   - proposed PR title and short body;
   - confirmation that the real database was not changed.

   Ask for one explicit confirmation to push and create the PR. Earlier permission to edit or test is not permission to perform these external writes.

14. After confirmation, push without force and create the pull request:

    ```powershell
    git push -u origin <fix-branch>
    gh pr create --base main --head <fix-branch> --title <title> --body <body>
    ```

    If push succeeds but PR creation fails, do not create another branch or force-push. Report the pushed branch and retry only the PR creation step after correcting authentication or metadata.

15. Verify the returned PR URL, its `main` base, and that the remote fix branch points to the tested local commit. If any check fails, keep the PR/branch state intact and stop with the exact resumable step.

16. Return the checkout to a safe start-of-work state only after the PR and remote branch are verified:

   - If local `main` originally had novice commits, first prove that the rescue branch still points to the recorded original commit and that the tested fix commit exists on the pushed branch. While the fix branch remains checked out, realign only the local `main` pointer to the fetched `origin/main` with `git branch -f main origin/main`.
   - Run the bundled `.agents/skills/sync-main/scripts/sync-main.ps1`. `SYNC_MAIN_OK` is required; do not reproduce its branch-switching logic manually.
   - Success requires current branch `main`, a clean index and worktree, and `main == origin/main`. Keep the local fix branch, remote fix branch, and any rescue branch until the administrator merges the PR.

17. Report the PR URL and explain in plain language that the submitted changes remain safely in the PR and will reappear on `main` after the administrator merges it and the user next runs `$sync-main`. Do not merge, deploy, or delete branches.

## Stop conditions

Stop safely when GitHub CLI is missing or unauthenticated, origin points to the wrong repository, the checkout did not start on `main`, origin/main is unavailable, unrelated changes cannot be separated, a conflict is ambiguous, tests remain failing after two cycles, any guarded real-data path changes, or the external submission confirmation is withheld. If submission already succeeded but return-to-main fails, report the live PR and preserved branches without claiming full workflow success. Always state the exact resumable step.
