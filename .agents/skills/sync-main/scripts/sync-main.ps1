[CmdletBinding()]
param(
    [string]$Remote = "origin",
    [string]$MainBranch = "main",
    [ValidateNotNullOrEmpty()]
    [string]$ExpectedRepository = "cjzymail-Mc/SSRC-Monday-com",
    [switch]$ValidateOriginOnly
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

$status = @(Invoke-Git -Arguments @("status", "--porcelain=v1", "--untracked-files=all"))
if ($status.Count -gt 0 -and ($status -join "").Length -gt 0) {
    [Console]::Error.WriteLine("SYNC_MAIN_DIRTY: local work was preserved; run `$commit-push-pr if it is intended work.")
    $status | ForEach-Object { [Console]::Error.WriteLine($_) }
    exit 10
}

[void](Invoke-Git -Arguments @("fetch", "--prune", $Remote))

& git show-ref --verify --quiet "refs/remotes/$Remote/$MainBranch"
if ($LASTEXITCODE -ne 0) {
    Stop-Sync -Code 13 -Message "SYNC_MAIN_REMOTE_MAIN_MISSING: refs/remotes/$Remote/$MainBranch"
}

& git show-ref --verify --quiet "refs/heads/$MainBranch"
$localMainExists = $LASTEXITCODE -eq 0
if (-not $localMainExists) {
    [void](Invoke-Git -Arguments @("switch", "--track", "-c", $MainBranch, "$Remote/$MainBranch"))
} else {
    $countsText = (Invoke-Git -Arguments @("rev-list", "--left-right", "--count", "$MainBranch...$Remote/$MainBranch") | Select-Object -First 1).Trim()
    $counts = $countsText -split "\s+"
    $localOnly = [int]$counts[0]
    $remoteOnly = [int]$counts[1]
    if ($localOnly -gt 0) {
        Stop-Sync -Code 11 -Message "SYNC_MAIN_LOCAL_MAIN_AHEAD_OR_DIVERGED: local=$localOnly remote=$remoteOnly; run `$commit-push-pr to preserve novice main commits."
    }
    [void](Invoke-Git -Arguments @("switch", $MainBranch))
    [void](Invoke-Git -Arguments @("merge", "--ff-only", "$Remote/$MainBranch"))
}

$localCommit = (Invoke-Git -Arguments @("rev-parse", $MainBranch) | Select-Object -First 1).Trim()
$remoteCommit = (Invoke-Git -Arguments @("rev-parse", "$Remote/$MainBranch") | Select-Object -First 1).Trim()
if ($localCommit -ne $remoteCommit) {
    Stop-Sync -Code 14 -Message "SYNC_MAIN_POSTCONDITION_FAILED: $MainBranch=$localCommit $Remote/$MainBranch=$remoteCommit"
}

$finalStatus = @(Invoke-Git -Arguments @("status", "--porcelain=v1", "--untracked-files=all"))
if ($finalStatus.Count -gt 0 -and ($finalStatus -join "").Length -gt 0) {
    Stop-Sync -Code 14 -Message "SYNC_MAIN_POSTCONDITION_FAILED: working tree became dirty."
}

$mergedFixBranches = @(Invoke-Git -Arguments @("for-each-ref", "--merged=refs/remotes/$Remote/$MainBranch", "--format=%(refname:short)", "refs/heads/fix"))
Write-Output "SYNC_MAIN_OK"
Write-Output "root=$root"
Write-Output "origin=$originUrl"
Write-Output "branch=$MainBranch"
Write-Output "commit=$localCommit"
if ($mergedFixBranches.Count -gt 0 -and ($mergedFixBranches -join "").Length -gt 0) {
    Write-Output "safely_deletable_fix_branches=$($mergedFixBranches -join ',')"
} else {
    Write-Output "safely_deletable_fix_branches="
}
