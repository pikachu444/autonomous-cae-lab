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
if ($ParaViewHome) {
    $installationRoot = [IO.Path]::GetFullPath($ParaViewHome)
    $candidates = @((Join-Path $installationRoot 'bin\paraview.exe'), (Join-Path $installationRoot 'paraview.exe'))
    $ParaViewExe = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if (-not $ParaViewExe) { throw "paraview.exe was not found in '$installationRoot\bin' or '$installationRoot'. Choose -ParaViewHome or an installed -ParaViewExe; no service was started." }
}
# Reject explicit missing inputs before installing packages or starting a service.
foreach ($entry in @(@('ParaViewExe',$ParaViewExe), @('Project',$Project), @('InputPath',$InputPath), @('Python',$Python))) {
    if ($entry[1] -and -not (Test-Path -LiteralPath $entry[1] -PathType Leaf)) {
        throw "-$($entry[0]) file was not found: $($entry[1]). Check the moved file or choose its current installed location; no service was started."
    }
}
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
    $installation = Get-Content -Encoding UTF8 -Raw -LiteralPath (Join-Path $RuntimeRoot 'install-receipt.json') | ConvertFrom-Json
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
