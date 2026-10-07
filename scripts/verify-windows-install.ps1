# Reproducible bootstrap smoke test. Leaves the uniquely named experiment store.
[CmdletBinding()]
param(
    [string]$RuntimeRoot = (Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\windows-runtime'),
    [ValidateRange(1024,65535)][int]$Port = 8767
)
$ErrorActionPreference = 'Stop'
$store = Join-Path $env:LOCALAPPDATA ('AutonomousCAELab\verification-store-' + [guid]::NewGuid().ToString('N'))
$existing = @(Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort $Port -State Listen -ErrorAction SilentlyContinue).Count -gt 0
$started = $false
try {
    & (Join-Path $PSScriptRoot 'start-windows.ps1') -NoBrowser -RuntimeRoot $RuntimeRoot -Store $store -Port $Port
    if (-not $?) { throw 'Windows launcher failed.' }
    $started = -not $existing
    $python = Join-Path ([IO.Path]::GetFullPath($RuntimeRoot)) 'venv\Scripts\python.exe'
    & $python (Join-Path $PSScriptRoot 'verify_windows_install.py') --url "http://127.0.0.1:$Port"
    if ($LASTEXITCODE -ne 0) { throw "Numerical HTTP verification failed with exit code $LASTEXITCODE" }
    Write-Host "Retained verification store: $store"
} finally {
    if ($started) {
        & (Join-Path $PSScriptRoot 'stop-windows.ps1') -Force -RuntimeRoot $RuntimeRoot -Port $Port
    }
}
