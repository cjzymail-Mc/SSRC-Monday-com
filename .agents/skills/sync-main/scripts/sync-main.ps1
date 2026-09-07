[CmdletBinding()]
param(
    [string]$Remote = "origin",
    [string]$MainBranch = "main",
    [ValidateNotNullOrEmpty()]
    [string]$ExpectedRepository = "cjzymail-Mc/SSRC-Monday-com",
    [switch]$ValidateOriginOnly,
    [switch]$RequireClean,
    [switch]$CompleteRecovery,
    [string]$RecoverySnapshot,
    [string]$FetchedMainCommit
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Git {
    param([Parameter(Mandatory)][string[]]$Arguments)
    $output = & git @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed:`n$($output -join [Environment]::NewLine)"
    }
    return @($output)
}

function Stop-Sync {
    param([Parameter(Mandatory)][int]$Code, [Parameter(Mandatory)][string]$Message)
    [Console]::Error.WriteLine($Message)
    exit $Code
}

function Get-GitHubRepositorySlug {
    param([Parameter(Mandatory)][string]$Url)

    $candidate = $Url.Trim().TrimEnd("/")
    if ($candidate.EndsWith(".git", [System.StringComparison]::OrdinalIgnoreCase)) {
        $candidate = $candidate.Substring(0, $candidate.Length - 4)
    }

    $match = [regex]::Match(
        $candidate,
        "^(?:https?://|ssh://git@|git@)github\.com[:/](?<slug>[^/\s]+/[^/\s]+)$",
        [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
    )
    if (-not $match.Success) {
        return $null
    }
    return $match.Groups["slug"].Value
}

function Get-GitPaths {
    param([string[]]$Arguments)
    # NUL-delimited paths preserve spaces, Unicode, quoting and rename endpoints.
    $raw = (Invoke-Git -Arguments $Arguments) -join "`n"
    return $raw.Split([char]0, [System.StringSplitOptions]::RemoveEmptyEntries)
}

function Assert-SafePaths {
    param([string[]]$Paths)
    foreach ($path in $Paths) {
        if ($path -match '(?i)(^|/)(flowboard\.db(?:-(?:wal|shm))?|backups|flowboard-attachments|local-test-data|\.env(?:\.[^/]*)?|credentials(?:\.[^/]*)?|\.ssh|id_rsa|id_ed25519)(/|$)' -or
            $path -match '(?i)^(temp\.md|\.copilot-(?:message\.md|state\.json|task\.md))$' -or
            $path -match '(?i)\.(pem|key|pfx|p12)$') {
            Stop-Sync -Code 16 -Message "SYNC_MAIN_GUARDED_PATH: $path; leave runtime data/credentials in place and resolve tracking separately."
        }
    }
}

function Get-WorkStatus {
    return @(Invoke-Git -Arguments @("status", "--porcelain=v1", "--untracked-files=all"))
}

function Save-Recovery {
    # A per-worktree journal prevents a second invocation from stashing a partial restore.
    $recovery | ConvertTo-Json | Set-Content -LiteralPath $recoveryPath -Encoding utf8
}

function Write-SyncReport {
    param([string]$Mode, [bool]$WorktreeDirty)
    Write-Output $(if ($WorktreeDirty -or $snapshot) { "SYNC_MAIN_WIP_OK" } else { "SYNC_MAIN_OK" })
    Write-Output "mode=$Mode"
    Write-Output "root=$root"
    Write-Output "origin=$originUrl"
    Write-Output "branch=$MainBranch"
    Write-Output "commit=$localCommit"
    Write-Output "remote_commit=$remoteCommit"
    Write-Output "observed_remote_commit=$latestRemote"
    Write-Output "remote_reference_changed=$($latestRemote -ne $remoteCommit)"
    Write-Output "commits_received=$received"
    Write-Output "worktree_dirty=$WorktreeDirty"
    Write-Output "snapshot=$snapshot"
    Write-Output "fetch_reused=$([bool]$FetchedMainCommit)"
    # An already-current checkout does not need a branch-cleanup inventory.
    if ($Mode -ne "unchanged") {
        $mergedFixBranches = @(Invoke-Git -Arguments @("for-each-ref", "--merged=refs/remotes/$Remote/$MainBranch", "--format=%(refname:short)", "refs/heads/fix"))
        Write-Output "safely_deletable_fix_branches=$($mergedFixBranches -join ',')"
    }
}

$root = (Invoke-Git -Arguments @("rev-parse", "--show-toplevel") | Select-Object -First 1).Trim()
Set-Location -LiteralPath $root

$operationPaths = @(
    "MERGE_HEAD",
    "CHERRY_PICK_HEAD",
    "REVERT_HEAD",
    "rebase-merge",
    "rebase-apply"
)
foreach ($operation in $operationPaths) {
    $operationPath = (Invoke-Git -Arguments @("rev-parse", "--git-path", $operation) | Select-Object -First 1).Trim()
    if (Test-Path -LiteralPath $operationPath) {
        Stop-Sync -Code 12 -Message "SYNC_MAIN_OPERATION_IN_PROGRESS: $operationPath"
    }
}

$originUrl = (Invoke-Git -Arguments @("remote", "get-url", $Remote) | Select-Object -First 1).Trim()
$actualRepository = Get-GitHubRepositorySlug -Url $originUrl
if ($null -eq $actualRepository -or
    -not $actualRepository.Equals($ExpectedRepository, [System.StringComparison]::OrdinalIgnoreCase)) {
    Stop-Sync -Code 15 -Message "SYNC_MAIN_UNEXPECTED_ORIGIN: expected=github.com/$ExpectedRepository actual=$originUrl"
}
if ($ValidateOriginOnly) {
    Write-Output "SYNC_MAIN_ORIGIN_OK"
    Write-Output "root=$root"
    Write-Output "origin=$originUrl"
    exit 0
}

# Only an already-fetched, exact upstream commit can be reused by a clean-return
# consumer. Normal user synchronization still fetches; this is not an offline mode.
if ($FetchedMainCommit -and (-not $RequireClean -or $CompleteRecovery -or
        $FetchedMainCommit -notmatch '^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$')) {
    Stop-Sync -Code 17 -Message "SYNC_MAIN_INVALID_FETCH_REUSE: requires -RequireClean and an exact fetched commit OID; not available for WIP/recovery."
}

$recoveryPath = (Invoke-Git -Arguments @("rev-parse", "--git-path", "flowboard-sync-main.json") | Select-Object -First 1).Trim()
$branch = (Invoke-Git -Arguments @("branch", "--show-current") | Select-Object -First 1)
if (-not $branch) {
    Stop-Sync -Code 12 -Message "SYNC_MAIN_DETACHED: attach the checkout before synchronization."
}
$snapshot = ""
$received = 0
$recovering = Test-Path -LiteralPath $recoveryPath
if ($recovering) {
    $recovery = Get-Content -Raw -LiteralPath $recoveryPath -Encoding utf8 | ConvertFrom-Json
    if (-not $CompleteRecovery) {
        Stop-Sync -Code 20 -Message "SYNC_MAIN_RECOVERY_REQUIRED: journal=$recoveryPath snapshot=$($recovery.snapshot) phase=$($recovery.phase); continue the skill's conflict-resolution workflow, do not start another sync."
    }
    if ($RequireClean -or -not $RecoverySnapshot -or $RecoverySnapshot -ne $recovery.snapshot -or
        $recovery.phase -notin @("restoring", "restore_failed", "restored")) {
        Stop-Sync -Code 20 -Message "SYNC_MAIN_RECOVERY_NOT_READY: inspect the journal and preserved snapshot before completing."
    }
    $snapshot = $recovery.snapshot
    $savedSnapshot = (Invoke-Git -Arguments @("rev-parse", $recovery.snapshotRef) | Select-Object -First 1).Trim()
    $head = (Invoke-Git -Arguments @("rev-parse", "HEAD") | Select-Object -First 1).Trim()
    if ($savedSnapshot -ne $snapshot -or $branch -ne $MainBranch -or $head -ne $recovery.target) {
        Stop-Sync -Code 20 -Message "SYNC_MAIN_RECOVERY_STATE_CHANGED: snapshot, branch or HEAD differs from the journal."
    }
    if (@(Get-GitPaths -Arguments @("diff", "--name-only", "--diff-filter=U", "-z")).Count -gt 0) {
        Stop-Sync -Code 20 -Message "SYNC_MAIN_UNRESOLVED: finish resolving and stage only resolved paths before completion."
    }
    # This acknowledges the agent's semantic review/tests, not just the absence of markers.
    [void](Invoke-Git -Arguments @("diff", "--check"))
    [void](Invoke-Git -Arguments @("diff", "--cached", "--check"))
    $remoteCommit = $recovery.target
    $received = $recovery.received
} elseif ($CompleteRecovery) {
    Stop-Sync -Code 20 -Message "SYNC_MAIN_NO_RECOVERY: no pending journal exists."
} else {
    if (@(Get-GitPaths -Arguments @("diff", "--name-only", "--diff-filter=U", "-z")).Count -gt 0) {
        Stop-Sync -Code 12 -Message "SYNC_MAIN_UNRELATED_UNMERGED_INDEX: resolve the existing conflict before starting a new synchronization."
    }
    $status = @(Get-WorkStatus)
    $dirty = ($status -join "").Length -gt 0
    if ($dirty -and ($RequireClean -or $branch -ne $MainBranch)) {
        Stop-Sync -Code 10 -Message "SYNC_MAIN_DIRTY: work preserved; WIP synchronization requires main and does not support -RequireClean."
    }

    # Reject protected tracked files even when clean: a stash contains whole trees.
    Assert-SafePaths -Paths @(Get-GitPaths -Arguments @("ls-files", "-z"))
    Assert-SafePaths -Paths @(Get-GitPaths -Arguments @("ls-tree", "-r", "--name-only", "-z", "HEAD"))
    Assert-SafePaths -Paths @(Get-GitPaths -Arguments @("ls-files", "--others", "--exclude-standard", "-z"))
    if (@(Invoke-Git -Arguments @("ls-files", "--stage")) -match '^160000 ') {
        Stop-Sync -Code 16 -Message "SYNC_MAIN_SUBMODULE: nested repository work requires a separate preservation decision."
    }
    $nestedRepos = @(Get-GitPaths -Arguments @("ls-files", "--others", "--exclude-standard", "--directory", "-z") |
        Where-Object { $_.EndsWith("/") -and (Test-Path -LiteralPath (Join-Path $_ ".git")) })
    if ($nestedRepos.Count -gt 0) {
        Stop-Sync -Code 16 -Message "SYNC_MAIN_NESTED_REPOSITORY: $($nestedRepos -join ',')"
    }

    # Fetch before judging ahead/diverged, and before temporarily removing any work.
    if (-not $FetchedMainCommit) {
        [void](Invoke-Git -Arguments @("fetch", "--prune", $Remote))
    }
    & git show-ref --verify --quiet "refs/remotes/$Remote/$MainBranch"
    if ($LASTEXITCODE -ne 0) {
        Stop-Sync -Code 13 -Message "SYNC_MAIN_REMOTE_MAIN_MISSING: refs/remotes/$Remote/$MainBranch"
    }
    $remoteCommit = (Invoke-Git -Arguments @("rev-parse", "$Remote/$MainBranch") | Select-Object -First 1).Trim()
    if ($FetchedMainCommit -and $FetchedMainCommit -ne $remoteCommit) {
        Stop-Sync -Code 17 -Message "SYNC_MAIN_FETCH_REUSE_CHANGED: origin/main differs from the supplied fetched OID; no checkout mutation; inspect the new reference or run normal -RequireClean synchronization."
    }
    & git show-ref --verify --quiet "refs/heads/$MainBranch"
    $localMainExists = $LASTEXITCODE -eq 0
    if ($localMainExists) {
        $counts = ((Invoke-Git -Arguments @("rev-list", "--left-right", "--count", "$MainBranch...$remoteCommit")) -join "").Trim() -split "\s+"
        if ([int]$counts[0] -gt 0) {
            Stop-Sync -Code 11 -Message "SYNC_MAIN_LOCAL_MAIN_AHEAD_OR_DIVERGED: local=$($counts[0]) remote=$($counts[1]); preserve commits; use commit-push-pr only when the fix is ready for submission."
        }
        $received = [int]$counts[1]
    }
    # All local guards have passed. Nothing to integrate: do not re-enumerate the
    # same tree, inspect repair semantics, create a stash, or initiate any tests.
    if ($branch -eq $MainBranch -and $localMainExists -and $received -eq 0) {
        $localCommit = $remoteCommit
        $latestRemote = $remoteCommit
        Write-SyncReport -Mode "unchanged" -WorktreeDirty $dirty
        exit 0
    }
    Assert-SafePaths -Paths @(Get-GitPaths -Arguments @("ls-tree", "-r", "--name-only", "-z", $remoteCommit))
    if ($dirty -and $received -gt 0) {
        $id = [guid]::NewGuid().ToString("N")
        $recovery = [ordered]@{
            originalHead = ((Invoke-Git -Arguments @("rev-parse", "HEAD")) -join "").Trim()
            target = $remoteCommit
            received = $received
            snapshot = ""
            snapshotRef = "refs/sync-main/$id"
            label = "sync-main-$id"
            phase = "saving"
        }
        Save-Recovery
        try {
            [void](Invoke-Git -Arguments @("stash", "push", "--include-untracked", "-m", $recovery.label))
            $snapshot = ((Invoke-Git -Arguments @("rev-parse", "refs/stash")) -join "").Trim()
            $snapshotBase = ((Invoke-Git -Arguments @("rev-parse", "$snapshot^1")) -join "").Trim()
            $snapshotMessage = (Invoke-Git -Arguments @("log", "-1", "--format=%s", $snapshot)) -join ""
            if ($snapshotBase -ne $recovery.originalHead -or -not $snapshotMessage.Contains($recovery.label)) {
                throw "Stash identity does not match this synchronization; preserve the journal and inspect the reflog."
            }
            $recovery.snapshot = $snapshot
            $recovery.phase = "saved"
            Save-Recovery
            [void](Invoke-Git -Arguments @("update-ref", $recovery.snapshotRef, $snapshot))
            Write-Output "snapshot=$snapshot"
            Write-Output "snapshot_ref=$($recovery.snapshotRef)"
            Write-Output "journal=$recoveryPath"
            if ((@(Get-WorkStatus) -join "").Length -gt 0) {
                throw "Worktree is not clean after snapshot; inspect remaining paths before updating main."
            }
        } catch {
            Stop-Sync -Code 20 -Message "SYNC_MAIN_SAVE_INCOMPLETE: $($_.Exception.Message); inspect $recoveryPath and stash reflog; do not retry automatically."
        }
    }
    try {
        if (-not $localMainExists) {
            [void](Invoke-Git -Arguments @("switch", "--no-overwrite-ignore", "--track", "-c", $MainBranch, "$Remote/$MainBranch"))
        } elseif ($branch -ne $MainBranch) {
            [void](Invoke-Git -Arguments @("switch", "--no-overwrite-ignore", $MainBranch))
        }
        if ($received -gt 0) {
            [void](Invoke-Git -Arguments @("merge", "--ff-only", "--no-autostash", "--no-overwrite-ignore", $remoteCommit))
        }
    } catch {
        Stop-Sync -Code 21 -Message "SYNC_MAIN_UPDATE_FAILED: $($_.Exception.Message); snapshot=$snapshot journal=$recoveryPath; inspect HEAD and restore saved work before retrying."
    }
    if ($snapshot) {
        $recovery.phase = "restoring"
        Save-Recovery
        try {
            # Apply by immutable OID; never pop/drop an entry or touch an older stash.
            [void](Invoke-Git -Arguments @("stash", "apply", "--index", $snapshot))
        } catch {
            $recovery.phase = "restore_failed"
            Save-Recovery
            Stop-Sync -Code 20 -Message "SYNC_MAIN_RESOLVE_REQUIRED: $($_.Exception.Message); snapshot=$snapshot journal=$recoveryPath; agent must now resolve conflicts and verify, then use -CompleteRecovery -RecoverySnapshot $snapshot."
        }
        $recovery.phase = "restored"
        Save-Recovery
    }
}

$localCommit = ((Invoke-Git -Arguments @("rev-parse", $MainBranch)) -join "").Trim()
$latestRemote = ((Invoke-Git -Arguments @("rev-parse", "$Remote/$MainBranch")) -join "").Trim()
$finalBranch = ((Invoke-Git -Arguments @("branch", "--show-current")) -join "").Trim()
if ($localCommit -ne $remoteCommit -or $finalBranch -ne $MainBranch) {
    Stop-Sync -Code 14 -Message "SYNC_MAIN_POSTCONDITION_FAILED: branch/base changed; preserve any recovery journal."
}
Assert-SafePaths -Paths @(Get-GitPaths -Arguments @("ls-files", "-z"))
Assert-SafePaths -Paths @(Get-GitPaths -Arguments @("ls-files", "--others", "--exclude-standard", "-z"))
$finalStatus = @(Get-WorkStatus)
$worktreeDirty = ($finalStatus -join "").Length -gt 0
if ($RequireClean -and $worktreeDirty) {
    Stop-Sync -Code 14 -Message "SYNC_MAIN_POSTCONDITION_FAILED: clean checkout required."
}
if ($snapshot) {
    Remove-Item -LiteralPath $recoveryPath
}
$mode = if ($CompleteRecovery) { "recovered" } elseif ($snapshot) { "wip" } else { "clean" }
Write-SyncReport -Mode $mode -WorktreeDirty $worktreeDirty
