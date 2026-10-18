# Install a verified local Data package without its developer SDK.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$PackageRoot,
    [string]$RuntimeRoot = (Join-Path $env:LOCALAPPDATA 'AutonomousCAELab/windows-runtime'),
    [string]$DataRuntimeRoot = (Join-Path $env:LOCALAPPDATA 'AutonomousCAELab/data-runtime')
)
$ErrorActionPreference = 'Stop'
$package = (Resolve-Path -LiteralPath $PackageRoot).Path
$python = Join-Path ([IO.Path]::GetFullPath($RuntimeRoot)) 'venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $python -PathType Leaf)) {
    throw '먼저 Install-CAE-Lab.cmd로 연구 프로그램을 설치하세요.'
}
$source = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $source
try {
    & $python -m apps.research.native_data_runtime --install $package --root ([IO.Path]::GetFullPath($DataRuntimeRoot))
    if ($LASTEXITCODE -ne 0) { throw 'Data runtime 설치를 완료하지 못했습니다. 기존 설치는 보존됩니다.' }
} finally { Pop-Location }
