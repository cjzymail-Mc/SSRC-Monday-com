---
name: commit-push-pr
description: Move completed Flowboard fixes made directly on local main into a fresh fix branch, refresh and rebase onto current origin/main, reuse fresh test evidence and run only risk-triggered checks, push the branch to the authenticated contributor's public fork, create a pull request against the upstream repository, then safely return the checkout to main. Use only when the user explicitly invokes $commit-push-pr after local testing; do not request upstream write access, expand the fix, merge, or deploy the pull request.
---

# Commit Push PR

Turn novice work performed directly on local `main` into a reviewable temporary `fix/*` branch without losing or pushing unrelated state. For a contributor account, push that branch to the contributor-owned public fork and open the pull request against the upstream `main`; do not require Collaborator or Write access to the upstream repository. The outcome is an open pull request targeting upstream `main` and a clean checkout returned to current `origin/main`; approval, merge, deployment, and release remain human actions.

## Safety contract

- Read `AGENTS.md`, the relevant current feature state, and `README.md` test instructions before acting.
- Preserve every pre-existing user change. Never use `reset --hard`, `clean`, checkout-overwrite, automatic stash, or destructive recovery.
- Never stage, commit, copy, migrate, or test against the real `flowboard.db`, its WAL/SHM files, `backups/`, credentials, `.env` files, or machine-local state.
- Stage explicit paths only. Never use `git add .`, `git add -A`, or a wildcard that can sweep unrelated files into the pull request.
- Never append a new fix to a branch that already has an open, merged, or closed pull request. Each invocation creates a fresh `fix/*` branch from work that began on `main`.
- Keep `origin` permanently pointed at `github.com/cjzymail-Mc/SSRC-Monday-com`; it is the authoritative upstream used for fetch, rebase, comparison, and `$sync-main`. Never rename, delete, or retarget it to a contributor fork.
- When the authenticated GitHub account is not `cjzymail-Mc`, push only to that account's verified fork through a remote named `contributor-fork`. Public visibility grants fork/PR access, not direct upstream push access. Do not request Collaborator/Write access or fall back to pushing `origin`.
- Creating a GitHub fork is an external write covered by the submission confirmation below. During preflight, inspect whether the fork exists but do not create it.
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

   Stop before fetch, staging, or other mutation if the host or repository differs. Treat `origin` as read-only upstream throughout the contributor workflow; branch protection is not a substitute for selecting the correct push remote.

   Determine the authenticated account and submission topology without mutation:

   ```powershell
   $upstream = "cjzymail-Mc/SSRC-Monday-com"
   $contributor = gh api user --jq .login
   gh repo view $upstream --json nameWithOwner,visibility
   gh api "repos/$contributor/SSRC-Monday-com" --jq '{full_name: .full_name, fork: .fork, source: .source.full_name}'
   ```

   A `404` from the final inspection means the contributor fork does not yet exist; record that it must be created after confirmation rather than treating it as upstream denial. If `$contributor` is not `cjzymail-Mc`, require the upstream repository to be public and use `<contributor>/SSRC-Monday-com` as the submission fork. If that same-name repository already exists, require `fork == true` and `source == cjzymail-Mc/SSRC-Monday-com`; stop rather than overwrite or repurpose an unrelated repository. If a local `contributor-fork` remote already exists, validate that it points to this exact fork; never repair a mismatch with `git remote set-url`. Only the authenticated upstream owner may use `origin` as the push target.

3. Require an attached checkout on local `main` before handling the fix. If the current branch is detached or is not `main`, do not stage, commit, rebase, push, or create a PR:

   - Preserve and list any dirty paths. A non-`main` dirty checkout needs an explicit recovery decision because the work may already be mixed with an earlier pull request.
   - For a clean `fix/*` branch, inspect its pull-request state explicitly against the upstream repository with `gh pr list --repo cjzymail-Mc/SSRC-Monday-com --state all --head "<contributor>:<branch>"`. Report whether the earlier PR is open, merged, or closed without merge, then route to `$sync-main`; never reuse that branch.
   - For any other clean branch, report it as an unsupported starting state and route to `$sync-main`.

4. Fetch the newest `origin` state, then inspect the relationship of `main` to `origin/main`:

   ```powershell
   git fetch --prune origin
   git rev-list --left-right --count main...origin/main
   git log --oneline origin/main..main
   ```

   Fetch must happen before deciding whether `main` is ahead or diverged. Record both the fetched `origin/main` commit ID and the original local `main` commit ID when local-only commits exist. The fetched remote commit is the initial submission base and must be refreshed again before push.

