---
name: commit-push-pr
description: Submit current Flowboard changes and local-only main commits according to verified GitHub identity; upstream owners/admins push main directly; other contributors use a fresh fix branch, their fork and an upstream PR. Integrate origin/main and reuse valid test evidence. Use only when explicitly invoked as $commit-push-pr; do not expand the fix, merge or deploy.
---

# Commit Push PR

Package the current submission batch through the verified account's route: upstream owners/admins commit and push main directly; other contributors submit through their fork and an upstream PR, then return to main. Inspect once and reuse applicable PASS. Fork setup and conflict recovery are conditional work.

## Boundaries

- Read AGENTS.md once; reuse unchanged instructions already read in this session. Read current feature contracts and README test guidance only when needed to understand the submitted change or choose missing coverage.
- Preserve local work. Never use reset --hard, clean, checkout-overwrite, arbitrary automatic stash, force-push or destructive recovery. Do not reuse a branch from an earlier PR.
- Never stage, commit, copy, migrate or test against real flowboard.db, its WAL/SHM files, backups/, attachments, credentials, .env files or machine-local state. Review names beyond the helper's known guards. Stage explicit reviewed paths only; never git add . or git add -A.
- Keep origin at github.com/cjzymail-Mc/SSRC-Monday-com. Only the authenticated upstream owner or a verified upstream admin may push origin/main; other contributors use their verified public fork via contributor-fork. Never request additional upstream access, change branch protection or retarget a mismatched remote.
- Explicitly invoking $commit-push-pr authorizes committing and submitting all current eligible tracked/staged/untracked changes and local-only main commits through the verified route, unless the user expressly narrows the scope. For owners/admins this includes push to origin/main; for contributors it includes any needed verified fork setup, fork push and upstream PR creation. Do not request another scope or push confirmation merely because several features, earlier local commits or other tasks' existing changes are present.
- Review the whole outgoing batch and exclude protected data; `all` never overrides those exclusions. Submission packages existing work but does not authorize implementing additional fixes, rewriting unrelated tests, merging, deployment, branch deletion or cleaning old backups. A request only to read/edit this skill does not invoke submission.

## 1. Local preflight and early exit

Batch cheap local inspection: root, attached branch and tracked/staged/untracked status. Require main; preserve a non-main checkout and route to sync-main without inspecting old PRs or setting up GitHub. Reject unmerged index entries, an unrelated Git operation, or a pending flowboard-sync-main.json recovery journal before packaging.

Use the shared validator once; it checks origin and in-progress Git operations. Do not separately repeat its root/origin commands:

```powershell
pwsh -NoProfile -File .agents/skills/sync-main/scripts/sync-main.ps1 -ValidateOriginOnly
git fetch --prune origin
git rev-parse main
git rev-parse origin/main
git rev-list --left-right --count main...origin/main
```

Record original main OID and fetched origin/main OID as the initial submission base. Judge divergence after this fetch. If **no uncommitted work and no local-only main commits** exist, finish with "nothing to submit"; no GitHub authentication/topology queries, branch, rebase, tests, push or PR. A clean index alone is insufficient: existing local commits may be the intended repair.

Otherwise review the actual diff and all local-only commits as the outgoing batch. Include every eligible current change and existing local-only commit by default; list them in the submission summary and proceed without asking whether to include them. Honor any explicit narrower scope, preserve excluded work and never stash it automatically. Stop for protected-data exposure, an unresolved semantic conflict or an invalid destination that cannot be resolved within the existing authorization; the mere size or mixed-feature nature of the batch is not such a blocker.

## 2. Resolve the submission target once

Determine the current account once with `gh api user --jq .login`; a failed authentication/tool check stops the submission. Do not also run gh auth status merely to repeat a successful identity check.

