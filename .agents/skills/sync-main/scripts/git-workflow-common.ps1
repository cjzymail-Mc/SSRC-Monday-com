Set-StrictMode -Version Latest

function Invoke-WorkflowGit {
    param([Parameter(Mandatory)][string[]]$Arguments)
    $output = & git @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "git $($Arguments -join ' ') failed: $($output -join [Environment]::NewLine)" }
    return ($output -join "`n").Trim()
}

function Get-GitHubRepositorySlug {
    param([Parameter(Mandatory)][string]$Url)
    $match = [regex]::Match($Url.Trim(), '^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)(?<slug>[^/\s]+/[^/\s]+?)(?:\.git)?/?$', 'IgnoreCase')
    if (-not $match.Success) { return $null }
    return $match.Groups['slug'].Value
}

function Read-WorkflowConfiguration {
    param([Parameter(Mandatory)][string]$Root)
    $configPath = Join-Path $Root '.agents/git-workflow.json'
    if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) { return @{} }
    $config = Get-Content -LiteralPath $configPath -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
    if ($config -isnot [System.Collections.IDictionary]) { throw 'Git workflow configuration must be an object.' }
    $known = @('repositoryPath', 'upstreamRepository', 'upstreamRemote', 'mainBranch', 'protectedPaths', 'protectedPathPatterns', 'legacyRecoveryJournals', 'checks', 'syntaxChecks')
    foreach ($key in $config.Keys) {
        if ($key -notin $known) { throw "Unknown Git workflow configuration field: $key" }
    }
    foreach ($key in @('repositoryPath', 'upstreamRepository', 'upstreamRemote', 'mainBranch')) {
        if ($config.Contains($key) -and ($config[$key] -isnot [string] -or -not $config[$key].Trim())) { throw "Invalid configuration field: $key" }
    }
    foreach ($key in @('protectedPaths', 'protectedPathPatterns', 'legacyRecoveryJournals')) {
        if ($config.Contains($key)) {
            if ($config[$key] -isnot [array]) { throw "$key must be an array." }
            foreach ($item in $config[$key]) {
                if ($item -isnot [string] -or -not $item) { throw "Invalid entry in $key" }
                if ($key -eq 'protectedPathPatterns') { [void][regex]::new($item) }
                elseif ([IO.Path]::IsPathRooted($item) -or $item -match '(^|[/\\])\.\.([/\\]|$)') { throw "$key entries must stay inside the repository." }
            }
        }
    }
    if ($config.Contains('syntaxChecks') -and $config['syntaxChecks'] -isnot [bool]) { throw 'syntaxChecks must be a boolean.' }
    return $config
}

function Get-RemoteSlug {
    param([Parameter(Mandatory)][string]$Remote, [switch]$Push)
    $arguments = @('remote', 'get-url', '--all')
    if ($Push) { $arguments += '--push' }
    $urls = @( (Invoke-WorkflowGit -Arguments ($arguments + $Remote)) -split "`n" )
    if ($urls.Count -ne 1) { throw "Remote $Remote must have exactly one URL for this operation." }
    $slug = Get-GitHubRepositorySlug -Url $urls[0]
    if (-not $slug) { throw "Remote $Remote is not a supported github.com URL." }
    return $slug
}

function Assert-RemoteRepository {
    param([string]$Remote, [string]$ExpectedRepository, [switch]$Push)
    $actual = Get-RemoteSlug -Remote $Remote -Push:$Push
    if (-not $actual.Equals($ExpectedRepository, [StringComparison]::OrdinalIgnoreCase)) { throw "Remote $Remote does not identify the verified repository $ExpectedRepository." }
}

function Invoke-WorkflowApi {
    param([Parameter(Mandatory)][string]$Endpoint)
    $output = & gh api $Endpoint 2>&1
    if ($LASTEXITCODE -ne 0) { throw "GitHub verification failed for $Endpoint; preserve state and diagnose authentication, network or API failure." }
    return ($output -join "`n") | ConvertFrom-Json -AsHashtable
}

