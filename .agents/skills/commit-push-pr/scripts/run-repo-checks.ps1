# Run repository-configured checks only when full regression is required.
[CmdletBinding()]
param([string]$RepositoryPath = '.', [string]$SubmissionBase = '', [switch]$PlanOnly, [switch]$CollectAllFailures)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../../sync-main/scripts/git-workflow-common.ps1')

function Invoke-Checked {
    param([Parameter(Mandatory)][string]$Label, [Parameter(Mandatory)][scriptblock]$Command)
    Write-Host "==> $Label"
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Label failed with exit code $LASTEXITCODE" }
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

function Get-TrackedSourcePaths {
    # Read Git's NUL-delimited UTF-8 output directly; line-based native output
    # handling and core.quotepath would otherwise damage unusual file names.
    $start = [System.Diagnostics.ProcessStartInfo]::new()
    $start.FileName = "git"
    $start.UseShellExecute = $false
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.StandardOutputEncoding = [System.Text.UTF8Encoding]::new($false)
    $start.ArgumentList.Add("ls-files")
    $start.ArgumentList.Add("-z")
    $start.ArgumentList.Add("--cached")
    $process = [System.Diagnostics.Process]::Start($start)
    try {
        $errorRead = $process.StandardError.ReadToEndAsync()
        $output = $process.StandardOutput.ReadToEnd()
        $process.WaitForExit()
        $errorText = $errorRead.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) {
            throw "Unable to enumerate tracked source files: $errorText"
        }
        foreach ($path in $output.Split([char]0, [System.StringSplitOptions]::RemoveEmptyEntries)) {
            if ($path -match '^(?:\.agents/|tests/skill_checks/)') { continue }
            if ($path -match '\.(?:py|js|mjs|cjs)$') { $path }
        }
    } finally {
        $process.Dispose()
    }
}

$location = Resolve-WorkflowRoot -RepositoryPath $RepositoryPath
$root = $location.root
$config = $location.config
Set-Location -LiteralPath $root
$checks = @()
if ($config.Contains('checks')) {
    if ($config['checks'] -isnot [array] -or $config['checks'].Count -eq 0) { throw 'checks must be a nonempty array.' }
    foreach ($entry in $config['checks']) {
        if ($entry -isnot [System.Collections.IDictionary] -or -not $entry.Contains('name') -or -not $entry.Contains('command') -or -not $entry.Contains('arguments')) { throw 'Each check requires name, command and arguments.' }
        if ($entry['name'] -isnot [string] -or -not $entry['name'] -or $entry['command'] -isnot [string] -or -not $entry['command'] -or $entry['arguments'] -isnot [array]) { throw 'Invalid configured check.' }
        foreach ($argument in $entry['arguments']) { if ($argument -isnot [string]) { throw 'Check arguments must be strings.' } }
        $checks += $entry
    }
} else {
    $package = if (Test-Path -LiteralPath 'package.json') { Get-Content -LiteralPath 'package.json' -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable } else { @{} }
    if ($package.Contains('scripts') -and $package['scripts'].Contains('check')) {
        $checks += @{ name = 'Repository checks'; command = 'npm'; arguments = @('run', 'check') }
    } elseif (Test-Path -LiteralPath 'tests' -PathType Container) {
        if (@(Get-ChildItem -LiteralPath 'tests' -Filter 'test_*.py' -File).Count -gt 0) {
            $pythonArguments = @('-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py', '-v')
            if (-not $CollectAllFailures) { $pythonArguments += '-f' }
            $checks += @{ name = 'Python full suite'; command = 'python'; arguments = $pythonArguments }
        }
        $nodeTests = @(Get-ChildItem -LiteralPath 'tests' -Filter '*.test.js' -File | ForEach-Object FullName)
        if ($nodeTests.Count -gt 0) { $checks += @{ name = 'Node full suite'; command = 'node'; arguments = @('--test') + $nodeTests } }
    }
}
if ($checks.Count -eq 0) { throw 'No full regression command was discovered; configure checks rather than claim PASS.' }
$syntaxChecks = if ($config.Contains('syntaxChecks')) { $config['syntaxChecks'] } else { $true }
if (-not $SubmissionBase) {
    $main = if ($config.Contains('mainBranch')) { $config['mainBranch'] } else { 'main' }
    $SubmissionBase = $main
    foreach ($name in @('upstream', 'origin')) {
        & git show-ref --verify --quiet "refs/remotes/$name/$main"
        if ($LASTEXITCODE -eq 0) { $SubmissionBase = "refs/remotes/$name/$main"; break }
    }
}
$SubmissionBase = Invoke-WorkflowGit -Arguments @('rev-parse', '--verify', '--end-of-options', "$SubmissionBase^{commit}")
if ($PlanOnly) {
    foreach ($check in $checks) { Write-Output ($check['name'] + ': ' + $check['command'] + ' ' + ($check['arguments'] -join ' ')) }
    Write-Output "tracked_source_syntax=$syntaxChecks"
    Write-Output "submission_base=$SubmissionBase"
    Write-Output 'Plan only; checks and protected-data guards have not run.'
    exit 0
}

