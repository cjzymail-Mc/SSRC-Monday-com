# Runtime-data-safe full checks for $commit-push-pr.
[CmdletBinding()]
param([switch]$PlanOnly)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param(
        [Parameter(Mandatory)][string]$Label,
        [Parameter(Mandatory)][scriptblock]$Command
    )
    Write-Host "==> $Label"
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

function Get-TextSha256 {
    param([Parameter(Mandatory)][AllowEmptyString()][string]$Text)

    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
        return [System.Convert]::ToHexString($sha256.ComputeHash($bytes))
    } finally {
        $sha256.Dispose()
    }
}

function Get-PathSnapshot {
    param([Parameter(Mandatory)][string]$Path)

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    if (-not (Test-Path -LiteralPath $fullPath)) {
        return [pscustomobject]@{ Exists = $false; Kind = "absent"; Digest = "" }
    }

    $item = Get-Item -Force -LiteralPath $fullPath
    if (-not $item.PSIsContainer) {
        return [pscustomobject]@{
            Exists = $true
            Kind = "file"
            Digest = (Get-FileHash -Algorithm SHA256 -LiteralPath $fullPath).Hash
        }
    }

    $records = [System.Collections.Generic.List[string]]::new()
    $records.Add("D`t.")
    $children = @(Get-ChildItem -Force -Recurse -LiteralPath $fullPath | Sort-Object FullName)
    foreach ($child in $children) {
        $relativePath = [System.IO.Path]::GetRelativePath($fullPath, $child.FullName).Replace("\", "/")
        if ($child.PSIsContainer) {
            $records.Add("D`t$relativePath")
        } else {
            $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $child.FullName).Hash
            $records.Add("F`t$relativePath`t$($child.Length)`t$hash")
        }
    }
    return [pscustomobject]@{
        Exists = $true
        Kind = "directory"
        Digest = Get-TextSha256 -Text ($records -join "`n")
    }
}

function Get-RootEnvironmentSnapshot {
    param([Parameter(Mandatory)][string]$Root)

    $records = [System.Collections.Generic.List[string]]::new()
    $environmentFiles = @(Get-ChildItem -Force -File -LiteralPath $Root |
        Where-Object { $_.Name -eq ".env" -or $_.Name.StartsWith(".env.", [System.StringComparison]::OrdinalIgnoreCase) } |
        Sort-Object Name)
    foreach ($file in $environmentFiles) {
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash
        $records.Add("F`t$($file.Name)`t$($file.Length)`t$hash")
    }
    return Get-TextSha256 -Text ($records -join "`n")
}

$rootOutput = & git rev-parse --show-toplevel 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Not inside a Git repository: $rootOutput"
}
$root = ($rootOutput | Select-Object -First 1).Trim()
Set-Location -LiteralPath $root

$plan = @(
    "python -m unittest discover -s tests -p 'test_*.py' -v",
    "node --test <all tests/*.test.js>",
    "python -m py_compile <all repository *.py>",
    "node --check <all repository *.js>",
    "git diff --check origin/main...HEAD plus index/worktree cleanliness"
)
if ($PlanOnly) {
    $plan | ForEach-Object { Write-Output $_ }
    exit 0
}

$guardedPaths = [ordered]@{
    "flowboard.db" = Join-Path $root "flowboard.db"
    "flowboard.db-wal" = Join-Path $root "flowboard.db-wal"
    "flowboard.db-shm" = Join-Path $root "flowboard.db-shm"
    "backups" = Join-Path $root "backups"
    "flowboard-attachments" = Join-Path $root "flowboard-attachments"
}
$guardSnapshotsBefore = [ordered]@{}
foreach ($entry in $guardedPaths.GetEnumerator()) {
    $guardSnapshotsBefore[$entry.Key] = Get-PathSnapshot -Path $entry.Value
}
$environmentSnapshotBefore = Get-RootEnvironmentSnapshot -Root $root

try {
    Invoke-Checked -Label "Python full suite" -Command {
        & python -m unittest discover -s tests -p "test_*.py" -v
    }

    $nodeTests = @(Get-ChildItem -LiteralPath (Join-Path $root "tests") -Filter "*.test.js" -File | ForEach-Object FullName)
    if ($nodeTests.Count -eq 0) {
        throw "No Node test files were found."
    }
    Invoke-Checked -Label "Node full suite" -Command {
        & node --test @nodeTests
    }

    $pythonFiles = @(Get-ChildItem -LiteralPath $root -Recurse -Filter "*.py" -File | Where-Object { $_.FullName -notmatch "[\\/]\.git[\\/]" })
    foreach ($file in $pythonFiles) {
        Invoke-Checked -Label "Python compile: $($file.FullName)" -Command {
            & python -m py_compile $file.FullName
        }
    }

    $javascriptFiles = @(Get-ChildItem -LiteralPath $root -Recurse -Filter "*.js" -File | Where-Object { $_.FullName -notmatch "[\\/]\.git[\\/]" })
    foreach ($file in $javascriptFiles) {
        Invoke-Checked -Label "JavaScript syntax: $($file.FullName)" -Command {
            & node --check $file.FullName
        }
    }

    Invoke-Checked -Label "Git whitespace check" -Command {
        & git diff --check "origin/main...HEAD"
    }
    Invoke-Checked -Label "Git working-tree whitespace check" -Command {
        & git diff --check
    }
    Invoke-Checked -Label "Git index whitespace check" -Command {
        & git diff --cached --check
    }

    $status = @(& git status --porcelain=v1 --untracked-files=all)
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect final Git status."
    }
    if ($status.Count -gt 0 -and ($status -join "").Length -gt 0) {
        throw "GIT_CLEANLINESS_FAILED: checks must finish with a clean worktree and index.`n$($status -join [Environment]::NewLine)"
    }
} finally {
    $guardViolations = [System.Collections.Generic.List[string]]::new()
    foreach ($entry in $guardedPaths.GetEnumerator()) {
        $before = $guardSnapshotsBefore[$entry.Key]
        $after = Get-PathSnapshot -Path $entry.Value
        if ($before.Exists -ne $after.Exists -or $before.Kind -ne $after.Kind -or $before.Digest -ne $after.Digest) {
            $guardViolations.Add($entry.Key)
        }
    }
    $environmentSnapshotAfter = Get-RootEnvironmentSnapshot -Root $root
    if ($environmentSnapshotBefore -ne $environmentSnapshotAfter) {
        $guardViolations.Add(".env*")
    }
    if ($guardViolations.Count -gt 0) {
        throw "REAL_DATA_GUARD_FAILED: protected runtime data changed during checks: $($guardViolations -join ', ')."
    }
}

Write-Output "FLOWBOARD_CHECKS_OK"
Write-Output "real_data_guard=unchanged"
$databaseSnapshotBefore = $guardSnapshotsBefore["flowboard.db"]
if ($databaseSnapshotBefore.Exists -and $databaseSnapshotBefore.Kind -eq "file") {
    Write-Output "real_database_sha256=$($databaseSnapshotBefore.Digest)"
} else {
    Write-Output "real_database_sha256=absent"
}
