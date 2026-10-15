# SPDX-License-Identifier: BSD-3-Clause
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$ParaViewDir,
  [Parameter(Mandatory=$true)][string]$Qt6Dir,
  [Parameter(Mandatory=$true)][string]$BuildDir,
  [string]$Python = 'python',
  [ValidateSet('Ninja','Visual Studio 17 2022')][string]$Generator = 'Ninja',
  [switch]$RunQtHarness
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$requiredTools = @('cmake','cl','ctest',$Python)
if ($Generator -eq 'Ninja') { $requiredTools += 'ninja' }
foreach ($name in $requiredTools) {
  if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
    throw "Missing $name. Use an x64 Native Tools prompt with the free OSS Build Tools workload and Windows SDK."
  }
}
# CreateProcessW in the existing Job runner needs an executable path, rather
# than PowerShell's command lookup. Resolve it before launching any test app.
$ctestExecutable = (Get-Command ctest -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
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
$configureArguments = @('-S',$PSScriptRoot,'-B',$BuildDir,'-G',$Generator,
  '-DCMAKE_BUILD_TYPE=Release',"-DParaView_DIR=$ParaViewDir","-DQt6_DIR=$Qt6Dir",'-DBUILD_TESTING=ON')
if ($Generator -eq 'Visual Studio 17 2022') {
  $configureArguments += @('-A','x64','-T','host=x64','-DCMAKE_CONFIGURATION_TYPES=Release')
}
Invoke-Logged 'cmake' $configureArguments 'configure.log'
Invoke-Logged 'cmake' @('--build',$BuildDir,'--config','Release') 'build.log'
# The existing Job runner owns ctest and every executable it launches.
Invoke-Logged $Python @($jobRunner,'--timeout','120','--output-dir',(Join-Path $BuildDir 'core-test-job'),'--',
  $ctestExecutable,'--test-dir',$BuildDir,'-C','Release','--output-on-failure','-R','cae_exit_transaction|cae_exit_c_python_abi') 'core-tests.log'
if ($RunQtHarness) {
  $previousCapture = $env:CAE_EXIT_CAPTURE_DIR
  $env:CAE_EXIT_CAPTURE_DIR = Join-Path $BuildDir 'qt-captures'
  New-Item -ItemType Directory $env:CAE_EXIT_CAPTURE_DIR | Out-Null
  try {
    Invoke-Logged $Python @($jobRunner,'--timeout','120','--output-dir',(Join-Path $BuildDir 'qt-test-job'),'--',
      $ctestExecutable,'--test-dir',$BuildDir,'-C','Release','--output-on-failure','-R','cae_exit_qt') 'qt-tests.log'
  } finally {
    if ($null -eq $previousCapture) { Remove-Item Env:CAE_EXIT_CAPTURE_DIR }
    else { $env:CAE_EXIT_CAPTURE_DIR = $previousCapture }
  }
}
Write-Output 'Build finished. This is NOT Windows ParaView end-to-end acceptance. Pin the artifact and run the managed native checklist.'