- Upstream owner: the authenticated login equals cjzymail-Mc (case-insensitive). Use the direct-main route; skip contributor fork/public-visibility queries.
- Other accounts: inspect `gh api repos/cjzymail-Mc/SSRC-Monday-com` once and retain upstream identity, visibility and `permissions.admin`. Require the expected full_name. Only `permissions.admin == true` qualifies as another upstream admin; ordinary Write/Maintain access, commit author names, `site_admin` or an unverified claim do not.
- Verified upstream admin: use the direct-main route. A failed identity/repository query stops submission; missing permission evidence never grants direct-main access.
- Non-admin contributor: reuse upstream visibility from that response and inspect `repos/<contributor>/SSRC-Monday-com` metadata once. Require public upstream; an existing same-name repository must have fork=true and source.full_name=cjzymail-Mc/SSRC-Monday-com. Only a verified 404 means the fork is absent. A contributor-fork remote, if present, must identify this exact repository; do not repair a mismatch automatically.
- Reuse these verified facts within this invocation while identity/remotes remain unchanged. Re-query only a target that was newly created/changed, a resumed session, or an actual failure suggesting stale evidence. Do not build a persistent account cache.

**Owners/admins:** follow [Direct main submission](references/direct-main.md), reusing the shared verification guidance in section 4, then finish. Do not create a fix branch, fork or PR, or run the contributor return-to-main steps.

**Non-admin contributors:** continue through sections 3-6. Use a fresh unique fix/<date>-<summary>-<suffix> branch. Validate its name and absence locally, in fetched upstream refs, and on the existing verified submission remote. Never append to an existing PR branch. Missing-fork creation is deferred until submission is authorized.

## 3. Contributor: package and integrate

1. Switch to the new fix branch; uncommitted work follows the checkout. If main has local-only commits, first retain a unique rescue/pre-submit-main-* reference to the recorded original main.
2. Stage only the reviewed paths, inspect the staged diff, and commit the requested repair. If existing commits already contain the entire repair, do not create an empty commit. Require a clean index/worktree before rebase or push.
3. If the fetched submission base is already an ancestor of fix HEAD, skip rebase and its recovery-reference creation. Otherwise retain a unique rescue/pre-rebase-* reference, record old/new base OIDs, and rebase only the fix branch onto the exact fetched OID.
4. On conflicts, read [Active conflict resolution](../sync-main/references/conflict-resolution.md), reconcile both behaviors, stage explicit resolved paths and continue. Ordinary textual conflicts must be solved within this invocation, not merely reported. Review renamed interfaces and dependencies even when Git merges without textual conflicts.
5. If rebase proves the intended patch is already upstream and no submitted diff remains, report that outcome and retain recovery references; do not push or open an empty PR.

## 4. Choose the smallest sufficient verification

Use one brief explanation of the evidence choice; no separate planning report or new approval is needed to choose checks.

| Final change/evidence | Action |
| --- | --- |
| Documentation only | Review content and diff integrity; no product suite or executable syntax checks. |
| Credible PASS covers unchanged relevant content/behavior | Reuse it and proceed after submission-integrity checks; no duplicate focused or full run. |
| Small repair lacks adequate evidence, or relevant content/base changed | Run the smallest related syntax/unit/API/browser check needed for that behavior. |
| Conflict resolution changes behavior | Verify the resolved behavior and affected upstream behavior; a conflict does not automatically require the full suite. |
| Permission, migration, deletion/recovery or broad coupled change | Require proportionate coverage; widen to product regression only when focused evidence is insufficient. Reuse an already adequate PASS. |
| Git skill/helper change | Run relevant isolated tests under tests/skill_checks; do not run product regression unless product behavior also changed. |

Credible evidence identifies commands/results and covers the current repair at appropriate risk. Branch switching, committing identical content, a SHA change alone or unrelated upstream edits do not invalidate it. Lack of test evidence calls for an appropriate test, not automatically all tests.

Always review the final paths/diff against the recorded base, run `git diff --check <submission-base>...HEAD`, ensure the worktree/index are clean, and ensure protected paths are excluded. Run low-cost syntax checks only for changed executable content not already covered by reusable evidence. Routine submission does not hash the live database, attachments or backup directory.

