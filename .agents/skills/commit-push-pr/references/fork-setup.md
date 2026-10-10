# Conditional contributor fork setup

Read only when a verified personal fork or its submission remote is missing. Submission authorization already covers required setup; skill development/tests never create real GitHub forks or PRs.

Retain canonical `$UpstreamRepository`, authenticated `$Contributor` and `$RepositoryName` derived from that upstream's name. Preserve origin and every existing remote. Require a public upstream and a personal repository with fork=true, expected owner and source.full_name equal to the canonical upstream. Only an actual 404 proves absence; authentication, rate-limit and network failures stop this path.

1. If confirmed absent, create without cloning or changing remotes:

   ```powershell
   gh repo fork $UpstreamRepository --clone=false --remote=false
   ```

   Re-query the new fork and verify identity/source before adding a remote.
2. Reuse origin or contributor-fork only if its fetch and single push URL identify that verified fork. Otherwise add a missing contributor-fork with the verified owner/repository URL. Never overwrite a mismatched name or same-name non-fork repository. Do not request upstream Write access as a fallback.
3. Revalidate only changed targets and the unchanged upstream assertion. Then return to push/PR; adding a remote alone does not invalidate tested content or require repeating fetch, rebase, tests or approval.

A setup/validation failure preserves local state and reports the exact resumable step. A successful push followed by PR failure is resumed at PR creation, not repackaged.
