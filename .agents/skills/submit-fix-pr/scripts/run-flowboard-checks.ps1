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

$databasePath = Join-Path $root "flowboard.db"
$databaseHashBefore = if (Test-Path -LiteralPath $databasePath) {
    (Get-FileHash -Algorithm SHA256 -LiteralPath $databasePath).Hash
} else {
    $null
}

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
    if ($null -ne $databaseHashBefore) {
        if (-not (Test-Path -LiteralPath $databasePath)) {
            throw "REAL_DATABASE_GUARD_FAILED: flowboard.db disappeared during checks."
        }
        $databaseHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $databasePath).Hash
        if ($databaseHashBefore -ne $databaseHashAfter) {
            throw "REAL_DATABASE_GUARD_FAILED: flowboard.db changed during checks."
        }
    }
}

Write-Output "FLOWBOARD_CHECKS_OK"
if ($null -ne $databaseHashBefore) {
    Write-Output "real_database_sha256=$databaseHashBefore"
} else {
    Write-Output "real_database_sha256=absent"
}
