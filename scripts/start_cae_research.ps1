# Research tools using the existing private-runtime/service launcher.
[CmdletBinding()]
param(
    [ValidateSet('material','runner')][string]$Tool = 'material',
    [string]$DocumentId,
    [string]$JobId,
    [string]$RuntimeRoot = (Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\windows-runtime'),
    [ValidateRange(1024,65535)][int]$Port = 8766,
    [string]$Store = (Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\research-store'),
    [switch]$PrepareOnly
)
$ErrorActionPreference = 'Stop'
if ($Tool -eq 'runner' -and $DocumentId) { throw 'Use -JobId to select a Runner job.' }
if ($Tool -eq 'material' -and $JobId) { throw 'Use -DocumentId to select a Material document.' }
& (Join-Path $PSScriptRoot 'start-windows.ps1') -NoBrowser -ResearchUI -RuntimeRoot $RuntimeRoot -Port $Port -Store $Store
if (-not $?) { throw 'The shared research service could not be started or verified.' }
$python = Join-Path ([IO.Path]::GetFullPath($RuntimeRoot)) 'venv\Scripts\python.exe'
$url = "http://127.0.0.1:$Port"
if ($PrepareOnly) {
    Write-Output ([pscustomobject]@{ServiceUrl=$url;Python=$python;Tool=$Tool;DocumentId=$DocumentId;JobId=$JobId})
    return
}
$arguments = @('-m',"apps.research.$($Tool)_window",'--service',$url)
if ($DocumentId) { $arguments += @('--document-id',$DocumentId) }
if ($JobId) { $arguments += @('--job-id',$JobId) }
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw "$Tool exited with code $LASTEXITCODE" }
