# Open an exact native project or VTU/PVD input; no example or solver is selected.
[CmdletBinding()]
param(
    [string]$Project,
    [string]$InputPath,
    [string]$InputId,
    [string]$OriginJobId,
    [string]$ParaViewHome,
    [string]$ParaViewExe,
    [string]$OutputDirectory,
    [string]$ServiceUrl,
    [string]$Python,
    [switch]$ConnectService,
    [string]$RuntimeRoot = (Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\windows-runtime'),
    [ValidateRange(1024,65535)][int]$Port = 8766,
    [string]$Store = (Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\research-store'),
    [switch]$PrepareOnly
)
$ErrorActionPreference = 'Stop'
$repository = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (@($Project, $InputPath, $InputId).Where({ $_ }).Count -gt 1) { throw 'Choose one of -Project, -InputPath or -InputId.' }
if ($ParaViewHome -and $ParaViewExe) { throw 'Choose -ParaViewHome or -ParaViewExe.' }
if ($ParaViewHome) { $ParaViewExe = Join-Path $ParaViewHome 'bin\paraview.exe' }
if (-not $ServiceUrl) {
    & (Join-Path $PSScriptRoot 'start-windows.ps1') -NoBrowser -ResearchUI -RuntimeRoot $RuntimeRoot -Port $Port -Store $Store
    if (-not $?) { throw 'The shared research service could not be started or verified.' }
    $ServiceUrl = "http://127.0.0.1:$Port"
} elseif (-not $Python) {
    # An explicit existing service stays authoritative; install its desktop
    # client runtime without starting a second controller.
    & (Join-Path $PSScriptRoot 'install-windows.ps1') -ResearchUI -RuntimeRoot $RuntimeRoot
    if (-not $?) { throw 'The private desktop client Python could not be installed.' }
}
if (-not $Python) {
    $Python = Join-Path ([IO.Path]::GetFullPath($RuntimeRoot)) 'venv\Scripts\python.exe'
    $installation = Get-Content -Raw -LiteralPath (Join-Path $RuntimeRoot 'install-receipt.json') | ConvertFrom-Json
    $repository = $installation.source_root
}
$arguments = @('-m','apps.research.desktop','--service',$ServiceUrl,'post')
if ($ParaViewExe) { $arguments += @('--executable',[IO.Path]::GetFullPath($ParaViewExe)) }
if ($Project) { $arguments += @('--project',(Resolve-Path -LiteralPath $Project).Path) }
if ($InputPath) { $arguments += @('--input-path',(Resolve-Path -LiteralPath $InputPath).Path) }
if ($InputId) { $arguments += @('--input-id',$InputId) }
if ($OriginJobId) { $arguments += @('--job-id',$OriginJobId) }
if ($OutputDirectory) { $arguments += @('--output',[IO.Path]::GetFullPath($OutputDirectory)) }
if ($PrepareOnly) { $arguments += '--prepare-only' }
Push-Location -LiteralPath $repository
try {
    & $Python @arguments
    if ($LASTEXITCODE -ne 0) { throw "Post launch helper exited with code $LASTEXITCODE" }
} finally { Pop-Location }
