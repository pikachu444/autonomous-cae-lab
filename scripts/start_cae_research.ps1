# Material editor with the existing verified private-runtime/service launcher.
[CmdletBinding()]
param(
    [string]$DocumentId,
    [string]$RuntimeRoot = (Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\windows-runtime'),
    [ValidateRange(1024,65535)][int]$Port = 8766,
    [string]$Store = (Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\research-store'),
    [switch]$PrepareOnly
)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'start-windows.ps1') -NoBrowser -ResearchUI -RuntimeRoot $RuntimeRoot -Port $Port -Store $Store
if (-not $?) { throw 'The shared research service could not be started or verified.' }
$python = Join-Path ([IO.Path]::GetFullPath($RuntimeRoot)) 'venv\Scripts\python.exe'
$url = "http://127.0.0.1:$Port"
if ($PrepareOnly) {
    Write-Output ([pscustomobject]@{ServiceUrl=$url;Python=$python;DocumentId=$DocumentId})
    return
}
$arguments = @('-m','apps.research.material_window','--service',$url)
if ($DocumentId) { $arguments += @('--document-id',$DocumentId) }
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw "Material Research exited with code $LASTEXITCODE" }
