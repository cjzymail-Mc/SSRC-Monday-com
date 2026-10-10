# Repository context and local configuration

These two skills are copied together unchanged between repositories. They require Git and PowerShell 7; GitHub topology/identity verification uses GitHub CLI. Helpers are located relative to their installed skill directories. All Git/product operations run in the selected target checkout.

## Resolve a target without a fixed layout

Use an explicit user-selected repository/path first; otherwise use the current Git working directory. `git rev-parse --show-toplevel` defines the root. Do not scan unrelated repositories or pick a nested checkout merely by its name. Optional `.agents/git-workflow.json` in that root can contain `repositoryPath`, resolved relative to that root, to route an outer workspace to an independent checkout. The destination must itself be a Git root; never fall back to the enclosing repository. Only one routing hop is supported. Then load the destination's own configuration and rules.

Local inspection uses `scripts/inspect-repository.ps1 -RepositoryPath <selected-dir>` and never authenticates or mutates Git. `-ResolveUpstream` verifies repository metadata when no local assertion exists. `-InspectIdentity` resolves upstream and verifies authenticated owner/admin status. Retain results within the invocation; helpers do not persist account/permission caches.

Select a configured upstream remote, otherwise a remote matching the asserted upstream, otherwise upstream/origin/an unambiguous sole remote. For an unasserted remote, query `gh api repos/<remote-slug>`; require matching full_name. If fork=true, require its source.full_name and find a remote for that source. If absent, inspection reports a missing upstream remote so the agent can add one after verification; it never retargets origin. If source and selection are ambiguous, ask for the target rather than guess. github.com HTTPS, SCP-style SSH and ssh://git@github.com URLs are supported; foreign hosts and multiple operation URLs stop verification.

Use the canonical upstream owner/name throughout all API, fork and PR operations. Owners are determined from authenticated login; other admins require a boolean `permissions.admin == true` on the exact upstream. No Write/Maintain escalation. A verified owner/admin uses the source remote's validated single push URL; non-admin collaborators use a verified public fork. Failures never imply a fork is absent or the user is an admin.

## Optional project configuration

Configuration belongs outside `skills/`, so distributing the skills does not overwrite project policy. It must contain no secrets. Only configure actual project needs:

```json
{
  "upstreamRepository": "example-team/example-project",
  "upstreamRemote": "upstream",
  "mainBranch": "main",
  "protectedPaths": ["runtime", "private-attachments"],
  "protectedPathPatterns": ["(?i)^private-reports(/|$)"],
  "checks": [
    {"name": "Project checks", "command": "npm", "arguments": ["run", "check"]}
  ],
  "syntaxChecks": false
}
```

Every field is optional. `upstreamRepository` pins the intended owner/name and rejects a conflicting selected remote; omit it for GitHub-based discovery. Do not copy this example's identity or remote blindly. `upstreamRemote` and `mainBranch` select existing local conventions; main defaults to main. Generic secret/database/backup guards cannot be disabled by project configuration. `protectedPaths` adds literal repo-relative files/subtrees; `protectedPathPatterns` adds regex guards for path review/snapshotting. Paths must remain in the repo. Dummy `.env.example`, `.env.sample`, `.env.template` are allowed subject to content review.

For an outer workspace, its entire configuration may be just `{"repositoryPath": "relative/path/to/code"}`; the code checkout holds its own test/data configuration. The shared skills contain no such project path.

`checks` supplies trusted local executable/argument arrays, not shell command strings. Run them only when regression is justified; do not auto-install dependencies or connect to production. Without checks, the full-check helper prefers a package.json check script, otherwise root tests/test_*.py and tests/*.test.js. No discovered check is an error, not PASS. `syntaxChecks` defaults true and checks tracked Python/JS/MJS/CJS source while excluding skills and isolated helper tests; set false when configured project checks already cover syntax. `-SubmissionBase <exact-oid>` pins diff integrity to the tested upstream. PlanOnly executes no product checks and reads no runtime snapshots.

Full checks verify index/worktree cleanliness and unchanged existing/new root database files, environment files, standard runtime directories and configured protectedPaths even when a check fails. Patterns guard Git paths but do not identify every ignored runtime file; list critical ignored runtime files/subtrees in protectedPaths. Full checks are exceptional; routine submission does not fingerprint live data.

`legacyRecoveryJournals` may list previous journal names when migrating a project; active legacy recovery is resumed in place, not discarded. New journals use git-workflow-sync-main.json. Multiple pending journals require reconciliation before continuing.
