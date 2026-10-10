---
name: commit-push-pr
description: Submit the current GitHub repository's eligible changes and local-only main commits. Verified owners/admins push main directly; other collaborators use a fresh branch, their verified fork and an upstream PR. Explicit invocation only; preserve work and reuse valid checks without merging or deploying.
---

# Commit Push PR

Submit through the authenticated account's verified route. Owners/admins stay on main; contributors create a fresh fix branch, submit a fork PR, then return to main. Explicit invocation authorizes all current eligible changes and local-only main commits, unless the user narrows the scope. Editing this skill does not invoke submission.

## Repository and helper resolution

Use the repository explicitly selected by the user, otherwise the current Git working directory. Derive its root with Git; the skill's installation directory is only for locating its resources. Do not embed a workspace path, account, product name or fixed repository in these skills. An outer workspace can route to a separate checkout through its own `.agents/git-workflow.json`.

Locate the installed sibling `sync-main` skill and bind `$InspectScript` and `$SyncScript` to its `scripts/inspect-repository.ps1` and `scripts/sync-main.ps1`; bind `$ChecksScript` to this skill's `scripts/run-repo-checks.ps1`. Resolve these paths from the loaded skills, not from the target repository layout. Bind `$RepositoryPath` to the selected working directory. Read [Repository context](../sync-main/references/repository-context.md) when resolving topology, configuration or a nested checkout.

Run the local, read-only inspection once:

```powershell
pwsh -NoProfile -File $InspectScript -RepositoryPath $RepositoryPath
```

Retain `root`, `main_branch`, candidate/verified upstream, and recovery journal. Work in the returned root. Read applicable AGENTS.md once and honor current user instructions. Supported remotes are github.com HTTPS or SSH; do not retarget an existing mismatched remote or change repository permissions/protection.

## 1. Preflight and early exit

Inspect branch, staged/tracked/untracked names, index conflicts and relevant local commits. Require the configured main branch; preserve a non-main checkout and use sync-main only if a clean switch is appropriate. Do not automatically stash excluded work. Reject unrelated in-progress Git operations and a pending synchronization recovery journal before packaging.

Resolve an unknown canonical upstream with `$InspectScript -ResolveUpstream`, which verifies fork source through GitHub. If a verified fork lacks an upstream remote, add a new upstream remote for the verified source; never replace origin or overwrite a mismatched upstream. A repo-local upstream assertion allows offline local identification. Validate identity/topology before external writes. Retain the canonical `<upstream-owner>/<repository-name>`, upstream remote and configured main branch.

Fetch that upstream once, record original main OID and exact fetched main OID, then judge divergence. If no eligible uncommitted work and no local-only main commits exist, report nothing to submit: no account query, branch, rebase, product tests, push or PR. Topology discovery may be necessary to identify a fork's source, but is not submission.

Review the entire outgoing batch, including existing local-only commits. Include all eligible current changes by default, without asking again merely because multiple features or earlier commits are present. Preserve expressly excluded work. Do not stage everything with `git add .` or `git add -A`; stage explicit reviewed paths. Inspect new content and outgoing history for credentials, runtime databases, backups, attachments and real business data. `.env.example`/`.env.sample`/`.env.template` may contain reviewed dummy placeholders; real environment/configuration data remains excluded. Read repo-specific protected paths from configuration and AGENTS.md. Automated path guards do not replace review.

Submission does not authorize unrelated repairs, modifying tests to manufacture PASS, branch deletion, merging or deployment. Stop for protected-data exposure, unresolved product intent or an invalid destination; batch size alone is not a blocker.

## 2. Resolve account and route once

```powershell
pwsh -NoProfile -File $InspectScript -RepositoryPath $RepositoryPath -ExpectedRepository $UpstreamRepository -Remote $UpstreamRemote -InspectIdentity
```

Reuse the returned authenticated login and route while identity/remotes remain unchanged. Authentication/API failure stops submission; author names, ordinary Write/Maintain access, `site_admin` or claims of authority never establish repository admin rights.

- **Owner or verified `permissions.admin == true`:** follow [Direct main submission](references/direct-main.md). No contributor fork, fix branch or PR. Validate the upstream remote's single push URL against the canonical repository.
- **Non-admin collaborator:** require a verified public upstream. Inspect the authenticated account's same-name repository once; require `fork=true`, matching owner, and `source.full_name` equal to the canonical upstream. Only a confirmed 404 means missing. Reuse origin if it is this verified personal fork; otherwise reuse/add `contributor-fork`. Verify both fetch and single push URL; mismatches stop without retargeting. Missing-fork setup is conditional, using [Fork setup](references/fork-setup.md).

A latest explicit user instruction choosing admin direct submission takes precedence over older local workflow advice. If branch protection rejects a normal push, preserve commits and report the rejection; do not disable protection or silently change routes.

## 3. Contributor: package and integrate