function Resolve-WorkflowRoot {
    param([string]$RepositoryPath = '.')
    $root = Invoke-WorkflowGit -Arguments @('-C', $RepositoryPath, 'rev-parse', '--show-toplevel')
    $config = Read-WorkflowConfiguration -Root $root
    if ($config.Contains('repositoryPath')) {
        $target = [IO.Path]::GetFullPath((Join-Path $root $config['repositoryPath']))
        $root = Invoke-WorkflowGit -Arguments @('-C', $target, 'rev-parse', '--show-toplevel')
        if (-not ([IO.Path]::GetFullPath($root)).Equals($target, [StringComparison]::OrdinalIgnoreCase)) { throw 'repositoryPath must identify a Git repository root, not a directory in its parent repository.' }
        $config = Read-WorkflowConfiguration -Root $root
        if ($config.Contains('repositoryPath')) { throw 'Chained repositoryPath routing is not supported.' }
    }
    return [pscustomobject]@{ root = $root; config = $config }
}

function Resolve-WorkflowContext {
    param([string]$RepositoryPath = '.', [string]$Remote = '', [string]$MainBranch = '', [string]$ExpectedRepository = '', [switch]$ResolveUpstream, [switch]$InspectIdentity)
    $location = Resolve-WorkflowRoot -RepositoryPath $RepositoryPath
    $root = $location.root
    $config = $location.config
    Set-Location -LiteralPath $root
    foreach ($operation in @('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-merge', 'rebase-apply', 'sequencer')) {
        if (Test-Path -LiteralPath (Invoke-WorkflowGit -Arguments @('rev-parse', '--git-path', $operation))) { throw "SYNC_MAIN_OPERATION_IN_PROGRESS: $operation" }
    }
    if (-not $MainBranch) { $MainBranch = if ($config.Contains('mainBranch')) { $config['mainBranch'] } else { 'main' } }
    [void](Invoke-WorkflowGit -Arguments @('check-ref-format', '--branch', $MainBranch))
    if ($MainBranch.StartsWith('-')) { throw 'Invalid main branch.' }
    if (-not $ExpectedRepository -and $config.Contains('upstreamRepository')) { $ExpectedRepository = $config['upstreamRepository'] }
    if ($ExpectedRepository -and $ExpectedRepository -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$') { throw 'Expected repository must be owner/name.' }
    $remotes = @((Invoke-WorkflowGit -Arguments @('remote')) -split "`n" | Where-Object { $_ })
    if (-not $Remote -and $config.Contains('upstreamRemote')) { $Remote = $config['upstreamRemote'] }
    if ($Remote -and $Remote -notin $remotes) { throw "Missing configured upstream remote: $Remote" }
    if (-not $Remote -and $ExpectedRepository) {
        $matches = @($remotes | Where-Object { (Get-GitHubRepositorySlug -Url (Invoke-WorkflowGit -Arguments @('remote', 'get-url', $_))) -ieq $ExpectedRepository })
        if ('upstream' -in $matches) { $Remote = 'upstream' }
        elseif ('origin' -in $matches) { $Remote = 'origin' }
        elseif ($matches.Count -eq 1) { $Remote = $matches[0] }
        elseif ($matches.Count -gt 1) { throw 'Several upstream remotes match; specify upstreamRemote.' }
    }
    $candidate = $Remote
    if (-not $candidate) {
        if ('upstream' -in $remotes) { $candidate = 'upstream' }
        elseif ('origin' -in $remotes) { $candidate = 'origin' }
        elseif ($remotes.Count -eq 1) { $candidate = $remotes[0] }
        else { throw 'No unambiguous GitHub repository remote; specify the target repository or upstreamRemote.' }
    }
    $candidateSlug = Get-RemoteSlug -Remote $candidate
    if ($Remote -and $ExpectedRepository -and $candidateSlug -ine $ExpectedRepository) { throw 'Configured upstream remote and repository disagree.' }
    $metadata = $null
    if (($ResolveUpstream -or $InspectIdentity) -and -not $ExpectedRepository) {
        $metadata = Invoke-WorkflowApi -Endpoint "repos/$candidateSlug"
        if (-not $metadata.Contains('full_name') -or $metadata['full_name'] -ine $candidateSlug) { throw 'GitHub repository identity mismatch.' }
        if ($metadata.Contains('fork') -and $metadata['fork'] -eq $true) {
            if (-not $metadata.Contains('source') -or -not $metadata['source'].Contains('full_name')) { throw 'Fork source could not be verified.' }
            $ExpectedRepository = $metadata['source']['full_name']
        } else { $ExpectedRepository = $metadata['full_name'] }
        $Remote = $null
        foreach ($name in $remotes) {
            if ((Get-GitHubRepositorySlug -Url (Invoke-WorkflowGit -Arguments @('remote', 'get-url', $name))) -ieq $ExpectedRepository) {
                if (-not $Remote -or $name -eq 'upstream') { $Remote = $name }
            }
        }
    }
    if ($ExpectedRepository -and $candidateSlug -ieq $ExpectedRepository -and -not $Remote) { $Remote = $candidate }
    if ($Remote -and $ExpectedRepository) { Assert-RemoteRepository -Remote $Remote -ExpectedRepository $ExpectedRepository }
    $branch = Invoke-WorkflowGit -Arguments @('branch', '--show-current')
    if (-not $branch) { throw 'SYNC_MAIN_DETACHED: preserve work and choose a branch.' }
    $journal = Invoke-WorkflowGit -Arguments @('rev-parse', '--git-path', 'git-workflow-sync-main.json')
    $journals = @($journal | Where-Object { Test-Path -LiteralPath $_ })
    if ($config.Contains('legacyRecoveryJournals')) {
        foreach ($legacy in $config['legacyRecoveryJournals']) {
            $legacyPath = Invoke-WorkflowGit -Arguments @('rev-parse', '--git-path', $legacy)
            if (Test-Path -LiteralPath $legacyPath) { $journals += $legacyPath }
        }
    }
    if ($journals.Count -gt 1) { throw 'Multiple recovery journals exist; preserve them and reconcile before continuing.' }
    if ($journals.Count -eq 1) { $journal = $journals[0] }
    $context = [ordered]@{ root = $root; branch = $branch; main_branch = $MainBranch; upstream_repository = $ExpectedRepository; upstream_remote = $Remote; candidate_remote = $candidate; candidate_repository = $candidateSlug; recovery_journal = $journal; config = $config }
    if ($InspectIdentity) {
        if (-not $ExpectedRepository) { throw 'Upstream identity is unresolved.' }
        $user = Invoke-WorkflowApi -Endpoint 'user'
        if (-not $user.Contains('login') -or -not $user['login']) { throw 'Authenticated GitHub identity is missing.' }
        $context['login'] = $user['login']
        if ($user['login'] -ieq ($ExpectedRepository -split '/')[0]) {
            $context['route'] = 'direct-main'
        } else {
            if (-not $metadata -or $metadata['full_name'] -ine $ExpectedRepository) { $metadata = Invoke-WorkflowApi -Endpoint "repos/$ExpectedRepository" }
            if ($metadata['full_name'] -ine $ExpectedRepository) { throw 'Upstream identity mismatch.' }
            $admin = $metadata.Contains('permissions') -and $metadata['permissions'].Contains('admin') -and $metadata['permissions']['admin'] -is [bool] -and $metadata['permissions']['admin']
            $context['route'] = if ($admin) { 'direct-main' } else { 'fork-pr' }
            if (-not $admin -and (-not $metadata.Contains('private') -or $metadata['private'] -isnot [bool] -or $metadata['private'])) { throw 'Contributor fork submission requires a verified public upstream.' }
        }
        if ($context['route'] -eq 'direct-main') {
            if (-not $Remote) { throw 'Add a verified upstream remote before direct submission.' }
            Assert-RemoteRepository -Remote $Remote -ExpectedRepository $ExpectedRepository -Push
        }
    }
    return [pscustomobject]$context
}

function Test-WorkflowProtectedPath {
    param([string]$Path, [System.Collections.IDictionary]$Config = @{})
    $candidate = $Path.Replace('\', '/')
    if ($candidate -match '(?i)(^|/)(\.local|\.ssh|backups?|attachments?|credentials(?:\.[^/]*)?|id_rsa|id_ed25519)(/|$)') { return $true }
    if ($candidate -match '(?i)(^|/)\.env(?:\.[^/]*)?(/|$)' -and $candidate -notmatch '(?i)(^|/)\.env\.(example|sample|template)$') { return $true }
    if ($candidate -match '(?i)\.(?:db|sqlite|sqlite3)(?:-(?:wal|shm))?$|\.(?:pem|key|pfx|p12)$' -or $candidate -match '(?i)^(temp\.md|\.copilot-(message\.md|state\.json|task\.md))$') { return $true }
    if ($Config.Contains('protectedPaths')) {
        foreach ($protected in $Config['protectedPaths']) {
            $prefix = $protected.Replace('\', '/').TrimEnd('/')
            if ($candidate -ieq $prefix -or $candidate.StartsWith($prefix + '/', [StringComparison]::OrdinalIgnoreCase)) { return $true }
        }
    }
    if ($Config.Contains('protectedPathPatterns')) {
        foreach ($pattern in $Config['protectedPathPatterns']) { if ($candidate -match $pattern) { return $true } }
    }
    return $false
}
