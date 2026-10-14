# SPDX-License-Identifier: BSD-3-Clause
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$ParaViewDir,
  [Parameter(Mandatory=$true)][string]$Qt6Dir,
  [Parameter(Mandatory=$true)][string]$BuildDir,
  [string]$Python = 'python',
  [switch]$RunQtHarness
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
foreach ($name in @('cmake','cl','ninja','ctest',$Python)) {
  if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
    throw "Missing $name. Use an x64 Native Tools prompt with the free OSS Build Tools workload and Windows SDK."
  }
}
$jobRunner = Join-Path $PSScriptRoot '../../scripts/native_check.py'
if (-not (Test-Path -LiteralPath $jobRunner -PathType Leaf)) {
  throw 'The existing root-owned scripts/native_check.py is required; no test app was launched.'
}
if (-not (Test-Path $ParaViewDir -PathType Container)) { throw 'ParaView SDK config directory is absent' }
if (-not (Test-Path (Join-Path $Qt6Dir 'Qt6Config.cmake'))) { throw 'Qt 6.9.0 development config is absent' }
if (Test-Path $BuildDir) { throw 'Use a new build directory; existing builds and logs are preserved' }
New-Item -ItemType Directory $BuildDir | Out-Null
$BuildDir = (Resolve-Path $BuildDir).Path
function Invoke-Logged([string]$Program, [string[]]$Arguments, [string]$Log) {
  & $Program @Arguments 2>&1 | Tee-Object -FilePath (Join-Path $BuildDir $Log)
  if ($LASTEXITCODE -ne 0) { throw "$Program failed ($LASTEXITCODE). Retained log: $Log" }
}
Invoke-Logged 'cmake' @('-S',$PSScriptRoot,'-B',$BuildDir,'-G','Ninja',
  '-DCMAKE_BUILD_TYPE=Release',"-DParaView_DIR=$ParaViewDir","-DQt6_DIR=$Qt6Dir",'-DBUILD_TESTING=ON') 'configure.log'
Invoke-Logged 'cmake' @('--build',$BuildDir,'--config','Release') 'build.log'
# The existing Job runner owns ctest and every executable it launches.
Invoke-Logged $Python @($jobRunner,'--timeout','120','--output-dir',(Join-Path $BuildDir 'core-test-job'),'--',
  'ctest','--test-dir',$BuildDir,'-C','Release','--output-on-failure','-R','cae_exit_transaction|cae_exit_c_python_abi') 'core-tests.log'
if ($RunQtHarness) {
  $previousCapture = $env:CAE_EXIT_CAPTURE_DIR
  $env:CAE_EXIT_CAPTURE_DIR = Join-Path $BuildDir 'qt-captures'
  New-Item -ItemType Directory $env:CAE_EXIT_CAPTURE_DIR | Out-Null
  try {
    Invoke-Logged $Python @($jobRunner,'--timeout','120','--output-dir',(Join-Path $BuildDir 'qt-test-job'),'--',
      'ctest','--test-dir',$BuildDir,'-C','Release','--output-on-failure','-R','cae_exit_qt') 'qt-tests.log'
  } finally {
    if ($null -eq $previousCapture) { Remove-Item Env:CAE_EXIT_CAPTURE_DIR }
    else { $env:CAE_EXIT_CAPTURE_DIR = $previousCapture }
  }
}
Write-Output 'Build finished. This is NOT Windows ParaView end-to-end acceptance. Pin the artifact and run the managed native checklist.'
