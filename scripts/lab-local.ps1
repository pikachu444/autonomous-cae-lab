param(
    [string]$Store = 'runs/local-lab',
    [ValidateRange(1024, 65535)][int]$Port = 8766,
    [switch]$WithoutHistory
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$arguments = @('-m', 'apps.lab', '--store', $Store, '--port', "$Port")
if (-not $WithoutHistory) {
    # Explicit historical roots; the browser cannot supply filesystem paths.
    $history = [ordered]@{
        demo = 'runs/local-20260930-demo'
        native = 'artifacts/local-20260930-native'
        linear = 'artifacts/local-20260930-linear'
        doe = 'artifacts/local-20260930-doe'
        finer = 'artifacts/local-20260930-finer'
        optimization = 'artifacts/local-20260930-optimization'
        pde = 'artifacts/local-20260930-pde'
        openscience = 'runs/local-20260930-openscience-live-03'
    }
    foreach ($entry in $history.GetEnumerator()) {
        if (Test-Path -LiteralPath (Join-Path $projectRoot "$($entry.Value)/studies")) {
            $arguments += @('--library', "$($entry.Key)=$($entry.Value)")
        }
    }
}
Write-Host "Autonomous CAE Lab: http://127.0.0.1:$Port"
Write-Host '새 실행은 지정한 저장소에 남고, 이전 실행 기록은 읽기 전용입니다. 종료: Ctrl+C'
& (Join-Path $PSScriptRoot 'local.ps1') -PythonArgs $arguments
exit $LASTEXITCODE
