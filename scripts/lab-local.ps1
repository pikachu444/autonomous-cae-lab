# Compatibility entrypoint for the shared workbench; no research profile or AI account is required.
[CmdletBinding()]
param(
    [string]$Store = 'runs/local-lab',
    [ValidateRange(1024,65535)][int]$Port = 8766,
    [string]$Python = 'python',
    [string]$WorkbenchConfigPath,
    [string]$AssemblyMeshConfigPath,
    [string[]]$Library = @(),
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot)
)
& (Join-Path $PSScriptRoot 'cae-research-local.ps1') @PSBoundParameters
exit $LASTEXITCODE