5. Review tracked, staged, and untracked paths plus the actual diff. Separate intended fix files from unrelated user work. If the grouping is materially ambiguous, ask one concise question before staging anything.

6. Derive a short lowercase branch slug from the user's summary; use a unique name such as `fix/20260828-timeline-node-menu`. Validate it with `git check-ref-format --branch` and ensure it does not already exist locally, on upstream, or on an already-existing contributor fork after the fetch. Do not reuse a fork branch from an earlier pull request.

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

   This rebase is how the workflow automatically absorbs another contributor's already-pushed `main` changes while preserving the submitted fix. Do not call `$sync-main` while local fix work is being packaged: that skill intentionally stops on dirty work or local-only `main` commits. Resolve only conflicts whose intended behavior is supported by current code, tests, or frozen contracts. After each resolution inspect the combined diff. If resolution is ambiguous, abort the rebase and report; do not guess. After a successful rebase, record the current `origin/main` commit as the base covered by the submission evidence.

11. Treat credible PASS evidence from the just-completed repair as submission evidence; entering this packaging workflow does not by itself justify repeating tests. Evidence is reusable when it identifies the commands and results, covers the submitted behavior at a risk-appropriate level, and the relevant files have not changed since those checks. Switching branches, staging, or committing identical content does not invalidate it.

    Always perform only the submission-integrity checks that test evidence cannot cover: review the final changed paths and diff, run `git diff --check`, run low-cost syntax checks for changed executable files, and confirm that protected real-data paths were not changed. Do not rerun a focused or full suite merely to obtain a second PASS.

    Rerun the smallest relevant test only when one or more of these triggers applies:

    - credible PASS evidence is missing, failed, incomplete, or does not cover the submitted behavior;
    - a relevant implementation or test file changed after the recorded PASS;
    - fetch/rebase introduced a relevant base change, or conflict resolution changed the tested result;
    - the submitted diff requires stronger coverage than the recorded evidence because it touches permissions, migrations, API/data semantics, deletion/recovery, or several coupled product areas;
    - the user explicitly requests another run.

    High-risk changes require adequate evidence, not duplicate execution: reuse a fresh full-regression PASS for unchanged final content. Run the bundled complete checker only when full regression is required by the triggers above and no reusable full PASS already covers the final content:

   ```powershell
   pwsh -NoProfile -File .agents/skills/commit-push-pr/scripts/run-flowboard-checks.ps1
   ```

   When the complete checker is actually required, `FLOWBOARD_CHECKS_OK` is required. Any guarded-path change is always a hard failure. If sandboxing blocks Chromium or Node subprocesses, request controlled execution rather than skipping required coverage. Use `-PlanOnly` only to inspect the planned commands, never as acceptance evidence.

   The complete checker fails fast on the first Python failure so a stale or environmental E2E does not multiply 30-second waits. Use `-CollectAllFailures` only after the first failure has been classified and a complete failure inventory is genuinely needed; it does not raise the acceptance standard or authorize unrelated repairs.

12. When checks fail, first classify the failure as an in-scope regression, an unrelated/pre-existing failure, a stale test expectation, or an environment/tooling failure. Repair only an in-scope regression. For every other class, preserve the evidence and stop that repair path; do not edit unrelated production files or tests without the user's explicit authorization. Rerun only the relevant check after an in-scope repair, and expand verification only if its risk requires it. This repository's `tests/` directory is not a Python package: rerun a file with `python -m unittest discover -s tests -p "test_name.py" -v -f`, or set `PYTHONPATH` to `tests` before naming `test_name.Class.test_method`; do not use the invalid `tests.test_name...` module form. Stop after two consecutive failed implementation/test cycles, on contract conflict, scope ambiguity, or when a product decision is required. Never hide a known relevant failure or push a dirty branch.

## Final remote refresh and external submission gate

13. Immediately before assembling the submission summary, fetch `origin` again and compare the latest `origin/main` commit with the base recorded after step 10:

   ```powershell
   git fetch --prune origin
   git rev-parse origin/main
   ```

   If `origin/main` advanced, automatically rebase the current fix branch onto the new `origin/main`; never merge it into or rewrite local `main` for this refresh. Apply the same conflict rules as step 10, then repeat the integrity checks and risk-triggered verification in steps 11-12 against the new combined result. Refresh the commit list, diff summary, and test evidence after every successful rebase.

