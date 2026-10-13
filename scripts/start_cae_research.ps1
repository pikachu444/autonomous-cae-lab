# Independent research tools share the existing private Python and local service.
[CmdletBinding()]
param(
    [ValidateSet('material','data','numerical','pde','expert','runner','simulation','evaluation','study')][string]$Tool = 'runner',
    [string]$DocumentId,
    [string]$JobId,
    [switch]$Documents,
    [switch]$MCP,
    [switch]$Sensitivity,
    [string]$RuntimeRoot = (Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\windows-runtime'),
    [ValidateRange(1024,65535)][int]$Port = 8766,
    [string]$Store = (Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\research-store'),
    [switch]$PrepareOnly
)
$ErrorActionPreference = 'Stop'
if ($Tool -eq 'runner' -and $DocumentId) { throw 'Use -JobId to select a Runner job.' }
if ($Tool -ne 'runner' -and $JobId) { throw 'Use -DocumentId to select a research document.' }
& (Join-Path $PSScriptRoot 'start-windows.ps1') -NoBrowser -ResearchUI -Documents:$Documents -MCP:$MCP -Sensitivity:$Sensitivity -RuntimeRoot $RuntimeRoot -Port $Port -Store $Store
if (-not $?) { throw 'The shared research service could not be started or verified.' }
$python = Join-Path ([IO.Path]::GetFullPath($RuntimeRoot)) 'venv\Scripts\python.exe'
$url = "http://127.0.0.1:$Port"
$installation = Get-Content -Raw -LiteralPath (Join-Path $RuntimeRoot 'install-receipt.json') | ConvertFrom-Json
if ($PrepareOnly) {
    Write-Output ([pscustomobject]@{ServiceUrl=$url;Python=$python;Tool=$Tool;DocumentId=$DocumentId;JobId=$JobId})
    return
}
$desktopTool = $Tool.ToLowerInvariant()
$arguments = @('-m','apps.research.desktop','--service',$url,$desktopTool)
if ($DocumentId) { $arguments += @('--document-id',$DocumentId) }
if ($JobId) { $arguments += @('--job-id',$JobId) }
Push-Location -LiteralPath $installation.source_root
try {
    & $python @arguments
    $desktopExitCode = $LASTEXITCODE
} finally { Pop-Location }
if ($desktopExitCode -ne 0) {
    Write-Error "$Tool desktop exited with code $desktopExitCode." -ErrorAction Continue
}
exit $desktopExitCode
