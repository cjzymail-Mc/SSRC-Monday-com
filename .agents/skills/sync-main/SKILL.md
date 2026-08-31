---
name: sync-main
description: Safely validate the Flowboard origin and return this checkout to a clean, current origin/main before starting new work or after a pull request is merged. Use only when the user explicitly invokes $sync-main; do not use it to submit local changes.
---

# Sync Main

Bring the checkout to the latest `origin/main` without losing local work. This is the beginner-safe start-of-work command; it does not submit fixes.

## Safety contract

- Read the repository `AGENTS.md` before acting.
- Never use `reset --hard`, `clean`, checkout-overwrite, automatic stash, or forced branch deletion to make the tree look clean.
- Never write, migrate, restore, rebuild, stage, or commit `flowboard.db`, its WAL/SHM files, `backups/`, credentials, `.env` files, or machine-local state.
- Do not proceed through an in-progress merge, rebase, cherry-pick, or revert.
- Accept only the configured Flowboard repository `cjzymail-Mc/SSRC-Monday-com` as `origin`; normalize ordinary GitHub HTTPS and SSH URL forms before comparing, and stop on any other host or repository.
- Fetching and pulling change external/local Git state. Treat the explicit `$sync-main` invocation as the requested workflow, while still honoring any tool approval required immediately before network access.

## Workflow

1. Resolve the repository root and inspect, without mutation:

   ```powershell
   git rev-parse --show-toplevel
   git branch --show-current
   git status --short --branch
   git remote get-url origin
   ```

2. If tracked or untracked work exists, stop. List the affected paths and tell the user to run `$commit-push-pr <short summary>` if those files are intended work. Do not stash or move the changes automatically.

3. Normalize the configured `origin` URL and verify that it identifies `github.com/cjzymail-Mc/SSRC-Monday-com`. Do this before fetch. If local `main` contains commits not present on `origin/main`, stop and route to `$commit-push-pr`; those commits may be novice fixes made directly on `main`. If `main` and `origin/main` have diverged, do not rebase or rewrite `main` automatically.

4. With a clean tree, use the bundled deterministic script for fetch, branch switching, fast-forward, postcondition checks, and the merged-branch report:

   ```powershell
   pwsh -NoProfile -File .agents/skills/sync-main/scripts/sync-main.ps1
   ```

   Exit `0` with `SYNC_MAIN_OK` is the only success result. Exit `10` means dirty work was preserved; `11` means local `main` is ahead or diverged; other nonzero exits identify an unsafe or incomplete state. Do not bypass these exits with manual destructive commands.

   The script creates a missing local `main` from `origin/main`. If it exists and has no local-only commits, its effective update is:

   ```powershell
   git switch main
   git merge --ff-only origin/main
   ```

   Never merge a feature branch into `main` locally. `main` is fast-forwarded only from `origin/main`.

5. The script prunes stale remote-tracking references but does not delete local branches. Report `fix/*` branches that Git proves are merged into `origin/main`; the user may clean them later with `git branch -d`.

6. Finish with a compact report containing the current branch, local and remote commit IDs, working-tree cleanliness, commits received, and any safely deletable local fix branches. Success requires `main`, a clean tree, and `main == origin/main`.

## Stop conditions

Stop without expanding scope when the origin is missing or points anywhere except the configured Flowboard repository, authentication/network access fails, the worktree is dirty, local `main` is ahead or diverged, an operation is already in progress, or fast-forward is impossible. Preserve all work and state the exact next action.
