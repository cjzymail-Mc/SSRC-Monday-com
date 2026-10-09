# Direct main submission for verified owners/admins

Read after the shared local preflight and identity routing in SKILL.md. This route stays on main and submits to origin/main. Explicit invocation of $commit-push-pr authorizes committing and pushing the default batch: all current eligible changes plus every local-only main commit, unless the user explicitly narrows it. Reading/editing the skill alone does not invoke submission.

## Package and integrate on main

1. Reuse the recorded original main and initial fetched origin/main OIDs. Stage all reviewed eligible current paths explicitly, inspect the staged diff and commit on main. Existing local commits may already contain the whole batch; do not create an empty commit. Require a clean index/worktree before rebase or push.
2. If the recorded fetched base is already an ancestor of main HEAD, skip rebase. Otherwise retain a unique local `rescue/pre-rebase-main-*` reference to the current main OID, record old/new bases, and rebase only the local main commits onto that exact fetched OID. Keep every rescue reference.
3. On conflicts, read the shared procedure in [Active conflict resolution](../../sync-main/references/conflict-resolution.md), applying its pre-rebase preservation and semantic reconciliation to main rather than a fix branch. Resolve ordinary conflicts within this invocation and verify affected local/upstream behavior. Do not skip commits merely to finish.
4. Use section 4 of SKILL.md for the smallest sufficient verification. Review all final paths/commits against the pinned base, run `git diff --check <submission-base>...HEAD`, exclude protected paths and require a clean tree. Reuse adequate unchanged PASS.
5. If integration proves the whole batch is already upstream and no local commits remain, report that outcome with main at the integrated base; do not push an empty submission.

## Review, refresh and push

Prepare and show a concise summary containing all current changes and local-only commits, checks run/reused, verified identity, destination `cjzymail-Mc/SSRC-Monday-com:main`, and protected-data exclusion. Proceed directly under the explicit invocation; do not ask whether to include existing commits/other features or reconfirm the push. Honor any user-specified narrower scope.

Before push, fetch origin once more and pin the final fetched base. This is the second and final ordinary fetch in this invocation. If it advanced, integrate on main as above and repeat only impact-triggered checks. Show the updated summary; compatible conflict resolution or SHA changes stay authorized, while a materially new implementation decision or destination outside that authorization requires a decision.

Record the final tested main OID and prove the final fetched base is its ancestor. Recheck that main is checked out, the worktree/index are clean, and the outgoing commits contain the reviewed authorized batch and no protected data. Push normally with an explicit destination:

```powershell
git push origin main:main
```

Never force-push. If branch protection, authentication or a newer upstream commit rejects the push, preserve local commits and recovery references, diagnose the specific rejection and report the resumable step. Do not alter protection, bypass it, automatically switch to PR submission or loop through extra fetches. A push rejection does not authorize another submission route.

## Verify and finish on main

Verify that `git ls-remote origin refs/heads/main` reports the tested main OID and that the local checkout is still clean on main at that OID. If the verification query fails or the remote has moved again, preserve state and report push/verification separately; do not claim current remote equality without evidence.

Do not invoke the contributor's return-to-main helper with the pre-push fetched base: that base predates the newly submitted main commits. No branch switch, PR or local-main realignment is needed here.

Report the submitted commit, origin/main destination and checks briefly. Direct submission changes upstream main immediately; it does not deploy or restart the application.
