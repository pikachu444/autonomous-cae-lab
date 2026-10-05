param(
    [string]$Store = 'runs/local-lab',
    [ValidateRange(1024, 65535)][int]$Port = 8766,
    [switch]$WithoutHistory,
    # Trusted startup configuration only; the browser cannot choose an owner.
    [string]$OpenScienceOwner,
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath($RepoRoot)
$arguments = @('-m', 'apps.lab', '--store', $Store, '--port', "$Port")
if ($OpenScienceOwner) {
    # The Lab runs in WSL. Its existing bridge reads Windows owner bytes through
    # the host facade, so admit only absolute Windows or mounted-drive paths.
    $ownerWslPath = & {
        param([string]$LabOwnerPath, [string]$LabSourceRoot)
        if ($LabOwnerPath -match '[\r\n\x00]') { throw 'The research owner must be a single local path.' }
        if ($LabOwnerPath -cmatch '^/mnt/([a-zA-Z])/(.+)$') {
            $drive = $Matches[1].ToLowerInvariant(); $relative = $Matches[2]
            if (@($relative.Split('/') | Where-Object { $_ -in @('', '.', '..') }).Count) {
                throw 'The mounted research owner path must be absolute and normalized.'
            }
            return "/mnt/$drive/$relative"
        }
        if ($LabOwnerPath -notmatch '^[A-Za-z]:[\\/]') {
            throw 'Use an absolute Windows drive path or its /mnt/<drive>/ WSL path for the research owner.'
        }
        # Isolate dot-sourced runner parameters from this launcher's Port/Store.
        . (Join-Path $LabSourceRoot 'scripts/openscience-server-local.ps1') -Library
        ConvertTo-OpenScienceWslPath $LabOwnerPath
    } $OpenScienceOwner $projectRoot
    $arguments += @('--openscience-owner', $ownerWslPath)
}
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
& (Join-Path $projectRoot 'scripts/local.ps1') -PythonArgs $arguments
exit $LASTEXITCODE