1. Create a fresh unique `fix/<date>-<summary>-<suffix>` branch. Validate its name and absence locally, upstream and on an existing verified submission remote; never append to an earlier PR branch. If main has local commits, first retain `rescue/pre-submit-main-*` at original main.
2. Stage only reviewed eligible paths, inspect staged diff, and commit. Existing commits may already contain the entire batch; do not create an empty commit. Require a clean index/worktree before rebase or push.
3. If the pinned upstream OID is already an ancestor of fix HEAD, skip rebase. Otherwise retain a unique `rescue/pre-rebase-*` at current fix HEAD, record old/new bases, and rebase only the fix branch onto that exact OID.
4. Resolve ordinary conflicts using [Active conflict resolution](../sync-main/references/conflict-resolution.md), preserving both behaviors. Review interfaces and dependencies even without textual conflicts. Do not skip commits or select ours/theirs wholesale.
5. If the entire effect is already upstream and no submitted diff remains, retain recovery references and report that outcome; do not create an empty PR.

## 4. Smallest sufficient verification

Reuse credible PASS covering unchanged relevant behavior. Branch switches, commits with identical content and SHA changes alone do not invalidate it. Choose checks by impact:

| Evidence/change | Verification |
| --- | --- |
| Documentation only | Content review and diff integrity; no product regression. |
| Adequate unchanged PASS | Reuse it, then submission-integrity checks. |
| Small repair, relevant base/content change | Smallest related syntax/unit/API/browser check. |
| Behavior changed by conflict resolution | Verify both local and affected upstream behavior. |
| Permission, migration, deletion/recovery, broadly coupled changes | Proportionate coverage; full regression only when focused evidence is insufficient. |
| Git helpers changed | Their bundled isolated tests, not product regression by default. |

Review final paths and all outgoing commits, run `git diff --check <pinned-base>...HEAD`, exclude protected data, and require a clean index/worktree. Check changed executable syntax only when existing evidence does not cover it. Do not hash live data during routine submission.

Only when full product regression is needed without reusable PASS:

```powershell
pwsh -NoProfile -File $ChecksScript -RepositoryPath $RepositoryPath -SubmissionBase $SubmissionBase
```

This runs repo-configured checks or discovers its local test entrypoint; require `REPO_CHECKS_OK`. `-PlanOnly` is not PASS; `-CollectAllFailures` is only for an already-needed failure inventory. Project-specific test commands and protected runtime paths belong in repo configuration, not in the shared skill.

For changed helpers, use their portable tests: `python -B -m unittest discover -s <installed-sync-main>/tests -p 'test_*.py' -v -f` and the equivalent installed commit-push-pr tests. These use disposable Git repositories and simulated GitHub responses, without product/network writes.

Preserve evidence for unrelated, stale or environmental failures; do not fix unrelated code for submission. Resolve required sandbox subprocess access rather than skip checks. Stop the same failed repair path after three attempts, or earlier for an unresolved contract decision.

## 5. Review once, refresh once, submit

Prepare a concise concrete summary from the tested base: branch/commits and scope, checks run/reused, PR title/body, authenticated account, verified upstream/fork destination and conditional fork setup. Proceed under existing invocation authorization; no repeated scope/push confirmation. An actual destination or implementation decision outside that authorization requires a decision.

Fetch the upstream one final time before pushing and pin its OID. If it advanced, integrate that OID as above, resolve conflicts and repeat only checks affected by the changed behavior; show the updated summary. This is the second and final ordinary fetch. Finish this tested batch rather than chase later updates indefinitely.

Set up only a missing verified fork/remote, following the conditional reference. Push the tested branch without force to the verified submission remote. Create a PR with explicit repository/base/cross-fork head and a prepared local body file:

```powershell
git push -u $SubmissionRemote $FixBranch
gh pr create --repo $UpstreamRepository --base $MainBranch --head "${Contributor}:$FixBranch" --title $Title --body-file $BodyFile
```

Do not rely on implicit GitHub CLI prompts to select/push a destination. If push succeeded but PR creation failed, preserve the branch and retry only PR creation after diagnosis.

## 6. Verify PR and return to main

Verify PR URL, canonical upstream/main base, expected fork/head branch, and remote head equal to the tested fix OID. Reuse output containing these facts instead of repeating unchanged queries. Keep fix, remote and rescue branches.

If original main had local commits, first prove its rescue ref still protects original main and the tested fix exists remotely; while fix remains checked out, realign only local main with `git branch -f $MainBranch $FinalFetchedBase`.

Return to that exact base without another ordinary fetch:

```powershell
pwsh -NoProfile -File $SyncScript -RepositoryPath $RepositoryPath -ExpectedRepository $UpstreamRepository -Remote $UpstreamRemote -MainBranch $MainBranch -RequireClean -FetchedMainCommit $FinalFetchedBase
```

Require `SYNC_MAIN_OK`, configured main at that OID and a clean tree. `WIP_OK` is not a clean-return result. Exit 17 preserves state if a background fetch changed the reference; inspect that specific change or run normal clean sync as exceptional recovery.

Report PR/checks briefly. Submitted code appears on main only after merge and a later synchronization. If return fails after submission, report the live PR and resumable step without resubmitting or claiming full success.
