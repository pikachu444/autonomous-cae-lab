param(
    [string]$FreeCADRoot,
    [string]$Source,
    [string]$Assembly,
    [string]$Output,
    [switch]$PrepareOnly
)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $FreeCADRoot) { $FreeCADRoot = Join-Path $repoRoot 'runs/prepost-session-20261008-01/tools/FreeCAD_1.1.4-Windows-x86_64-py311' }
if (-not $Source) { $Source = Join-Path $repoRoot 'runs/p1-native-edit-baseline-20261001-01/experiments/E-native-width38/cad/editable.FCStd' }
if (-not $Assembly) { $Assembly = Join-Path $repoRoot 'runs/cae-assembly-conditions-20261006-01/experiments/E-assembly-default/cad/assembly.step' }
if (-not $Output) { $Output = Join-Path $repoRoot ('runs/pre-desktop-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,6)) }
$exePath = Join-Path $FreeCADRoot 'FreeCAD.exe'
foreach ($requiredPath in @($exePath, $Source, $Assembly)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) { throw "Missing required file: $requiredPath" }
}
if ((Test-Path -LiteralPath $Output) -and (Get-ChildItem -LiteralPath $Output -Force | Select-Object -First 1)) {
    throw 'Output must be a new or empty directory; existing execution records are preserved.'
}
New-Item -ItemType Directory -Path $Output -Force | Out-Null
$Output = (Resolve-Path -LiteralPath $Output).Path
$configPath = Join-Path $Output 'config.json'
$config = @{ output=$Output; source=(Resolve-Path -LiteralPath $Source).Path; assembly=(Resolve-Path -LiteralPath $Assembly).Path; gmsh=(Join-Path $FreeCADRoot 'bin/gmsh.exe') }
$config | ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding utf8
$modulePath = (Join-Path $repoRoot 'apps/desktop_pre') | ConvertTo-Json -Compress
$jsonPath = $configPath | ConvertTo-Json -Compress
$macroPath = Join-Path $Output 'start.FCMacro'
@"
import sys
sys.path.insert(0, $modulePath)
import cae_prep
cae_prep.start($jsonPath)
"@ | Set-Content -LiteralPath $macroPath -Encoding utf8
$userCfg = Join-Path $Output 'user.cfg'
$systemCfg = Join-Path $Output 'system.cfg'
if ($PrepareOnly) { $Output; return }
$nativeArgs = @('-u', ('"' + $userCfg + '"'), '-s', ('"' + $systemCfg + '"'), ('"' + $macroPath + '"'))
$process = Start-Process -FilePath $exePath -ArgumentList $nativeArgs -PassThru -WindowStyle Normal
@{pid=$process.Id; output=$Output; exe=$exePath} | ConvertTo-Json
