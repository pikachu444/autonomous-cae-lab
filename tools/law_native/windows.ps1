[CmdletBinding()]
param(
  [string]$Python = 'py',
  [string[]]$PythonArgs = @('-3.12'),
  [string]$Venv = '.venv-law-native',
  [string]$Wheelhouse = '',
  [switch]$Install,
  [switch]$RunSpatial,
  [switch]$RunGui
)
$ErrorActionPreference = 'Stop'
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Output = Join-Path $Repo ('runs\law-native-windows-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Output | Out-Null
$Runner = $Python
$RunnerArgs = $PythonArgs
$Check = Join-Path $PSScriptRoot 'owned_check.py'
function Invoke-OwnedCheck([string]$Name, [int]$Seconds, [string[]]$Command) {
  & $Runner @RunnerArgs $Check --output (Join-Path $Output $Name) --timeout $Seconds -- @Command
  if ($LASTEXITCODE -ne 0) { throw "Check '$Name' exited $LASTEXITCODE. Preserve its stdout/stderr/receipt; do not treat timeout as PASS." }
}
Push-Location $Repo
Start-Transcript -Path (Join-Path $Output 'powershell.log') | Out-Null
try {
  $VenvPath = if ([IO.Path]::IsPathRooted($Venv)) { [IO.Path]::GetFullPath($Venv) } else { [IO.Path]::GetFullPath((Join-Path $Repo $Venv)) }
  $VenvPython = Join-Path $VenvPath 'Scripts\python.exe'
  if ($Install) {
    if (-not (Test-Path $VenvPython)) {
      Invoke-OwnedCheck 'create-venv' 60 (@($Python) + $PythonArgs + @('-m','venv',$VenvPath))
    }
    $Runner = $VenvPython; $RunnerArgs = @()
    $PackageArgs = @('-m','pip','--isolated','install','--no-input','--report',(Join-Path $Output 'pip-report.json'))
    if ($Wheelhouse) {
      $PackageArgs += @('--no-index','--find-links',(Resolve-Path $Wheelhouse).Path)
    } else { $PackageArgs += @('--index-url','https://pypi.org/simple') }
    # Existing repository dependencies; no alternative solver, optimizer, or MFront compiler.
    $PackageArgs += @('-e','.[material,research-ui]','pytest==8.4.2')
    Invoke-OwnedCheck 'install-fixed-dependencies' 300 (@($VenvPython) + $PackageArgs)
  }
  if (-not (Test-Path $VenvPython)) { throw 'No selected venv. Use -Install explicitly or pass the existing environment path.' }
  $Runner = $VenvPython; $RunnerArgs = @()
  Invoke-OwnedCheck 'point-retention-J2' 60 @($Runner,'-m','pytest','-q',
    'tests/law_native/test_constitutive.py','tests/law_native/test_retention_transfer.py',
    'tests/law_native/test_fe_runtime.py::test_fixed_material_abi_state_restore_without_claiming_FE',
    'tests/test_ns1_material_limits.py')
  Invoke-OwnedCheck 'owned-process-finally' 15 @($Runner,'tools/law_native/check_process_cleanup.py','--output',(Join-Path $Output 'process-cases'))
  Invoke-OwnedCheck 'existing-fit-CAS' 60 @($Runner,'examples/material-tests/law-native/point_fit_workflow.py','--output',(Join-Path $Output 'fit-workflow'))
  if ($RunSpatial) {
    Invoke-OwnedCheck 'actual-spatial-pairs' 300 @($Runner,'-m','pytest','-q','tests/law_native/test_fe_runtime.py')
    Invoke-OwnedCheck 'existing-FE-owner-cold' 600 @($Runner,'examples/material-tests/law-native/fe_workflow.py','--output',(Join-Path $Output 'fe-workflow'))
  }
  if ($RunGui) {
    Invoke-OwnedCheck 'actual-Qt-windows' 60 @($Runner,'-m','pytest','-q','tests/law_native/test_gui_runtime.py')
  }
  Write-Output "Evidence retained at $Output. Runtime PASS/FAIL/SKIP records, not this script's existence, establish execution."
} finally {
  Stop-Transcript | Out-Null
  Pop-Location
}
