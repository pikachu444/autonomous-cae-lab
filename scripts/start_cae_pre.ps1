# Start an editable native Pre document through the shared private runtime.
[CmdletBinding()]
param(
    [string]$FreeCADRoot,
    [string]$FreeCADExe,
    [string]$Source,
    [string]$InputId,
    [string]$Assembly,
    [string]$Output,
    [string]$Gmsh,
    [string]$ServiceUrl,
    [string]$Python,
    [string]$RuntimeRoot = (Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\windows-runtime'),
    [ValidateRange(1024,65535)][int]$Port = 8766,
    [string]$Store = (Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\research-store'),
    [switch]$PrepareOnly
)
$ErrorActionPreference = 'Stop'
$repository = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if ($FreeCADRoot -and $FreeCADExe) { throw 'Choose -FreeCADRoot or -FreeCADExe.' }
if ($FreeCADRoot) {
    $installationRoot = [IO.Path]::GetFullPath($FreeCADRoot)
    $candidates = @((Join-Path $installationRoot 'bin\FreeCAD.exe'), (Join-Path $installationRoot 'FreeCAD.exe'))
    $FreeCADExe = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if (-not $FreeCADExe) { throw "FreeCAD.exe was not found in '$installationRoot\bin' or '$installationRoot'. Choose -FreeCADRoot or an installed -FreeCADExe." }
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
$arguments = @('-m','apps.research.desktop','--service',$ServiceUrl,'pre')
if ($FreeCADExe) { $arguments += @('--executable',[IO.Path]::GetFullPath($FreeCADExe)) }
if ($Source) { $arguments += @('--source',(Resolve-Path -LiteralPath $Source).Path) }
if ($InputId) { $arguments += @('--input-id',$InputId) }
if ($Assembly) { $arguments += @('--assembly',(Resolve-Path -LiteralPath $Assembly).Path) }
if ($Output) { $arguments += @('--output',[IO.Path]::GetFullPath($Output)) }
if ($Gmsh) { $arguments += @('--gmsh',(Resolve-Path -LiteralPath $Gmsh).Path) }
if ($PrepareOnly) { $arguments += '--prepare-only' }
Push-Location -LiteralPath $repository
try {
    & $Python @arguments
    if ($LASTEXITCODE -ne 0) { throw "Pre launch helper exited with code $LASTEXITCODE" }
} finally { Pop-Location }
