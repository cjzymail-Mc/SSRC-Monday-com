[CmdletBinding()]
param([string]$RepositoryPath = '.', [string]$Remote = '', [string]$MainBranch = '', [string]$ExpectedRepository = '', [switch]$ResolveUpstream, [switch]$InspectIdentity)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'git-workflow-common.ps1')
$context = Resolve-WorkflowContext @PSBoundParameters
$context | ConvertTo-Json -Depth 10