function Get-GuardPaths {
    $paths = @('backups', 'attachments', '.local')
    if ($config.Contains('protectedPaths')) { $paths += $config['protectedPaths'] }
    $paths += @(Get-ChildItem -LiteralPath $root -File -Force | Where-Object { $_.Name -match '(?i)\.(db|sqlite|sqlite3)(-(wal|shm))?$' } | ForEach-Object Name)
    return @($paths | Select-Object -Unique)
}
$guardSnapshotsBefore = [ordered]@{}
foreach ($relative in (Get-GuardPaths)) { $guardSnapshotsBefore[$relative] = Get-PathSnapshot -Path (Join-Path $root $relative) }
$environmentSnapshotBefore = Get-RootEnvironmentSnapshot -Root $root
$checkFailure = $null
$guardFailure = $null
try {
    $failures = [System.Collections.Generic.List[System.Exception]]::new()
    foreach ($check in $checks) {
        try {
            $checkCommand = $check['command']
            $checkArguments = [string[]]$check['arguments']
            Invoke-Checked -Label $check['name'] -Command { & $checkCommand @checkArguments }
        } catch {
            if (-not $CollectAllFailures) { throw }
            $failures.Add($_.Exception)
        }
    }
    if ($failures.Count -gt 0) { throw [System.AggregateException]::new('Product checks failed.', $failures.ToArray()) }
    if ($syntaxChecks) {
        $sourcePaths = @(Get-TrackedSourcePaths)
        $pythonFiles = @($sourcePaths | Where-Object { $_ -match '\.py$' })
        if ($pythonFiles.Count -gt 0) {
            Invoke-Checked -Label "Python syntax batch ($($pythonFiles.Count) tracked files)" -Command {
                # stdin avoids Windows command-line length limits. compile(bytes)
                # respects source encoding and does not create __pycache__ artifacts.
                $syntaxCheck = @'
import json
from pathlib import Path
import sys

for name in json.load(sys.stdin):
    compile(Path(name).read_bytes(), name, "exec")
'@
                ConvertTo-Json -InputObject $pythonFiles -Compress | & python -c $syntaxCheck
            }
        }

        $javascriptFiles = @($sourcePaths | Where-Object { $_ -match '\.(?:js|mjs|cjs)$' })
        foreach ($file in $javascriptFiles) {
            Invoke-Checked -Label "JavaScript syntax: $file" -Command {
                & node --check (Join-Path $root $file)
            }
        }

    }
    Invoke-Checked -Label 'Git whitespace check' -Command { & git diff --check "$SubmissionBase...HEAD" }
    Invoke-Checked -Label 'Git working-tree whitespace check' -Command { & git diff --check }
    Invoke-Checked -Label 'Git index whitespace check' -Command { & git diff --cached --check }
    $status = @(& git status --porcelain=v1 --untracked-files=all)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect final Git status.' }
    if (($status -join '').Length -gt 0) { throw 'GIT_CLEANLINESS_FAILED: checks must finish with a clean worktree and index.' }
} catch { $checkFailure = $_ }
finally {
    try {
        $violations = [System.Collections.Generic.List[string]]::new()
        foreach ($relative in @(@($guardSnapshotsBefore.Keys) + @(Get-GuardPaths) | Select-Object -Unique)) {
            $before = if ($guardSnapshotsBefore.Contains($relative)) { $guardSnapshotsBefore[$relative] } else { [pscustomobject]@{ Exists = $false; Kind = 'absent'; Digest = '' } }
            $after = Get-PathSnapshot -Path (Join-Path $root $relative)
            if ($before.Exists -ne $after.Exists -or $before.Kind -ne $after.Kind -or $before.Digest -ne $after.Digest) { $violations.Add($relative) }
        }
        if ($environmentSnapshotBefore -ne (Get-RootEnvironmentSnapshot -Root $root)) { $violations.Add('.env*') }
        if ($violations.Count -gt 0) { throw "REAL_DATA_GUARD_FAILED: protected runtime data changed: $($violations -join ', ')." }
    } catch { $guardFailure = $_ }
}
if ($null -ne $checkFailure -and $null -ne $guardFailure) { throw [System.AggregateException]::new('CHECKS_AND_REAL_DATA_GUARD_FAILED', [System.Exception[]]@($checkFailure.Exception, $guardFailure.Exception)) }
if ($null -ne $checkFailure) { throw $checkFailure }
if ($null -ne $guardFailure) { throw $guardFailure }
Write-Output 'REPO_CHECKS_OK'
Write-Output 'real_data_guard=unchanged'