14. Before the first external write, show the user:

   - branch and commit list relative to `origin/main`;
   - intended changed paths and diff summary;
   - tests/checks run or reused, their results, and why that evidence level matches the final diff;
   - proposed PR title and short body;
   - authenticated contributor, upstream repository, fork repository, and whether the fork or `contributor-fork` remote must be created;
   - confirmation that the real database was not changed.

   Ask for one explicit confirmation to create the fork if needed, push the branch to the contributor fork, and create the PR. Earlier permission to edit or test is not permission to perform these external writes.

15. After confirmation and immediately before push, fetch once more and compare `origin/main` with the base covered by the displayed evidence. If it advanced, the prior confirmation is stale: return to step 13, rebase and reverify, then show the updated summary and request confirmation again. Allow at most two such final refresh/rebase cycles in one invocation; if `origin/main` keeps advancing, stop without pushing and report that the submission needs a quieter retry window.

    When the base is unchanged, prepare the previously disclosed submission target. For a non-owner contributor:

    - If the verified fork is absent, create it without cloning and without changing `origin`:

      ```powershell
      gh repo fork $upstream --clone=false --fork-name SSRC-Monday-com --remote --remote-name contributor-fork
      ```

    - If the verified fork already exists but the local remote is absent, add `contributor-fork` with `git remote add contributor-fork "https://github.com/<contributor>/SSRC-Monday-com.git"`. If the remote exists, require it to match; never rename or retarget `origin`.
    - Re-run the shared `-ValidateOriginOnly` check after any fork/remote setup, then re-query the fork metadata and require `fork == true` and `source == cjzymail-Mc/SSRC-Monday-com` before pushing. If fork creation or validation fails, stop; do not fall back to an upstream push or ask for Write access.

    Push without force to the verified fork, then create the pull request with an explicit upstream repository and cross-fork head so `gh` cannot silently choose another remote:

    ```powershell
    git push -u contributor-fork <fix-branch>
    gh pr create --repo cjzymail-Mc/SSRC-Monday-com --base main --head "<contributor>:<fix-branch>" --title <title> --body <body>
    ```

    When the authenticated account is the upstream owner `cjzymail-Mc`, skip fork creation, push the temporary branch to `origin`, and still create the PR explicitly against `cjzymail-Mc/SSRC-Monday-com`. Never use an implicit `gh pr create` prompt to choose, fork, or push a repository.

    If push succeeds but PR creation fails, do not create another branch or force-push. Report the pushed branch and retry only the PR creation step after correcting authentication or metadata.

16. Verify the returned PR URL, upstream repository, `main` base, contributor-owned head repository and branch, and that the fork branch points to the tested local commit. If any check fails, keep the PR/branch state intact and stop with the exact resumable step.

17. Return the checkout to a safe start-of-work state only after the PR and remote branch are verified:

   - If local `main` originally had novice commits, first prove that the rescue branch still points to the recorded original commit and that the tested fix commit exists on the pushed branch. While the fix branch remains checked out, realign only the local `main` pointer to the fetched `origin/main` with `git branch -f main origin/main`.
   - Run the bundled `.agents/skills/sync-main/scripts/sync-main.ps1`. `SYNC_MAIN_OK` is required; do not reproduce its branch-switching logic manually.
   - Success requires current branch `main`, a clean index and worktree, and `main == origin/main`. Keep the local fix branch, fork branch, `contributor-fork` remote, and any rescue branch until the administrator merges the PR. `$sync-main` continues to use only upstream `origin`.

18. Report the PR URL and explain in plain language that the submitted changes remain safely in the PR and will reappear on `main` after the administrator merges it and the user next runs `$sync-main`. Do not merge, deploy, or delete branches.

## Stop conditions

Stop safely when GitHub CLI is missing or unauthenticated, origin points to the wrong repository, the authenticated identity is unclear, the upstream is not public for a non-owner submission, the expected fork is unavailable or belongs to another fork network, `contributor-fork` points elsewhere, the checkout did not start on `main`, origin/main is unavailable, unrelated changes cannot be separated, a conflict is ambiguous, tests remain failing after two cycles, `origin/main` advances through more than two final refresh cycles, any guarded real-data path changes, or the external submission confirmation is withheld. If submission already succeeded but return-to-main fails, report the live PR and preserved branches without claiming full workflow success. Always state the exact resumable step.