Only when product full regression is actually required and no reusable PASS covers it:

```powershell
pwsh -NoProfile -File .agents/skills/commit-push-pr/scripts/run-flowboard-checks.ps1
```

FLOWBOARD_CHECKS_OK is required if that checker is run. It retains protected-data guards; PlanOnly is not PASS. CollectAllFailures is only for a needed failure inventory after classification. Git tool tests have their own explicit entrypoint:

```powershell
python -m unittest discover -s tests/skill_checks -p 'test_*.py' -v -f
```

Do not run those tool tests on ordinary product fixes. For one Python product test use `python -m unittest discover -s tests -p "test_name.py" -v -f`; tests/ is not a Python package. Preserve evidence for unrelated, stale or environmental failures and stop that repair path without editing unrelated code/tests. Resolve required sandbox subprocess access rather than skipping checks. Stop after three consecutive failures of the same resolution/test or a product decision that evidence cannot settle.

## 5. Contributor: review once, refresh once, submit

Prepare a concise summary from the already-fetched/tested base; **do not fetch again just to assemble the summary**. Include the final branch/commit list and scope, checks run/reused, proposed PR title/body, current identity and destination, any needed fork/remote creation, and protected-data exclusion.

Present the concrete summary and proceed: explicit invocation already authorizes the default batch, any needed verified fork setup, push and upstream PR. Do not ask for another confirmation for those actions. If the user expressly limited submission, respect that limit; an actual destination change or unresolved semantic decision outside the authorized work still requires a decision.

Before push, fetch origin once more and pin this final fetched OID. If it advanced, integrate that OID using section 3, actively resolve conflicts and repeat only impact-triggered checks from section 4. Show the updated summary. Compatible resolution/SHA changes within the submitted batch and verified destination remain authorized; a materially new implementation decision or destination outside that authorization requires a decision.

This is the second and final ordinary fetch in this invocation. Finish this tested batch rather than chasing every later coworker update. Record tested base and fix OIDs; do not claim newer upstream commits are integrated or that the PR is merge-ready without evidence.

Prepare only the verified, authorized target:

- Existing verified fork and contributor-fork remote: reuse them without repeating unchanged metadata queries.
- Missing/changed fork or remote: read [Fork setup](references/fork-setup.md), perform only the needed setup, then revalidate the changed target and origin.

Push without force, and create the PR with explicit upstream and cross-fork head:

```powershell
git push -u contributor-fork <fix-branch>
gh pr create --repo cjzymail-Mc/SSRC-Monday-com --base main --head "<contributor>:<fix-branch>" --title <title> --body-file <prepared-body-file>
```

Never rely on an implicit gh prompt to choose or push a repository. If push succeeded but PR creation failed, retain the branch and retry only PR creation after diagnosis; do not restart the whole packaging workflow.

## 6. Contributor: verify the PR and return to main

Verify PR URL, upstream main base, expected head repository/branch and that the remote head is the tested local OID. Reuse PR/API output containing those facts rather than duplicating reads. Retain all local fix, remote and rescue branches.

If main originally had local commits, prove its rescue reference still points to original main and the tested fix exists on the remote, then realign only the local main pointer while fix remains checked out: `git branch -f main <final-fetched-base>`.

Return using that exact fetched base, without another network refresh:

```powershell
pwsh -NoProfile -File .agents/skills/sync-main/scripts/sync-main.ps1 -RequireClean -FetchedMainCommit <final-fetched-base>
```

Require SYNC_MAIN_OK, main at the supplied base, and a clean tree. WIP_OK is not a clean-return result. If an IDE/background process changed origin/main meanwhile, exit 17 preserves state; inspect that specific change or run normal -RequireClean synchronization. This exceptional recovery may fetch; it is not part of the normal two-fetch path.

Report the PR URL and checks briefly. Submitted changes remain in the PR and appear on main after administrator merge and a later sync-main. If return-to-main fails after external submission, report the live PR and the exact resumable step without repeating submission or claiming full workflow success.
