# Conditional contributor fork setup

Read only when the verified contributor fork or contributor-fork remote is missing/changed. Authorization must already cover this setup and submission; no real GitHub writes during skill development/tests.

Keep origin at github.com/cjzymail-Mc/SSRC-Monday-com. Never overwrite a same-name non-fork repository or retarget a mismatched remote. Never request upstream Write access as a fallback.

1. If the fork was confirmed absent (404), create it without cloning or replacing origin:

   ```powershell
   gh repo fork cjzymail-Mc/SSRC-Monday-com --clone=false --fork-name SSRC-Monday-com --remote --remote-name contributor-fork
   ```

2. If the fork already exists but the local remote is absent, add exactly the previously verified contributor-owned URL:

   ```powershell
   git remote add contributor-fork "https://github.com/<contributor>/SSRC-Monday-com.git"
   ```

3. After setup, validate origin with `.agents/skills/sync-main/scripts/sync-main.ps1 -ValidateOriginOnly`, confirm contributor-fork resolves to the exact authenticated contributor's fork, and query its metadata. Require fork=true and source.full_name=cjzymail-Mc/SSRC-Monday-com before push. A setup/validation failure stops this external-write path; preserve existing state and report the resumable step.

Return to the main skill's push/PR step. Do not redo fetch, rebase, tests or submission confirmation merely because a remote was added; the checked code has not changed.
